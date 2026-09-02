"""Coursedog catalog API parser (Tacoma Community College).

TCC's catalog at catalog.tacomacc.edu is a Coursedog SPA backed by a public
JSON API. The previous TCC pipeline extracted two-column text from a manually
downloaded PDF (see parsers/tcc.py); this reads the same catalog directly, so
there is no manual download step and no column-reconstruction guesswork.

The API rejects requests without an Origin/Referer from the catalog host — it
answers 401 otherwise. Nothing else is required; there is no key and no login.

Endpoint (as observed from the catalog's own network traffic):

  GET https://app.coursedog.com/api/v1/cm/{school}/courses/search/$filters
        ?catalogId=<id>&skip=<n>&limit=<n>&orderBy=code
        &effectiveDatesRange=<date>,<date>
        &ignoreEffectiveDating=false&ignoreTotalCount=false
        &columns=<comma-separated>

Records carry status Active / Inactive / Idle. Only Active courses are yielded:
the catalog holds roughly twice as many records as it publishes, and the
inactive ones are retired courses no Running Start student can enrol in.

Codes arrive already in Common Course Number form ("ENGL&101"), matching the
convention used across the rest of the pipeline.

The API exposes no lecture/lab component breakdown, so components fall back to
prose inference over the description, as the PDF path did.

config keys:
  institution      str
  school           str   Coursedog school slug, e.g. "tacomacc"
  catalog_id       str   Coursedog catalog id (changes each catalog year)
  effective_date   str   YYYY-MM-DD; selects the catalog edition in force
  origin           str   Origin/Referer to send, e.g. "https://catalog.tacomacc.edu"
  catalog_year     str
  uploaded_at      str
  source_url       str
  request_delay    float default 0.30
  page_size        int   default 200
"""
from __future__ import annotations
import csv
import io
import json
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterator

from . import base

UA = "Mozilla/5.0 (PSD course equivalency parser; cantonwinej@psd401.net)"

COLUMNS = (
    "credits.creditHours,description,name,longName,courseNumber,subjectCode,"
    "code,alternativeCode,status,requisites,departments,department"
)

API = "https://app.coursedog.com/api/v1/cm/{school}/courses/search/%24filters"


class CoursedogError(RuntimeError):
    """The API answered with something other than a usable page of courses."""


def _fetch_page(cfg: dict, skip: int, limit: int) -> dict:
    qs = urllib.parse.urlencode({
        "catalogId": cfg["catalog_id"],
        "skip": skip,
        "limit": limit,
        "orderBy": "code",
        "formatDependents": "false",
        "effectiveDatesRange": f"{cfg['effective_date']},{cfg['effective_date']}",
        "ignoreEffectiveDating": "false",
        "ignoreTotalCount": "false",
        "columns": COLUMNS,
    })
    url = API.format(school=cfg["school"]) + "?" + qs
    origin = cfg["origin"]
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json",
        # Required: the API answers 401 without these.
        "Origin": origin,
        "Referer": origin + "/",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            if r.status != 200:
                raise CoursedogError(f"HTTP {r.status} for skip={skip}")
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        raise CoursedogError(
            f"HTTP {e.code} for skip={skip}. A 401 usually means the Origin/Referer "
            f"header was rejected; a 404 usually means catalog_id {cfg['catalog_id']!r} "
            f"is stale — reopen the catalog and read catalogId off its own requests."
        ) from e


CSV_URL = ("https://app.coursedog.com/api/v1/ca/{school}/catalogs/{catalog_id}"
           "/courses/csv/$filters?orderBy=code&ignoreEffectiveDating=false")

# The catalog's own "Export all results as CSV" button. Same filter and the
# same orderBy=code as the JSON search, so the two come back in lockstep.
CSV_FILTER = {
    "condition": "AND",
    "filters": [{"condition": "and", "filters": [{
        "id": "status-course", "condition": "field", "name": "status",
        "inputType": "select", "group": "course", "type": "is",
        "value": "Active", "customField": False,
    }]}],
}


def _fetch_credits_csv(cfg: dict) -> list[dict]:
    """Credit hours, via the catalog's CSV export.

    The courses/search endpoint returns credits as null or {} for the large
    majority of courses, and TCC's catalog UI never displays them — but the CSV
    export carries a populated "Total Credits" column for every active course.
    It is a POST with a filter body; a plain GET 404s.

    The export has no code column, so rows can only be matched positionally.
    That is safe ONLY because both requests use orderBy=code and the identical
    Active filter — and the caller verifies the alignment on the description
    column before trusting any of it.
    """
    url = CSV_URL.format(school=cfg["school"], catalog_id=cfg["catalog_id"])
    origin = cfg["origin"]
    req = urllib.request.Request(
        url, data=json.dumps(CSV_FILTER).encode("utf-8"), method="POST",
        headers={
            "User-Agent": UA,
            "Content-Type": "application/json",
            "Accept": "text/csv,*/*",
            "Origin": origin,
            "Referer": origin + "/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            text = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise CoursedogError(f"CSV export failed: HTTP {e.code}") from e

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise CoursedogError("CSV export returned no rows")
    header = [h.strip() for h in rows[0]]
    return [dict(zip(header, r)) for r in rows[1:] if any(c.strip() for c in r)]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _credit_hours(raw: str):
    """Parse the CSV's Total Credits cell: "5", "1-3", "" all appear."""
    v = (raw or "").strip()
    if not v:
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)$", v)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return float(lo) if lo == hi else {"min": lo, "max": hi}
    m = re.match(r"^(\d+(?:\.\d+)?)$", v)
    return float(m.group(1)) if m else None


def _resolve_credits(rec: dict, csv_value, fallback: dict):
    """Credits, strongest source first.

    1. The JSON's creditHours — the only source that expresses a min/max range.
    2. A prior scrape's range, but ONLY when its minimum matches the CSV figure.
       That keeps a stale record from overriding live data while still
       recovering ranges the CSV cannot express.
    3. The CSV's single figure.
    """
    from_json = _credits(rec)
    if from_json is not None:
        return from_json
    prior = fallback.get(rec.get("code"))
    if (isinstance(prior, dict) and isinstance(csv_value, float)
            and float(prior.get("min", -1)) == csv_value):
        return prior
    return csv_value


def _department(rec: dict) -> str | None:
    """First department name. Coursedog returns `departments` as a list of bare
    strings for most courses but as a list of objects for some, so accept both
    rather than assuming the shape holds across the whole catalog."""
    for d in (rec.get("departments") or []):
        if isinstance(d, str) and d.strip():
            return d.strip()
        if isinstance(d, dict):
            for k in ("name", "displayName", "deptId", "id"):
                v = d.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    for d in (rec.get("departmentOwnership") or []):
        if isinstance(d, dict) and isinstance(d.get("deptId"), str):
            return d["deptId"]
    return rec.get("subjectCode") or None


def _credits(rec: dict):
    ch = ((rec.get("credits") or {}).get("creditHours")) or {}
    lo, hi = ch.get("min"), ch.get("max")
    if lo is None and hi is None:
        return None
    if hi is None or lo == hi:
        return float(lo if lo is not None else hi)
    return {"min": float(lo), "max": float(hi)}


CONDITION_PROSE = {
    "completedAllOf": "complete all of",
    "completedOneOf": "complete one of",
    "completedAnyOf": "complete any of",
    "minimumGrade": "minimum grade",
    "concurrentEnrollment": "concurrent enrollment in",
}


def _rule_courses(value) -> list[str]:
    """Pull course codes out of a rule's nested value structure.

    Coursedog nests them as value.values[].value, where each `value` is itself
    a list of codes. Walk defensively — the shape varies by rule type.
    """
    codes: list[str] = []
    if not isinstance(value, dict):
        return codes
    for entry in value.get("values") or []:
        if not isinstance(entry, dict):
            continue
        v = entry.get("value")
        if isinstance(v, str):
            codes.append(v)
        elif isinstance(v, list):
            codes.extend(x for x in v if isinstance(x, str))
    return codes


def _prerequisites(rec: dict) -> str:
    """Render Coursedog's requisite rules as readable prose.

    Most rules are NOT plain strings: a freeformText rule carries its text in
    `value`, but minimumGrade / completedAllOf rules carry a nested structure
    whose course codes live at value.values[].value. Reading only the string
    case dropped prerequisites for 384 of 839 courses.
    """
    req = rec.get("requisites") or {}
    parts: list[str] = []
    for group in req.get("requisitesSimple") or []:
        for rule in group.get("rules") or []:
            name = (rule.get("name") or "").strip()
            cond = rule.get("condition") or ""
            value = rule.get("value")

            if isinstance(value, str) and value.strip():
                parts.append(base.normalize_text(value.strip()))
                continue

            codes = _rule_courses(value)
            if not codes:
                continue
            phrase = CONDITION_PROSE.get(cond, cond or "requires")
            grade = rule.get("grade")
            if cond == "minimumGrade" and grade:
                phrase = f"minimum grade {grade} in"
            lead = f"{name}: " if name else ""
            parts.append(base.normalize_text(f"{lead}{phrase} {', '.join(codes)}"))

    seen, uniq = set(), []
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            uniq.append(part)
    return "; ".join(uniq)


def parse(config: dict) -> Iterator[dict]:
    institution = config["institution"]
    delay = float(config.get("request_delay", 0.30))
    limit = int(config.get("page_size", 200))

    print(f"  coursedog: fetching {institution} catalog {config['catalog_id']}...")
    records: list[dict] = []
    skip = 0
    total = None
    while True:
        payload = _fetch_page(config, skip, limit)
        page = payload.get("data") or []
        if total is None:
            total = payload.get("listLength") or payload.get("totalCount") or 0
        if not page:
            break
        records.extend(page)
        skip += len(page)
        if total and skip >= total:
            break
        if delay:
            time.sleep(delay)

    active = [r for r in records if r.get("status") == "Active"]
    skipped = len(records) - len(active)
    print(f"  coursedog: {len(records)} records, {len(active)} active "
          f"({skipped} inactive/idle skipped)")

    # Credits come from the CSV export, positionally joined. Verify the join on
    # the description column before using any of it: a silent misalignment would
    # attach the wrong credit hours to every course, and hs_credits is derived
    # straight from that. Bail out rather than publish a plausible-looking but
    # shifted dataset.
    csv_rows = _fetch_credits_csv(config)
    if len(csv_rows) != len(active):
        raise CoursedogError(
            f"CSV export has {len(csv_rows)} rows but the API returned {len(active)} "
            f"active courses. The two are joined by position, so they must match. "
            f"Check that both use orderBy=code and the same Active filter."
        )
    desc_key = next((k for k in (csv_rows[0] if csv_rows else {}) if "description" in k.lower()), None)
    cred_key = next((k for k in (csv_rows[0] if csv_rows else {}) if "credit" in k.lower()), None)
    if not cred_key:
        raise CoursedogError(f"No credits column in CSV export; columns were {list(csv_rows[0])}")
    if desc_key:
        mismatch = sum(
            1 for rec, row in zip(active, csv_rows)
            if _norm(rec.get("description"))[:120] != _norm(row.get(desc_key))[:120]
        )
        if mismatch:
            raise CoursedogError(
                f"CSV/API positional join is misaligned: {mismatch} of {len(active)} rows "
                f"have a different description. Refusing to attach credits."
            )
        print(f"  coursedog: CSV/API join verified on {len(active)} descriptions")
    credits_by_index = [_credit_hours(row.get(cred_key)) for row in csv_rows]
    missing = sum(1 for c in credits_by_index if c is None)
    if missing:
        print(f"  !! coursedog: {missing} courses have no credit value in the CSV export")

    # Variable-credit courses: the CSV publishes a single figure (the minimum),
    # so a 1-10 credit practicum exports as "1". The JSON carries a real
    # min/max for only 119 of 839 courses. Where neither source has the range,
    # fall back to the previous scrape, which did — accepting only ranges whose
    # minimum agrees with the CSV, so a stale record cannot contradict live data.
    fallback: dict[str, dict] = {}
    fb_path = config.get("credits_fallback_path")
    if fb_path:
        try:
            for rec in json.loads(pathlib.Path(fb_path).read_text()):
                ct = rec.get("credits_total")
                if isinstance(ct, dict) and rec.get("code"):
                    fallback[rec["code"]] = ct
        except Exception as e:
            print(f"  !! coursedog: could not read credits fallback {fb_path}: {e}")
        else:
            print(f"  coursedog: credit-range fallback loaded "
                  f"({len(fallback)} variable-credit courses from {pathlib.Path(fb_path).name})")

    yielded = 0
    unparsed: list[str] = []
    for idx, rec in enumerate(active):
        code = rec.get("code") or f"{rec.get('subjectCode','')}{rec.get('courseNumber','')}"
        title = (rec.get("name") or rec.get("longName") or "").strip()
        if not code or not title:
            unparsed.append(str(rec.get("id") or code or "<no id>"))
            continue
        desc = base.normalize_text(rec.get("description") or "")
        yielded += 1
        yield base.make_record(
            institution=institution,
            code=code,
            title=title,
            department=_department(rec),
            description=desc,
            components=base.infer_components_from_text(desc),
            credits_total=_resolve_credits(rec, credits_by_index[idx], fallback),
            prerequisites=_prerequisites(rec),
            catalog_year=config["catalog_year"],
            uploaded_at=config.get("uploaded_at"),
            source_url=config.get("source_url", config["origin"]),
        )

    base.report_parse_coverage("coursedog", institution, len(active), yielded, unparsed)

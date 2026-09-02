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
import json
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


def _prerequisites(rec: dict) -> str:
    """Flatten Coursedog's nested requisite rules into readable prose."""
    req = rec.get("requisites") or {}
    out: list[str] = []
    for group in req.get("requisitesSimple") or []:
        for rule in group.get("rules") or []:
            val = rule.get("value")
            if isinstance(val, str) and val.strip():
                out.append(base.normalize_text(val.strip()))
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return " ".join(uniq)


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

    yielded = 0
    unparsed: list[str] = []
    for rec in active:
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
            credits_total=_credits(rec),
            prerequisites=_prerequisites(rec),
            catalog_year=config["catalog_year"],
            uploaded_at=config.get("uploaded_at"),
            source_url=config.get("source_url", config["origin"]),
        )

    base.report_parse_coverage("coursedog", institution, len(active), yielded, unparsed)

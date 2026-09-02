"""Shared utilities for per-institution catalog parsers.

CourseRecord is a plain dict (JSON-serializable). We use a TypedDict-style
contract documented here, but enforce only at the parser-output boundary in
build_dataset.py for simplicity and forward compatibility.

Required fields:
  institution      str
  code             str           (normalized, e.g. "MATH&151" or "BUS101")
  is_common_course bool
  common_code      str | None
  title            str
  department       str | None
  description      str
  components       list[{type, credits} | {type, credits_min, credits_max}]
  credits_total    float | dict | None
  prerequisites    str
  catalog_year     str
  uploaded_at      str (YYYY-MM-DD)
  source_url       str
"""
from __future__ import annotations
import html
import re
from datetime import date
from typing import Iterable

COMMON_COURSE_RE = re.compile(r"^([A-Z]{2,6})&(\d{2,3}[A-Z]{0,2})$")


def normalize_text(s: str | None) -> str:
    """Decode HTML entities and fold curly punctuation to ASCII.

    Catalog HTML carries numeric/named entities (&#8217;, &nbsp;, &eacute;) and
    smart quotes that otherwise render literally in the viewer (e.g. the title
    "speaker&#8217;s"). html.unescape resolves all entities to real characters;
    we then fold the most common typographic quotes/spaces to ASCII so titles
    and descriptions read cleanly and export safely to CSV. Real dashes (– —)
    are preserved as-is."""
    if not s:
        return ""
    s = html.unescape(s)
    return (s.replace("’", "'").replace("‘", "'")
             .replace("“", '"').replace("”", '"')
             .replace("\xa0", " "))


def normalize_code(raw: str) -> str:
    """Strip whitespace, uppercase, preserve `&` and trailing letter codes."""
    if not raw:
        return ""
    s = raw.strip().upper().replace(" ", "")
    return s


def extract_common_course(code: str) -> tuple[bool, str | None]:
    """Return (is_common, common_code). The common_code is the bare
    `PREFIX&NUMBER` form usable as a join key across colleges."""
    if not code:
        return False, None
    m = COMMON_COURSE_RE.match(code)
    return (True, code) if m else (False, None)


def parse_credit_string(s: str) -> float | dict | None:
    """Coerce a credit string into either a scalar, {min,max}, or None.

    Examples:
      "5"          → 5.0
      "5.0"        → 5.0
      "1-3"        → {"min": 1.0, "max": 3.0}
      "Variable"   → None
      "3 (2 lec, 1 lab)" → 3.0  (takes the leading scalar)
    """
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)\s*[-–to]+\s*(\d+(?:\.\d+)?)\b", s)
    if m:
        return {"min": float(m.group(1)), "max": float(m.group(2))}
    m = re.match(r"^(\d+(?:\.\d+)?)", s)
    if m:
        return float(m.group(1))
    return None


_COMPONENT_KEYWORDS = ("Lecture", "Lab", "Laboratory", "Seminar", "Clinical", "Studio", "Field")

# Pierce (and other Acalog catalogs) print an explicit contact-hour table in
# the description prose, e.g.
#     "Lecture Contact Hours 50 Lab Contact Hours 0 Clinical Contact Hours 0"
# A bare keyword scan reads "Lab" out of that line and invents a lab component
# for a course that explicitly has zero lab hours.
_CONTACT_HOURS_RE = re.compile(
    rf"\b({'|'.join(_COMPONENT_KEYWORDS)})\s+Contact\s+Hours[:\s]+(\d+(?:\.\d+)?)",
    re.I,
)


def _normalize_component_type(kw: str) -> str:
    return "Lab" if kw.lower() == "laboratory" else kw.title()


def parse_contact_hours(text: str) -> dict[str, float] | None:
    """Parse an explicit "<Type> Contact Hours <N>" table out of catalog prose.

    Returns {component type: hours} when such a table is present (including
    entries with 0 hours, so callers can tell "declared zero" apart from
    "not mentioned"), or None when the text has no contact-hour table.
    """
    found = _CONTACT_HOURS_RE.findall(text or "")
    if not found:
        return None
    hours: dict[str, float] = {}
    for kw, value in found:
        t = _normalize_component_type(kw)
        # Keep the largest figure if a type is listed more than once.
        hours[t] = max(hours.get(t, 0.0), float(value))
    return hours


def infer_components_from_text(text: str) -> list[dict]:
    """Fallback component inference when a parser can't get structured data.

    Prefers an explicit contact-hour table when the catalog publishes one —
    a component declared with 0 contact hours is NOT part of the course.
    Otherwise falls back to scanning for component keywords.

    Returns components without credit values — the classifier only uses
    the type field for Lab detection.
    """
    hours = parse_contact_hours(text)
    if hours is not None:
        return [{"type": t} for t, h in hours.items() if h > 0]

    types = []
    for kw in _COMPONENT_KEYWORDS:
        if re.search(rf"\b{kw}\b", text, re.I):
            t = _normalize_component_type(kw)
            if t not in [c["type"] for c in types]:
                types.append({"type": t})
    return types


def report_parse_coverage(
    parser: str, institution: str, enumerated: int, yielded: int,
    unparsed: list[str], sample: int = 10,
) -> None:
    """Report how many enumerated pages actually became records.

    A parser that fetches a page and cannot read it drops the course silently.
    That is how the Bates CCN title bug removed the college's whole transfer
    catalog without a single warning. Any gap is printed loudly with a sample
    of the offending URLs so a regex drift is caught on the next run.
    """
    print(f"  {parser}: {institution}: {yielded}/{enumerated} pages parsed")
    if enumerated == 0:
        # A blocked or challenged enumeration otherwise reports "0/0 pages
        # parsed", which reads exactly like a clean run of an empty catalog.
        print(f"  !! {parser}: {institution}: enumerated ZERO courses — this is almost "
              f"certainly a blocked crawl, not an empty catalog. Do NOT publish this run.")
        return
    if not unparsed:
        return
    pct = 100.0 * len(unparsed) / enumerated if enumerated else 0.0
    print(f"  !! {parser}: {institution}: {len(unparsed)} pages ({pct:.1f}%) fetched but NOT parsed")
    for u in unparsed[:sample]:
        print(f"     - {u}")
    if len(unparsed) > sample:
        print(f"     … and {len(unparsed) - sample} more")
    print(f"  !! Investigate before trusting this scrape — a detail-page regex may have drifted.")


def make_record(
    *,
    institution: str,
    code: str,
    title: str,
    department: str | None,
    description: str,
    components: list[dict],
    credits_total,
    prerequisites: str,
    catalog_year: str,
    uploaded_at: str | None = None,
    source_url: str,
) -> dict:
    """Build a course record dict matching the v2 schema."""
    code = normalize_code(code)
    is_common, common_code = extract_common_course(code)
    return {
        "institution": institution,
        "code": code,
        "is_common_course": is_common,
        "common_code": common_code,
        "title": normalize_text(title).strip(),
        "department": normalize_text(department).strip() or None,
        "description": normalize_text(description).strip(),
        "components": components or [],
        "credits_total": credits_total,
        "prerequisites": normalize_text(prerequisites).strip(),
        "catalog_year": catalog_year,
        "uploaded_at": uploaded_at or date.today().isoformat(),
        "source_url": source_url,
    }


def dedupe(records: Iterable[dict]) -> list[dict]:
    """Dedupe by (institution, code) keeping the entry with the longest description."""
    by_key: dict[tuple[str, str], dict] = {}
    for r in records:
        key = (r["institution"], r["code"])
        prev = by_key.get(key)
        if prev is None or len(r.get("description") or "") > len(prev.get("description") or ""):
            by_key[key] = r
    return sorted(by_key.values(), key=lambda r: (r["institution"], r["code"]))

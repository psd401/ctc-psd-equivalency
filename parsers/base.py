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
import re
from datetime import date
from typing import Iterable

COMMON_COURSE_RE = re.compile(r"^([A-Z]{2,6})&(\d{2,3}[A-Z]{0,2})$")


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


def infer_components_from_text(text: str) -> list[dict]:
    """Fallback component inference when a parser can't get structured data.
    Looks for tokens 'Lab', 'Lecture', 'Seminar', 'Clinical' in the text.
    Returns components without credit values — the classifier only uses
    the type field for Lab detection.
    """
    types = []
    for kw in ("Lecture", "Lab", "Laboratory", "Seminar", "Clinical", "Studio", "Field"):
        if re.search(rf"\b{kw}\b", text, re.I):
            t = "Lab" if kw == "Laboratory" else kw.title()
            if t not in [c["type"] for c in types]:
                types.append({"type": t})
    return types


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
        "title": (title or "").strip(),
        "department": (department or "").strip() or None,
        "description": (description or "").strip(),
        "components": components or [],
        "credits_total": credits_total,
        "prerequisites": (prerequisites or "").strip(),
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

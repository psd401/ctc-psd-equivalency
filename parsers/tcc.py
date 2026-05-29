"""TCC parser.

TCC publishes its catalog as a 2-column PDF on Coursedog (no public JSON API
for course descriptions). The TCC-specific pipeline is:

  1. Download the PDF (manual, archived under archives/)
  2. Run extract_columns.py to dump column-aware text (one file)
  3. This module's parse() consumes that text and yields course records

config keys:
  text_path     str   path to tcc-columnwise.txt
  catalog_year  str   e.g. "2025-2026"
  uploaded_at   str   ISO date the catalog snapshot was taken
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Iterator

from . import base

INSTITUTION = "tcc"
SOURCE_URL = "https://catalog.tacomacc.edu/"

COURSE_HDR_RE = re.compile(r"^([A-Z]{2,6}&?\d{2,3}[A-Z]{0,2}) - (.+)$")
DEPT_RE = re.compile(r"^([A-Z][A-Za-z &]+?) Department$")
SECTION_MARKERS = {"---LEFT---", "---RIGHT---"}


def _split_blocks(lines):
    dept = None
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        if line.startswith("@@@PAGE") or line in SECTION_MARKERS:
            i += 1
            continue
        m = DEPT_RE.match(line)
        if m:
            dept = m.group(1)
            i += 1
            continue
        m = COURSE_HDR_RE.match(line)
        if not m:
            i += 1
            continue
        code, title_first = m.group(1), m.group(2)
        body = []
        j = i + 1
        while j < n:
            ln = lines[j].rstrip()
            if ln.startswith("@@@PAGE") or ln in SECTION_MARKERS:
                j += 1
                continue
            if COURSE_HDR_RE.match(ln) or DEPT_RE.match(ln):
                break
            body.append(ln)
            j += 1
        yield dept, code, title_first, body
        i = j


def _parse_block(dept, code, title_first, body, catalog_year, uploaded_at):
    title_parts = [title_first]
    desc_start = None
    for idx, ln in enumerate(body):
        if ln.strip() == "General Information":
            desc_start = idx
            break
        if not ln.strip():
            continue
        title_parts.append(ln.strip())
    title = " ".join(t.strip() for t in title_parts if t.strip())

    desc = ""
    if desc_start is not None:
        desc_lines = []
        for ln in body[desc_start + 1:]:
            s = ln.strip()
            if s.startswith("Components") or s == "Enrollment Requirements":
                break
            desc_lines.append(s)
        desc = " ".join(filter(None, desc_lines)).strip()
        desc = re.sub(r"\s{2,}", " ", desc)

    comp_lines = []
    in_comp = False
    has_max_col = False
    for ln in body:
        s = ln.strip()
        if s.startswith("Components"):
            in_comp = True
            has_max_col = "Max Credits" in s
            continue
        if not in_comp:
            continue
        if s == "Enrollment Requirements" or s.startswith("Simple Requisites"):
            break
        if s:
            comp_lines.append(s)

    components = []
    credits_total = None
    if comp_lines:
        for cl in comp_lines:
            if has_max_col:
                m = re.match(r"(.+?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)$", cl)
                if m:
                    components.append({
                        "type": m.group(1).strip(),
                        "credits_min": float(m.group(2)),
                        "credits_max": float(m.group(3)),
                    })
                    continue
            m = re.match(r"(.+?)\s+(\d+(?:\.\d+)?)$", cl)
            if m:
                components.append({
                    "type": m.group(1).strip(),
                    "credits": float(m.group(2)),
                })
        if has_max_col and components:
            credits_total = {
                "min": sum(c.get("credits_min", c.get("credits", 0)) for c in components),
                "max": sum(c.get("credits_max", c.get("credits", 0)) for c in components),
            }
        elif components:
            credits_total = sum(c["credits"] for c in components if "credits" in c)

    prereq = ""
    found_prereq = False
    prereq_lines = []
    for ln in body:
        s = ln.strip()
        if s == "Prerequisite":
            found_prereq = True
            continue
        if found_prereq:
            prereq_lines.append(s)
    if prereq_lines:
        prereq = re.sub(r"\s+", " ", " ".join(prereq_lines)).strip()[:1200]

    return base.make_record(
        institution=INSTITUTION,
        code=code,
        title=title,
        department=dept,
        description=desc,
        components=components,
        credits_total=credits_total,
        prerequisites=prereq,
        catalog_year=catalog_year,
        uploaded_at=uploaded_at,
        source_url=SOURCE_URL,
    )


def parse(config: dict) -> Iterator[dict]:
    """Yield CourseRecord dicts from the TCC column-wise text dump.

    Required config:
      text_path     path to tcc-columnwise.txt
      catalog_year  e.g. "2025-2026"
      uploaded_at   ISO date
    """
    text_path = Path(config["text_path"])
    catalog_year = config["catalog_year"]
    uploaded_at = config.get("uploaded_at")
    lines = text_path.read_text().splitlines()
    for dept, code, t0, body in _split_blocks(lines):
        yield _parse_block(dept, code, t0, body, catalog_year, uploaded_at)

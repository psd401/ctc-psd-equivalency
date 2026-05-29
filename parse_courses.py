"""Parse course records from the column-wise text dump.

Strategy: single forward pass with a small state machine.
- Track current department from "X Department" header lines.
- A new course block starts at a standalone "CODE - Title" line.
- A course block ENDS at:
    * the next "CODE - Title" line, OR
    * the next "X Department" header, OR
    * end of file.
- After collecting the block text, regex out description / components / credits / prereqs.
"""
import json
import re
from datetime import date
from pathlib import Path

SRC = Path("tcc-columnwise.txt")
OUT = Path("tcc-courses.json")

INSTITUTION = "tcc"
CATALOG_YEAR = "2025-2026"
CATALOG_UPLOADED_AT = date.today().isoformat()
SOURCE_URL = "https://catalog.tacomacc.edu/"

COMMON_COURSE_RE = re.compile(r"^([A-Z]{2,6})&(\d{2,3}[A-Z]{0,2})$")

COURSE_HDR_RE = re.compile(r"^([A-Z]{2,6}&?\d{2,3}[A-Z]{0,2}) - (.+)$")
DEPT_RE = re.compile(r"^([A-Z][A-Za-z &]+?) Department$")
SECTION_MARKERS = {"---LEFT---", "---RIGHT---"}


def split_blocks(lines):
    """Yield (department, code, title_first_line, body_lines) tuples."""
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


def parse_block(dept, code, title_first, body):
    # Stitch title: first line + any leading non-blank lines before
    # "General Information"
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

    # Description: from after "General Information" until "Components" / "Components Credits" /
    # "Enrollment Requirements" / end
    desc = ""
    if desc_start is not None:
        desc_lines = []
        for ln in body[desc_start + 1:]:
            s = ln.strip()
            if s.startswith("Components") or s == "Enrollment Requirements":
                break
            desc_lines.append(s)
        desc = " ".join(filter(None, desc_lines)).strip()
        # collapse any stray double spaces
        desc = re.sub(r"\s{2,}", " ", desc)

    # Components block: lines after a "Components..." header until "Enrollment Requirements" or end
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
        nums_only = []
        for cl in comp_lines:
            if has_max_col:
                # Format: "Type minCredits maxCredits" → two trailing numbers
                m = re.match(r"(.+?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)$", cl)
                if m:
                    components.append({
                        "type": m.group(1).strip(),
                        "credits_min": float(m.group(2)),
                        "credits_max": float(m.group(3)),
                    })
                    continue
            # Single-number "Type credits"
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

    # Prerequisites: everything after "Prerequisite" line, collapsed
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

    is_common = bool(COMMON_COURSE_RE.match(code))
    return {
        "institution": INSTITUTION,
        "code": code,
        "is_common_course": is_common,
        "common_code": code if is_common else None,
        "title": title,
        "department": dept,
        "description": desc,
        "components": components,
        "credits_total": credits_total,
        "prerequisites": prereq,
        "catalog_year": CATALOG_YEAR,
        "uploaded_at": CATALOG_UPLOADED_AT,
        "source_url": SOURCE_URL,
    }


def main():
    lines = SRC.read_text().splitlines()
    raw = []
    for dept, code, t0, body in split_blocks(lines):
        raw.append(parse_block(dept, code, t0, body))

    # Dedupe by code — keep the entry with the longest description.
    by_code = {}
    for c in raw:
        prev = by_code.get(c["code"])
        if prev is None or len(c["description"]) > len(prev["description"]):
            by_code[c["code"]] = c
    deduped = sorted(by_code.values(), key=lambda c: c["code"])
    OUT.write_text(json.dumps(deduped, indent=2))
    print(f"Parsed {len(raw)} raw blocks → {len(deduped)} unique courses → {OUT}")

    from collections import Counter
    no_desc = sum(1 for c in deduped if not c["description"])
    no_cr = sum(1 for c in deduped if c["credits_total"] is None)
    no_dept = sum(1 for c in deduped if not c["department"])
    print(f"  missing description: {no_desc}")
    print(f"  missing credits:     {no_cr}")
    print(f"  missing department:  {no_dept}")
    ct = Counter(c["department"] for c in deduped)
    print(f"  departments:         {len(ct)}")
    print("  top 6 by count:")
    for d, n in sorted(ct.items(), key=lambda kv: -kv[1])[:6]:
        print(f"    {n:>4}  {d}")


if __name__ == "__main__":
    main()

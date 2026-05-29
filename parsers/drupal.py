"""Drupal catalog parser (Bates Technical College).

Bates' 2025-26 catalog is a custom Drupal site at catalog.batestech.edu.
The /courses index lists every course (50 per page, paginated ?page=N).
Each course has its own detail page like /accounting/acct-207.

Course detail structure:
  <h1>ACCT 207: QuickBooks</h1>
  <span class="field--name-field-credits">… <span class="field__item">5</span> …</span>
  <div class="field--name-field-semester-offered">…<div class="field__item">3</div>…</div>
  <div class="field--name-field-description … field__item">description text</div>
  <div class="field--name-field-distribution">…<div class="field__item">Career Training</div>…</div>

config keys:
  institution      str
  base_url         str   e.g. "https://catalog.batestech.edu"
  list_path        str   e.g. "/courses"
  catalog_year     str
  uploaded_at      str
  source_url       str
  request_delay    float default 0.10
"""
from __future__ import annotations
import re
import time
import urllib.request
from typing import Iterator

from . import base

UA = "Mozilla/5.0 (PSD course equivalency parser; cantonwinej@psd401.net)"

# Course detail URL pattern: /{department-slug}/{prefix}-{number}
COURSE_LINK_RE = re.compile(r'href="(/[a-z][a-z0-9-]+/[a-z]+-[0-9]+[a-z]*)"')
TITLE_RE = re.compile(
    r"<h1[^>]*>\s*([A-Z]+\s*\d+[A-Z]*)\s*:\s*(.+?)\s*</h1>",
    re.S | re.I,
)
CREDITS_RE = re.compile(
    r"field--name-field-credits[^<]*<.*?field__item[^>]*>\s*([^<]+?)\s*</",
    re.I | re.S,
)
DESC_RE = re.compile(
    r'field--name-field-description[^"]*field__item"[^>]*>(.*?)</div>',
    re.I | re.S,
)
DISTRIBUTION_RE = re.compile(
    r"field--name-field-distribution[^<]*<.*?field__item[^>]*>\s*([^<]+?)\s*</",
    re.I | re.S,
)
DEPT_RE = re.compile(r"^/([a-z0-9-]+)/")


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&#39;", "'", s)
    s = re.sub(r"&quot;", '"', s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _list_course_paths(base_url: str, list_path: str) -> list[str]:
    """Walk paginated /courses?page=N. Return relative course detail paths."""
    seen: set[str] = set()
    ordered: list[str] = []
    page = 0
    max_pages = 100  # safety cap
    while page < max_pages:
        url = f"{base_url}{list_path}?page={page}"
        try:
            html = _fetch(url)
        except Exception as e:
            print(f"  drupal: page {page} fetch error: {e}")
            break
        new = []
        for m in COURSE_LINK_RE.finditer(html):
            path = m.group(1)
            # Filter out non-course links (we want /dept/prefix-N, not /dept/policy-page)
            if path not in seen and re.search(r"/[a-z]+-\d+[a-z]*$", path):
                seen.add(path)
                new.append(path)
        if not new:
            break
        ordered.extend(new)
        page += 1
    return ordered


def _parse_detail(html: str, source_path: str) -> dict | None:
    m = TITLE_RE.search(html)
    if not m:
        return None
    raw_code = m.group(1).strip().replace("&amp;", "&")
    code = base.normalize_code(raw_code.replace(" ", ""))
    # Title may include nested HTML or whitespace; clean it
    title = _strip_tags(m.group(2))

    credits = None
    cm = CREDITS_RE.search(html)
    if cm:
        credits = base.parse_credit_string(_strip_tags(cm.group(1)))

    desc = ""
    dm = DESC_RE.search(html)
    if dm:
        desc = _strip_tags(dm.group(1))[:5000]

    dept = None
    dept_match = DEPT_RE.match(source_path)
    if dept_match:
        dept = dept_match.group(1).replace("-", " ").title()

    components = base.infer_components_from_text(desc)

    return {
        "code": code,
        "title": title,
        "department": dept,
        "description": desc,
        "components": components,
        "credits_total": credits,
        "prerequisites": "",  # Bates doesn't publish structured prereqs in this layout
    }


def parse(config: dict) -> Iterator[dict]:
    institution = config["institution"]
    base_url = config["base_url"].rstrip("/")
    list_path = config.get("list_path", "/courses")
    catalog_year = config["catalog_year"]
    uploaded_at = config.get("uploaded_at")
    source_url = config.get("source_url", base_url + "/")
    delay = float(config.get("request_delay", 0.10))

    print(f"  drupal: enumerating course paths for {institution}...")
    paths = _list_course_paths(base_url, list_path)
    print(f"  drupal: {len(paths)} courses")

    for i, path in enumerate(paths, 1):
        if i % 100 == 0:
            print(f"    {institution}: {i}/{len(paths)}")
        try:
            html = _fetch(base_url + path)
        except Exception as e:
            print(f"  drupal: {path} fetch error: {e}")
            continue
        parsed = _parse_detail(html, path)
        if not parsed:
            continue
        yield base.make_record(
            institution=institution,
            code=parsed["code"],
            title=parsed["title"],
            department=parsed["department"],
            description=parsed["description"],
            components=parsed["components"],
            credits_total=parsed["credits_total"],
            prerequisites=parsed["prerequisites"],
            catalog_year=catalog_year,
            uploaded_at=uploaded_at,
            source_url=source_url,
        )
        if delay:
            time.sleep(delay)

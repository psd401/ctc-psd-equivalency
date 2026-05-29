"""SmartCatalog parser (Clover Park Technical College).

SmartCatalog publishes per-prefix listing pages and per-course detail pages.
The /courses index lists every prefix; each prefix has level-subdirectories
(100, 200, 300, …); each level subdirectory lists per-course detail pages.

Detail page structure:
  <div id="main">
    <h1><span>ACCT& 201</span> Principles of Accounting I</h1>
    <div class="desc"><p>...</p></div>
    <div class="sc_credits"><div class="credits">5</div></div>
    <div class="sc_prereqs">prereq text</div>
    <div class="sc_coreqs">coreq text</div>
  </div>

config keys:
  institution      str
  base_url         str   e.g. "https://cptc.smartcatalogiq.com"
  catalog_path     str   e.g. "/en/2025-2026/catalog/courses"
  catalog_year     str
  uploaded_at      str
  source_url       str
  request_delay    float  default 0.10
"""
from __future__ import annotations
import re
import time
import urllib.request
from typing import Iterator

from . import base

UA = "Mozilla/5.0 (PSD course equivalency parser; cantonwinej@psd401.net)"
TITLE_RE = re.compile(
    r"<h1>\s*<span>\s*([^<]+?)\s*</span>\s*([^<]+?)\s*</h1>",
    re.I | re.S,
)
DESC_RE = re.compile(r'<div class="desc">(.*?)</div>', re.I | re.S)
CREDITS_RE = re.compile(r'<div class="credits">\s*(.*?)\s*</div>', re.I | re.S)
PREREQ_RE = re.compile(r'<div class="sc_prereqs">(.*?)</div>\s*(?:<div|$)', re.I | re.S)


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


def _list_course_urls(base_url: str, catalog_path: str) -> list[str]:
    """Walk the SmartCatalog tree. Returns absolute URLs of every per-course page.

    Strategy: BFS the listing tree, distinguishing listing pages from course
    pages by depth (course detail pages live 3 segments below /courses/).
    """
    seen: set[str] = set()
    queue: list[str] = [catalog_path]
    course_urls: list[str] = []
    prefix_match = re.compile(re.escape(catalog_path) + r"/[a-z0-9-]+(?:/[a-z0-9-]+){0,2}")

    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        url = base_url + path
        try:
            html = _fetch(url)
        except Exception as e:
            print(f"  smartcatalog: {path} fetch error: {e}")
            continue
        # Find all matching sub-links
        for m in re.finditer(rf'href="({re.escape(catalog_path)}/[^"#]+)"', html):
            link = m.group(1)
            # Only follow links beneath this catalog tree
            if not prefix_match.match(link):
                continue
            depth = link[len(catalog_path):].count("/")  # path-segments after /courses
            if depth >= 3:
                if link not in seen:
                    seen.add(link)
                    course_urls.append(link)
            elif depth in (1, 2):
                if link not in seen:
                    queue.append(link)
    return [base_url + u for u in course_urls]


def _parse_detail(html: str) -> dict | None:
    m = TITLE_RE.search(html)
    if not m:
        return None
    # Decode HTML entities first — SmartCatalog renders & as &amp; in the markup
    raw_code = m.group(1).strip().replace("&amp;", "&").replace("&nbsp;", " ")
    code = base.normalize_code(raw_code.replace(" ", ""))
    title = _strip_tags(m.group(2))

    desc = ""
    dm = DESC_RE.search(html)
    if dm:
        desc = _strip_tags(dm.group(1))

    credits = None
    cm = CREDITS_RE.search(html)
    if cm:
        credits = base.parse_credit_string(_strip_tags(cm.group(1)))

    prereq = ""
    pm = PREREQ_RE.search(html)
    if pm:
        prereq = _strip_tags(pm.group(1))[:1200]

    components = base.infer_components_from_text(desc + " " + html[:5000])

    return {
        "code": code,
        "title": title,
        "description": desc,
        "components": components,
        "credits_total": credits,
        "prerequisites": prereq,
    }


def parse(config: dict) -> Iterator[dict]:
    institution = config["institution"]
    base_url = config["base_url"].rstrip("/")
    catalog_path = config["catalog_path"].rstrip("/")
    catalog_year = config["catalog_year"]
    uploaded_at = config.get("uploaded_at")
    source_url = config.get("source_url", base_url + "/")
    delay = float(config.get("request_delay", 0.10))

    print(f"  smartcatalog: enumerating course URLs for {institution}...")
    urls = _list_course_urls(base_url, catalog_path)
    print(f"  smartcatalog: {len(urls)} course URLs")

    for i, url in enumerate(urls, 1):
        if i % 100 == 0:
            print(f"    {institution}: {i}/{len(urls)}")
        try:
            html = _fetch(url)
        except Exception as e:
            print(f"  smartcatalog: {url} fetch error: {e}")
            continue
        parsed = _parse_detail(html)
        if not parsed:
            continue
        # Department: prefix is the first path segment after /courses/
        seg = url.split(catalog_path + "/")[-1].split("/")[0]
        dept = seg.replace("-", " ").title() if seg else None
        yield base.make_record(
            institution=institution,
            code=parsed["code"],
            title=parsed["title"],
            department=dept,
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

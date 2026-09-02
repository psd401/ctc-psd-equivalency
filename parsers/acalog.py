"""Acalog catalog parser.

Acalog is the catalog platform used by Olympic, Pierce, and Green River
(all Server: director, content.php?catoid=X&navoid=Y URL structure).

Strategy:
  1. Fetch the "Course Descriptions" navoid page
  2. Walk pagination via &filter[cpage]=N until no new coids appear
  3. For each unique coid, fetch the preview_course_nopop.php detail page
  4. Parse title/credits/description/prereqs/components from the detail HTML

config keys:
  institution      str   ID (e.g. "olympic")
  base_url         str   e.g. "https://catalog.olympic.edu"
  catoid           int   Acalog catalog ID for the current academic year
  course_navoid    int   navoid for the Course Descriptions page
  catalog_year     str   e.g. "2025-2026"
  uploaded_at      str   ISO date
  source_url       str   public URL stem shown in the HTML footer
  request_delay    float seconds between detail-page requests (default 0.1)
"""
from __future__ import annotations
import re
import time
import urllib.parse
import urllib.request
from typing import Iterator

from . import base

UA = "Mozilla/5.0 (PSD course equivalency parser; cantonwinej@psd401.net)"

COID_RE = re.compile(r"preview_course_nopop\.php\?catoid=\d+&coid=(\d+)")
TITLE_RE = re.compile(r"<h1[^>]*id=['\"]course_preview_title['\"][^>]*>([^<]+)</h1>")
CREDITS_RE = re.compile(r"<strong>\s*Credits?\s*:\s*</strong>\s*<strong>\s*([^<]+?)\s*</strong>", re.I)
# Fallback for catalogs that do not wrap the figure in the <strong> pair above.
# Green River renders it as plain text, so the strict pattern missed and every
# one of its 1378 courses was stored with credits_total None — the tool showed
# no HS credit value for the whole college.
CREDITS_TEXT_RE = re.compile(r"\bCredits?\s*:\s*([\d.]+(?:\s*-\s*[\d.]+)?)", re.I)
PREREQ_RE = re.compile(
    r"<strong>\s*Prerequisites?\s*:\s*</strong>\s*([^<]+?)(?:<br|</p|<strong)",
    re.I,
)
DEPT_RE = re.compile(r"^([A-Z]+)")


class ChallengeError(RuntimeError):
    """Acalog returned a bot-mitigation challenge instead of the page.

    catalog.*.edu answers content.php with HTTP 202 and an empty body when it
    decides a client looks automated. urlopen does not raise on 202, so without
    this check the caller reads the empty body as a legitimately empty course
    list, enumerates zero courses, and silently wipes the college.
    """


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        status = r.status
        body = r.read().decode("utf-8", errors="replace")
    if status != 200 or not body.strip():
        raise ChallengeError(
            f"HTTP {status} with {len(body)} bytes for {url} — "
            "looks like a bot-mitigation challenge, not a real page. "
            "Slow the request rate and retry later; do NOT treat this as an empty catalog."
        )
    return body


def _strip_tags(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&#160;", " ", s)
    s = re.sub(r"&quot;", '"', s)
    s = re.sub(r"&#39;", "'", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def _list_coids(base_url: str, catoid: int, course_navoid: int,
                delay: float = 0.0, challenge_retries: int = 3) -> list[str]:
    """Walk pagination and return de-duplicated coids in insertion order.

    Sleeps `delay` between pages. This loop previously fetched every listing
    page back to back with no pause at all while the site's robots.txt asks for
    crawl-delay: 120 — a burst of ~13 rapid requests to the same endpoint, which
    is what a bot filter is built to notice.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    page = 1
    max_pages = 100  # safety cap
    while page <= max_pages:
        url = (
            f"{base_url}/content.php?catoid={catoid}&navoid={course_navoid}"
            f"&filter%5Bitem_type%5D=3&filter%5Bonly_active%5D=1&filter%5B3%5D=1"
            f"&filter%5Bcpage%5D={page}"
        )
        html = None
        for attempt in range(challenge_retries):
            try:
                html = _fetch(url)
                break
            except ChallengeError as e:
                wait = delay * (attempt + 1) if delay else 30 * (attempt + 1)
                print(f"  acalog: page {page} challenged (attempt {attempt+1}/"
                      f"{challenge_retries}); waiting {wait:.0f}s — {e}")
                time.sleep(wait)
            except Exception as e:
                print(f"  acalog: page {page} fetch error: {e}")
                break
        if html is None:
            # Never treat a challenge as "end of pagination": that silently
            # truncates the catalog. Surface it so the run aborts instead.
            raise ChallengeError(
                f"listing page {page} for catoid={catoid} could not be fetched after "
                f"{challenge_retries} attempts. Aborting rather than returning a "
                f"partial course list."
            )
        new = [c for c in COID_RE.findall(html) if c not in seen]
        if not new:
            # Page returned no new course detail links → end of pagination
            break
        for c in new:
            seen.add(c)
            ordered.append(c)
        page += 1
        if delay:
            time.sleep(delay)
    return ordered


def _parse_detail(html: str) -> dict | None:
    """Parse a single Acalog preview_course_nopop.php page into fields."""
    m = TITLE_RE.search(html)
    if not m:
        return None
    title_raw = m.group(1).strip()
    # Acalog title formats seen across institutions:
    #   Olympic / GR:  "ENGL& 101 - English Composition I"
    #   Pierce:        "ACCT 101 Survey of Accounting (5 credits)"
    # Strip trailing "(N credits)" if present, then accept either "CODE - Title"
    # or "CODE Title" (no separator).
    title_raw = re.sub(r"\s*\(\s*\d+(?:\.\d+)?\s*-?\s*\d*(?:\.\d+)?\s*credits?\s*\)\s*$", "", title_raw, flags=re.I)
    title_raw = title_raw.strip()
    title_match = re.match(r"^([A-Z]+(?:&\s*)?\s*\d+[A-Z]{0,2})\s*[-–:]\s*(.+)$", title_raw)
    if not title_match:
        title_match = re.match(r"^([A-Z]+(?:&\s*)?\s*\d+[A-Z]{0,2})\s+(.+)$", title_raw)
    if not title_match:
        return None
    code = base.normalize_code(title_match.group(1).replace(" ", ""))
    title = title_match.group(2).strip()

    # The body after <h1> contains credits, description, prereqs, hours
    body_start = m.end()
    # Stop at the "Back to Top" link or social-media block
    body_end_match = re.search(
        r'(?:Back to Top|acalog-social-media-links|Add to (My )?Favorites)',
        html[body_start:],
    )
    body = html[body_start: body_start + body_end_match.start()] if body_end_match else html[body_start:]

    credits = None
    derived_credits = False
    cm = CREDITS_RE.search(body)
    if not cm:
        cm = CREDITS_TEXT_RE.search(_strip_tags(body))
    if cm:
        credits = base.parse_credit_string(_strip_tags(cm.group(1)))
    if credits is None:
        # Pierce publishes no credit figure at all — only a contact-hour table.
        # Derive from it rather than leaving every one of its courses with no
        # high-school credit value, and mark the record so the viewer can say
        # the number is derived rather than published.
        credits = base.derive_credits_from_contact_hours(_strip_tags(body))
        derived_credits = credits is not None

    prereq = ""
    pm = PREREQ_RE.search(body)
    if pm:
        prereq = _strip_tags(pm.group(1))[:1200]

    # Description: text between credits and prereq (or end)
    desc_body = body
    if cm:
        desc_body = desc_body[cm.end():]
    if pm:
        desc_body = desc_body[: desc_body.find("<strong>Prerequisite")] if "<strong>Prerequisite" in desc_body else desc_body
    desc = _strip_tags(desc_body)
    # Trim a trailing "X hours Lecture, Y hours Lab" tail into components
    components = []
    hours_match = re.search(
        r"(\d+(?:\.\d+)?)\s*hour[s]?\s+(Lecture|Lab|Laboratory|Seminar|Clinical|Studio|Field)",
        desc,
        re.I,
    )
    while hours_match:
        kind = hours_match.group(2)
        kind = "Lab" if kind.lower() in ("lab", "laboratory") else kind.title()
        components.append({"type": kind, "credits": float(hours_match.group(1))})
        desc = desc[: hours_match.start()] + desc[hours_match.end():]
        hours_match = re.search(
            r"(\d+(?:\.\d+)?)\s*hour[s]?\s+(Lecture|Lab|Laboratory|Seminar|Clinical|Studio|Field)",
            desc,
            re.I,
        )
    if not components:
        components = base.infer_components_from_text(body)

    return {
        "code": code,
        "title": title,
        "description": desc.strip(),
        "components": components,
        "credits_total": credits,
        "credits_derived": derived_credits,
        "prerequisites": prereq,
    }


def parse(config: dict) -> Iterator[dict]:
    institution = config["institution"]
    base_url = config["base_url"].rstrip("/")
    catoid = int(config["catoid"])
    course_navoid = int(config["course_navoid"])
    catalog_year = config["catalog_year"]
    uploaded_at = config.get("uploaded_at")
    source_url = config.get("source_url", base_url + "/")
    delay = float(config.get("request_delay", 0.10))

    print(f"  acalog: enumerating coids for {institution} "
          f"(catoid={catoid}, navoid={course_navoid}, delay={delay}s)...")
    coids = _list_coids(base_url, catoid, course_navoid, delay=delay)
    print(f"  acalog: {len(coids)} courses found")

    unparsed: list[str] = []
    yielded = 0
    for i, coid in enumerate(coids, 1):
        if i % 25 == 0:
            print(f"    {institution}: {i}/{len(coids)}", flush=True)
        html = None
        for attempt in range(3):
            try:
                html = _fetch(f"{base_url}/preview_course_nopop.php?catoid={catoid}&coid={coid}")
                break
            except ChallengeError as e:
                wait = delay or 30
                print(f"  acalog: coid={coid} challenged; waiting {wait:.0f}s", flush=True)
                time.sleep(wait)
            except Exception as e:
                print(f"  acalog: coid={coid} fetch error: {e}")
                break
        if html is None:
            unparsed.append(coid)
            continue
        parsed = _parse_detail(html)
        if not parsed:
            unparsed.append(coid)
            continue
        yielded += 1
        dept = None
        dept_m = DEPT_RE.match(parsed["code"])
        if dept_m:
            dept = dept_m.group(1)  # prefix-as-department fallback
        record = base.make_record(
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
        if parsed.get("credits_derived"):
            record["review_flags"] = [base.CREDITS_DERIVED_FLAG]
        yield record
        if delay:
            time.sleep(delay)

    base.report_parse_coverage("acalog", institution, len(coids), yielded, unparsed)

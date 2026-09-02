"""Re-add courses a college removed from its public catalog but did not delete.

A re-scrape takes the college's live index as truth, so a course the college
unpublished simply vanishes from our dataset. That is wrong for Bates: probing
every dropped URL showed 227 of 230 return HTTP 403 (Drupal's "Log in" page —
the node still exists, it is just no longer public) and ZERO return 404. The
courses were hidden, not retired, and dropping them would lose real history.

This script diffs a previous scrape against the current one, probes each
dropped course's detail URL, and decides per course:

  403  -> node exists but is not public: keep the old record, flagged
  200  -> still public but missing from the index (the index is not a complete
          listing — Bates' AMA122/130/134 are reachable yet unlisted):
          keep the old record, flagged, and report it as a crawl gap
  404  -> genuinely gone: drop

Retained records are marked with a `review_flags` entry, which classify_courses
carries through onto the classified record. No schema field is added.

Usage:
  python retain_unpublished.py <institution> --previous <old-scrape.json>
  python retain_unpublished.py bates --previous archives/2025-2026/bates-raw.json --dry-run
"""
from __future__ import annotations
import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CATALOG_DIR = HERE / "catalogs"

UA = "Mozilla/5.0 (PSD course equivalency parser; cantonwinej@psd401.net)"

# How to rebuild a detail URL from a stored record, per institution. Bates'
# department field is the URL slug title-cased, so it round-trips.
URL_BUILDERS = {
    "bates": lambda rec: (
        "https://catalog.batestech.edu/"
        + (rec.get("department") or "").lower().replace(" ", "-")
        + "/"
        + _slug_code(rec["code"])
    ),
}

FLAG_UNPUBLISHED = "Not in the college's published catalog as of {date} — retained from the {year} scrape"
FLAG_UNLISTED = "Public but absent from the college's course index as of {date} — retained from the {year} scrape"


def _slug_code(code: str) -> str:
    m = re.match(r"([A-Z]+)&?(\d+[A-Z]*)$", code)
    return f"{m.group(1).lower()}-{m.group(2).lower()}" if m else code.lower()


def probe(url: str) -> int | str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return type(e).__name__


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("institution")
    ap.add_argument("--previous", required=True, help="Path to the prior raw scrape JSON")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delay", type=float, default=0.15)
    args = ap.parse_args()

    inst = args.institution
    build_url = URL_BUILDERS.get(inst)
    if not build_url:
        raise SystemExit(f"No URL builder for {inst!r}; add one to URL_BUILDERS.")

    current_path = CATALOG_DIR / f"{inst}-courses.json"
    current = json.loads(current_path.read_text())
    previous = json.loads(Path(args.previous).read_text())

    have = {c["code"] for c in current}
    dropped = [c for c in previous if c["code"] not in have]
    print(f"{inst}: current={len(current)}  previous={len(previous)}  dropped={len(dropped)}")
    if not dropped:
        print("Nothing dropped — nothing to retain.")
        return

    today = time.strftime("%Y-%m-%d")
    keep, gone, unlisted, errors = [], [], [], []
    for i, rec in enumerate(dropped, 1):
        if i % 50 == 0:
            print(f"  probing {i}/{len(dropped)}")
        st = probe(build_url(rec))
        if st == 403:
            flag = FLAG_UNPUBLISHED.format(date=today, year=rec.get("catalog_year", "prior"))
            keep.append({**rec, "review_flags": [flag]})
        elif st == 200:
            flag = FLAG_UNLISTED.format(date=today, year=rec.get("catalog_year", "prior"))
            rec2 = {**rec, "review_flags": [flag]}
            keep.append(rec2)
            unlisted.append(rec["code"])
        elif st == 404:
            gone.append(rec["code"])
        else:
            errors.append((rec["code"], st))
        time.sleep(args.delay)

    print(f"\n  retain (unpublished, 403) : {len(keep) - len(unlisted)}")
    print(f"  retain (public but unlisted, 200): {len(unlisted)}  {unlisted[:10]}")
    print(f"  drop   (deleted, 404)     : {len(gone)}  {gone[:10]}")
    if errors:
        print(f"  !! unresolved            : {len(errors)}  {errors[:10]}")
        print("     These were neither confirmed present nor confirmed gone — "
              "they are NOT retained. Re-run before trusting the result.")
    if unlisted:
        print("\n  !! The college's index is not a complete listing: the courses above are "
              "publicly reachable but absent from it. The crawl should union the index "
              "with known URLs rather than trusting the index alone.")

    if args.dry_run:
        print("\n(dry-run; catalogs/ not modified)")
        return

    merged = current + keep
    merged.sort(key=lambda r: r["code"])
    current_path.write_text(json.dumps(merged, indent=2))
    print(f"\nWrote {len(merged)} records to {current_path.name} "
          f"({len(current)} live + {len(keep)} retained).")
    print("Re-run classify_courses.py / merge_catalogs.py to rebuild.")


if __name__ == "__main__":
    main()

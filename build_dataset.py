"""Orchestrator: parse + classify + merge multi-institution catalog data.

Usage:
  python build_dataset.py                  # all enabled institutions
  python build_dataset.py tcc olympic      # subset

Output:
  catalogs/<institution>-courses.json            (raw, per institution)
  catalogs/<institution>-courses-classified.json (classified, per institution)
  ctc-courses-classified.json                    (merged — drop-in for build_html.py)
  archives/<catalog_year>/<institution>.json     (snapshot for diff_catalogs.py)
"""
from __future__ import annotations
import json
import sys
from datetime import date
from pathlib import Path

from classify_courses import classify
from parsers import PARSERS

HERE = Path(__file__).parent
CATALOG_DIR = HERE / "catalogs"
ARCHIVE_DIR = HERE / "archives"
MERGED_OUT = HERE / "ctc-courses-classified.json"

# Per-institution parser config. Each entry tells the orchestrator which
# parser to call and with what options. Set "enabled": False to skip an
# institution without removing its config.
INSTITUTIONS = {
    "tcc": {
        "enabled": True,
        "parser": "tcc",
        "config": {
            "text_path": str(HERE / "tcc-columnwise.txt"),
            "catalog_year": "2025-2026",
            "uploaded_at": date.today().isoformat(),
        },
    },
    "olympic": {
        "enabled": True,
        "parser": "olympic",
        "config": {
            "institution": "olympic",
            "base_url": "https://catalog.olympic.edu",
            "catoid": 24,
            "course_navoid": 1243,
            "catalog_year": "2025-2026",
            "uploaded_at": date.today().isoformat(),
            "source_url": "https://catalog.olympic.edu/",
            "request_delay": 0.50,
        },
    },
    "greenriver": {
        "enabled": True,
        "parser": "greenriver",
        "config": {
            "institution": "greenriver",
            "base_url": "https://catalog.greenriver.edu",
            "catoid": 10,
            "course_navoid": 624,
            "catalog_year": "2025-2026",
            "uploaded_at": date.today().isoformat(),
            "source_url": "https://catalog.greenriver.edu/",
            "request_delay": 0.50,
        },
    },
    "pierce": {
        "enabled": True,
        "parser": "pierce",
        "config": {
            "institution": "pierce",
            "base_url": "https://catalog.pierce.ctc.edu",
            "catoid": 17,
            "course_navoid": 943,
            "catalog_year": "2025-2026",
            "uploaded_at": date.today().isoformat(),
            "source_url": "https://catalog.pierce.ctc.edu/",
            "request_delay": 0.50,
        },
    },
    "cloverpark": {
        "enabled": True,
        "parser": "cloverpark",
        "config": {
            "institution": "cloverpark",
            "base_url": "https://cptc.smartcatalogiq.com",
            "catalog_path": "/en/2025-2026/catalog/courses",
            "catalog_year": "2025-2026",
            "uploaded_at": date.today().isoformat(),
            "source_url": "https://cptc.smartcatalogiq.com/en/2025-2026/catalog",
            "request_delay": 0.50,
        },
    },
    "bates": {
        "enabled": True,
        "parser": "bates",
        "config": {
            "institution": "bates",
            "base_url": "https://catalog.batestech.edu",
            "list_path": "/courses",
            "catalog_year": "2025-2026",
            "uploaded_at": date.today().isoformat(),
            "source_url": "https://catalog.batestech.edu/",
            "request_delay": 0.50,
        },
    },
}


def run_one(inst_id: str, cfg: dict, out_dir: Path) -> list[dict]:
    parser_fn = PARSERS.get(cfg["parser"])
    if not parser_fn:
        print(f"[{inst_id}] no parser '{cfg['parser']}' registered — skipping")
        return []
    print(f"[{inst_id}] parsing...")
    raw = list(parser_fn(cfg["config"]))
    print(f"[{inst_id}] {len(raw)} raw records")
    classified = [classify(r) for r in raw]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{inst_id}-courses.json").write_text(json.dumps(raw, indent=2))
    (out_dir / f"{inst_id}-courses-classified.json").write_text(json.dumps(classified, indent=2))
    # Archive snapshot keyed by catalog_year
    catalog_year = (raw[0].get("catalog_year") if raw else cfg["config"].get("catalog_year")) or "unknown"
    arch = ARCHIVE_DIR / catalog_year
    arch.mkdir(parents=True, exist_ok=True)
    (arch / f"{inst_id}.json").write_text(json.dumps(classified, indent=2))
    return classified


def main():
    requested = sys.argv[1:]
    selected = [i for i in INSTITUTIONS if i in requested] if requested else [
        i for i, cfg in INSTITUTIONS.items() if cfg.get("enabled")
    ]
    if not selected:
        print("No institutions selected. Available:", ", ".join(INSTITUTIONS))
        sys.exit(1)

    print(f"Building dataset for: {', '.join(selected)}")
    for inst_id in selected:
        cfg = INSTITUTIONS[inst_id]
        try:
            run_one(inst_id, cfg, CATALOG_DIR)
        except Exception as e:
            print(f"[{inst_id}] ERROR: {e}")
            continue

    # Always run the merge so the HTML always reads the up-to-date combined
    # view of every catalogs/*-courses-classified.json on disk — including
    # institutions parsed in prior runs, not just the ones requested today.
    print()
    print("Merging all per-institution outputs → ctc-courses-classified.json...")
    import subprocess
    subprocess.run([__import__("sys").executable, str(HERE / "merge_catalogs.py")], check=True)


if __name__ == "__main__":
    main()

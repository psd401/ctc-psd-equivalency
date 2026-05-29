"""Merge all per-institution classified JSON files into the dataset HTML reads.

Use this after running per-institution ingests in parallel (each
`python build_dataset.py <inst>` writes to catalogs/<inst>-courses-classified.json
and also overwrites ctc-courses-classified.json with only its own records).

Usage:
  python merge_catalogs.py
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).parent
CATALOG_DIR = HERE / "catalogs"
OUT = HERE / "ctc-courses-classified.json"


def main():
    files = sorted(CATALOG_DIR.glob("*-courses-classified.json"))
    if not files:
        print(f"No catalogs in {CATALOG_DIR}")
        return
    merged = []
    summary = {}
    for f in files:
        records = json.loads(f.read_text())
        if not records:
            continue
        inst = records[0].get("institution", f.stem.split("-")[0])
        summary[inst] = len(records)
        merged.extend(records)
    OUT.write_text(json.dumps(merged, indent=2))
    print(f"Merged {len(files)} files → {OUT.name}  ({len(merged)} records)")
    for inst, n in sorted(summary.items()):
        print(f"  {inst}: {n}")


if __name__ == "__main__":
    main()

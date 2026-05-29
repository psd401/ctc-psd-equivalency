"""Year-over-year catalog diff.

Compares two classified JSON snapshots (per institution) and emits a
markdown report flagging meaningful changes worth a human review before
publishing the new catalog year.

Usage:
  python diff_catalogs.py <old-json> <new-json> [-o report.md]
  python diff_catalogs.py archives/2024-2025/tcc.json archives/2025-2026/tcc.json

Or compare a whole archive year against another:
  python diff_catalogs.py --year-from 2024-2025 --year-to 2025-2026

The report covers:
  - Added courses
  - Removed courses
  - Credit-type changed (auto-classification only — decisions are tool-state)
  - HS-credit changed
  - Title changed (often signals course-number reorg)
  - Confidence dropped > 0.10 (often a classifier-rule mismatch)
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

HERE = Path(__file__).parent
ARCHIVE_DIR = HERE / "archives"


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def index(records: list[dict]) -> dict[tuple[str, str], dict]:
    return {(r.get("institution", ""), r["code"]): r for r in records}


def cmp_sets(old_idx: dict, new_idx: dict):
    old_keys, new_keys = set(old_idx), set(new_idx)
    return new_keys - old_keys, old_keys - new_keys, new_keys & old_keys


def title_changed(o: dict, n: dict) -> bool:
    return (o.get("title") or "").strip().lower() != (n.get("title") or "").strip().lower()


def credit_types_changed(o: dict, n: dict) -> bool:
    return set(o.get("credit_types") or [o.get("credit_type")]) != set(n.get("credit_types") or [n.get("credit_type")])


def hs_changed(o: dict, n: dict) -> bool:
    return json.dumps(o.get("hs_credits"), sort_keys=True) != json.dumps(n.get("hs_credits"), sort_keys=True)


def confidence_dropped(o: dict, n: dict, threshold: float = 0.10) -> bool:
    if o.get("confidence") is None or n.get("confidence") is None:
        return False
    return o["confidence"] - n["confidence"] > threshold


def format_row(row: list) -> str:
    return "| " + " | ".join(str(c) for c in row) + " |"


def render(report_title: str, sections: dict[str, dict]) -> str:
    out = [f"# {report_title}\n"]
    total = sum(len(s["rows"]) for s in sections.values())
    out.append(f"_{total} changes total_\n")
    for name, section in sections.items():
        out.append(f"\n## {name} ({len(section['rows'])})\n")
        if not section["rows"]:
            out.append("_None._\n")
            continue
        header = section["headers"]
        out.append(format_row(header))
        out.append("| " + " | ".join("---" for _ in header) + " |")
        for row in section["rows"]:
            out.append(format_row(row))
    return "\n".join(out)


def compute(old_path: Path, new_path: Path) -> dict[str, dict]:
    old, new = load(old_path), load(new_path)
    old_idx, new_idx = index(old), index(new)
    added, removed, shared = cmp_sets(old_idx, new_idx)

    def types_str(r):
        return " + ".join(r.get("credit_types") or ([r.get("credit_type")] if r.get("credit_type") else []))

    sections = {
        "Added":                       {"headers": ["Institution", "Code", "Title", "Credit types"], "rows": []},
        "Removed":                     {"headers": ["Institution", "Code", "Title", "Credit types"], "rows": []},
        "Credit-type changed":         {"headers": ["Institution", "Code", "Title", "Old → New"],    "rows": []},
        "HS-credit changed":           {"headers": ["Institution", "Code", "Title", "Old → New"],    "rows": []},
        "Title changed":               {"headers": ["Institution", "Code", "Old title", "New title"], "rows": []},
        "Confidence dropped (> 0.10)": {"headers": ["Institution", "Code", "Title", "Old → New"],    "rows": []},
    }
    for key in sorted(added):
        r = new_idx[key]
        sections["Added"]["rows"].append([r.get("institution"), r["code"], r.get("title", ""), types_str(r)])
    for key in sorted(removed):
        r = old_idx[key]
        sections["Removed"]["rows"].append([r.get("institution"), r["code"], r.get("title", ""), types_str(r)])
    for key in sorted(shared):
        o, n = old_idx[key], new_idx[key]
        if credit_types_changed(o, n):
            sections["Credit-type changed"]["rows"].append([
                n.get("institution"), n["code"], n.get("title", ""),
                types_str(o) + " → " + types_str(n),
            ])
        if hs_changed(o, n):
            sections["HS-credit changed"]["rows"].append([
                n.get("institution"), n["code"], n.get("title", ""),
                f"{o.get('hs_credits')} → {n.get('hs_credits')}",
            ])
        if title_changed(o, n):
            sections["Title changed"]["rows"].append([
                n.get("institution"), n["code"], o.get("title", ""), n.get("title", ""),
            ])
        if confidence_dropped(o, n):
            sections["Confidence dropped (> 0.10)"]["rows"].append([
                n.get("institution"), n["code"], n.get("title", ""),
                f"{o.get('confidence')} → {n.get('confidence')}",
            ])
    return sections


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old", nargs="?", help="path to old classified JSON")
    ap.add_argument("new", nargs="?", help="path to new classified JSON")
    ap.add_argument("--year-from", help="archive year to compare from (e.g. 2024-2025)")
    ap.add_argument("--year-to", help="archive year to compare to (e.g. 2025-2026)")
    ap.add_argument("-o", "--out", help="output markdown path (default: stdout)")
    args = ap.parse_args()

    if args.year_from and args.year_to:
        old_dir = ARCHIVE_DIR / args.year_from
        new_dir = ARCHIVE_DIR / args.year_to
        if not old_dir.exists() or not new_dir.exists():
            print(f"Missing archive: {old_dir if not old_dir.exists() else new_dir}")
            return
        # Merge per-institution snapshots into one comparison
        old_records, new_records = [], []
        for f in old_dir.glob("*.json"):
            old_records.extend(json.loads(f.read_text()))
        for f in new_dir.glob("*.json"):
            new_records.extend(json.loads(f.read_text()))
        old_path = HERE / f".diff_old_{args.year_from}.json"
        new_path = HERE / f".diff_new_{args.year_to}.json"
        old_path.write_text(json.dumps(old_records))
        new_path.write_text(json.dumps(new_records))
        title = f"Catalog diff: {args.year_from} → {args.year_to}"
    elif args.old and args.new:
        old_path, new_path = Path(args.old), Path(args.new)
        title = f"Catalog diff: {old_path.name} → {new_path.name}"
    else:
        ap.print_help()
        return

    sections = compute(old_path, new_path)
    md = render(title, sections)
    if args.out:
        Path(args.out).write_text(md)
        print(f"Wrote {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()

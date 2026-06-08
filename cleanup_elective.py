"""Batch-remove the redundant "Elective" credit type.

"Elective" is the catch-all category — it only applies when no other credit
type does. This script strips "Elective" wherever it appears alongside another
type, in two places:

  --sheet            : current decisions in the live Decisions backend.
                       Re-POSTs a corrected (superseding) row for each affected
                       decision, preserving every other field and appending a
                       cleanup note to the rationale. The Sheet is append-only,
                       so the prior row is retained in history.

  --audit FILE [...] : audit result JSON files (e.g. audit-health.json). Rewrites
                       each verdict's `recommended_types` array in place.

By default this is a DRY RUN: it prints what would change and writes nothing.
Pass --apply to actually update the Sheet / rewrite the files.

Usage:
  python cleanup_elective.py --audit audit-health.json audit-cte.json
  python cleanup_elective.py --audit audit-health.json audit-cte.json --apply
  python cleanup_elective.py --sheet
  python cleanup_elective.py --sheet --apply
  python cleanup_elective.py --sheet --audit audit-health.json --apply
"""
from __future__ import annotations
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzWhXfKmN7ryC8wiPXypvHmChGvQ9LdCKPDu6EolyNODNARsdfF41wpG_9GF2cdWWIJ/exec"

CLEANUP_NOTE = " [cleanup: removed redundant Elective]"

# Fields a decision row carries; we re-POST all of them so superseding a row
# never silently blanks a field. (decision_id / is_current / superseded_by /
# created_at / last_updated are managed server-side and intentionally omitted.)
DECISION_FIELDS = [
    "course_code",
    "institution",
    "applies_to",
    "status",
    "override_credit_types",
    "override_hs_credits",
    "rationale",
    "decided_by",
    "decided_date",
    "source_citation",
    "decided_for_year",
]


def drop_redundant_elective(types: list[str]) -> list[str]:
    """Strip "Elective" when at least one other credit type is present."""
    if len(types) > 1 and "Elective" in types:
        return [t for t in types if t != "Elective"]
    return list(types)


def split_pipe(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in str(value).split("|") if x.strip()]


# ---------------- Sheet cleanup ----------------

def http_get(url: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def http_post(decision: dict) -> dict:
    body = json.dumps(decision).encode("utf-8")
    req = urllib.request.Request(
        APPS_SCRIPT_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "text/plain;charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def cleanup_sheet(apply: bool, delay: float) -> None:
    print("Fetching current decisions from backend…")
    resp = http_get(APPS_SCRIPT_URL + "?action=list")
    if not resp.get("ok"):
        print("  ERROR listing decisions:", resp)
        sys.exit(1)
    decisions = resp.get("decisions", [])
    print(f"  {len(decisions)} current decisions.")

    affected = []
    for d in decisions:
        types = split_pipe(d.get("override_credit_types"))
        cleaned = drop_redundant_elective(types)
        if cleaned != types:
            affected.append((d, types, cleaned))

    if not affected:
        print("No decisions have 'Elective' alongside another credit type. Nothing to do.")
        return

    print(f"\n{len(affected)} decision(s) to clean:")
    for d, before, after in affected:
        print(f"  {d.get('institution',''):<10} {d.get('course_code',''):<12} "
              f"{'|'.join(before)}  ->  {'|'.join(after)}")

    if not apply:
        print("\n(dry-run; nothing posted. Re-run with --apply to update the Sheet.)")
        return

    print()
    ok = 0
    failures = []
    for d, before, after in affected:
        payload = {k: d.get(k, "") for k in DECISION_FIELDS}
        payload["override_credit_types"] = "|".join(after)
        rationale = str(d.get("rationale", "") or "")
        if CLEANUP_NOTE.strip() not in rationale:
            payload["rationale"] = rationale + CLEANUP_NOTE
        try:
            r = http_post(payload)
            if not r.get("ok"):
                raise RuntimeError(str(r))
            ok += 1
            print(f"  ✓ {d.get('institution',''):<10} {d.get('course_code',''):<12} "
                  f"{r.get('action','?')} {r.get('decision_id','')}")
            time.sleep(delay)
        except Exception as e:  # noqa: BLE001
            failures.append((d.get("course_code", ""), str(e)))
            print(f"  ✗ {d.get('institution',''):<10} {d.get('course_code',''):<12} ERROR: {e}")
    print(f"\nDone. {ok}/{len(affected)} updated.")
    if failures:
        print("Failures:")
        for code, err in failures:
            print(f"  {code}: {err}")


# ---------------- Audit-file cleanup ----------------

def cleanup_audit_file(path: Path, apply: bool) -> None:
    blob = json.loads(path.read_text())
    verdicts = blob.get("verdicts") if isinstance(blob, dict) else blob
    if not verdicts:
        print(f"{path.name}: no verdicts; skipping.")
        return

    changed = []
    for v in verdicts:
        before = v.get("recommended_types")
        if not isinstance(before, list):
            continue
        after = drop_redundant_elective(before)
        if after != before:
            v["recommended_types"] = after
            changed.append((v.get("institution", ""), v.get("code", ""), before, after))

    if not changed:
        print(f"{path.name}: clean (no Elective + other). Nothing to do.")
        return

    print(f"{path.name}: {len(changed)} verdict(s) to clean:")
    for inst, code, before, after in changed:
        print(f"  {inst:<10} {code:<12} {before}  ->  {after}")

    if not apply:
        print("  (dry-run; file unchanged. Re-run with --apply to rewrite.)")
        return

    # Match the source files exactly (2-space indent, no trailing newline) so
    # the only diff is the cleaned recommended_types arrays.
    path.write_text(json.dumps(blob, indent=2))
    print(f"  ✓ rewrote {path.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", action="store_true",
                    help="Clean current decisions in the live backend.")
    ap.add_argument("--audit", nargs="+", metavar="FILE", default=[],
                    help="Audit result JSON file(s) to clean in place.")
    ap.add_argument("--apply", action="store_true",
                    help="Actually write changes. Without this, runs as a dry run.")
    ap.add_argument("--delay", type=float, default=0.5,
                    help="Seconds between Sheet POSTs (default 0.5).")
    args = ap.parse_args()

    if not args.sheet and not args.audit:
        ap.error("nothing to do: pass --sheet and/or --audit FILE [...]")

    if not args.apply:
        print("== DRY RUN (no changes will be written) ==\n")

    for f in args.audit:
        cleanup_audit_file(Path(f), args.apply)
        print()

    if args.sheet:
        cleanup_sheet(args.apply, args.delay)


if __name__ == "__main__":
    main()

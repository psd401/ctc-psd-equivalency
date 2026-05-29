"""Apply a workflow audit result as decisions in the Sheet.

Reads the workflow's saved `result` JSON (the one with `verdicts` array) and
POSTs each verdict to the Apps Script Web App as a decision.

For Common Course Numbers (`&`-prefixed) we still scope each decision to the
single (course_code, institution) pair — because the audit found different
verdicts at different colleges for the same CCN (e.g. NUTR&101 stays Health
at Clover Park but drops Health at Olympic). applies_to="all" only when the
verdict is consistent across all institutions offering that code.

Usage:
  python apply_audit_decisions.py <audit-result.json> [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzWhXfKmN7ryC8wiPXypvHmChGvQ9LdCKPDu6EolyNODNARsdfF41wpG_9GF2cdWWIJ/exec"

DEFAULT_ROLE = "Director of Research & Assessment (AI-assisted audit)"
DEFAULT_SOURCE = "OSPI K-12 Health Learning Standards audit (2026-05-29)"
DEFAULT_YEAR = "2025-2026"


def post(decision: dict) -> dict:
    body = json.dumps(decision).encode("utf-8")
    req = urllib.request.Request(
        APPS_SCRIPT_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "text/plain;charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def build_decision(v: dict, applies_to: str) -> dict:
    return {
        "course_code": v["code"],
        "institution": v["institution"],
        "applies_to": applies_to,
        "status": "decided",
        "override_credit_types": "|".join(v["recommended_types"]),
        "override_hs_credits": "",
        "rationale": f"[Workflow audit · {v.get('verdict','')}] {v.get('reasoning','')}",
        "decided_by": DEFAULT_ROLE,
        "decided_date": date.today().isoformat(),
        "source_citation": DEFAULT_SOURCE,
        "decided_for_year": DEFAULT_YEAR,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audit_path", help="Path to JSON file with workflow result (has 'verdicts')")
    ap.add_argument("--dry-run", action="store_true", help="Print decisions without POSTing")
    ap.add_argument("--include-keep", action="store_true", help="Also apply keep_health verdicts as confirmations")
    ap.add_argument("--delay", type=float, default=0.5)
    args = ap.parse_args()

    blob = json.loads(Path(args.audit_path).read_text())
    # Support either {"verdicts": [...]} or [...]
    verdicts = blob.get("verdicts") if isinstance(blob, dict) else blob
    if not verdicts:
        print("No verdicts in payload")
        sys.exit(1)

    # Decide applies_to scope per verdict.
    # For CCNs where every institution offering it got the same recommended_types
    # we collapse to applies_to=all. Otherwise apply per-institution.
    by_code = defaultdict(list)
    for v in verdicts:
        by_code[v["code"]].append(v)

    decisions: list[tuple[dict, str]] = []
    for code, vs in by_code.items():
        is_ccn = "&" in code
        if is_ccn and len({tuple(v["recommended_types"]) for v in vs}) == 1 and len(vs) > 1:
            # All institutions agree on the same recommendation → single all-scope decision
            v = vs[0]
            if not args.include_keep and v["verdict"].startswith("keep"):
                continue
            decisions.append((build_decision(v, "all"), "all"))
        else:
            for v in vs:
                if not args.include_keep and v["verdict"].startswith("keep"):
                    continue
                decisions.append((build_decision(v, v["institution"]), v["institution"]))

    print(f"Will apply {len(decisions)} decisions:")
    for d, scope in decisions:
        print(f"  [{scope:>10}] {d['institution']:<10} {d['course_code']:<12} → {d['override_credit_types']:<40} verdict={d['rationale'][:60]}…")

    if args.dry_run:
        print("\n(dry-run; nothing posted)")
        return

    print()
    successes = 0
    failures: list[tuple[str, str]] = []
    for d, scope in decisions:
        try:
            r = post(d)
            if not r.get("ok"):
                raise RuntimeError(str(r))
            successes += 1
            print(f"  ✓ {d['institution']:<10} {d['course_code']:<12} → {r.get('action','?')} {r.get('decision_id','')}")
            time.sleep(args.delay)
        except Exception as e:
            failures.append((d["course_code"], str(e)))
            print(f"  ✗ {d['institution']:<10} {d['course_code']:<12} ERROR: {e}")
    print()
    print(f"Done. {successes}/{len(decisions)} succeeded.")
    if failures:
        print("Failures:")
        for c, e in failures:
            print(f"  {c}: {e}")


if __name__ == "__main__":
    main()

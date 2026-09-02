"""Normalize a Common Course Number to one credit-type answer at every college.

A CCN (`&`-suffixed) is statewide-equivalent, so the same code should not
resolve to different PSD credit types at different colleges. Divergence creeps
in because per-college audits ran at different times against different evidence.
This script posts the decisions that collapse a CCN back to a single answer.

Scope matters, and the obvious choice is usually wrong. The viewer's
`effective()` (see build_html.py) resolves a direct `(course_code, institution)`
decision BEFORE any `applies_to="all"` decision:

    DECISIONS_BY_KEY.get(code + "|" + inst)          # <- checked first
      ?? DECISIONS_BY_CODE_ALL.get(common_code)      # <- only if no direct hit

So an all-scope row is silently ignored at every college that already has an
institution-scoped row. Most CCNs here carry institution-scoped rows from the
2026-05-29 / 2026-06-11 audits, so each one must be superseded in place —
hence one row per college by default.

ALL_SCOPE is the exception: those codes are governed today by a single
all-scope row with no competing institution-scoped rows, so the correct move
is to supersede that one row rather than fan out. Check before adding to it —
`?action=list` shows the current scope of every decision.

Re-running is a no-op: the script fresh-fetches the current decisions and skips
any (code, institution) pair whose override already matches the target.

Usage:
  export CTC_DECISIONS_KEY=...          # see decisions_setup/SETUP.md
  python normalize_ccn_decisions.py --dry-run
  python normalize_ccn_decisions.py
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "equivalency-data.json"

APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzWhXfKmN7ryC8wiPXypvHmChGvQ9LdCKPDu6EolyNODNARsdfF41wpG_9GF2cdWWIJ/exec"
API_KEY = os.environ.get("CTC_DECISIONS_KEY", "")

DECIDED_BY = "AI Classifier"
YEAR = "2025-2026"
SOURCE = "PSD Running Start Course Equivalency worksheet reconciliation (2026-09-02)"

# code -> institution that owns the existing all-scope row. An all-scope row is
# stored under whichever college posted it, so a supersede must reuse that owner.
ALL_SCOPE = {"CHEM&139": "olympic", "CHEM&141": "olympic", "CHEM&142": "olympic"}

# code -> (credit types, rationale). Applied 2026-09-02; kept as the record of
# what was decided and as the template for the next normalization pass.
TARGETS = {
    "NUTR&101": (
        ["Health", "Science (Non-Lab)"],
        "Nutrition carries HS Health credit with college science as a secondary. "
        "Matches the PSD equivalency worksheet HEALTH row and replaces the split "
        "outcome (Elective at Clover Park/Green River, Science (Non-Lab) elsewhere).",
    ),
    "CMST&220": (
        ["ELA"],
        "Public Speaking substitutes for 1 ELA credit per OSPI. Four of five colleges "
        "were already decided ELA; Olympic was the lone Elective.",
    ),
    "ENGR&204": (
        ["Science (Lab)"],
        "Electrical Circuits is lecture + lab everywhere components are published "
        "(Olympic 6cr Lecture+Lab, TCC 6cr Lecture+Lab, Pierce 20 lab contact hours). "
        "Green River publishes no components; normalized to match.",
    ),
    "ENGR&215": (
        ["Science (Non-Lab)"],
        "Dynamics is 5-credit lecture-only at every college (Pierce declares "
        "Lab Contact Hours 0). Drops the inconsistent CTE secondary.",
    ),
    "ENGR&224": (
        ["Science (Non-Lab)"],
        "Thermodynamics is 5-credit lecture-only at every college (Pierce declares "
        "Lab Contact Hours 0). Drops Green River's Lab and TCC's CTE secondary.",
    ),
    "CS&141": (
        ["CTE", "Math"],
        "Computer Science I — CTE primary with Math secondary, matching the Olympic "
        "decision; Pierce was CTE only.",
    ),
    # Corrections to 2026-06-08/11 decisions made while parsers/base.py inferred a
    # phantom "Lab" component from Pierce's "... Lab Contact Hours 0 ..." line.
    "CHEM&139": (
        ["Science (Non-Lab)"],
        "General Chemistry Prep is lecture-only: Olympic is 5cr Lecture with labs "
        "split into CHEM&151/152, and Pierce declares Lab Contact Hours 0. The "
        "2026-06-08 Science (Lab) decision rested on a phantom lab component.",
    ),
    "CHEM&141": (
        ["Science (Non-Lab)"],
        "General Chemistry I is lecture-only: Olympic is 5cr Lecture with labs split "
        "into CHEM&151/152, and Pierce declares Lab Contact Hours 0. The 2026-06-08 "
        "Science (Lab) decision rested on a phantom lab component.",
    ),
    "CHEM&142": (
        ["Science (Non-Lab)"],
        "General Chemistry II is lecture-only: Olympic is 5cr Lecture with labs split "
        "into CHEM&151/152, and Pierce declares Lab Contact Hours 0. The 2026-06-08 "
        "Science (Lab) decision rested on a phantom lab component.",
    ),
    "BIOL275": (
        ["Science (Non-Lab)"],
        "Pierce declares Lab Contact Hours 0. The 2026-06-11 Science (Lab) decision "
        "rested on a phantom lab component inferred from that same line.",
    ),
}


def fetch_current() -> dict[tuple[str, str], str]:
    """(course_code, institution) -> override_credit_types for current rows.

    Reachable without the key; override_credit_types is a public field, which is
    all the skip check needs.
    """
    url = APPS_SCRIPT_URL + "?action=list"
    if API_KEY:
        url += "&k=" + urllib.parse.quote(API_KEY)
    with urllib.request.urlopen(url, timeout=60) as r:
        payload = json.load(r)
    if not payload.get("ok"):
        raise RuntimeError(f"list failed: {payload}")
    return {
        (d.get("course_code"), d.get("institution")): d.get("override_credit_types") or ""
        for d in payload.get("decisions", [])
        if d.get("is_current") is not False
    }


def post(decision: dict) -> dict:
    body = json.dumps({**decision, "k": API_KEY}).encode("utf-8")
    req = urllib.request.Request(
        APPS_SCRIPT_URL, data=body, method="POST",
        headers={"Content-Type": "text/plain;charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def build_rows(courses: list[dict], current: dict[tuple[str, str], str]) -> list[dict]:
    rows: list[dict] = []
    for code, (types, rationale) in TARGETS.items():
        offering = sorted({c["institution"] for c in courses
                           if c.get("common_code") == code or c["code"] == code})
        if not offering:
            print(f"!! {code}: no college offers this — skipped")
            continue
        if code in ALL_SCOPE:
            owner = ALL_SCOPE[code]
            if owner not in offering:
                print(f"!! {code}: all-scope owner {owner!r} not among {offering} — skipped")
                continue
            offering = [owner]

        want = "|".join(types)
        for inst in offering:
            if current.get((code, inst)) == want:
                print(f"   = {inst:<11} {code:<10} already {want} — skipped")
                continue
            rows.append({
                "course_code": code,
                "institution": inst,
                "applies_to": "all" if code in ALL_SCOPE else inst,
                "status": "decided",
                "override_credit_types": want,
                "override_hs_credits": "",
                "rationale": rationale,
                "decided_by": DECIDED_BY,
                "decided_date": date.today().isoformat(),
                "source_citation": SOURCE,
                "decided_for_year": YEAR,
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Print decisions without POSTing")
    ap.add_argument("--delay", type=float, default=0.5)
    args = ap.parse_args()

    courses = json.loads(DATA.read_text())
    current = fetch_current()
    print(f"Fetched {len(current)} current decisions.\n")

    rows = build_rows(courses, current)
    if not rows:
        print("\nNothing to do — every target already matches.")
        return

    print(f"\nWill post {len(rows)} decisions:\n")
    for d in rows:
        print(f"  [{d['applies_to']:>10}] {d['institution']:<11} {d['course_code']:<10} → {d['override_credit_types']}")

    if args.dry_run:
        print("\n(dry-run; nothing posted)")
        return
    if not API_KEY:
        print("\nCTC_DECISIONS_KEY is not set — writes would be rejected. Aborting.")
        sys.exit(1)

    print()
    ok = 0
    for d in rows:
        try:
            r = post(d)
            if not r.get("ok"):
                raise RuntimeError(str(r))
            ok += 1
            print(f"  ✓ {d['institution']:<11} {d['course_code']:<10} {r.get('action','?')} {r.get('decision_id','')}")
            time.sleep(args.delay)
        except Exception as e:
            print(f"  ✗ {d['institution']:<11} {d['course_code']:<10} ERROR: {e}")
    print(f"\nDone. {ok}/{len(rows)} succeeded.")


if __name__ == "__main__":
    main()

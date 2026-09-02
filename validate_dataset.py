"""Assert the dataset is sane before it reaches counselors.

Every serious defect this project has hit was a silent absence, not a crash:

  * The Bates drupal parser dropped every Common Course Number course — the
    whole transfer catalog — because a regex could not cross "&". Four months.
  * Green River stored credits_total: None on all 1378 of its courses because a
    credits regex matched only one of two markup shapes. The tool showed no
    high-school credit for a third of the dataset.
  * A WAF challenge read as an empty catalog would have wiped three colleges,
    and reported "0/0 pages parsed" while doing it.
  * Pierce has been read from its 2023-2024 catalog while labelled 2025-2026.

None of these raised an error. Each produced a smaller, quieter, plausible
dataset. This module encodes what "plausible" is NOT, so the next one fails the
build instead of reaching a counselor advising a student.

Checks are either ERROR (block a deploy) or WARN (worth a look). Thresholds are
deliberately loose: this catches collapses and blackouts, not drift.

Usage:
  python validate_dataset.py                  # check equivalency-data.json
  python validate_dataset.py path/to/data.json
  python validate_dataset.py --strict         # treat warnings as errors too

Exit code 0 = clean (warnings allowed), 1 = at least one error.
"""
from __future__ import annotations
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT = HERE / "equivalency-data.json"

# Every college we expect to publish, with a floor on its course count. Floors
# sit well under current counts — they catch a collapse, not normal churn.
EXPECTED_INSTITUTIONS = {
    "bates": 900,
    "cloverpark": 800,
    "greenriver": 1000,
    "olympic": 900,
    "pierce": 700,
    "tcc": 600,
}

# A college with more than this fraction of courses missing a credit value is
# almost certainly a parser fault rather than a catalog that declines to say.
# Pierce genuinely publishes contact hours instead of credits, so it is exempt
# until that conversion is agreed — see the note in validate_credits().
MAX_MISSING_CREDITS = 0.25
# Pierce was exempt while it had no credit values at all; since 2026-09-02 its
# credits are derived from published contact hours, so it is held to the same
# bar as everyone else.
CREDITS_EXEMPT: set[str] = set()

DERIVED_CREDITS_PREFIX = "Credit value DERIVED from published contact hours"

VALID_TYPES = {
    "ELA", "Math", "Science (Lab)", "Science (Non-Lab)",
    "Social Studies - US History", "Social Studies - World History",
    "Social Studies - Washington State History", "Social Studies - Civics",
    "Social Studies - Elective", "Fine & Performing Arts", "World Language",
    "Health", "PE / Fitness", "CTE", "Elective",
}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def validate_shape(courses: list[dict], r: Report) -> None:
    """Every record must carry the fields the viewer reads."""
    required = ("institution", "code", "title", "credit_types", "catalog_year")
    for field in required:
        missing = [c.get("code", "<no code>") for c in courses if not c.get(field)]
        if missing:
            r.error(f"{len(missing)} records have no {field} (e.g. {missing[:5]})")

    blank_titles = [c["code"] for c in courses if not (c.get("title") or "").strip()]
    if blank_titles:
        r.error(f"{len(blank_titles)} records have a blank title (e.g. {blank_titles[:5]})")

    dupes = [k for k, n in Counter(
        (c.get("institution"), c.get("code")) for c in courses).items() if n > 1]
    if dupes:
        r.error(f"{len(dupes)} duplicate (institution, code) pairs (e.g. {dupes[:5]})")


def validate_coverage(courses: list[dict], r: Report) -> None:
    """Every expected college present, and none of them collapsed."""
    counts = Counter(c["institution"] for c in courses)
    for inst, floor in EXPECTED_INSTITUTIONS.items():
        n = counts.get(inst, 0)
        if n == 0:
            r.error(f"{inst}: MISSING ENTIRELY — a blocked crawl looks exactly like this")
        elif n < floor:
            r.error(f"{inst}: only {n} courses, below the floor of {floor} — "
                    f"likely a truncated scrape, not a smaller catalog")
    for inst in set(counts) - set(EXPECTED_INSTITUTIONS):
        r.warn(f"{inst}: {counts[inst]} courses from an institution not in EXPECTED_INSTITUTIONS")


def validate_credits(courses: list[dict], r: Report) -> None:
    """A college-wide credit blackout is a parser fault, not a catalog fact.

    Pierce is exempt: it publishes Total Contact Hours rather than credits, and
    converting (lecture/10 + lab/20) matches peer colleges for 139 of 150 CCN
    courses — strong but not certain, so it has not been applied.
    """
    by_inst = defaultdict(list)
    for c in courses:
        by_inst[c["institution"]].append(c)
    for inst, recs in sorted(by_inst.items()):
        missing = sum(1 for c in recs if c.get("hs_credits") is None)
        frac = missing / len(recs)
        if inst in CREDITS_EXEMPT:
            if missing:
                r.warn(f"{inst}: {missing}/{len(recs)} courses have no credit value (known: "
                       f"publishes contact hours, not credits)")
            continue
        if frac > MAX_MISSING_CREDITS:
            r.error(f"{inst}: {missing}/{len(recs)} ({frac:.0%}) courses have no credit value — "
                    f"this is what a missed credits pattern looks like")
        elif missing:
            r.warn(f"{inst}: {missing}/{len(recs)} courses have no credit value")


def validate_common_courses(courses: list[dict], r: Report) -> None:
    """Every college should carry Common Course Numbers, and lots of them.

    This is the check that would have caught the Bates bug in May. That parser
    dropped every "&" course — 1285 records still landed, comfortably above any
    total-count floor, so a coverage check saw nothing wrong. The signature was
    visible only here:

        bates          0 CCN of 1285 total
        cloverpark    45 CCN of 1116
        greenriver   178 CCN of 1378
        olympic      174 CCN of 1246
        pierce       181 CCN of  947
        tcc          137 CCN of  828

    Zero CCNs at a Washington community or technical college is not a catalog
    fact — it means the code that recognises them broke. And CCNs are exactly
    the transfer courses Running Start students enrol in, so losing them is the
    most consequential possible silent failure.
    """
    by_inst = defaultdict(int)
    totals = Counter(c["institution"] for c in courses)
    for c in courses:
        if c.get("is_common_course"):
            by_inst[c["institution"]] += 1
    if not by_inst:
        r.error("no college has ANY common-course records — CCN detection is broken")
        return
    counts = sorted(by_inst.get(i, 0) for i in totals)
    median = counts[len(counts) // 2] or 1
    for inst in sorted(totals):
        n = by_inst.get(inst, 0)
        if n == 0:
            r.error(f"{inst}: ZERO common-course (&) records out of {totals[inst]} courses — "
                    f"peers carry ~{median}. The transfer catalog is missing.")
        elif n < median * 0.10:
            r.warn(f"{inst}: only {n} common-course records out of {totals[inst]} "
                   f"(peers carry ~{median}) — worth checking the code pattern")


def validate_flags(courses: list[dict], r: Report) -> None:
    """review_flags must not accumulate duplicates.

    classify_courses reads and rewrites its own output, and classify() carries
    ingest-stage flags through from the incoming record. Without a dedupe every
    rerun appended another copy — four identical "CTE crosswalk review" entries
    had already reached the published dataset before this check existed.
    """
    dupes = [c for c in courses
             if len(c.get("review_flags") or []) != len(set(c.get("review_flags") or []))]
    if dupes:
        r.error(f"{len(dupes)} records have duplicate review_flags — classify() is not "
                f"idempotent (e.g. {dupes[0]['institution']} {dupes[0]['code']}: "
                f"{dupes[0]['review_flags']})")


def validate_derived_credits(courses: list[dict], r: Report) -> None:
    """A derived credit value must say so, and must actually have a value.

    Pierce publishes contact hours and no credit figure, so its credits are
    computed (lecture/10 + lab/20 + clinical/30). That is defensible only while
    the record carries the flag saying it is derived — a counselor reading the
    number needs to know it is inferred before it counts toward graduation. A
    derived value with the flag stripped is worse than no value at all.
    """
    flagged = [c for c in courses
               if any(f.startswith(DERIVED_CREDITS_PREFIX) for f in (c.get("review_flags") or []))]
    empty = [c for c in flagged if c.get("hs_credits") is None]
    if empty:
        r.error(f"{len(empty)} records are flagged as having derived credits but carry no "
                f"value (e.g. {empty[0]['institution']} {empty[0]['code']})")
    if flagged:
        by_inst = Counter(c["institution"] for c in flagged)
        r.warn(f"{len(flagged)} records carry DERIVED credit values, not published by the "
               f"college: {dict(by_inst)}")


def validate_types(courses: list[dict], r: Report) -> None:
    """Credit types must be known values, and Elective is the catch-all."""
    for c in courses:
        for t in c.get("credit_types") or []:
            if t not in VALID_TYPES:
                r.error(f"{c['institution']} {c['code']}: unknown credit type {t!r}")
        types = c.get("credit_types") or []
        if len(types) > 1 and "Elective" in types:
            r.error(f"{c['institution']} {c['code']}: carries Elective alongside "
                    f"{[t for t in types if t != 'Elective']} — Elective is the catch-all")
        if not types:
            r.error(f"{c['institution']} {c['code']}: no credit type at all")


def validate_ccn_consistency(courses: list[dict], r: Report) -> None:
    """A Common Course Number is statewide-equivalent: one answer everywhere.

    This is base-layer only. The viewer overlays decisions at runtime, so a
    divergence here can still resolve correctly for users — but it means the
    classifier and the decisions Sheet disagree, which is worth knowing.
    """
    by_ccn: dict[str, dict[str, str]] = defaultdict(dict)
    for c in courses:
        if c.get("common_code"):
            by_ccn[c["common_code"]][c["institution"]] = "|".join(c.get("credit_types") or [])
    diverging = {k: v for k, v in by_ccn.items() if len(set(v.values())) > 1}
    if diverging:
        r.warn(f"{len(diverging)} common courses resolve to different credit types "
               f"across colleges (base layer): {sorted(diverging)[:8]}")


def validate_catalog_year(courses: list[dict], r: Report) -> None:
    """Flag colleges whose catalog year looks stale or inconsistent."""
    by_inst = defaultdict(set)
    for c in courses:
        by_inst[c["institution"]].add(c.get("catalog_year"))
    for inst, years in sorted(by_inst.items()):
        if len(years) > 1:
            r.error(f"{inst}: mixed catalog years in one college: {sorted(years)}")
    all_years = {y for ys in by_inst.values() for y in ys}
    if len(all_years) > 1:
        r.warn(f"colleges are on different catalog editions: "
               f"{ {i: sorted(y)[0] for i, y in sorted(by_inst.items())} }")


CHECKS = (
    validate_shape,
    validate_coverage,
    validate_credits,
    validate_common_courses,
    validate_flags,
    validate_derived_credits,
    validate_types,
    validate_ccn_consistency,
    validate_catalog_year,
)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    strict = "--strict" in sys.argv
    path = Path(args[0]) if args else DEFAULT

    courses = json.loads(path.read_text())
    print(f"Validating {path.name} — {len(courses)} records\n")

    r = Report()
    for check in CHECKS:
        check(courses, r)

    for w in r.warnings:
        print(f"  WARN   {w}")
    for e in r.errors:
        print(f"  ERROR  {e}")

    print()
    if r.errors:
        print(f"FAILED — {len(r.errors)} error(s), {len(r.warnings)} warning(s)")
        sys.exit(1)
    if r.warnings and strict:
        print(f"FAILED (--strict) — {len(r.warnings)} warning(s)")
        sys.exit(1)
    print(f"OK — 0 errors, {len(r.warnings)} warning(s)")


if __name__ == "__main__":
    main()

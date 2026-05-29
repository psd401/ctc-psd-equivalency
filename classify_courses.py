"""Classify each course into a PSD/WA-SBE credit type and compute HS credit value.

Rules:
  * 100+ level course → HS credits = quarter_credits / 5
  * Sub-100 level course → flagged for Fresh Start (Open Doors) discussion; HS value left null
  * Variable-credit courses (e.g. ABE20) → HS min/max
Credit types follow WA SBE 24-credit framework (subdivided per James's spec).

CLI:
  python classify_courses.py                  # reclassify the merged dataset in place
  python classify_courses.py path/to/in.json [path/to/out.json]
"""
import json
import re
import sys
from pathlib import Path

SRC = Path("ctc-courses-classified.json")  # merged dataset (default)
OUT = Path("ctc-courses-classified.json")

# ----- Credit type taxonomy -----
# Per WA SBE + James's clarifications.
TYPES = [
    "ELA",
    "Math",
    "Science (Lab)",
    "Science (Non-Lab)",
    "Social Studies - US History",
    "Social Studies - World History",
    "Social Studies - Washington State History",
    "Social Studies - Civics",
    "Social Studies - Elective",
    "Fine & Performing Arts",
    "World Language",
    "Health",
    "PE / Fitness",
    "CTE",
    "Elective",
]

# ----- Prefix → credit-type mapping (universal across colleges) -----
# The 5-tier resolution precedence (most specific wins):
#   1. SPECIFIC_OVERRIDES[(institution, code)]
#   2. COMMON_COURSE_OVERRIDES[common_code]       (any college, &-prefix only)
#   3. PREFIX_DIRECT_BY_INSTITUTION[institution][prefix]
#   4. PREFIX_DIRECT_UNIVERSAL[prefix]            (was PREFIX_DIRECT)
#   5. fallback Elective with low confidence
PREFIX_DIRECT_UNIVERSAL = {
    # Core academic
    "ENGL":  ("ELA",                 0.95, []),
    "ENGLC": ("ELA",                 0.85, ["Co-req for ENGL&101 — sub-100"]),
    "WRITE": ("ELA",                 0.85, []),
    "MATH":  ("Math",                0.95, []),

    # Social Studies (default; HIST/POLS get refined below)
    "HIST":  ("Social Studies - Elective", 0.70, ["Refine into US/World History"]),
    "POLS":  ("Social Studies - Elective", 0.70, ["Refine into Civics for POLS&202"]),
    "ECON":  ("Social Studies - Elective", 0.90, []),
    "ANTH":  ("Social Studies - Elective", 0.90, []),
    "SOC":   ("Social Studies - Elective", 0.90, []),
    "PSYC":  ("Social Studies - Elective", 0.85, []),
    "GEOG":  ("Social Studies - Elective", 0.85, []),

    # Communication Studies → WA allows Public Speaking (CMST&220) to satisfy 1 ELA credit
    "CMST":  ("Elective",            0.70, ["CMST&220 may substitute for ELA per OSPI; review"]),

    # Sciences (lab vs non-lab decided by components)
    "BIOL":  ("Science (Lab)",       0.95, []),
    "CHEM":  ("Science (Lab)",       0.95, []),
    "PHYS":  ("Science (Lab)",       0.95, []),
    "GEOL":  ("Science (Lab)",       0.95, []),
    "ENVS":  ("Science (Lab)",       0.95, []),
    "OCEA":  ("Science (Lab)",       0.95, []),
    "ASTR":  ("Science (Lab)",       0.95, []),
    "BOT":   ("Science (Lab)",       0.90, []),
    "ATMS":  ("Science (Lab)",       0.90, []),
    "SCI":   ("Science (Non-Lab)",   0.70, ["Generic SCI prefix — review"]),
    "NUTR":  ("Science (Non-Lab)",   0.75, ["Nutrition — may count as Science or Health"]),

    # Engineering → typically not Science for HS; OSPI guidance varies
    "ENGR":  ("CTE",                 0.60, ["WA OSPI: Engineering may count as Math/Science equivalency; review"]),

    # Arts
    "ART":   ("Fine & Performing Arts", 0.95, []),
    "MUSC":  ("Fine & Performing Arts", 0.95, []),
    "HUM":   ("Fine & Performing Arts", 0.75, ["Humanities — review for Arts vs Elective"]),

    # World languages — ASL would go here if TCC offered it (currently not in catalog)
    "SPAN":  ("World Language",      0.95, []),
    "FREN":  ("World Language",      0.95, []),
    "JAPN":  ("World Language",      0.95, []),
    "CHIN":  ("World Language",      0.95, []),
    "GER":   ("World Language",      0.95, []),
    "ASL":   ("World Language",      0.95, []),

    # PE / Health
    "PE":    ("PE / Fitness",        0.95, []),
    "PHED":  ("PE / Fitness",        0.95, []),
    # NOTE: CHP / CHPM / CHRC are TCC-specific Community Health prefixes.
    # The OSPI-standards audit (2026-05-29) showed they're workforce-track,
    # not K-12 personal health literacy. Moved to PREFIX_DIRECT_BY_INSTITUTION["tcc"]
    # with CTE default. Other colleges using these prefixes would need their
    # own rules added.

    # CTE (flag every CTE entry — WA state CTE alignment rules need review)
    "ACCT":  ("CTE", 0.85, ["CTE — WA state CTE crosswalk review"]),
    "BUS":   ("CTE", 0.85, ["CTE — WA state CTE crosswalk review"]),
    "CS":    ("CTE", 0.85, ["CTE — programming, NOT a World Language"]),
    "IT":    ("CTE", 0.85, ["CTE — programming/IT, NOT a World Language"]),
    "ITC":   ("CTE", 0.85, ["CTE — IT"]),
    "CU":    ("CTE", 0.85, ["CTE — Computer User"]),
    "HIM":   ("CTE", 0.85, ["CTE — Health Information Management"]),
    "HIT":   ("CTE", 0.85, ["CTE — Health Information Technology"]),
    "NAC":   ("CTE", 0.85, ["CTE — Nursing Assistant Certified"]),
    "NURS":  ("CTE", 0.85, ["CTE — Nursing"]),
    "EMS":   ("CTE", 0.85, ["CTE — Emergency Medical Services"]),
    "CT":    ("CTE", 0.85, ["CTE — Computed Tomography"]),
    "DMS":   ("CTE", 0.85, ["CTE — Diagnostic Medical Sonography"]),
    "RS":    ("CTE", 0.85, ["CTE — Radiologic Science"]),
    "RC":    ("CTE", 0.85, ["CTE — Respiratory Care"]),
    "MO":    ("CTE", 0.85, ["CTE — Medical Office"]),
    "PLST":  ("CTE", 0.85, ["CTE — Paralegal Studies"]),
    "ECED":  ("CTE", 0.85, ["CTE — Early Childhood Education"]),
    "ECE":   ("CTE", 0.85, ["CTE — Early Childhood Education"]),
    "HFL":   ("CTE", 0.85, ["CTE — Home & Family Life"]),
    "LOG":   ("CTE", 0.80, ["CTE — Logistics"]),
    "AH":    ("CTE", 0.80, ["CTE — Allied Health intro"]),

    # Adult/Basic Ed & Fresh Start → leave as Elective (and flagged by sub-100 rule)
    "ABE":   ("Elective", 0.60, ["Adult Basic Ed — Fresh Start program; HS credit unclear"]),
    "ELA":   ("ELA",      0.70, ["English Language Acquisition — sub-100; review"]),
    "EAP":   ("ELA",      0.70, ["English for Academic Purposes — sub-100; review"]),
    "FRSH":  ("Elective", 0.60, ["Fresh Start program"]),
    "IBEST": ("Elective", 0.60, ["Integrated Basic Education Skills Training"]),

    # Misc → Elective
    "HD":    ("Elective", 0.80, []),
    "HUMDV": ("Elective", 0.75, []),
    "HSP":   ("Elective", 0.80, ["Human Services"]),
    "COL":   ("Elective", 0.90, ["College success — typically elective"]),
    "EDUC":  ("Elective", 0.85, ["Education — review for CTE alignment"]),
    "LS":    ("Elective", 0.80, ["Library Science"]),
    "SOCSC": ("Social Studies - Elective", 0.75, []),
    "PHIL":  ("Elective", 0.75, ["Philosophy — may count as ELA or Elective"]),
}

# ----- Per-institution prefix overrides -----
# Use this when a college's local prefix means something different from the
# universal-prefix default. Populated as concrete conflicts emerge through
# decision-making and audit workflows.
PREFIX_DIRECT_BY_INSTITUTION: dict[str, dict[str, tuple]] = {
    "tcc": {
        # OSPI-standards audit (2026-05-29) confirmed these are workforce/
        # professional-track programs, not K-12 personal health literacy.
        "CHP":  ("CTE", 0.75, ["Community Health — OSPI audit reclassified from Health; verify per-course"]),
        "CHPM": ("CTE", 0.80, ["Community Health Promotion / EMS — workforce track"]),
        "CHRC": ("CTE", 0.85, ["Community Health Resource Coordination — workforce track"]),
    },
}


# ----- Common Course Number overrides -----
# WA Common Course Numbers (`&`-suffix prefixes) are statewide-equivalent.
# Decisions about a CCN apply at every college that offers it.
COMMON_COURSE_OVERRIDES = {
    "HIST&126": ("Social Studies - World History", 0.95, []),
    "HIST&127": ("Social Studies - World History", 0.95, []),
    "HIST&128": ("Social Studies - World History", 0.95, []),
    "HIST&146": ("Social Studies - US History", 0.95, []),
    "HIST&147": ("Social Studies - US History", 0.95, []),
    "HIST&148": ("Social Studies - US History", 0.95, []),
    "HIST&214": ("Social Studies - Washington State History", 0.95, ["Pacific NW History — satisfies WA State History"]),
    "HIST&215": ("Social Studies - US History", 0.85, []),
    "HIST&219": ("Social Studies - US History", 0.85, []),
    "HIST&220": ("Social Studies - US History", 0.85, []),
    "POLS&101": ("Social Studies - Civics", 0.85, ["Intro Political Science — may count as Civics or SS"]),
    "POLS&202": ("Social Studies - Civics", 0.95, ["US Government — Civics"]),
    "POLS&201": ("Social Studies - Elective", 0.85, []),
    "POLS&203": ("Social Studies - Elective", 0.85, []),
    "CMST&220": ("ELA", 0.75, ["Public Speaking — WA OSPI allows substitute for 1 ELA credit"]),
    "ENGR&225": ("Elective", 0.70, ["Mechanics of Materials — Engineering"]),
}


# ----- Course-specific overrides (institution-aware) -----
# Keyed by (institution, code). For local-prefix courses unique to one college.
SPECIFIC_OVERRIDES: dict[tuple[str, str], tuple] = {
    ("tcc", "HIST210"):  ("Social Studies - World History", 0.85, []),
    ("tcc", "HIST211"):  ("Social Studies - World History", 0.85, []),
    ("tcc", "HIST230"):  ("Social Studies - World History", 0.85, []),
    ("tcc", "HIST224"):  ("Social Studies - US History", 0.85, []),
    ("tcc", "HIST231"):  ("Social Studies - US History", 0.80, []),
    ("tcc", "HIST240"):  ("Social Studies - US History", 0.80, []),
    ("tcc", "HIST244"):  ("Social Studies - US History", 0.80, []),
}


# ----- Secondary credit types -----
# Universal (keyed by &-CCN) and per-institution (keyed by (inst, code)).
SECONDARY_TYPES_COMMON: dict[str, list[str]] = {
    "BUS&201":  ["Social Studies - Elective"],                       # Business Law
    "ECON&201": ["CTE"],                                             # Microeconomics (CTE pathway)
    "ECON&202": ["CTE"],                                             # Macroeconomics (CTE pathway)
    "HIST&214": ["Social Studies - US History"],                     # Pacific NW also satisfies US Hist
    # NUTR&101 Health secondary REMOVED 2026-05-29 — OSPI audit found most
    # college nutrition courses lean college-science, not K-12 Health.
    # Per-institution audit decisions add Health back where appropriate
    # (e.g. Clover Park, Pierce kept Health alongside Science).
    "CMST&220": ["CTE"],                                             # Public Speaking — workforce-readiness CTE
}
SECONDARY_TYPES_BY_INSTITUTION: dict[tuple[str, str], list[str]] = {}


def _resolve_primary(institution: str, code: str, is_common: bool, common_code):
    """Five-tier resolution. Returns (ctype, confidence, rule_flags, rule_label)."""
    # 1. SPECIFIC_OVERRIDES[(institution, code)]
    key = (institution, code)
    if key in SPECIFIC_OVERRIDES:
        ctype, conf, fl = SPECIFIC_OVERRIDES[key]
        return ctype, conf, fl, f"specific:{institution}:{code}"

    # 2. COMMON_COURSE_OVERRIDES[common_code]
    if is_common and common_code in COMMON_COURSE_OVERRIDES:
        ctype, conf, fl = COMMON_COURSE_OVERRIDES[common_code]
        return ctype, conf, fl, f"common-course:{common_code}"

    # 3. PREFIX_DIRECT_BY_INSTITUTION[institution][prefix]
    prefix_match = re.match(r"([A-Z]+)", code)
    prefix = prefix_match.group(1) if prefix_match else ""
    inst_map = PREFIX_DIRECT_BY_INSTITUTION.get(institution, {})
    if prefix in inst_map:
        ctype, conf, fl = inst_map[prefix]
        return ctype, conf, fl, f"prefix:{institution}:{prefix}"

    # 4. PREFIX_DIRECT_UNIVERSAL[prefix]
    if prefix in PREFIX_DIRECT_UNIVERSAL:
        ctype, conf, fl = PREFIX_DIRECT_UNIVERSAL[prefix]
        return ctype, conf, fl, f"prefix:{prefix}"

    # 5. fallback
    return "Elective", 0.30, [f"Unmapped prefix '{prefix}' — review"], "fallback"


def _resolve_secondaries(institution: str, code: str, is_common: bool, common_code, primary: str):
    secondaries = []
    if is_common and common_code in SECONDARY_TYPES_COMMON:
        secondaries.extend(SECONDARY_TYPES_COMMON[common_code])
    inst_secondaries = SECONDARY_TYPES_BY_INSTITUTION.get((institution, code), [])
    secondaries.extend(inst_secondaries)
    # Dedupe and drop primary
    seen = set()
    out = []
    for t in secondaries:
        if t != primary and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def classify(course):
    code = course["code"]
    institution = course.get("institution", "tcc")
    is_common = course.get("is_common_course", False)
    common_code = course.get("common_code")
    flags = []

    # Level check
    num_match = re.match(r"[A-Z]+&?(\d+)", code)
    level = int(num_match.group(1)) if num_match else 0
    is_sub_100 = level < 100
    if is_sub_100:
        flags.append("Sub-100 — Fresh Start (Open Doors) review")

    # HS credit conversion (5 quarter credits = 1.0 HS credit)
    ct = course.get("credits_total")
    hs_credits = None
    if ct is None:
        hs_credits = None
    elif isinstance(ct, dict):
        hs_credits = {
            "min": round(ct["min"] / 5, 2),
            "max": round(ct["max"] / 5, 2),
        }
    else:
        hs_credits = round(ct / 5, 2)

    # 5-tier primary credit-type resolution
    ctype, conf, rule_flags, rule = _resolve_primary(institution, code, is_common, common_code)
    flags.extend(rule_flags)

    # Science lab/non-lab refinement: check components for "Lab"
    if ctype.startswith("Science"):
        has_lab = any("Lab" in c.get("type", "") for c in course.get("components", []))
        ctype = "Science (Lab)" if has_lab else "Science (Non-Lab)"

    # Sub-100 World Language → not transferable as HS World Language unless review
    if is_sub_100 and ctype == "World Language":
        flags.append("Sub-100 World Language — verify HS credit eligibility")

    # Secondary credit types
    secondaries = _resolve_secondaries(institution, code, is_common, common_code, ctype)
    credit_types = [ctype, *secondaries]

    return {
        **course,
        "level": level,
        "is_sub_100": is_sub_100,
        "hs_credits": hs_credits,
        "credit_type": ctype,                 # deprecated alias
        "credit_types": credit_types,
        "primary_credit_type": ctype,
        "classification_rule": rule,
        "confidence": conf,
        "review_flags": flags,
    }


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else (src if src == SRC else src.with_name(src.stem + "-classified.json"))
    courses = json.loads(src.read_text())
    classified = [classify(c) for c in courses]
    out.write_text(json.dumps(classified, indent=2))
    print(f"Read {len(courses)} from {src}; wrote classified → {out}")

    # Summary
    from collections import Counter
    ct = Counter(c["credit_type"] for c in classified)
    print()
    print("Credit-type distribution:")
    for t in TYPES:
        n = ct.get(t, 0)
        print(f"  {n:>4}  {t}")
    other = {k: v for k, v in ct.items() if k not in TYPES}
    for k, v in other.items():
        print(f"  {v:>4}  {k}  (unexpected!)")

    sub_100 = sum(1 for c in classified if c["is_sub_100"])
    has_flags = sum(1 for c in classified if c["review_flags"])
    low_conf = sum(1 for c in classified if c["confidence"] < 0.70)
    print(f"\nSub-100 courses (Fresh Start review): {sub_100}")
    print(f"Courses with any review flag:         {has_flags}")
    print(f"Courses with confidence < 0.70:       {low_conf}")


if __name__ == "__main__":
    main()

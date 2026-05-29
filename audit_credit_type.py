"""Generate a Workflow script that audits one credit type against OSPI standards.

Reads ctc-courses-classified.json, filters courses currently classified as the
target credit type, and writes a self-contained Workflow JS with candidates
inlined. Print the script path so the caller can invoke Workflow with it.

Usage:
  python audit_credit_type.py "Health"
  python audit_credit_type.py "Fine & Performing Arts" --max 50
  python audit_credit_type.py "CTE" --min-confidence 0.0 --max-confidence 0.85

Run with --dry-run to see counts only (no script generated).
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "ctc-courses-classified.json"
OUT_DIR = Path("/tmp")  # workflow scripts are ephemeral

# Map credit type → OSPI standards reference URLs the standards-research agent
# should prioritize. (Agent does its own search but this seeds the prompt.)
OSPI_STANDARDS_HINTS = {
    "Health": "k12.wa.us/student-success/resources-subject-area/health-and-physical-education",
    "PE / Fitness": "k12.wa.us/student-success/resources-subject-area/health-and-physical-education",
    "ELA": "k12.wa.us/student-success/learning-standards-instructional-materials/english-language-arts",
    "Math": "k12.wa.us/student-success/learning-standards-instructional-materials/mathematics",
    "Science (Lab)": "k12.wa.us/student-success/learning-standards-instructional-materials/science",
    "Science (Non-Lab)": "k12.wa.us/student-success/learning-standards-instructional-materials/science",
    "Social Studies - US History": "k12.wa.us/student-success/learning-standards-instructional-materials/social-studies",
    "Social Studies - World History": "k12.wa.us/student-success/learning-standards-instructional-materials/social-studies",
    "Social Studies - Washington State History": "k12.wa.us/student-success/learning-standards-instructional-materials/social-studies",
    "Social Studies - Civics": "k12.wa.us/student-success/learning-standards-instructional-materials/social-studies",
    "Social Studies - Elective": "k12.wa.us/student-success/learning-standards-instructional-materials/social-studies",
    "Fine & Performing Arts": "k12.wa.us/student-success/learning-standards-instructional-materials/arts",
    "World Language": "k12.wa.us/student-success/learning-standards-instructional-materials/world-languages",
    "CTE": "k12.wa.us/student-success/career-technical-education",
    "Elective": None,
}

# Per-type framing — what kind of misalignment to look for.
TYPE_FRAMING = {
    "Health": "Topics that SOUND like Health but do NOT align with K-12 Health (typically college/professional-level: epidemiology, biostatistics, public health policy, healthcare administration, healthcare informatics, medical billing/coding, healthcare law, environmental health policy, professional clinical training).",
    "PE / Fitness": "Topics that sound like PE but don't align with K-12 PE standards (e.g. exercise physiology at college-science level, sports management, recreation administration, athletic training as a clinical pre-professional course).",
    "ELA": "Topics that sound like ELA but don't align with K-12 ELA standards (e.g. linguistics as a science, technical writing for professional/CTE pathways, journalism as a workforce program).",
    "Math": "Topics that sound like Math but don't fit HS Math credit (e.g. business math at a workforce level vs. algebra/geometry/statistics core; software engineering math).",
    "Science (Lab)": "Topics that sound like lab science but might be misaligned (e.g. medical lab tech CTE programs, allied-health prerequisite anatomy taught for clinical track only).",
    "Science (Non-Lab)": "Topics that sound like science but might be social science or CTE coursework (e.g. forensic science as criminal justice; nutrition as personal health rather than biochemistry).",
    "Social Studies - US History": "Topics labelled as history but that primarily teach historiography methods, public history careers, or genealogy — these belong in Social Studies Elective or CTE.",
    "Social Studies - World History": "Distinguish global studies from world civilizations (the former is current-events/policy oriented; the latter is the actual HS World History strand).",
    "Social Studies - Washington State History": "Verify the course actually centers WA State / Pacific Northwest, not just touches on it.",
    "Social Studies - Civics": "Distinguish American Government / political institutions (the K-12 Civics strand) from political theory or international relations (Social Studies Elective).",
    "Social Studies - Elective": "Courses bucketed here that may actually fit a more specific Social Studies subtype.",
    "Fine & Performing Arts": "Courses labelled arts that are actually arts management, theatre tech (CTE), or arts therapy (Health/Allied Health).",
    "World Language": "Courses listed as language but actually computer programming, linguistics-as-science, or international studies.",
    "CTE": "Courses bucketed as CTE that don't actually align with WA OSPI CTE Frameworks / industry standards.",
}


WORKFLOW_TEMPLATE = """\
export const meta = {
  name: NAME_PLACEHOLDER,
  description: DESC_PLACEHOLDER,
  phases: [
    { title: 'Standards research' },
    { title: 'Per-course verdicts' },
    { title: 'Synthesize' },
  ],
}

const TARGET = TARGET_PLACEHOLDER
const CANDIDATES = CANDIDATES_PLACEHOLDER

phase('Standards research')
const STANDARDS_SCHEMA = {
  type: 'object',
  required: ['summary', 'key_strands', 'misfit_topics', 'source_urls'],
  properties: {
    summary: { type: 'string', description: '3-5 sentence overview of what HS courses in this credit type cover per OSPI standards' },
    key_strands: { type: 'array', items: { type: 'string' } },
    misfit_topics: { type: 'array', items: { type: 'string' } },
    source_urls: { type: 'array', items: { type: 'string' } },
  },
}

const standards = await agent(
  `You are auditing Washington community college courses currently classified as fulfilling the high-school "${TARGET}" credit per WA SBE's 24-credit framework.

Research the WA OSPI K-12 Learning Standards for this credit type. Use WebSearch and WebFetch. Authoritative source: ${STANDARDS_HINT_PLACEHOLDER || 'k12.wa.us/student-success/learning-standards-instructional-materials'}

Return a structured summary:
1. What HS courses MUST cover per OSPI (content strands)
2. FRAMING_PLACEHOLDER

Cite source URLs you actually verify.`,
  { schema: STANDARDS_SCHEMA, phase: 'Standards research' }
)

log(`Standards loaded: ${standards.key_strands.length} strands, ${standards.misfit_topics.length} misfit categories`)

phase('Per-course verdicts')
const ALL_TYPES = ['ELA','Math','Science (Lab)','Science (Non-Lab)','Social Studies - US History','Social Studies - World History','Social Studies - Washington State History','Social Studies - Civics','Social Studies - Elective','Fine & Performing Arts','World Language','Health','PE / Fitness','CTE','Elective']
const VERDICT_SCHEMA = {
  type: 'object',
  required: ['institution', 'code', 'verdict', 'recommended_types', 'reasoning', 'confidence'],
  properties: {
    institution: { type: 'string' },
    code: { type: 'string' },
    verdict: { type: 'string', enum: ['keep_target', 'remove_target', 'add_other'], description: `keep_target = aligns with ${TARGET} standards; remove_target = misclassified, use recommended_types instead; add_other = stays ${TARGET} but also satisfies another credit type` },
    recommended_types: { type: 'array', items: { type: 'string', enum: ALL_TYPES } },
    reasoning: { type: 'string' },
    confidence: { type: 'number', minimum: 0, maximum: 1 },
  },
}

const strandsList = standards.key_strands.map(s => `  - ${s}`).join('\\n')
const misfitsList = standards.misfit_topics.map(s => `  - ${s}`).join('\\n')

const verdicts = await parallel(CANDIDATES.map(c => () =>
  agent(
    `Audit one course's "${TARGET}" credit classification.

CONTEXT — OSPI K-12 ${TARGET} standards:
${standards.summary}

Key content strands HS ${TARGET} courses must address:
${strandsList}

Topics that SOUND like ${TARGET} but are NOT aligned with K-12 standards:
${misfitsList}

COURSE:
- Institution: ${c.institution}
- Code: ${c.code}
- Title: ${c.title}
- Currently classified as: ${TARGET}${c.secondaries.length ? ' + ' + c.secondaries.join(' + ') : ''}
- Description: ${c.description || '(none)'}

RULES:
- "keep_target" — Course aligns with the K-12 ${TARGET} strands directly.
- "remove_target" — Course is misclassified. Recommend the right type(s).
- "add_other" — Course meets ${TARGET} AND another type; recommend the union.

recommended_types is the FULL replacement list. Be conservative: when truly marginal, lean keep_target.`,
    { schema: VERDICT_SCHEMA, phase: 'Per-course verdicts', label: `verdict:${c.code}` }
  )
))

phase('Synthesize')
const valid = verdicts.filter(Boolean)
const removed = valid.filter(v => v.verdict === 'remove_target')
const added = valid.filter(v => v.verdict === 'add_other')
const kept = valid.filter(v => v.verdict === 'keep_target')

let md = `# ${TARGET} classification audit vs OSPI K-12 standards\\n\\n`
md += `_${valid.length} of ${CANDIDATES.length} courses audited._\\n\\n`
md += `## Summary\\n\\n- **Keep ${TARGET}:** ${kept.length}\\n- **Remove ${TARGET}:** ${removed.length}\\n- **Add other credit type:** ${added.length}\\n\\n`
md += `## Standards reference\\n\\n${standards.summary}\\n\\n### Key strands\\n${strandsList}\\n\\n### Misfit topics\\n${misfitsList}\\n\\n_Sources:_ ${standards.source_urls.map(u => `[${u}](${u})`).join(' · ')}\\n\\n`

const lookup = (v) => CANDIDATES.find(x => x.code === v.code && x.institution === v.institution) || {title: ''}
if (removed.length) {
  md += `## Recommended REMOVE ${TARGET}\\n\\n| Institution | Code | Title | New types | Reasoning |\\n|---|---|---|---|---|\\n`
  for (const v of removed) {
    md += `| ${v.institution} | ${v.code} | ${lookup(v).title} | ${v.recommended_types.join(' + ')} | ${v.reasoning} |\\n`
  }
  md += '\\n'
}
if (added.length) {
  md += `## Recommended ADD other credit type\\n\\n| Institution | Code | Title | New types | Reasoning |\\n|---|---|---|---|---|\\n`
  for (const v of added) {
    md += `| ${v.institution} | ${v.code} | ${lookup(v).title} | ${v.recommended_types.join(' + ')} | ${v.reasoning} |\\n`
  }
  md += '\\n'
}
return { report_md: md, standards, verdicts: valid }
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("credit_type", help='e.g. "Health" or "Fine & Performing Arts"')
    ap.add_argument("--max", type=int, default=0, help="Cap candidates (0 = no cap)")
    ap.add_argument("--min-confidence", type=float, default=0.0)
    ap.add_argument("--max-confidence", type=float, default=1.0)
    ap.add_argument("--include-institutions", nargs="*", help="Only include these institutions")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    target = args.credit_type
    data = json.loads(DATA.read_text())
    candidates = [
        c for c in data
        if target in c["credit_types"]
        and args.min_confidence <= c["confidence"] <= args.max_confidence
        and (not args.include_institutions or c["institution"] in args.include_institutions)
    ]
    if args.max:
        candidates = candidates[: args.max]
    print(f"Target: {target!r}")
    print(f"Candidates: {len(candidates)}")
    from collections import Counter
    by_inst = Counter(c["institution"] for c in candidates)
    for i, n in sorted(by_inst.items()):
        print(f"  {i}: {n}")

    if args.dry_run:
        return

    # Compact candidates. Workflow scripts have a 512KB cap, so trim
    # descriptions and drop fields the prompt doesn't need. current_types is
    # implicit (it always contains TARGET) — surface secondary types only.
    DESC_TRIM = 600
    compact = []
    for c in candidates:
        secondaries = [t for t in c["credit_types"] if t != target]
        compact.append({
            "institution": c["institution"],
            "code": c["code"],
            "title": c["title"],
            "description": (c.get("description") or "")[:DESC_TRIM],
            "secondaries": secondaries,
        })

    slug = target.lower().replace(" ", "-").replace("&", "and").replace("/", "-")
    name_literal = json.dumps(f"audit-{slug}")
    desc_literal = json.dumps(f"Audit '{target}' classifications against WA OSPI K-12 standards.")
    target_literal = json.dumps(target)
    candidates_literal = json.dumps(compact)
    standards_hint = OSPI_STANDARDS_HINTS.get(target, "")
    hint_literal = json.dumps(standards_hint or "")
    framing = TYPE_FRAMING.get(target, "Topics that SOUND like this credit type but do not align with the K-12 standards.")
    # framing is plain text placed directly into a backtick string. Backtick
    # special chars (`, $, \) need escaping if present.
    framing_literal = framing.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    js = (
        WORKFLOW_TEMPLATE
        .replace("NAME_PLACEHOLDER", name_literal)
        .replace("DESC_PLACEHOLDER", desc_literal)
        .replace("TARGET_PLACEHOLDER", target_literal)
        .replace("CANDIDATES_PLACEHOLDER", candidates_literal)
        .replace("STANDARDS_HINT_PLACEHOLDER", hint_literal)
        .replace("FRAMING_PLACEHOLDER", framing_literal)
    )

    out_path = OUT_DIR / f"audit-{slug}.js"
    out_path.write_text(js)
    print()
    print(f"Wrote workflow → {out_path}")
    print()
    print("To run:")
    print(f"  Workflow({{scriptPath: '{out_path}'}})")
    print()
    print("After completion, save verdicts to a JSON file and apply:")
    print(f"  python apply_audit_decisions.py audit-{slug}.json")


if __name__ == "__main__":
    main()

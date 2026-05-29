# CTC ↔ PSD Course Equivalency

Maps courses from 6 Washington community & technical colleges to PSD high school credit types per the [WA State Board of Education](https://sbe.wa.gov/our-work/graduation-requirements) 24-credit framework.

**Live:** https://psd401.github.io/ctc-psd-equivalency/

## Audiences

- **Counselors, CTC staff, students & families** — read-only public view: course → HS credit value + type
- **District deciders** (Chief Academic Officer · Director of Secondary Teaching & Learning · Director of CTE · Director of Research & Assessment) — edit-enabled view; decisions persist to a Google Sheet via Apps Script

## Two outputs from one data source

| File | Audience | Edits |
|---|---|---|
| `ctc-psd-equivalency.html` + `equivalency-data.json` | Public | No |
| `ctc-psd-decisions.html` | Deciders (URL-gated) | Yes — saves to Sheet via Apps Script |

## Institutions covered

| College | Catalog platform | Course count (2025-2026) |
|---|---|---|
| Tacoma Community College | Coursedog | 828 |
| Olympic College | Acalog | 1,246 |
| Pierce College | Acalog | 947 |
| Green River College | Acalog | 1,378 |
| Clover Park Technical College | SmartCatalog | 1,116 |
| Bates Technical College | Drupal | 1,285 |
| **Total** | | **6,800** |

## Quick start

```bash
# Rebuild HTML + sidecar from existing classified dataset
python build_html.py

# Refresh one institution's catalog
python build_dataset.py olympic

# Refresh all enabled institutions
python build_dataset.py

# Re-classify the merged dataset in place (after editing classify_courses.py)
python classify_courses.py

# Re-merge per-institution files into the unified dataset
python merge_catalogs.py

# Year-over-year diff after annual catalog update
python diff_catalogs.py --year-from 2025-2026 --year-to 2026-2027 -o diff.md
```

See [PIPELINE.md](./PIPELINE.md) for the full architecture and operational guide.

## OSPI-standards audit workflow

For each credit type, an LLM workflow compares course descriptions against the relevant WA OSPI K-12 Learning Standards and flags misclassifications. Roughly $0.05/course in API costs.

```bash
# Generate workflow script for one credit type
python audit_credit_type.py "Health"                    # all candidates
python audit_credit_type.py "CTE" --max-confidence 0.85 # focus on uncertain
python audit_credit_type.py "Math" --include-institutions tcc olympic

# Workflow runs externally (1 standards agent + N verdict agents in parallel)
# Then capture the result JSON and apply:
python apply_audit_decisions.py audit-health.json --dry-run
python apply_audit_decisions.py audit-health.json
```

Decisions posted by the audit are flagged `decided_by = "Director of Research & Assessment (AI-assisted audit)"` so they're distinguishable from human-made decisions. The Sheet is append-only, so any human override of an audit decision is preserved as a new row.

Completed audits: see `audit-health-vs-ospi.md` and `audit-cte-vs-ospi.md`.

## Decisions backend setup

See [decisions_setup/SETUP.md](./decisions_setup/SETUP.md). The backing Google Sheet uses an append-only v2 schema:

```
decision_id | course_code | institution | applies_to | status |
override_credit_types | override_hs_credits | rationale | decided_by |
decided_date | source_citation | decided_for_year |
is_current | superseded_by | created_at | last_updated
```

WA Common Course Numbers (`&`-prefixed) default to `applies_to=all`, so a decision about `HIST&146` at TCC automatically applies at every college offering it.

## Deploy

```bash
./deploy.sh           # stages docs/ for GitHub Pages
git add docs/ && git commit -m "Deploy" && git push
```

## License

Internal Peninsula School District tool. Not for redistribution.

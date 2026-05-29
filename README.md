# CTC ↔ PSD Course Equivalency

Maps courses from 6 Washington community & technical colleges to PSD high school credit types per the [WA State Board of Education](https://sbe.wa.gov/our-work/graduation-requirements) 24-credit framework.

## Audiences

- **Counselors, TCC staff, students & families** — read-only public view: course → HS credit value + type
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
| Olympic College | Acalog | 1246 |
| Pierce College | Acalog | (retry pending) |
| Green River College | Acalog | (retry pending) |
| Clover Park Technical College | SmartCatalog | 1116 |
| Bates Technical College | Drupal | 1285 |

## Quick start

```bash
# Rebuild from existing per-institution data
python build_html.py

# Refresh one institution
python build_dataset.py olympic

# Refresh all enabled institutions
python build_dataset.py

# Year-over-year diff after annual catalog update
python diff_catalogs.py --year-from 2025-2026 --year-to 2026-2027 -o diff.md
```

See [PIPELINE.md](./PIPELINE.md) for the full architecture and operational guide.

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

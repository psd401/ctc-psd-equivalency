# Pipeline overview

## Architecture

```
catalogs/         ← per-institution intermediate JSON
archives/         ← per-year, per-institution snapshots for diff_catalogs.py
parsers/          ← per-platform catalog parsers
decisions_setup/  ← Apps Script (Code.gs) + sheet migration recipe
docs/             ← what GitHub Pages serves

parsers/__init__.py        ← PARSERS registry
parsers/base.py            ← CourseRecord, normalize_code, parse_credit_string
parsers/tcc.py             ← Coursedog PDF→text→state-machine
parsers/acalog.py          ← Olympic, Pierce, Green River
parsers/smartcatalog.py    ← Clover Park
parsers/drupal.py          ← Bates

build_dataset.py           ← Orchestrator (calls merge_catalogs at the end)
merge_catalogs.py          ← Combine per-institution → ctc-courses-classified.json
classify_courses.py        ← 5-tier credit-type resolution
build_html.py              ← Emits both HTML outputs + equivalency-data.json sidecar
diff_catalogs.py           ← Year-over-year diff report
audit_credit_type.py       ← Generate OSPI-standards audit workflow for one credit type
apply_audit_decisions.py   ← POST workflow verdicts to the Sheet as decisions
deploy.sh                  ← Stage docs/ for GitHub Pages
```

## Daily build (from a clean checkout)

```bash
# 1. Refresh per-institution data (network-bound; ~40 min total)
python build_dataset.py              # all enabled institutions
# OR a subset:
python build_dataset.py tcc olympic

# 2. Rebuild HTML
python build_html.py
```

Outputs:
- `catalogs/<inst>-courses.json` — raw, per institution
- `catalogs/<inst>-courses-classified.json` — classified, per institution
- `ctc-courses-classified.json` — merged, drop-in input for build_html.py
- `archives/<year>/<inst>.json` — snapshot used by diff_catalogs.py
- `ctc-psd-decisions.html` — decider tool (single-file, ~1 MB inline)
- `ctc-psd-equivalency.html` + `equivalency-data.json` — public tool (~30 KB shell + ~1 MB sidecar)

## Adding a new institution

1. **Identify the catalog platform.** Server header is usually the giveaway:
   - `Server: director` → Acalog (use `parsers/acalog.py`)
   - SmartCatalog → URL is *.smartcatalogiq.com (use `parsers/smartcatalog.py`)
   - Drupal → custom; may need a new parser (see `parsers/drupal.py` for Bates pattern)

2. **Add the institution to `INSTITUTIONS`** in `build_dataset.py` with the right `parser` and `config`. Acalog needs `catoid` + `course_navoid` (find these by opening the catalog homepage and following the "Course Descriptions" link).

3. **Add the institution to `INSTITUTIONS`** in `build_html.py` — same id, plus display label.

4. **Update `parsers/__init__.py`** registry if it's a new platform.

5. **Add per-institution classifier overrides** in `classify_courses.py` (`PREFIX_DIRECT_BY_INSTITUTION`, `SPECIFIC_OVERRIDES`) only when concrete conflicts emerge — don't pre-empt.

## GitHub Pages deploy

Once you have a public repo set up:

1. **Enable Pages** — repo Settings → Pages → Source: Deploy from a branch → Branch: `main` / `/docs` → Save.
2. **Stage files** — run `./deploy.sh`. It rebuilds and copies into `docs/`:
   - `docs/index.html` (public tool, default landing)
   - `docs/equivalency-data.json` (sidecar)
   - `docs/decisions-x7q3.html` (decider tool, unguessable filename)
   - `docs/.nojekyll` (so Jekyll doesn't munge the HTML)
3. **Commit + push**:
   ```bash
   git add docs/
   git commit -m "Deploy YYYY-MM-DD"
   git push
   ```
4. **GitHub Pages builds** in ~30 seconds. URLs:
   - Public: https://psd401.github.io/ctc-psd-equivalency/
   - Decider: https://psd401.github.io/ctc-psd-equivalency/decisions-x7q3.html

GitHub Pages enables gzip automatically, so the multi-MB sidecar JSON compresses to ~700 KB over the wire.

## OSPI-standards audit workflow

For any credit type, an LLM-driven audit checks each course's description against the WA OSPI K-12 Learning Standards for that type and recommends keep / remove / add-other verdicts.

```bash
# 1. Generate a workflow script for a credit type
python audit_credit_type.py "Health"
python audit_credit_type.py "CTE" --max-confidence 0.85
python audit_credit_type.py "Math" --include-institutions tcc olympic

# 2. Run the workflow externally (returns a JSON result with a `verdicts` array)
#    Save that result to e.g. audit-health.json

# 3. Apply (dry-run first)
python apply_audit_decisions.py audit-health.json --dry-run
python apply_audit_decisions.py audit-health.json
```

Behavior:
- For Common Course Numbers (`&`-prefixed), `apply_audit_decisions.py` collapses verdicts to `applies_to=all` when every institution offering the code got the same recommendation; otherwise it writes per-institution decisions.
- `keep_*` verdicts are skipped by default (no action needed). Pass `--include-keep` to write them as positive confirmations.
- Cost guidance: roughly $0.05/course. The Health audit (37 courses) was ~$4; the CTE audit (877 courses) was ~$50.

Audits completed: `audit-health-vs-ospi.md`, `audit-cte-vs-ospi.md`.

When two audits disagree on a course, apply the more specific/well-reasoned one and skip the conflict from the other (the Sheet's append-only history shows both verdicts for review).

## Catalog ingest caveats

- Some institutions (notably Pierce) rate-limit aggressive scraping. If a parser reports 0 records after enumerating coids successfully, the institution has likely IP-blocked you. Wait ~1 hour and retry, or run from a different network.
- Default request delay is 100 ms per detail page. To be gentler, raise `request_delay` in the institution config (e.g. 0.30 = 300 ms).
- Ingests can run in parallel: each writes only to its own `catalogs/<inst>-*.json` (and per-archive snapshot). After parallel runs, run `python merge_catalogs.py` to combine — `build_dataset.py` calls this automatically at the end of each run.

## Annual catalog refresh

1. Run `python build_dataset.py` to ingest the new catalog(s).
2. The orchestrator stamps each record with `catalog_year` and `uploaded_at`, and archives a snapshot under `archives/<year>/<inst>.json`.
3. Run a diff against last year:
   ```bash
   python diff_catalogs.py --year-from 2025-2026 --year-to 2026-2027 -o diff-2026-2027.md
   ```
4. Review the markdown report. Decisions that need re-confirmation are typically in the "Credit-type changed" + "Confidence dropped" sections.
5. Rebuild HTML with `python build_html.py`.

## Decisions Sheet schema (v2)

See `decisions_setup/SETUP.md` for the deploy + migration recipe.

```
decision_id | course_code | institution | applies_to | status |
override_credit_types | override_hs_credits | rationale | decided_by |
decided_date | source_citation | decided_for_year |
is_current | superseded_by | created_at | last_updated
```

`applies_to` and `override_credit_types` are pipe-delimited strings.
- `applies_to="all"` means the decision applies at every college (typical for WA Common Course Numbers, e.g. `HIST&146`)
- `applies_to="tcc"` (or any single inst id) means the decision is scoped to that college only
- `applies_to="tcc|olympic"` allows arbitrary subsets

The append-only model: every save adds a new row. The prior current row is marked `is_current=FALSE` and gets `superseded_by=<new_id>`. To see the audit trail for one course, `GET /exec?action=history&course_code=X&institution=Y`.

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

> **Local viewing:** the public tool `fetch()`es its sidecar, which the browser blocks under `file://`. Run `./serve.sh` and open `http://localhost:8000/ctc-psd-equivalency.html` instead of double-clicking. The decider tool embeds data inline and opens fine from `file://`.

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
   - `docs/.nojekyll` (so Jekyll doesn't munge the HTML)

   The decider tool is **not** deployed (since 2026-06-12): the repo is
   public, so an "unguessable" docs/ filename was browsable on GitHub. Run it
   locally instead: `./serve.sh` → http://localhost:8000/ctc-psd-decisions.html
   (it prompts once for the decisions API key — see `decisions_setup/SETUP.md`).
3. **Commit + push**:
   ```bash
   git add docs/
   git commit -m "Deploy YYYY-MM-DD"
   git push
   ```
4. **GitHub Pages builds** in ~30 seconds. URL:
   - Public: https://psd401.github.io/ctc-psd-equivalency/

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

Audits completed — all initial audits are done: `audit-health-vs-ospi.md`, `audit-cte-vs-ospi.md`, and the full Elective reclassification (2026-06-11: all 1,418 remaining Elective-only courses reviewed against the WA SBE 24-credit framework and career clusters; 862 decisions applied). The elective audit artifacts (`audit-electives-2026-06-11.md`/`.json`) are deliberately kept local-only, not committed: they contain per-course decision reasoning, and the district's stance is that decision rationale is not published (see the public-view marker removal in `build_html.py`). Sheet decisions cite the artifact filename in `source_citation`.

When two audits disagree on a course, apply the more specific/well-reasoned one and skip the conflict from the other (the Sheet's append-only history shows both verdicts for review).

## Credit values: published vs derived

`hs_credits` is `credits_total / 5` (5 quarter credits = 1.0 HS credit). Everything
downstream depends on `credits_total`, so how each college publishes it matters.

| College | How credits are obtained |
| --- | --- |
| Bates | `field-credits` on the detail page |
| Clover Park | `<div class="credits">` on the detail page |
| Green River | plain-text `Credits: N` in the page body (see below) |
| Olympic | `<strong>Credits:</strong><strong>N</strong>` |
| TCC | the catalog's CSV export (`Total Credits`); the JSON API returns null for ~86% of courses |
| **Pierce** | **DERIVED from contact hours — the college publishes no credit figure at all** |

Two traps here, both of which silently emptied a column for months:

- **Green River** renders the same field as plain text rather than the `<strong>`
  pair Olympic and Pierce use. `CREDITS_RE` missed it, so all 1378 of its courses
  stored `credits_total: None` and the tool showed no HS credit for the college.
  `CREDITS_TEXT_RE` is the fallback. (Fixed 2026-09-02.)
- **Pierce** has no credits field anywhere — not in the markup, not in its catalog
  UI. It publishes a contact-hour table instead.

### The Pierce derivation

`base.derive_credits_from_contact_hours()` converts Pierce's published contact
hours using the standard WA quarter-credit ratios — one credit per:

    10 lecture hours   |   20 lab hours   |   30 clinical hours

So a course printing `Lecture Contact Hours 50, Lab 0, Clinical 0` derives 5.0
credits; `Lecture 40, Lab 40` derives 6.0; `Lecture 5, Clinical 45` derives 2.0.
945 of Pierce's 947 courses carry such a table (`EMS150` and `SSBH125` do not, and
keep no credit value).

**How it was validated.** 164 Pierce Common Course Numbers are also offered by
colleges that DO publish credits. Every one of the 164 derives a value that at
least one peer college assigns to that same course.

Note the shape of that claim. Peers disagree *with each other* on lab sciences —
`BIOL&241` is 5.0 at Bates, Clover Park, Green River and TCC but 6.0 at Olympic;
`PHYS&221` is 5.0 at Bates and Green River, 6.0 at Clover Park and TCC. There is
no single correct figure to check against, only a range, and the derivation stays
inside it in all 164 cases. An earlier check that scored against the *modal* peer
value reported 93% and looked like 11 formula failures; 6 of those were peer
disagreement rather than error, and 2 were a genuine bug (clinical hours ignored).

**It is still derived, not published.** Every such record carries
`base.CREDITS_DERIVED_FLAG` in `review_flags`, the public viewer renders a
`derived` badge beside the credit figure with the formula in its tooltip, and
`validate_dataset.validate_derived_credits` fails the build if a flagged record
has no value. Pierce's registrar remains the authority: confirm before a derived
figure counts toward a graduation requirement.

Pierce is additionally pinned to `catoid=17`, which is Acalog's **2023-2024**
catalog, so its contact hours are three years old regardless. Moving to
`catoid=21` is blocked while Acalog serves a WAF challenge.

## Catalog ingest caveats

- **Acalog (Olympic, Green River, Pierce) serves an AWS WAF JavaScript challenge on
  `content.php` as of 2026-09-02.** `_fetch` raises `ChallengeError` rather than
  reading the empty 202 body as an empty catalog. Their `robots.txt` permits the
  paths we read but asks for `crawl-delay: 120`; we ran at 0.50 for months, which
  is the likely trigger. `request_delay` now defaults to 120s for those three
  (override with `ACALOG_DELAY`). `run_acalog_overnight.sh` re-scrapes at that
  rate. The durable fix is a supported export from the colleges, not a slower loop.
- Some institutions rate-limit aggressive scraping. A parser reporting 0 records
  after a successful enumeration is a block, not an empty catalog — `build_dataset`
  refuses to overwrite a catalog file when a scrape returns under
  `COLLAPSE_THRESHOLD` (50%) of what is on disk, and exits non-zero.
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

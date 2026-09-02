# ctc-catalog — Claude project notes

CTC↔PSD course-equivalency pipeline (Python). Scrapes 6 WA community/technical college catalogs (~6,800 courses), classifies each to PSD high-school credit types per the WA SBE 24-credit framework, and emits two single-file HTML tools. Live on GitHub Pages. (Renamed from `tcc-catalog`; stale `tcc-` paths may appear in old transcripts.)

## Environment
- **Activate the venv before ANY Python command:** `source .venv/bin/activate` (venv lives at `ctc-catalog/.venv`). Deps managed with uv.

## Running locally
- The public viewer (`ctc-psd-equivalency.html`) `fetch()`es `equivalency-data.json`, which is BLOCKED under `file://`. Serve it: `./serve.sh` (localhost:8000) — do not double-click the file.
- The decider tool (`ctc-psd-decisions.html`) embeds its data inline and opens fine from `file://`. It prompts once for the decisions API key (stored in localStorage).

## Decisions API (Apps Script, Sheet-backed)
- `list`/`history` are publicly reachable but REDACTED (no rationale/decided_by/source_citation) without `?k=<key>`; POST requires the key. Key lives in the script's `API_KEY` Script Property — never in this public repo. Python posters read `CTC_DECISIONS_KEY` from the env.
- Decision posts: attribute AI-applied changes to decided_by "AI Classifier"; always fresh-fetch `?action=list` first and skip already-decided (code, institution) pairs — existing decisions are deliberate.

## Deploy
- `./deploy.sh`, then commit/push the `docs/` dir. Repo: github.com/psd401/ctc-psd-equivalency (branch `main`). PUBLIC repo — never commit keys or per-course decision reasoning (audit artifacts stay local; see PIPELINE.md). The decider tool is NOT deployed (local-only since 2026-06-12).

## Credit values
- `hs_credits` = `credits_total / 5`. Pierce publishes NO credit figure — its credits are derived from contact hours (`lecture/10 + lab/20 + clinical/30`) and every such record carries `base.CREDITS_DERIVED_FLAG` plus a `derived` badge in the viewer. Never strip that flag.
- Acalog (Olympic/Green River/Pierce) serves an AWS WAF challenge on `content.php` since 2026-09-02; their `robots.txt` asks `crawl-delay: 120`. `ACALOG_DELAY` controls the rate; `run_acalog_overnight.sh` does a full pass.
- Run `python validate_dataset.py` before publishing — `deploy.sh` does it automatically and aborts on error.

## Pipeline (detail in PIPELINE.md / README.md)
- `build_dataset.py` (scrape) → `merge_catalogs.py` → `classify_courses.py` (5-tier) → `build_html.py` (both outputs).
- LLM audit: `audit_credit_type.py` / `apply_audit_decisions.py` (OSPI-standards check, ~$0.05/course).
- Platform parsers under `parsers/` (Coursedog / Acalog / SmartCatalog / Drupal).

## Workflow
- James does manual review, then hands back classification overrides via files (e.g. `prefix-decisions.txt`). Apply those as authoritative.
- Discuss/confirm before building; he approves in #.# numbered points.

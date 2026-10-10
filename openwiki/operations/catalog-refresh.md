---
type: Runbook
title: Catalog refresh, scraping safety and year-over-year diffs
description: Operational guide for re-scraping college catalogs - collapse guard, Acalog WAF challenge and crawl-delay policy, overnight runner, retaining unpublished courses, annual refresh and diff reports, adding a new institution.
tags: [operations, scraping, acalog, waf, refresh, diff]
openwiki:
  roles: [operations, workflow]
  change_kinds: [ingest, institution-config, scrape-safety]
  source_paths: [build_dataset.py, run_acalog_overnight.sh, retain_unpublished.py, diff_catalogs.py, parsers/acalog.py, parsers/base.py]
  symbols: [INSTITUTIONS, COLLAPSE_THRESHOLD, run_one, ChallengeError, report_parse_coverage, URL_BUILDERS, compute]
  invariants:
    - "A scrape returning under COLLAPSE_THRESHOLD of the on-disk record count never overwrites the catalog file."
    - "build_dataset.py exits non-zero if any selected institution failed."
    - "Acalog request_delay defaults to 120s (robots.txt crawl-delay); do not lower it on a hunch."
  validation_commands: ["python build_dataset.py <inst>", "python validate_dataset.py"]
---

# Catalog refresh and scraping safety

Consult this page before re-running any scrape, adding a college, or interpreting a suspiciously small result. Pipeline context: [pipeline overview](../architecture/pipeline-overview.md); per-platform parsing: [catalog parsers](../integrations/catalog-parsers.md).

## Routine commands

```bash
python build_dataset.py            # all enabled colleges (about 40 min, network-bound at default delays)
python build_dataset.py olympic    # one college (or several ids)
python build_html.py               # rebuild outputs from ctc-courses-classified.json
```

`build_dataset.main` runs `run_one` per college, then always runs `merge_catalogs.py` and `classify_courses.py` over the merged result (so rule changes reach colleges not re-scraped), and finally exits 1 if any college failed, leaving its existing files untouched. Separate runs may proceed in parallel since each writes only its own `catalogs/<inst>-*.json`; follow with `python merge_catalogs.py`.

## Safeguards against silent absence

The project's worst defects were quiet shrinkages. The layers, in order:

1. **Parser coverage report** (`base.report_parse_coverage`): prints `N/M pages parsed`, loudly flags unparsed pages and a zero enumeration ("almost certainly a blocked crawl").
2. **Collapse guard** (`COLLAPSE_THRESHOLD`, env override, default 0.5): `run_one` raises if the new record count is under 50% of what is on disk. `FORCE_SCRAPE=1` sets the threshold to 0 when a drop is real (Bates legitimately went 1285 to 1167, 91%, which is why the threshold is not tighter).
3. **Challenge detection** (`acalog.ChallengeError`): HTTP status other than 200 or an empty body is never treated as an empty catalog; listing pages retry with growing waits and then abort rather than return a partial list.
4. **Dataset validation** before publishing: [validation and deploy](validation-and-deploy.md).

## Acalog (Olympic, Green River, Pierce) WAF challenge

Since 2026-09-02 `content.php` answers with an AWS WAF challenge. Their `robots.txt` permits the paths read but asks `crawl-delay: 120`; the earlier 0.5s rate was likely the trigger. `INSTITUTIONS[...]["request_delay"]` now defaults to `float(os.environ.get("ACALOG_DELAY", "120"))` for those three. A full pass is roughly 41h (Olympic), 46h (Green River), 32h (Pierce). `run_acalog_overnight.sh` runs the three colleges serially, each retried up to `ACALOG_RETRIES` (8) with `ACALOG_RETRY_GAP` (3600s) between attempts, logging to `logs/acalog-<timestamp>.log`; it is safe to interrupt. Run it detached with `nohup`. A smoke test showed challenges even at 45s and 90s waits, so this is a standing rule, not a transient rate trip. The durable fix is a supported export from the colleges. Until then Pierce stays on `catoid=17` (2023-2024); see [credit values](../domain/credit-values.md).

Other delays: TCC 0.30s, Clover Park and Bates 0.50s.

## Retaining unpublished courses

A re-scrape treats the live index as truth, so unpublished courses vanish. `retain_unpublished.py <inst> --previous <old raw scrape> [--dry-run]` diffs against a prior scrape and probes each dropped course URL: 403 (node exists, not public) and 200 (public but missing from the index) keep the old record with a `review_flags` entry (`FLAG_UNPUBLISHED` / `FLAG_UNLISTED`); 404 drops it; anything else is reported unresolved and not retained. Only Bates has a `URL_BUILDERS` entry. Re-run classify and merge afterwards.

## Annual refresh

1. Update catalog ids/years in `INSTITUTIONS` (TCC's Coursedog `catalog_id` changes each year, and its `effective_date` must match the new edition; instructions are in the inline comment). Bates' `catalog_year` is intentionally `scraped <date>` because the site is unversioned.
2. `python build_dataset.py` stamps `catalog_year` and `uploaded_at` and writes `archives/<year>/<inst>.json`.
3. `python diff_catalogs.py --year-from 2025-2026 --year-to 2026-2027 -o diff.md` (or two explicit files). Sections: Added, Removed, Credit-type changed, HS-credit changed, Title changed, Confidence dropped (> 0.10). Review "Credit-type changed" and "Confidence dropped" for decisions needing reconfirmation. The tool writes temporary `.diff_old_*.json` / `.diff_new_*.json` files at the repo root.
4. `python build_html.py`, then validate and deploy.

## Adding a new institution

1. Identify the platform ([catalog parsers](../integrations/catalog-parsers.md)); add a parser only for a genuinely new platform and register it in `parsers/__init__.py` `PARSERS`.
2. Add an `INSTITUTIONS` entry in `build_dataset.py` (`enabled`, `parser`, `config`).
3. Add `{id, label}` to `INSTITUTIONS` in `build_html.py` ([viewer](../architecture/viewer-and-decisions.md)).
4. Add the id and a count floor to `EXPECTED_INSTITUTIONS` in `validate_dataset.py`.
5. Add classifier overrides only when concrete conflicts emerge ([classification](../domain/classification.md)).

Omitting step 3 or 4 does not crash the build but hides the college's filter or leaves it unguarded (the validator only warns about unexpected institutions).

## Validation

No scraper tests exist; the narrow checks are the coverage lines printed by the run, `python validate_dataset.py`, and a before/after `diff_catalogs.py`. Live scraping is conditional: only run it when parser or config changes require fresh data, and prefer a single college.

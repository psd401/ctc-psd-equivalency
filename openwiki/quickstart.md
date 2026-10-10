---
type: Quickstart
title: OpenWiki quickstart - CTC to PSD course equivalency
description: Entry point for the wiki covering the Python pipeline that scrapes six Washington college catalogs, classifies courses to PSD high-school credit types, and publishes two HTML tools; includes a task-routing table, page map and backlog.
tags: [quickstart, overview, navigation]
openwiki:
  roles: [repository]
  source_paths: [README.md, PIPELINE.md, CLAUDE.md, build_dataset.py, classify_courses.py, build_html.py, validate_dataset.py]
  validation_commands: ["python validate_dataset.py"]
---

# CTC to PSD Course Equivalency - quickstart

Internal Peninsula School District (PSD) tool. It maps about 6,900 courses from six Washington community and technical colleges (Tacoma, Olympic, Green River, Pierce, Clover Park, Bates) to PSD high-school credit types under the WA State Board of Education 24-credit framework. `hs_credits` is `credits_total / 5`. Outputs: a public read-only viewer (GitHub Pages, https://psd401.github.io/ctc-psd-equivalency/) and a local-only decider tool whose decisions persist to a Google Sheet via Apps Script.

The repo is a flat set of Python scripts with **no package manifest and no test suite**. Quality is enforced by `validate_dataset.py` and idempotent classification. Activate the uv venv (`source .venv/bin/activate`) before Python commands. Existing human docs: `README.md`, `PIPELINE.md`, `CLAUDE.md`; this wiki links to and verifies them rather than copying.

## Wiki map

| Section | Page | Covers |
|---|---|---|
| Architecture | [Pipeline overview](architecture/pipeline-overview.md) | stages, artifacts, ordering invariants |
| Architecture | [Data model](architecture/data-model.md) | course record fields, decision Sheet schema |
| Architecture | [Viewer and decisions](architecture/viewer-and-decisions.md) | the two HTML outputs, decisions overlay, privacy |
| Integrations | [Catalog parsers](integrations/catalog-parsers.md) | Coursedog, Acalog, SmartCatalog, Drupal, legacy PDF |
| Domain | [Classification](domain/classification.md) | 5-tier credit-type resolution, taxonomy |
| Domain | [Credit values](domain/credit-values.md) | published vs derived credits, Pierce |
| Workflows | [OSPI audit](workflows/ospi-audit.md) | LLM audit and decision application |
| Operations | [Catalog refresh](operations/catalog-refresh.md) | scraping safety, WAF, annual refresh, new college |
| Operations | [Validation and deploy](operations/validation-and-deploy.md) | quality gate, GitHub Pages deploy, CI |
| Planning | [Tabled initiatives](planning/future-initiatives.md) | statewide expansion, Olympic DTA proposal |

## Task routing

| Change area / intent | Page | Entry points | Key symbols | Focused check (no test suite) | Minimal validation |
|---|---|---|---|---|---|
| Course lands on wrong credit type | [Classification](domain/classification.md) | `classify_courses.py` | `COMMON_COURSE_OVERRIDES`, `SPECIFIC_OVERRIDES`, `PREFIX_DIRECT_BY_INSTITUTION`, `_resolve_primary` | `validate_classification_current`, `validate_flags` | `python classify_courses.py && python validate_dataset.py` |
| Credit/HS value missing or wrong | [Credit values](domain/credit-values.md) | `parsers/base.py`, `parsers/acalog.py`, `parsers/coursedog.py` | `derive_credits_from_contact_hours`, `CREDITS_RE`, `CREDITS_TEXT_RE`, `_resolve_credits` | `validate_credits`, `validate_derived_credits` | `python validate_dataset.py` |
| A college's scrape breaks or shrinks | [Catalog parsers](integrations/catalog-parsers.md), [Catalog refresh](operations/catalog-refresh.md) | `parsers/<platform>.py`, `build_dataset.py` | `parse`, `report_parse_coverage`, `COLLAPSE_THRESHOLD`, `ChallengeError` | `validate_coverage`, `validate_common_courses` | `python build_dataset.py <inst>` then `python validate_dataset.py` |
| Add a college or platform | [Catalog refresh](operations/catalog-refresh.md#adding-a-new-institution) | `build_dataset.py`, `build_html.py`, `parsers/__init__.py`, `validate_dataset.py` | `INSTITUTIONS`, `PARSERS`, `EXPECTED_INSTITUTIONS` | `validate_coverage` | `python build_html.py && python validate_dataset.py` |
| Viewer UI, filters, CSV export | [Viewer and decisions](architecture/viewer-and-decisions.md) | `build_html.py` (`TEMPLATE`, `emit`) | `effective`, `applyFilters`, `exportCSV` | open via `./serve.sh` | `python build_html.py` |
| Decisions overlay or Apps Script contract | [Viewer and decisions](architecture/viewer-and-decisions.md), [Data model](architecture/data-model.md) | `build_html.py` | `fetchDecisions`, `postDecision`, `normalizeDecision`, `APPS_SCRIPT_URL` | manual, decider tool | `python build_html.py` |
| Add or change a record field | [Data model](architecture/data-model.md) | `parsers/base.py` | `make_record`, `CLASSIFIED_FIELDS` | `validate_shape` | `python validate_dataset.py` |
| Run an OSPI audit | [OSPI audit](workflows/ospi-audit.md) | `audit_credit_type.py` | `OSPI_STANDARDS_HINTS`, `TYPE_FRAMING` | `--dry-run` | `python audit_credit_type.py "<type>" --dry-run` |
| Year-over-year refresh | [Catalog refresh](operations/catalog-refresh.md#annual-refresh) | `diff_catalogs.py`, `build_dataset.py` | `compute`, `INSTITUTIONS` | diff report | `python diff_catalogs.py --year-from A --year-to B` |
| Publish the site | [Validation and deploy](operations/validation-and-deploy.md) | `deploy.sh`, `validate_dataset.py` | `CHECKS` | the validator | `python validate_dataset.py` (conditional: `./deploy.sh` only when publishing) |

Expensive and conditional: live scrapes (minutes for most colleges, days for the three Acalog colleges at the 120s crawl delay), `./deploy.sh`, and LLM audits (about $0.05/course). Do not run them for rule-only or doc changes.

## Cross-cutting rules (read before editing)

- The repo is **public**: no keys, no per-course decision reasoning, no audit artifacts; the decider tool is never deployed.
- Silent absence is the dominant failure mode; preserve loud failures (collapse guard, `ChallengeError`, `report_parse_coverage`, validator).
- Never strip `CREDITS_DERIVED_FLAG` from derived (Pierce) credits.
- Some paths are excluded from this wiki by `.openwikiignore` (generated datasets, catalogs and archives, the decisions backend runbook and posting scripts, audit artifacts); the wiki describes them only as far as README/PIPELINE and visible code reference them.

## Backlog

- `decisions_setup/` (Apps Script `Code.gs`, Sheet migration recipe): excluded by `.openwikiignore`; the server-side contract is documented only from the client side in [Viewer and decisions](architecture/viewer-and-decisions.md).
- `apply_audit_decisions.py`, `cleanup_elective.py`, `normalize_ccn_decisions.py`: excluded; behavior is taken from `README.md`/`PIPELINE.md` in [OSPI audit](workflows/ospi-audit.md).
- Legacy TCC PDF path (`parse_courses.py`, `extract_columns.py`, `inspect_page.py`, `parsers/tcc.py`): only summarized in [Catalog parsers](integrations/catalog-parsers.md); low priority as TCC now reads Coursedog live.


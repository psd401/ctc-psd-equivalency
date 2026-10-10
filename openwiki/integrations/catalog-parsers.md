---
type: Integration Reference
title: Catalog parsers by platform
description: How each college catalog platform (Coursedog, Acalog, SmartCatalog, Drupal, legacy TCC PDF) is scraped into course records, with the PARSERS registry, per-college config, known traps, and a recipe for adding a college.
tags: [scraping, parsers, coursedog, acalog, smartcatalog, drupal]
openwiki:
  roles: [integration]
  change_kinds: [parser, registry, config]
  source_paths: [parsers/__init__.py, parsers/base.py, parsers/coursedog.py, parsers/acalog.py, parsers/smartcatalog.py, parsers/drupal.py, parsers/tcc.py, build_dataset.py]
  symbols: [PARSERS, parse, make_record, report_parse_coverage, ChallengeError, CoursedogError, CREDITS_TEXT_RE]
  validation_commands: ["python build_dataset.py <inst>", "python validate_dataset.py"]
---

# Catalog parsers by platform

Consult this page when a college's data looks wrong, a catalog site changes, or a new college is added. Every parser exposes `parse(config: dict) -> Iterator[dict]` yielding records built with `base.make_record` (shape in [data model](../architecture/data-model.md)). `build_dataset.run_one` looks parsers up in `parsers.PARSERS` and passes `INSTITUTIONS[inst]["config"]` ([pipeline](../architecture/pipeline-overview.md)).

| College id | Parser key -> module | Platform | Notes |
|---|---|---|---|
| `tcc` | `coursedog.parse` | Coursedog JSON API + CSV export | live since 2026-09-02 |
| `tcc-pdf` | `tcc.parse` | archived 2-column PDF text | legacy; reproduces old scrapes only |
| `olympic`, `greenriver`, `pierce` | `acalog.parse` | Acalog (`content.php`) | WAF challenge, 120 s crawl delay |
| `cloverpark` | `smartcatalog.parse` | SmartCatalog | no component data |
| `bates` | `drupal.parse` | custom Drupal | unversioned catalog |

## Shared helpers (`parsers/base.py`)

- `make_record`, `dedupe`, `normalize_code`, `extract_common_course`, `normalize_text`.
- `parse_credit_string` ("5" -> 5.0, "1-3" -> `{min,max}`, "Variable" -> None).
- `parse_contact_hours` / `infer_components_from_text`: an explicit `"<Type> Contact Hours N"` table is authoritative (0 hours = component absent); otherwise keyword scan.
- `derive_credits_from_contact_hours` + `CREDITS_DERIVED_FLAG`: see [credit values](../domain/credit-values.md).
- `report_parse_coverage(parser, inst, enumerated, yielded, unparsed)`: prints `yielded/enumerated` and loud `!!` warnings for zero enumeration (blocked crawl) or unparsed pages (regex drift). Every parser must call it.

## Per-platform behavior

**Coursedog (`parsers/coursedog.py`, TCC).** Pages `GET app.coursedog.com/api/v1/cm/{school}/courses/search/$filters` (needs `Origin`/`Referer` of the catalog host, else 401). Keeps only `status == "Active"`. Credits are missing from the JSON for most courses, so `_fetch_credits_csv` POSTs the catalog's CSV export and joins **by position**; `parse` aborts with `CoursedogError` if row count differs from active count or if any first-120-char description mismatches. `_resolve_credits` precedence: JSON `creditHours` (only source of ranges) > prior-scrape range from `credits_fallback_path` (only if its min equals the CSV figure) > CSV figure. `_prerequisites` renders nested requisite rules (reading only string values once dropped prerequisites for 384 of 839 courses). The `catalog_id` changes every catalog year; refresh it from the catalog's own network requests (comment in `build_dataset.INSTITUTIONS["tcc"]`).

**Acalog (`parsers/acalog.py`, Olympic/Green River/Pierce).** `_list_coids` paginates `content.php?catoid&navoid&filter[cpage]=N` until no new `coid`s; `_parse_detail` reads `preview_course_nopop.php`. `_fetch` raises `ChallengeError` on any non-200 or empty body (the AWS WAF challenge answers 202 with an empty body) and the listing loop aborts rather than truncating. Credits: `CREDITS_RE` (`<strong>` pair, Olympic/Pierce) then `CREDITS_TEXT_RE` fallback (Green River plain text; its absence once left all 1,378 courses without credits), then Pierce-only derivation. Config keys: `catoid`, `course_navoid`, `request_delay` (defaults to env `ACALOG_DELAY`, 120). Department is just the code prefix. Operational consequences: [catalog refresh](../operations/catalog-refresh.md).

**SmartCatalog (`parsers/smartcatalog.py`, Clover Park).** BFS over listing pages; course pages are those at depth >= 3 below `catalog_path` (`/en/<year>/catalog/courses`). Credits from `div.credits`. Publishes no structured components, so components are keyword-inferred from the description; when that yields none, the classifier falls back to the `w/ Lab` title heuristic.

**Drupal (`parsers/drupal.py`, Bates).** Paginates `/courses?page=N` (0-based), detail path `/{dept-slug}/{prefix}-{num}`. `TITLE_RE` must accept `&` (rendered `&amp;`); omitting it once dropped every CCN course for four months. Transfer pages carry lecture/lab/clinical hours (`HOURS_RE`), workforce pages do not. The catalog has no year marker, so `catalog_year` is `scraped <date>`. Courses a college unpublishes (HTTP 403) can be re-added with `retain_unpublished.py` ([catalog refresh](../operations/catalog-refresh.md)).

**Legacy TCC PDF (`parsers/tcc.py`, `parse_courses.py`, `extract_columns.py`, `inspect_page.py`).** Earlier path: pdfplumber column extraction to `tcc-columnwise.txt`, then a state-machine parse. Kept for reproducing 2025-2026 archives; not used by `build_dataset.py` for `tcc` any more.

## Change recipe: add or re-point a college

1. Identify the platform (Acalog sites answer `Server: director`; SmartCatalog URLs are `*.smartcatalogiq.com`; otherwise a new parser).
2. Add an entry to `INSTITUTIONS` in `build_dataset.py` (`enabled`, `parser`, `config`; Acalog needs `catoid` + `course_navoid` from the "Course Descriptions" link).
3. Add `{id, label}` to `INSTITUTIONS` in `build_html.py` (also feeds the viewer filters).
4. Register a new platform in `parsers/__init__.PARSERS`.
5. Add the id and a floor to `EXPECTED_INSTITUTIONS` in `validate_dataset.py`.
6. Only add classifier prefix overrides after concrete conflicts ([classification](../domain/classification.md)).
7. Validate: `python build_dataset.py <inst>` and read the `N/M pages parsed` line, then `python validate_dataset.py`.

For a new parser: yield `make_record(...)`, call `report_parse_coverage`, never swallow unparseable pages, and treat a zero-result enumeration as a failure. Expensive: a full Acalog scrape is a multi-day job; prefer a single-college run or fixtures saved from one detail page.

There are no unit tests; the regression defenses are the checks in [validation and deploy](../operations/validation-and-deploy.md).

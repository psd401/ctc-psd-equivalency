---
type: Domain Logic
title: HS credit values - published versus derived
description: How hs_credits is computed from credits_total (5 quarter credits = 1.0 HS credit), where each college's credit figure comes from, and the Pierce contact-hour derivation with its DERIVED flag, badge and validator.
tags: [credits, pierce, derived-credits, hs-credits]
openwiki:
  roles: [domain]
  change_kinds: [credits, parser, validation]
  source_paths: [parsers/base.py, parsers/acalog.py, parsers/coursedog.py, classify_courses.py, validate_dataset.py, build_html.py]
  symbols: [derive_credits_from_contact_hours, CONTACT_HOURS_PER_CREDIT, CREDITS_DERIVED_FLAG, CREDITS_TEXT_RE, validate_derived_credits, validate_credits, MAX_MISSING_CREDITS, creditsAreDerived]
  invariants:
    - "hs_credits = credits_total / 5; ranges stay ranges."
    - "Every derived credit value carries CREDITS_DERIVED_FLAG; never strip it."
    - "A flagged record with no hs_credits fails validation."
  validation_commands: ["python validate_dataset.py"]
---

# HS credit values: published versus derived

Everything downstream (the viewer's credit column, graduation counting) depends on `credits_total`, so where each college's number comes from matters. `classify()` turns it into `hs_credits = credits_total / 5` (5 quarter credits = 1.0 HS credit, rounded to 2 places; `{min,max}` converts both ends). The conversion rule is hard-coded in `classify_courses.classify`; the [statewide plan](../planning/future-initiatives.md) proposes making it configurable.

## Source of the credit figure per college

| College | Source | Implementation |
|---|---|---|
| Bates | `field-credits` on detail page | `parsers/drupal.py` `CREDITS_RE` |
| Clover Park | `div.credits` | `parsers/smartcatalog.py` |
| Green River | plain text `Credits: N` | `acalog.CREDITS_TEXT_RE` fallback |
| Olympic | `<strong>Credits:</strong><strong>N</strong>` | `acalog.CREDITS_RE` |
| TCC | catalog CSV export "Total Credits" (JSON is null for ~86%) | `coursedog._fetch_credits_csv`, `_resolve_credits` |
| Pierce | **derived** from contact hours | `base.derive_credits_from_contact_hours` |

Two silent failures shaped this design: Green River's markup differs from Olympic's so one regex left all its credits `None`; and Pierce publishes no credit field at all.

## Pierce derivation

`derive_credits_from_contact_hours` parses `Lecture/Lab/Clinical Contact Hours N` (via `parse_contact_hours`) and sums lecture/10 + lab/20 + clinical/30 (`CONTACT_HOURS_PER_CREDIT`, WA quarter-credit convention), rounded to 2 places. `acalog._parse_detail` calls it only when no published credit was found and sets `credits_derived`; `acalog.parse` then adds `base.CREDITS_DERIVED_FLAG` to `review_flags`. Examples: 50 lecture -> 5.0; 40 lecture + 40 lab -> 6.0; 5 lecture + 45 clinical -> 2.0. Two Pierce courses (EMS150, SSBH125) have no table and stay valueless.

Validation evidence recorded in `PIPELINE.md`: all 164 Pierce CCNs also offered by peer colleges derive a value that at least one peer assigns. Peers disagree with each other on lab sciences (BIOL&241 is 5.0 at four colleges and 6.0 at Olympic), so the check is "inside the peer range", not "equals the mode". The derivation is still unpublished data: Pierce's registrar is the authority before it counts toward a graduation requirement.

Pierce is also pinned to Acalog `catoid=17`, which is the 2023-2024 catalog although `catalog_year` is labelled 2025-2026; updating is blocked by the WAF ([catalog refresh](../operations/catalog-refresh.md)). Treat the label as known-inaccurate.

## Guardrails

- **Flag:** `CREDITS_DERIVED_FLAG` starts with the text `Credit value DERIVED from published contact hours`; the validator (`DERIVED_CREDITS_PREFIX`) and the viewer (`DERIVED_CREDITS_RE`) both match on that prefix, so changing the wording means changing all three.
- **Viewer:** `derivedMark` renders a `derived` badge with the flag as tooltip in the **public** view too ([viewer](../architecture/viewer-and-decisions.md)).
- **Validator:** `validate_derived_credits` errors on a flagged record with `hs_credits is None` and warns with counts; `validate_credits` errors if more than `MAX_MISSING_CREDITS` (25%) of a college lacks credits (`CREDITS_EXEMPT` is now empty, so Pierce is held to the same bar). See [validation and deploy](../operations/validation-and-deploy.md).
- Sub-100 courses still get `hs_credits`, but are flagged for Fresh Start (Open Doors) review ([classification](classification.md)).

## Change recipe: a new credit source or ratio

Change the parser (not the classifier) so `credits_total` is correct; if the value is inferred, attach a flag using the shared prefix; confirm with `python build_dataset.py <inst>` plus `python validate_dataset.py`; variable credit stays a `{min,max}` dict end to end.

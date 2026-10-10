---
type: Planning Reference
title: Tabled initiatives - statewide expansion and Olympic DTA proposal
description: Summary of the two planning-only folders (statewide/ and dta-olympic/) - status, locked decisions, sizing evidence, slices, gating questions - and which current code seams they would touch.
tags: [planning, statewide, dta, roadmap]
openwiki:
  roles: [repository]
  change_kinds: [planning]
  source_paths: [statewide/PLAN.md, statewide/README.md, dta-olympic/PLAN.md, dta-olympic/README.md]
---

# Tabled initiatives

Both folders are **planning stubs, not implementations**. Do not start building from them without the stated gate being cleared. They build on the [pipeline](../architecture/pipeline-overview.md).

## Statewide expansion (`statewide/`)

Status: **TABLED 2026-06-02**; gated on stakeholder validation of the *outputs* (advisory framing, public output fields, whether `5 quarter credits = 1.0 HS credit` stays the default, how low-confidence courses display).

- Goal: all 34 WA community and technical colleges, searchable, with recommended HS credit conversions and types, owned by a single authority (PSD short term).
- Locked decisions (D1-D7): statewide at launch; recommendations in scope; single owner; accept bus-factor of one; static files plus a real search index now (managed Postgres only when a maintainer exists, avoid bespoke cloud apps); recommendations are advisory with a disclaimer; harvest the human-reviewed 6-college set to improve the LLM pass.
- Sizing evidence (measured on the 6-college set 2026-06-02, so now partly dated): about 38,000 projected courses; 268 distinct Common Course Numbers (highest-leverage review); 63.7% of records on the low-confidence Elective fallback; about $2,000 for a statewide LLM audit pass; the inline-all-data HTML design breaks at that scale (needs sharded or lazy index).
- Proposed slices 0-5: curate seed set and gold eval; ingestion scale-out (mostly `INSTITUTIONS` config, since Acalog is the most common platform); statewide classification pass; search index and front-end rework; recommendation, provenance and publishing; handoff readiness (credit policy as config rather than hard-coded).

Code seams it would touch: `build_dataset.py` and `build_html.py` `INSTITUTIONS` ([catalog refresh](../operations/catalog-refresh.md)), the inline data design in [the viewers](../architecture/viewer-and-decisions.md), the hard-coded credit ratio in [credit values](../domain/credit-values.md), and the [audit workflow](../workflows/ospi-audit.md).

## Olympic College DTA pathway proposal (`dta-olympic/`)

Status: **SKETCH 2026-06-02**, plan only. Goal: a discussion document for a meeting with Olympic College showing how PSD dual-credit offerings cover parts of a Direct Transfer Associate (DTA) degree, the gaps, and asks for OC.

- Inputs: Olympic's classified catalog (in repo), OC's DTA requirement structure (to confirm), PSD dual-credit offerings (to gather, not in repo).
- New piece: a DTA-distribution-area mapping layer (Communication, Quantitative, Humanities, Social Sciences, Natural Sciences with a lab, electives). HS credit types are not DTA areas; WA Common Course Numbers make much of it a lookup table.
- Reuses record fields `credits_total`, `level`, `is_common_course`, `common_code`, `components` ([data model](../architecture/data-model.md)).

Open questions (authority of the presenter, which DTA variant) are listed in each `PLAN.md`; read those files directly before acting.

# Statewide expansion — plan (tabled)

> Status: **TABLED 2026-06-02.** Beginnings of a plan only. Gated on stakeholder
> feedback about the **outputs** before any build work. No time estimates by design.

## 1. Context

- **Foundation:** the existing tool maps 6 WA community/technical colleges (~6,800
  courses) to PSD HS credit types per the WA SBE 24-credit framework. Pipeline,
  parsers, classifier, LLM audit, and outputs are documented in `../README.md`
  and `../PIPELINE.md`. The `ctc-catalog/` repo is the working foundation this
  builds on.
- **Goal:** extend to **all 34 WA SBCTC colleges**, searchable + filterable, with
  **recommended credit conversions and credit types** — not just a raw catalog.
- **Origin:** scoped in a feasibility conversation (2026-06-02). This file
  preserves the decisions and evidence so slices can be defined later.

## 2. Locked decisions (from the feasibility discussion)

| # | Decision | Rationale |
|---|---|---|
| D1 | **Statewide on launch** (not staged by region/platform) | Stakeholder intent — "if we do this, statewide." |
| D2 | **Recommendations in scope**, not catalog-only | The recommended conversion is the useful part. |
| D3 | **Single owner.** Short term: **PSD**. Medium term: a **consortium that does not yet exist** | Other bodies (OSPI/SBE/SBCTC) unlikely to take it on; single owner removes the 295-district reconciliation problem. |
| D4 | **No named maintenance successor** — accept bus-factor-of-one | Stakeholder accepts the risk; it drives the hosting choice (D5). |
| D5 | **Hosting: static + real search index now; managed Postgres (Supabase/Neon) only when a consortium/maintainer exists. Avoid bespoke cloud app (Amplify/DynamoDB/Cognito).** | D4 means minimize ops + maximize portability. Static files and `pg_dump` hand off cleanly; an AWS account (billing/IAM) does not. |
| D6 | **Recommendations are advisory defaults**, with disclaimer ("verify with your district") | A PSD-authored statewide recommendation has no formal authority; this is also the liability framing. |
| D7 | **Harvest the human-reviewed 6-college set to improve the statewide LLM pass** | The current audit judges courses cold; prior human decisions are unused leverage. |

## 3. Sizing evidence (validated against current data, 2026-06-02)

- **Coverage gap:** 6 of 34 colleges (~18%).
- **Projected scale:** ~38,000 courses (1,133/college × 34).
- **Platform reuse:** 4 parsers cover the 6 today (Coursedog, Acalog, SmartCatalog,
  Drupal). Acalog covers 3 of 6 and is the most common platform statewide — most
  new colleges are *config* entries, not new code.
- **WA Common Course Numbers (`&`):** 715 records (10.5%), **268 distinct codes**.
  A decision on a CCN applies at every college offering it (`applies_to=all`).
  Highest-leverage place to spend human review.
- **Classification quality (the bottleneck):** 63.7% of current records land on the
  low-confidence **fallback** ("Elective"); 83.7% carry ≥1 review flag; only ~36%
  resolve via prefix/common-course rules. Statewide ≈ **24,000 low-confidence
  courses** to adjudicate.
- **LLM audit cost:** ≈ $0.05/course → full statewide pass across all credit types
  ≈ **~$2,000** per pass. Cheap relative to human adjudication effort.
- **Output scaling limit:** current design *inlines all data* (11 MB single-file
  decider HTML at 6,800 courses). At ~38k that inline approach (~60 MB) **breaks** —
  must move to a sharded/lazy index. This is a `build_html.py` change, independent
  of host.

## 4. Proposed slices (to define in detail later)

> Vertical slices, roughly ordered. Slice 0 is prerequisite and high-leverage.

- **Slice 0 — Curate the seed set.** Human-review the existing 6-college
  classifications, prioritizing the 268 CCNs. Produce (a) a labeled **gold eval
  set**, (b) a **few-shot exemplar bank** of hard reclassifications (e.g. the
  CHP/CHPM "Community Health = workforce, not K-12 Health" call). Enables D7.
- **Slice 1 — Ingestion scale-out.** Extend `INSTITUTIONS` in `build_dataset.py`
  + `build_html.py` to all 34 colleges; map each to a platform parser; add a parser
  only for genuinely new platforms. Mostly config for Acalog colleges.
- **Slice 2 — Statewide classification pass.** Run the LLM audit across all credit
  types statewide, **seeded with Slice 0 exemplars**; measure against the held-out
  gold set; route low-confidence to human review. Publish a credit type only above
  a measured accuracy bar.
- **Slice 3 — Search/index + front-end rework.** Replace inline-everything with a
  sharded/lazy index (Pagefind, or MiniSearch/FlexSearch over chunked JSON);
  statewide-scale search + filter UI.
- **Slice 4 — Recommendation, provenance & publishing.** Advisory-default framing +
  disclaimer (D6); decision provenance (`decided_by`, append-only — already present);
  decide write store (Google Sheet vs versioned JSON in repo); public read vs gated
  decider tool.
- **Slice 5 — Handoff readiness.** Keep credit policy as **config, not hardcode**
  (e.g. the `5 quarter credits = 1.0 HS credit` rule); document consortium transfer;
  confirm the system is operable under D4.

## 5. Outputs to validate with stakeholders (the gate)

Before building, get feedback on **what the tool publishes**:

- O1 — Is an **advisory PSD-authored statewide recommendation** credible/usable to
  other districts, or does it need a different framing to be adopted?
- O2 — What does a useful **public output** look like (course → recommended HS credit
  + type + confidence + rationale)? What fields matter to counselors/families?
- O3 — Should the **conversion default** (`5 qtr credits = 1.0 HS credit`) stand as the
  statewide default, or be presented as configurable per district?
- O4 — How should **low-confidence / unreviewed** courses be shown (hidden, flagged,
  or shown with a caveat) so the tool isn't trusted beyond what's been adjudicated?

## 6. Open questions (carried forward)

- 2.1 Search index: **Pagefind** (turnkey, static-first) vs **MiniSearch/FlexSearch**
  (more control over facets/filters)?
- 2.2 Write store at statewide scale: keep **Google Sheet**, or move decisions to
  **versioned JSON in the repo** (Git as the audit trail)?
- 2.3 **Public read-only at launch**, or **gated** until the statewide pass clears the
  accuracy bar (Slice 2)?
- 2.4 Who, if anyone, becomes the eventual **consortium** — and what artifact (data +
  decisions export) do they need to take ownership cleanly?

## 7. Caveats

- Numbers in §3 are measured against the current 6-college dataset; statewide figures
  are extrapolations, not observed.
- "Feasible" here means the architecture extends and costs are bounded — **not** that
  accuracy at statewide scale is demonstrated. That is what Slice 2's accuracy bar
  exists to prove.
- Local/CTE prefix decisions are college-specific; they inform LLM *reasoning*, not
  statewide labels. Don't overfit to PSD-local prefix quirks.

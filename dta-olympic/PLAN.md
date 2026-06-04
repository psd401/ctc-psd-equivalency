# DTA pathway proposal — Olympic College (plan sketch)

> Status: **SKETCH 2026-06-02.** Beginnings of a plan to generate a DTA proposal
> for Kelsey's meeting with Olympic College. No time estimates by design.

## 1. Objective

Generate a **proposal Kelsey presents to Olympic College (OC)** for a structured
**Direct Transfer Associate (DTA)** pathway that PSD students can complete —
showing how PSD's existing dual-credit offerings already cover parts of the DTA,
where the gaps are, and what OC partnership would fill them.

This is a **discussion/advisory document** for a meeting, not a binding articulation.

## 2. Inputs

| Input | Source | Status |
|---|---|---|
| OC course catalog | `../catalogs/olympic-courses-classified.json` (1,246 courses, 174 CCNs) | **In repo** — refreshable via `python build_dataset.py olympic` |
| OC DTA requirement structure | OC catalog DTA worksheet / advising guide (ICRC-based) | **To confirm** — general ICRC frame known; OC specifics TBD |
| PSD current dual-credit offerings | PSD registration guide, CiHS contracts, CTE dual-credit articulations, Running Start partners, AP/IB list | **To gather** — not in this repo |
| DTA-area ↔ course mapping | New layer (see §4) | **To build** |

### Confirmed against OC data (2026-06-02)

DTA "core" anchors are present in OC's catalog:
`ENGL&101` (English Composition I), `ENGL&102` (Composition II), `CMST&220`
(Public Speaking), `MATH&107` (Math in Society), `MATH&141` (Precalc),
`MATH&146` (Intro Statistics), `MATH&148` (Business Calc), `PHIL&101`,
`ENGL&235`. OC also has 39 lab-science and 16 world-language courses by the
HS-type proxy — enough to populate Natural Science and Humanities distribution.

## 3. DTA reference frame (confirm OC specifics)

Standard WA ICRC **Associate in Arts DTA** (~90 quarter credits, junior standing
at WA public 4-years). Typical structure — **OC's exact credits/lists must be
verified from OC's worksheet**:

- **Communication Skills** — ~10 cr (English Composition + one more, e.g. ENGL&101
  + ENGL&102 or CMST&220)
- **Quantitative / Symbolic Reasoning** — ~5 cr (college-level math, intermediate
  algebra prerequisite)
- **Humanities distribution** — ~15 cr (discipline/skills caps apply)
- **Social Sciences distribution** — ~15 cr (discipline caps apply)
- **Natural Sciences distribution** — ~15 cr, **including ≥1 lab**
- **Electives / restricted electives** — to reach 90 cr
- **GPA / residency** — cumulative 2.0; residency minimum

> Note: there are also **major-related DTA/MRP** degrees (AS-T tracks, Associate in
> Business DTA, etc.). Decide in §6 whether the proposal targets the general
> **AA-DTA** or a major-related variant.

## 4. The new piece — DTA-area mapping

- The existing classifier outputs **HS credit types**, which do **not** equal **DTA
  distribution areas**. A new mapping layer is required:
  `OC course → DTA area (Comm / Quant / Humanities / Social Science / Natural
  Science+lab / elective)`.
- **Leverage:** ICRC distribution lists are largely keyed to **WA Common Course
  Numbers**. OC has **174 CCNs**, so the high-value core maps with a CCN lookup
  table rather than per-course judgment. Local (non-`&`) courses need OC's own
  distribution list to place.
- Reuse what exists: `credits_total`, `level`, `is_common_course`, `common_code`,
  and `components` (lab detection already used by the science classifier) all carry
  over.

## 5. Proposed work steps (when un-tabled)

- **Step 1 — Inventory PSD dual credit.** Compile current Running Start (which
  colleges), College in the High School courses + partners, CTE Dual Credit
  articulations, AP/IB. Output: a PSD offering list tagged by subject.
- **Step 2 — Lock the DTA target + worksheet.** Confirm OC's AA-DTA (or MRP)
  requirements from OC's catalog/advising sheet; encode the area buckets + credit
  minimums.
- **Step 3 — Map OC catalog → DTA areas.** Build the CCN-keyed area table; place
  OC's local courses using OC's distribution list. Output: OC courses grouped by
  DTA area.
- **Step 4 — Crosswalk PSD offerings → DTA areas.** Show which DTA areas PSD
  students can already satisfy through current dual credit, and which areas are
  **gaps**. Output: coverage matrix.
- **Step 5 — Draft the proposal for Kelsey.** Assemble: (a) a model DTA course plan
  using OC courses, (b) the PSD coverage/gap crosswalk, (c) concrete asks for OC
  (CiHS sections, Running Start advising, guaranteed seats, equivalency
  confirmations), (d) advisory framing + disclaimer.

## 6. Proposal outline (the deliverable for Kelsey)

1. **Purpose** — a DTA pathway for PSD students via OC; what's being asked.
2. **Model DTA plan** — OC courses filling each DTA area, sequenced across a
   student's timeline (Running Start / CiHS).
3. **PSD coverage today** — what current dual credit already satisfies.
4. **Gap analysis** — DTA areas not covered by current PSD offerings.
5. **Asks for OC** — specific partnership actions to close the gaps.
6. **Caveats** — advisory; final degree audit is OC's; verify equivalencies.

## 7. Open questions

- 3.1 **Kelsey's role / authority** — what is she empowered to propose or commit at
  the meeting? (shapes how strong the "asks" can be)
- 3.2 **Which DTA** — general **AA-DTA**, or a **major-related** degree (Business,
  STEM AS-T)?
- 3.3 **Pathway vehicle** — Running Start, College in the High School, or a blend?
  (affects who teaches, seat costs, and the asks)
- 3.4 **Target student profile** — full DTA-by-graduation, or partial/accelerated
  start?
- 3.5 **Is OC the right CTC** — PSD (Gig Harbor/Pierce Co.) also borders Tacoma CC
  and Pierce College. Confirm OC is the intended partner for this pathway.
- 3.6 **Meeting date / format** — drives how polished the deliverable needs to be.

## 8. Caveats

- OC's exact DTA requirements in §3 are the **standard ICRC frame**, not yet
  verified against OC's published worksheet — confirm before drafting.
- HS-type counts in `README.md`/§2 are a **proxy**; DTA-area placement requires the
  §4 mapping, not the existing classifier output.
- PSD dual-credit inventory is **not in this repo** and must be gathered before
  Step 4.

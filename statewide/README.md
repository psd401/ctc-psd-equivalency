# Statewide expansion — planning stub

**Status: TABLED (2026-06-02).** Captured for later. Do **not** start building.

**Gate before any work begins:** validate the *outputs* (what the tool publishes and how
recommendations are framed) with stakeholders. See "Outputs to validate" in `PLAN.md`.

## What this is

A planning stub for expanding the existing 6-college CTC↔PSD equivalency tool
(see `../README.md`, `../PIPELINE.md`) into a **statewide** course catalog —
all 34 WA community & technical colleges, searchable and filterable, with
**recommended HS credit conversions and credit types**, owned by a single
authority.

This folder holds *just enough* context to set up work slices later. It is not
an implementation spec.

## Files

- `PLAN.md` — context, locked decisions, sizing evidence, proposed slices, open questions.

## One-line summary of where we landed

Feasible. The ingestion architecture already extends; the real cost is
**adjudication quality**, not infrastructure. Cheapest credible path is also
the most portable (static + search index now; managed Postgres only when a
maintainer exists). Single PSD ownership removes the governance blocker.

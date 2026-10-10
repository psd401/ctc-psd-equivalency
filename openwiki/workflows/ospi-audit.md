---
type: Workflow
title: OSPI-standards LLM audit workflow
description: How audit_credit_type.py generates an external multi-agent workflow that checks a credit type against WA OSPI K-12 standards, and how the verdicts are applied to the decisions Sheet as AI-attributed append-only decisions.
tags: [audit, llm, ospi, decisions, classification]
openwiki:
  roles: [workflow]
  change_kinds: [audit, decisions]
  source_paths: [audit_credit_type.py, README.md, PIPELINE.md, CLAUDE.md]
  symbols: [OSPI_STANDARDS_HINTS, TYPE_FRAMING, WORKFLOW_TEMPLATE, main]
  invariants:
    - "Audit artifacts and per-course reasoning stay local and are never committed."
    - "Decisions are append-only; existing deliberate decisions are not overwritten."
  validation_commands: ["python audit_credit_type.py \"Health\" --dry-run"]
---

# OSPI-standards LLM audit workflow

Use this when a credit type's classifications need systematic review against state K-12 standards (what the Health, CTE and Elective passes did). It consumes the [classified dataset](../architecture/data-model.md) and produces human-reviewable verdicts that become [decisions](../architecture/viewer-and-decisions.md); permanent outcomes are later folded into [classification rules](../domain/classification.md).

## Steps

1. **Generate:** `python audit_credit_type.py "<Credit Type>" [--max N] [--min-confidence X] [--max-confidence X] [--include-institutions tcc olympic ...] [--dry-run]`. It selects records from `ctc-courses-classified.json` whose `credit_types` contain the target and whose `confidence` is within range, prints counts per college, and (without `--dry-run`) writes a self-contained JS workflow to `/tmp/audit-<slug>.js` (descriptions trimmed to 600 characters because workflow scripts have a 512 KB cap).
2. **Run externally:** the generated workflow has three phases: `Standards research` (one agent summarising OSPI standards, seeded by `OSPI_STANDARDS_HINTS` and `TYPE_FRAMING`), `Per-course verdicts` (one agent per course in parallel), `Synthesize` (markdown report). Each verdict is `keep_target`, `remove_target` or `add_other` with `recommended_types` as the full replacement list, plus reasoning and confidence. Be conservative: marginal cases lean `keep_target`. Save the result JSON (with a `verdicts` array) as `audit-<slug>.json`.
3. **Apply:** `python apply_audit_decisions.py audit-<slug>.json --dry-run`, then without `--dry-run`. This script (and `cleanup_elective.py`, `normalize_ccn_decisions.py`) posts to the decisions endpoint and is deliberately outside this wiki's scope. Behavior documented in `PIPELINE.md`: CCN verdicts collapse to `applies_to=all` when every college agrees, otherwise per-college decisions; `keep_*` verdicts are skipped unless `--include-keep`.

## Rules to respect

- Attribution: AI-applied decisions are marked as AI (`decided_by` "AI Classifier", or the "(AI-assisted audit)" director label used by README); the Sheet is append-only so a human override is a new row.
- Always fetch `?action=list` fresh first and skip already-decided `(code, institution)` pairs. Post key comes from env `CTC_DECISIONS_KEY` (never committed; see `CLAUDE.md`).
- When two audits disagree, apply the more specific, better-reasoned one; the Sheet history keeps both.
- Per-course reasoning is not published. Audit report/JSON artifacts (`audit-*.md`, `audit-*.json`) stay local; decisions cite the artifact filename in `source_citation`.
- Cost: about $0.05 per course (Health, 37 courses, about $4; CTE, 877 courses, about $50). Prefer `--max-confidence` to focus on uncertain courses and `--dry-run` first.

## Status of audits

Per `PIPELINE.md`, the initial audits are complete: Health, CTE, and a full Elective reclassification on 2026-06-11 (1,418 Elective-only courses reviewed, 862 decisions applied). Treat re-running as optional.

## Validation

There is no test harness. `python audit_credit_type.py "<type>" --dry-run` verifies selection; generated JS is only exercised by the external runner.

"""Catalog parsers for the TCC↔PSD equivalency tool.

Each parser exposes `parse(config: dict) -> Iterator[CourseRecord]`. The
build_dataset.py orchestrator looks up parsers by name via the PARSERS
registry below and runs them with per-institution config.
"""
from . import acalog, coursedog, drupal, smartcatalog, tcc

PARSERS = {
    # TCC stays on PDF text extraction. The Coursedog API (parsers/coursedog.py)
    # reads the same catalog live and finds 52 courses the PDF misses, but its
    # courses/search endpoint returns null credits for 720 of 839 active
    # courses, which would wipe hs_credits — the pipeline's core output. Not
    # usable as the TCC source until credits can be sourced.
    "tcc":         tcc.parse,
    "coursedog":   coursedog.parse,
    "olympic":     acalog.parse,
    "greenriver":  acalog.parse,
    "pierce":      acalog.parse,
    "cloverpark":  smartcatalog.parse,
    "bates":       drupal.parse,
}

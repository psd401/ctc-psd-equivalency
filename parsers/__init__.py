"""Catalog parsers for the TCC↔PSD equivalency tool.

Each parser exposes `parse(config: dict) -> Iterator[CourseRecord]`. The
build_dataset.py orchestrator looks up parsers by name via the PARSERS
registry below and runs them with per-institution config.
"""
from . import acalog, coursedog, drupal, smartcatalog, tcc

PARSERS = {
    # TCC reads its Coursedog catalog live as of 2026-09-02. Credits come from
    # the catalog's CSV export (the JSON search endpoint returns null credits
    # for 720 of 839 courses), positionally joined and verified against the
    # description column. parsers/tcc.py is kept for reproducing older scrapes
    # from the archived PDF text.
    "tcc":         coursedog.parse,
    "tcc-pdf":     tcc.parse,
    "olympic":     acalog.parse,
    "greenriver":  acalog.parse,
    "pierce":      acalog.parse,
    "cloverpark":  smartcatalog.parse,
    "bates":       drupal.parse,
}

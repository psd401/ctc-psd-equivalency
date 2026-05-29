"""Catalog parsers for the TCC↔PSD equivalency tool.

Each parser exposes `parse(config: dict) -> Iterator[CourseRecord]`. The
build_dataset.py orchestrator looks up parsers by name via the PARSERS
registry below and runs them with per-institution config.
"""
from . import acalog, drupal, smartcatalog, tcc

PARSERS = {
    "tcc":         tcc.parse,
    "olympic":     acalog.parse,
    "greenriver":  acalog.parse,
    "pierce":      acalog.parse,
    "cloverpark":  smartcatalog.parse,
    "bates":       drupal.parse,
}

# Files

- [Course record and decision data model](data-model.md) - Shape of the course record produced by parsers, the fields added by classify(), and the append-only decisions Sheet schema that the viewer overlays at runtime.
- [Pipeline overview - scrape, merge, classify, build, publish](pipeline-overview.md) - End-to-end data flow of the CTC-to-PSD course equivalency pipeline, its stages, intermediate artifacts, ordering invariants, and the single-command entry points.
- [HTML viewers and the decisions backend](viewer-and-decisions.md) - How build_html.py emits the public read-only viewer and the local decider tool from one template, how data is injected, how Sheet-backed decisions are overlaid on base classifications, and the public/private boundary.

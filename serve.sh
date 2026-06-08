#!/usr/bin/env bash
# Serve the catalog folder over HTTP for local viewing.
#
# ctc-psd-equivalency.html (the public viewer) loads its data from the
# equivalency-data.json sidecar via fetch(). Browsers block that fetch under
# file://, so double-clicking the HTML shows an empty table + warning banner.
# Serving over http(s) — as below, or via GitHub Pages — makes it work.
#
# Usage: ./serve.sh [port]   (default port 8000)
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-8000}"
echo "Serving $(pwd) at http://localhost:${PORT}/"
echo "Open:  http://localhost:${PORT}/ctc-psd-equivalency.html"
echo "       http://localhost:${PORT}/ctc-psd-decisions.html"
echo "Press Ctrl+C to stop."
exec python3 -m http.server "${PORT}"

#!/bin/bash
# Stage the built tools into ./docs/ so GitHub Pages can serve from the
# /docs folder on the main branch. Usage:
#   ./deploy.sh
#
# After running, commit and push:
#   git add docs/ && git commit -m "Deploy YYYY-MM-DD" && git push
#
# Repo setup (one time):
#   Settings → Pages → Source: Deploy from a branch → Branch: main / /docs → Save
#
# GitHub Pages serves docs/index.html as the root. We name the public file
# index.html so the canonical URL is just /<repo>/.
set -euo pipefail

cd "$(dirname "$0")"

# Rebuild HTML + sidecar to be safe
echo "Rebuilding HTML..."
PYTHON="${PYTHON:-$(pwd)/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="python3"
"$PYTHON" build_html.py >/dev/null

# Gate the deploy on the dataset being sane. Every serious defect this project
# has hit was a silent absence that still produced a plausible-looking file —
# a missing transfer catalog, a college-wide credit blackout — so "it built" is
# not evidence it is publishable. Set SKIP_VALIDATE=1 only with a reason.
if [ "${SKIP_VALIDATE:-0}" != "1" ]; then
  echo "Validating dataset..."
  if ! "$PYTHON" validate_dataset.py; then
    echo
    echo "Deploy ABORTED: the dataset failed validation (see errors above)."
    echo "Fix the cause, or re-run with SKIP_VALIDATE=1 if you have verified"
    echo "the failure is expected."
    exit 1
  fi
fi

mkdir -p docs

# Public read-only tool → index.html (default landing page)
cp ctc-psd-equivalency.html docs/index.html
cp equivalency-data.json    docs/equivalency-data.json

# The decider tool is intentionally NOT deployed. It is decider-facing only:
# run ./serve.sh and open http://localhost:8000/ctc-psd-decisions.html.
# (It used to ship to docs/ under an unguessable filename, but this repo is
# public, so the filename — and the full decider UI — were one GitHub browse
# away. Removed 2026-06-12 along with API-key gating of the decisions API.)

# A small landing index (so a stray crawler hits something neutral)
cat > docs/.nojekyll <<'EOF'
EOF

ls -lah docs/

cat <<EOF

Done. Files staged under docs/.

To publish:
  git add docs/
  git commit -m "Deploy \$(date +%Y-%m-%d)"
  git push

After GitHub Pages builds (~30 sec), the URL will be:
  https://<owner>.github.io/<repo>/                       (public tool)

(The decider tool is local-only: ./serve.sh → http://localhost:8000/ctc-psd-decisions.html)

EOF

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
python build_html.py >/dev/null

mkdir -p docs

# Public read-only tool → index.html (default landing page)
cp ctc-psd-equivalency.html docs/index.html
cp equivalency-data.json    docs/equivalency-data.json

# Decider tool — unguessable filename. Only deciders get this URL.
# Change the suffix occasionally as a soft rotate.
DEC_NAME="decisions-x7q3.html"
cp ctc-psd-decisions.html docs/${DEC_NAME}

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

After GitHub Pages builds (~30 sec), the URLs will be:
  https://<owner>.github.io/<repo>/                       (public tool)
  https://<owner>.github.io/<repo>/${DEC_NAME}            (decider tool)

EOF

#!/usr/bin/env bash
# Assemble the published site in _site/ (or $SITE_DIR).
#
# CI runs this before every deploy. To preview locally:
#   uv run ./build.sh && python3 -m http.server -d _site
set -euo pipefail
cd "$(dirname "$0")"

SITE_DIR="${SITE_DIR:-_site}"
PYTHON="${PYTHON:-python3}"

# Dates and the colophon come from git history, so fetch all of it.
if [ "$(git rev-parse --is-shallow-repository)" = "true" ]; then
  echo "Fetching full git history..."
  git fetch --quiet --unshallow
fi

rm -rf "$SITE_DIR"
mkdir -p "$SITE_DIR"

"$PYTHON" scripts/gather_links.py
"$PYTHON" scripts/publish.py "$SITE_DIR"
"$PYTHON" scripts/build_index.py "$SITE_DIR"
"$PYTHON" scripts/build_colophon.py "$SITE_DIR"
"$PYTHON" scripts/build_sitemap.py "$SITE_DIR"

echo "Site ready in $SITE_DIR"

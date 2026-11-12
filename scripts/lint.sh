#!/usr/bin/env bash
# Lint everything, or fix what can be fixed. See "Linting" in AGENTS.md.
#
#   scripts/lint.sh          # check, as CI's lint job does
#   scripts/lint.sh --fix    # fix and format, then check what's left
#
# Python with ruff, JavaScript (the Workers, the inlined scripts and every
# game's inline <script>) with Biome, build.sh with shellcheck and the
# workflows with actionlint, which runs shellcheck on their run: steps.
# Every version is pinned: ruff, shellcheck and actionlint in pyproject.toml's
# lint group, Biome here (with npx, so the games stay free of npm) and in
# biome.jsonc's $schema.
set -euo pipefail
cd "$(dirname "$0")/.."

BIOME_VERSION=2.6.7
# Warnings and errors; shellcheck's style and info notes aren't worth failing on.
export SHELLCHECK_OPTS="--severity=warning"

fix=false
case "${1:-}" in
  --fix) fix=true ;;
  "") ;;
  *) echo "usage: scripts/lint.sh [--fix]" >&2; exit 2 ;;
esac

# ruff, shellcheck and actionlint from the lint group alone, not the tests' deps.
tool() { uv run --only-group lint "$@"; }
biome() { npx --yes "@biomejs/biome@$BIOME_VERSION" "$@"; }

status=0
step() {
  echo "--- $*"
  "$@" || status=1
}

if $fix; then
  step tool ruff check --fix
  step tool ruff format
  step biome lint --write
else
  step tool ruff check
  step tool ruff format --check
  step biome ci
fi
step tool shellcheck build.sh scripts/lint.sh
step tool actionlint

exit $status

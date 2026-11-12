#!/usr/bin/env bash
# Lint everything, or fix what can be fixed. See "Linting" in AGENTS.md.
#
#   scripts/lint.sh                 # check everything, as CI's lint job does
#   scripts/lint.sh --fix           # fix and format everything, then check
#   scripts/lint.sh --fix FILE...   # the same for these files, as prek's
#                                   # pre-commit hook does for staged ones
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
if [ "${1:-}" = --fix ]; then fix=true; shift; fi
case "${1:-}" in -*) echo "usage: scripts/lint.sh [--fix] [FILE...]" >&2; exit 2 ;; esac

# ruff, shellcheck and actionlint from the lint group alone, not the tests' deps.
tool() { uv run --only-group lint "$@"; }
biome() { npx --yes "@biomejs/biome@$BIOME_VERSION" "$@"; }

status=0
step() {
  echo "--- $*"
  "$@" || status=1
}

# With no files, everything. With files (prek's pre-commit hook passes the
# staged ones), each tool gets those it reads, and ruff and Biome still skip
# what their config excludes.
py=() js=() sh=() workflows=()
if [ $# = 0 ]; then
  py=(.) js=(.) sh=(build.sh scripts/lint.sh .claude/hooks/session-start.sh) workflows=(.github/workflows/*.yml)
fi
for f in "$@"; do
  case "$f" in
    *.py) py+=("$f") ;;
    *.js | *.mjs | *.html | *.json | *.jsonc) js+=("$f") ;;
    *.sh) sh+=("$f") ;;
  esac
  case "$f" in .github/workflows/*.yml | .github/workflows/*.yaml) workflows+=("$f") ;; esac
done

if [ ${#py[@]} -gt 0 ]; then
  if $fix; then
    step tool ruff check --fix "${py[@]}"
    step tool ruff format "${py[@]}"
  else
    step tool ruff check "${py[@]}"
    step tool ruff format --check "${py[@]}"
  fi
fi
if [ ${#js[@]} -gt 0 ]; then
  if $fix; then
    step biome lint --write --no-errors-on-unmatched --files-ignore-unknown=true "${js[@]}"
  else
    step biome ci --no-errors-on-unmatched --files-ignore-unknown=true "${js[@]}"
  fi
fi
if [ ${#sh[@]} -gt 0 ]; then step tool shellcheck "${sh[@]}"; fi
if [ ${#workflows[@]} -gt 0 ]; then step tool actionlint "${workflows[@]}"; fi

exit $status

#!/bin/bash
# Cloud sessions start from a fresh clone, where git has no pre-commit hook
# yet: install the linters and prek's hook, so a session's commits are
# linted and fixed as a local clone's are (see "Linting" in AGENTS.md).
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi
cd "${CLAUDE_PROJECT_DIR:-.}"

# The lint group goes into .venv, which git ignores, so its hash file goes
# there too and disappears with the packages. The git hook itself lives in
# .git/hooks, so a missing one installs again as well.
hashes=.venv/.session-start-lint.sha256
if ! sha256sum --check --status "$hashes" 2>/dev/null || [ ! -f .git/hooks/pre-commit ]; then
  rm -f "$hashes"
  uv sync --locked --only-group lint --inexact
  uv run --only-group lint prek install
  sha256sum .claude/hooks/session-start.sh pyproject.toml uv.lock .pre-commit-config.yaml > "$hashes"
fi

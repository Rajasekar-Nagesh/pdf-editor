#!/usr/bin/env bash
# Stop hook: commit any uncommitted changes and push the current branch to origin.
# Never pushes main/master directly.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
branch=$(git rev-parse --abbrev-ref HEAD)
case "$branch" in main|master|HEAD) exit 0 ;; esac

if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git commit -q -m "Auto-commit: save work from Claude Code session"
fi

# Push only if there is something the remote does not have yet.
if ! git rev-parse --verify -q "origin/$branch" >/dev/null || [ -n "$(git log "origin/$branch..HEAD" --oneline)" ]; then
  for delay in 0 2 4 8 16; do
    sleep "$delay"
    git push -q -u origin "$branch" && break
  done
fi

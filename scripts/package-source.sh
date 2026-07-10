#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "Refusing to package a dirty tree. Commit or stash reviewed changes first." >&2
  exit 1
fi

if git ls-files | grep -E '(^|/)\.env$|(^|/)\.DS_Store$|\.(db|sqlite|sqlite3|tsbuildinfo)$' >/dev/null; then
  echo "Refusing to package while local-only artifacts are tracked." >&2
  exit 1
fi

output="${1:-agentqa-source-$(git rev-parse --short HEAD).tar.gz}"
git archive --format=tar.gz --prefix=AgentQA/ --output="$output" HEAD
echo "Created $output from reviewed tracked files."

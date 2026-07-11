#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "Refusing to package a dirty tree. Commit or stash reviewed changes first." >&2
  exit 1
fi

if git ls-files | grep -E '(^|/)\.env$|(^|/)\.DS_Store$|(^|/)\.git/|(^|/)__pycache__/|(^|/)\.pytest_cache/|(^|/)(coverage|htmlcov|dist|build|\.next)/|\.(db|sqlite|sqlite3|tsbuildinfo)$' >/dev/null; then
  echo "Refusing to package while local-only artifacts are tracked." >&2
  exit 1
fi

secret_pattern='(AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{20,}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|GEMINI_API_KEY=[^[:space:]]+)'
if git grep -I -E "$secret_pattern" -- ':!*.example' ':!scripts/package-source.sh' >/dev/null; then
  echo "Refusing to package because a likely secret pattern is tracked. Rotate exposed credentials manually." >&2
  exit 1
fi

output="${1:-agentqa-source-$(git rev-parse --short HEAD).tar.gz}"
git archive --format=tar.gz --prefix=AgentQA/ --output="$output" HEAD
echo "Created $output from reviewed tracked files."

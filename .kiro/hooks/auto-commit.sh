#!/usr/bin/env bash
# Commit repository changes after Kiro finishes a spec task.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
cd "$REPOSITORY_ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Auto-commit hook skipped: repository root is not a Git work tree." >&2
    exit 0
fi

if [[ -z "$(git status --porcelain)" ]]; then
    echo "Auto-commit hook: no changes to commit."
    exit 0
fi

# Stage tracked, deleted, and untracked files so the completed task is captured.
git add --all

if git diff --cached --quiet; then
    echo "Auto-commit hook: no staged changes to commit."
    exit 0
fi

COMMIT_MESSAGE="chore: commit completed Kiro task"
git commit -m "$COMMIT_MESSAGE"
echo "Auto-commit hook: committed completed task changes."

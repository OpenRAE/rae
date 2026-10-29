#!/usr/bin/env bash
set -euo pipefail

FILE_PATH=$(jq -r '.tool_input.file_path // empty')

if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"
# Claude Code sends an absolute file_path, but the checker accepts only
# repository-relative paths, so strip the project directory. Paths in a Claude
# Code worktree under .claude/worktrees/ stay absolute: that worktree is another
# checkout, whose paths the rules here would misread. The checker refuses them,
# and any path that leaves the repository.
case "$FILE_PATH" in
  "$PWD"/.claude/worktrees/*) ;;
  *) FILE_PATH=${FILE_PATH#"$PWD"/} ;;
esac
# "--" makes the checker read a file named like an option, such as -h, as a path.
implementations/python/.venv/bin/python tools/check_repo_policy.py --check-set file-local -- "$FILE_PATH"

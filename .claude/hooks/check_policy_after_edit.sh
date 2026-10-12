#!/usr/bin/env bash
set -euo pipefail

FILE_PATH=$(jq -r '.tool_input.file_path // empty')

if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"
PROJECT_DIR=$(pwd -P)
PYTHON=$PWD/implementations/tooling/python/.venv/bin/python
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=$PWD/implementations/python/.venv/bin/python
fi
# Claude Code sends an absolute file_path, but the checker accepts only paths
# relative to the root of the checkout that holds the file. That checkout can be
# a Claude Code worktree under .claude/worktrees/ or another checkout nested in
# the project, so ask git from the nearest existing directory, as a new file's
# directory may not exist yet. A worktree has no virtual environment, so every
# checker runs with one from this checkout: the tooling one if present, since a
# new checkout's first check installs Conftest, which needs its filelock, else
# the package one.
if [[ "$FILE_PATH" == /* ]]; then
  ABSOLUTE_PATH=$FILE_PATH
else
  ABSOLUTE_PATH=$PWD/$FILE_PATH
fi
DIR=$ABSOLUTE_PATH
while DIR=${DIR%/*}; [[ -n "$DIR" && ! -d "$DIR" ]]; do :; done
CHECKOUT=$(git -C "${DIR:-/}" rev-parse --show-toplevel 2>/dev/null) || CHECKOUT=
case "$CHECKOUT" in
  "$PROJECT_DIR" | "$PROJECT_DIR"/*)
    FILE_PATH=$(git -C "${DIR:-/}" rev-parse --show-prefix)${ABSOLUTE_PATH#"$DIR"/}
    cd "$CHECKOUT"
    ;;
  *)
    # Outside every checkout in the project, or without git, check the path here
    # without the project directory. The checker refuses a path that stays
    # absolute or climbs out with "..".
    FILE_PATH=${FILE_PATH#"$PWD"/}
    ;;
esac
# A checkout of another repository, or of a commit before the checker existed,
# has no policy to check.
if [[ ! -f tools/check_repo_policy.py ]]; then
  exit 0
fi
# "--" makes the checker read a file named like an option, such as -h, as a path.
"$PYTHON" tools/check_repo_policy.py --check-set file-local -- "$FILE_PATH"

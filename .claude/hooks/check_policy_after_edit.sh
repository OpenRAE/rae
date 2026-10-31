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
# the project, and the path can reach it through a symlink of its root. Take the
# nearest directory on the path with a .git entry as the checkout, while keeping
# an enclosing symlink's owning checkout as the boundary. Check the file at its
# canonical location relative to that checkout's canonical root, so
# a symlink inside the checkout is checked where it resolves to. A worktree has
# no virtual environment, so every checker runs with one from this checkout: the
# tooling one if present, since a new checkout's first check installs Conftest,
# which needs its filelock, else the package one.
if [[ "$FILE_PATH" == /* ]]; then
  ABSOLUTE_PATH=$FILE_PATH
else
  ABSOLUTE_PATH=$PWD/$FILE_PATH
fi
CHECKOUT=
# A path with a ".." segment is not resolved, so the checker still refuses it.
if [[ "/$ABSOLUTE_PATH/" != */../* ]]; then
  DIR=$ABSOLUTE_PATH
  while DIR=${DIR%/*}; [[ -n "$DIR" ]]; do
    if [[ -L "$DIR" ]]; then
      # A link to another checkout's root exposes its .git through the alias.
      # Keep the link's owning checkout as the boundary instead. An alias
      # outside any checkout has no such boundary; a contained alias is safe.
      LINK_PARENT=${DIR%/*}
      LINK_CHECKOUT=$(git -C "${LINK_PARENT:-/}" rev-parse --show-toplevel 2>/dev/null || true)
      if [[ -n "$LINK_CHECKOUT" && "$LINK_CHECKOUT" != "$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null)" ]]; then
        CHECKOUT=$LINK_CHECKOUT
        break
      fi
    fi
    if [[ -z "$CHECKOUT" && -e "$DIR/.git" ]]; then
      CHECKOUT=$(cd "$DIR" && pwd -P)
    fi
    # Keep walking: an ancestor symlink can expose another checkout's .git.
  done
fi
case "$CHECKOUT" in
  "$PROJECT_DIR" | "$PROJECT_DIR"/*)
    # Resolving the path reads no file. A new file's directory may not exist
    # yet, so ask git from the nearest existing directory of the resolved path.
    REAL_PATH=$("$PYTHON" -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$ABSOLUTE_PATH")
    DIR=$REAL_PATH
    while DIR=${DIR%/*}; [[ -n "$DIR" && ! -d "$DIR" ]]; do :; done
    if [[ "$(git -C "${DIR:-/}" rev-parse --show-toplevel 2>/dev/null)" == "$CHECKOUT" ]]; then
      FILE_PATH=${REAL_PATH#"$CHECKOUT"/}
      cd "$CHECKOUT"
    else
      # A symlink in the checkout leads out of it, perhaps into another
      # checkout: keep the path absolute, which the checker refuses unread.
      FILE_PATH=$ABSOLUTE_PATH
    fi
    ;;
  *)
    # Outside every checkout in the project, or with a ".." segment, check the
    # path here without the project directory. The checker refuses a path that
    # stays absolute or climbs out with "..".
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

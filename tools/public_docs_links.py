"""Check that public pages link to paths that exist in this repository.

``docs/public/conf.py`` keeps links into this repository out of the Sphinx link check,
so ``tools/check_public_docs.py`` runs this check on the links that name repository
content instead. A checked link starts with a prefix that ``linkcheck_ignore`` skips,
``https://github.com/OpenRAE/rae/`` or ``https://github.com/RAESystem/rae/``, continues
with ``blob/<ref>/`` or ``tree/<ref>/``, and names ``main``, ``dev`` or ``HEAD`` as the ref.
Those branches carry this tree: ``dev`` takes it when the change merges, and ``main``
(``HEAD``, the default branch) at the next release. A ``blob`` link must therefore name a
file that git tracks in this checkout, and a ``tree`` link a directory that holds one.
Git's list matches case exactly, as GitHub does, and leaves out untracked files.

The check skips links on other refs (commit SHAs, tags, other branches), because they can
name content that this checkout does not have. It ignores fragments and query strings, and
it does not check links to issues, pull requests or other repository pages. It reads every
line of a source, code included, so it errs toward false positives, like the directive scan
in ``tools/public_docs_markup.py``.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from tools.policy.common import PolicyFailure

RULE_ID = "public-docs-repository-link"
# The prefixes that linkcheck_ignore in docs/public/conf.py skips, then a route. A URL ends
# where whitespace or the Markdown, MyST or reStructuredText markup around it begins.
REPOSITORY_LINK = re.compile(r"https://github\.com/(?:OpenRAE|RAESystem)/rae/(?:blob|tree)/[^\s<>()\[\]{}\"'`|\\*]*")
# Punctuation that ends a sentence after a bare URL rather than belonging to it.
TRAILING_PUNCTUATION = ".,;:!?"
CHECKED_REFS = frozenset({"dev", "main", "HEAD"})
ROUTE_KINDS = {"blob": "file", "tree": "directory"}
KIND_ROUTES = {kind: route for route, kind in ROUTE_KINDS.items()}


def evaluate_repository_links(repo_root: Path, pages: Mapping[str, str]) -> list[PolicyFailure]:
    """Return a failure for each checked link in ``pages`` that git's tracked files do not resolve.

    ``pages`` maps the repository path of each public source to its text. The check fails
    closed when git cannot list the files it tracks under ``repo_root``.
    """

    try:
        tracked = _tracked_files(repo_root)
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as exc:
        return [PolicyFailure(RULE_ID, f"cannot list the files git tracks: {exc}")]
    return repository_link_failures(pages, tracked)


def repository_link_failures(pages: Mapping[str, str], tracked: Iterable[str]) -> list[PolicyFailure]:
    """Return a failure, located at ``<page>:<line>``, for each checked link that ``tracked`` does not resolve.

    A ``blob`` link resolves to a path in ``tracked``. A ``tree`` link resolves to a directory
    above one, and an empty path names the repository root.
    """

    kinds = _path_kinds(tracked)
    failures = (
        PolicyFailure(RULE_ID, problem, f"{page}:{number}")
        for page, text in pages.items()
        for number, line in enumerate(text.split("\n"), start=1)
        for problem in _line_problems(line, kinds)
    )
    return list(dict.fromkeys(failures))


def _tracked_files(repo_root: Path) -> list[str]:
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=repo_root, check=True, capture_output=True).stdout
    return [path for path in listing.decode("utf-8").split("\0") if path]


def _path_kinds(tracked: Iterable[str]) -> dict[PurePosixPath, str]:
    files = [PurePosixPath(path) for path in tracked]
    kinds = {directory: "directory" for path in files for directory in path.parents}
    kinds.update(dict.fromkeys(files, "file"))
    return kinds


def _line_problems(line: str, kinds: Mapping[PurePosixPath, str]) -> Iterator[str]:
    for match in REPOSITORY_LINK.finditer(line):
        problem = _link_problem(match.group().rstrip(TRAILING_PUNCTUATION), kinds)
        if problem is not None:
            yield problem


def _link_problem(url: str, kinds: Mapping[PurePosixPath, str]) -> str | None:
    # The URL path is /<owner>/rae/<route>/<ref>/<repository path>; REPOSITORY_LINK fixes the route.
    route, ref, *segments = urlsplit(url).path.split("/")[3:]
    if ref not in CHECKED_REFS:
        return None
    path = PurePosixPath(unquote("/".join(segments)))
    expected = ROUTE_KINDS[route]
    actual = kinds.get(path)
    if actual == expected:
        return None
    if actual is None:
        return f"{url} does not resolve: this checkout tracks no {expected} at {path}"
    return f"{url} names a {actual}: link {path} with /{KIND_ROUTES[actual]}/, not /{route}/"

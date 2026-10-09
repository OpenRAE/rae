"""Find the files a public documentation page reads or links in its MyST or reStructuredText source.

``tools/check_public_docs.py`` decides whether each target stays inside ``docs/public``.
"""

from __future__ import annotations

import itertools
import re

# A MyST directive opens with a fence of three or more backticks, tildes or colons.
MYST_DIRECTIVE_FENCE = r"^[ \t]*[`~:]{3,}[ \t]*\{"
# Options that make a directive read a file: :file: and :url: (raw, csv-table) and
# :diff: (literalinclude). MyST also accepts quoted keys and `key : value`.
FILE_OPTION = r"[\"']?(?:file|url|diff)[\"']?[ \t]*:[ \t]+(\S+)"
LOCAL_DIRECTIVE_PATTERNS = (
    re.compile(r"^\s*\.\.\s+(?:include|literalinclude|download)::\s+(\S+)", re.MULTILINE | re.IGNORECASE),
    re.compile(MYST_DIRECTIVE_FENCE + r"(?:include|literalinclude|download)\}\s+(\S+)", re.MULTILINE | re.IGNORECASE),
    re.compile(r"\{download\}`(?:[^`<]*<)?([^>`]+)>?`", re.IGNORECASE),
    # reStructuredText option fields and MyST `:key: value` option lines.
    re.compile(r"^[ \t]*:" + FILE_OPTION, re.MULTILINE | re.IGNORECASE),
)
# MyST also reads options from a YAML block between `---` lines that opens the body.
MYST_DIRECTIVE_OPENING = re.compile(MYST_DIRECTIVE_FENCE)
YAML_FILE_OPTION = re.compile(r"^[ \t]*" + FILE_OPTION, re.IGNORECASE)
YAML_OPTION_DELIMITER = "---"
# Markdown inline links and images, then reference-style link definitions.
MARKDOWN_LINK_PATTERNS = (
    re.compile(r"\]\(\s*<?([^)\s>]+)"),
    re.compile(r"^[ \t]*\[(?!\^)[^\]\n]+\]:[ \t]*<?([^\s>]+)", re.MULTILINE),
)
FENCE_CHARACTERS = "`~:"
MIN_FENCE_LENGTH = 3
BACKTICK_RUN = re.compile(r"(`+)")
# MyST reads these directive bodies as code, data or reStructuredText, not as Markdown.
CODE_BODY_DIRECTIVES = frozenset(
    {"code", "code-block", "sourcecode", "literalinclude", "raw", "math", "eval-rst", "csv-table"}
)


def directive_targets(text: str) -> list[str]:
    """Return the paths that directives read: arguments, file options and download roles.

    Code blocks count too, so this scan errs toward false positives. It reads only the forms
    in LOCAL_DIRECTIVE_PATTERNS and MyST YAML option blocks. tools/public_docs_guard.py fails
    the build whatever markup reads the file.
    """

    targets = [match.group(1) for pattern in LOCAL_DIRECTIVE_PATTERNS for match in pattern.finditer(text)]
    return [target.strip().strip("\"'") for target in [*targets, *_yaml_option_targets(text)]]


def markdown_link_targets(text: str) -> list[str]:
    """Return Markdown link, image and reference-definition targets outside code.

    Code fences, code spans and the bodies of CODE_BODY_DIRECTIVES are code. Other
    directive and colon fence bodies are scanned, because MyST parses most of them as
    Markdown. A link this misses still fails the build guard and evaluate_published_assets
    once Sphinx copies its target.
    """

    prose = _markdown_outside_code(text)
    return [match.group(1) for pattern in MARKDOWN_LINK_PATTERNS for match in pattern.finditer(prose)]


def _yaml_option_block(body: list[str]) -> list[str]:
    """Return the YAML option lines that open a MyST directive body between ``---`` lines."""

    if not body or not body[0].lstrip().startswith(YAML_OPTION_DELIMITER):
        return []
    return list(itertools.takewhile(lambda line: not line.lstrip().startswith(YAML_OPTION_DELIMITER), body[1:]))


def _yaml_option_targets(text: str) -> list[str]:
    lines = text.splitlines()
    return [
        match.group(1)
        for index, line in enumerate(lines)
        if MYST_DIRECTIVE_OPENING.match(line)
        for match in map(YAML_FILE_OPTION.match, _yaml_option_block(lines[index + 1 :]))
        if match
    ]


def _fence(line: str) -> tuple[str, str] | None:
    """Return the marker run and info string of a fence line, or None for any other line."""

    stripped = line.lstrip(" \t")
    marker = stripped[:1]
    if not marker or marker not in FENCE_CHARACTERS:
        return None
    info = stripped.lstrip(marker)
    run = stripped[: len(stripped) - len(info)]
    return (run, info) if len(run) >= MIN_FENCE_LENGTH else None


def _closes(fence: tuple[str, str] | None, opening: str) -> bool:
    if fence is None:
        return False
    run, info = fence
    return run[0] == opening[0] and len(run) >= len(opening) and not info.strip()


def _opens_markdown_body(fence: tuple[str, str]) -> bool:
    # MyST parses a plain colon fence body, and most directive bodies (`{note}`), as Markdown.
    run, info = fence
    name = next(iter(info.split()), "")
    if name.startswith("{") and name.endswith("}"):
        return name[1:-1].casefold() not in CODE_BODY_DIRECTIVES
    return run[0] == ":"


def _markdown_outside_code(text: str) -> str:
    kept: list[str] = []
    markdown_fences: list[str] = []
    code_fence = ""
    for line in text.splitlines():
        fence = _fence(line)
        if code_fence:
            if _closes(fence, code_fence):
                code_fence = ""
        elif fence is None:
            kept.append(_without_code_spans(line))
        elif markdown_fences and _closes(fence, markdown_fences[-1]):
            markdown_fences.pop()
        elif _opens_markdown_body(fence):
            markdown_fences.append(fence[0])
            kept.append(_without_code_spans(line))
        else:
            code_fence = fence[0]
    return "\n".join(kept)


def _without_code_spans(line: str) -> str:
    """Drop inline code spans: a backtick run through the next run of the same length."""

    # Splitting on a capturing group alternates text (even indexes) and backtick runs (odd).
    pieces = BACKTICK_RUN.split(line)
    kept: list[str] = []
    index = 0
    while index < len(pieces):
        closing = _closing_run(pieces, index)
        if closing is None:
            kept.append(pieces[index])
            index += 1
        else:
            index = closing + 1
    return "".join(kept)


def _closing_run(pieces: list[str], index: int) -> int | None:
    if index % 2 == 0:
        return None
    return next((later for later in range(index + 2, len(pieces), 2) if pieces[later] == pieces[index]), None)

"""Find the files a public documentation page reads or links in its MyST or reStructuredText source.

``tools/check_public_docs.py`` decides whether each target stays inside ``docs/public``.
"""

from __future__ import annotations

import itertools
import re
from collections import deque
from collections.abc import Iterator
from typing import TYPE_CHECKING

from markdown_it.renderer import RendererHTML
from myst_parser.config.main import MdParserConfig
from myst_parser.parsers.mdit import create_md_parser

if TYPE_CHECKING:
    from markdown_it.token import Token

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

    Use MyST's tokenizer so code, indentation and block containers have the same
    meaning as in the build. Parse Markdown directive bodies without rendering or
    executing directives. Unused reference definitions remain boundary-checked.
    """

    parser = create_md_parser(
        MdParserConfig(enable_extensions={"colon_fence", "deflist", "fieldlist", "tasklist"}), RendererHTML
    )
    pending = [text]
    targets: list[str] = []
    while pending:
        environment = {}
        tokens = parser.parse(pending.pop(), environment)
        targets.extend(reference["href"] for reference in environment.get("references", {}).values())
        for token in _walk_tokens(tokens):
            if token.type in {"fence", "colon_fence"} and _opens_markdown_body(token):
                pending.append(token.content)
            elif token.type in {"link_open", "image"}:
                target = token.attrGet("href" if token.type == "link_open" else "src")
                if target is not None:
                    targets.append(target)
    return list(dict.fromkeys(targets))


def _walk_tokens(tokens: list[Token]) -> Iterator[Token]:
    pending = deque(tokens)
    while pending:
        token = pending.popleft()
        pending.extendleft(reversed(token.children or []))
        yield token


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


def _opens_markdown_body(token: Token) -> bool:
    # MyST parses a plain colon fence body, and most directive bodies (`{note}`), as Markdown.
    name = next(iter(token.info.split()), "")
    if name.startswith("{") and name.endswith("}"):
        return name[1:-1].casefold() not in CODE_BODY_DIRECTIVES
    return token.type == "colon_fence"

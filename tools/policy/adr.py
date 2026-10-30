"""Shared parsing helpers for Architecture Decision Records.

These were extracted from ``tools/policy/repo_policy.py`` so the README↔ADR
index check there and the ADR acceptance-content pin gate
(``tools/check_adr_immutability.py``, ADR-059) parse ADR headers, status, and
date the same way instead of each growing its own parser. ``repo_policy.py``
re-imports these under their historical private names.
"""

from __future__ import annotations

import re
from pathlib import Path

from raes_contracts.errors import InvalidInputError, OperationalError

# A canonical MADR ADR header, e.g. ``# ADR-048: Datastore Service Runtime
# Inventory``. Group 1 is the zero-padded number, group 2 the title.
ADR_HEADER_RE = re.compile(r"^# ADR-(\d{3}): (.+)$", re.MULTILINE)


def extract_markdown_section(text: str, section: str) -> str:
    """Return the first non-empty line of the ``## <section>`` block (or a
    legacy ``**<section>:**`` inline marker). Raises ``InvalidInputError``
    when the section is absent or empty."""
    marker = f"## {section}"
    start = text.find(marker)
    if start != -1:
        body = text[start + len(marker) :]
        body = body.lstrip()
        next_header = body.find("\n## ")
        if next_header != -1:
            body = body[:next_header]
        lines = body.strip().splitlines()
        if not lines:
            raise InvalidInputError(f"missing {section} section")
        return lines[0].strip()

    legacy_marker = re.search(rf"^\*\*{re.escape(section)}:\*\*\s*(.+)$", text, re.MULTILINE)
    if legacy_marker:
        return legacy_marker.group(1).strip()

    raise InvalidInputError(f"missing {section} section")


def normalize_adr_status(status: str) -> str:
    """Collapse whitespace and canonicalise the ADR status vocabulary.
    Recognised values are ``accepted``/``proposed``/``deprecated`` and
    ``superseded by ADR-NNN``; anything else is returned whitespace-normalised
    but otherwise untouched."""
    normalized = " ".join(status.split())
    lowered = normalized.lower()
    if lowered in {"accepted", "proposed", "deprecated"}:
        return lowered
    superseded = re.fullmatch(r"superseded by (adr-\d{3})", lowered)
    if superseded:
        return f"superseded by {superseded.group(1).upper()}"
    return normalized


def parse_adr_file(path: Path) -> tuple[str, str, str, str]:
    """Parse an ADR file into ``(number, title, status, date)``. Raises
    ``InvalidInputError`` when the file is not UTF-8 text or the header or a
    required section is missing, and ``OperationalError`` when the host cannot
    read the file."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidInputError(f"{path} is not UTF-8 text") from exc
    except OSError as exc:
        raise OperationalError(f"{path} could not be read") from exc
    header = ADR_HEADER_RE.search(text)
    if not header:
        raise InvalidInputError(f"{path} is missing ADR header")
    status = normalize_adr_status(extract_markdown_section(text, "Status"))
    date = extract_markdown_section(text, "Date")
    return header.group(1), header.group(2).strip(), status.strip(), date.strip()

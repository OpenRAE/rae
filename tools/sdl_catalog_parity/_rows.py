"""Catalog table dataclasses and markdown-table parsing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tools.sdl_catalog_parity._paths import (
    _BACKTICK_RE,
    _MAX_CATALOG_BYTES,
    _MAX_CATALOG_ROWS,
    _PHASE_HEADING,
    _REFERENCE_HEADING,
    _RUNTIME_HEADING,
    _SEPARATOR_RE,
    _TOP_LEVEL_HEADING,
)


class CatalogParseError(ValueError):
    """A normative catalog table is absent or malformed."""


@dataclass(frozen=True)
class TopLevelRow:
    field: str
    kind: str
    shape: str
    lifecycle: tuple[str, ...]
    presence: str
    identity: str
    references: str
    owner: str
    line_no: int


@dataclass(frozen=True)
class ReferenceRow:
    source_path: str
    domain: str
    phase: str
    failure: str
    normative_owner: str
    evidence: str
    line_no: int

    @property
    def key(self) -> tuple[str, str]:
        parts = self.source_path.replace("[]", "").split(".")
        return parts[0], parts[-1]


@dataclass(frozen=True)
class RuntimeRow:
    key: str
    collection: str
    primary_id: str
    child_paths: tuple[str, ...]
    owner: str
    line_no: int


@dataclass(frozen=True)
class PhaseMemberRow:
    member: str
    normalized: str
    expanded: str
    instantiated: str
    materialized: str
    transfer: str
    line_no: int


def _cells(line: str) -> list[str]:
    parts = [part.strip() for part in line.strip().split("|")]
    if parts and not parts[0]:
        parts.pop(0)
    if parts and not parts[-1]:
        parts.pop()
    return parts


def _unquote(cell: str) -> str:
    match = _BACKTICK_RE.fullmatch(cell.strip())
    return match.group(1) if match else cell.strip()


def _table_lines(lines: list[str], start: int) -> list[tuple[int, list[str]]]:
    table: list[tuple[int, list[str]]] = []
    started = False
    for index, line in enumerate(lines[start:], start=start):
        if line.startswith("## "):
            break
        if line.lstrip().startswith("|"):
            started = True
            table.append((index + 1, _cells(line)))
            if len(table) > _MAX_CATALOG_ROWS + 2:
                raise CatalogParseError(f"catalog exceeds {_MAX_CATALOG_ROWS}-row limit")
        elif started:
            break
    return table


def _validated_table_rows(
    table: list[tuple[int, list[str]]],
    heading: str,
    columns: int,
) -> list[tuple[int, list[str]]]:
    if len(table) < 3:
        raise CatalogParseError(f"catalog under {heading!r} requires a header, separator, and data rows")
    if len(table[0][1]) != columns:
        raise CatalogParseError(f"catalog under {heading!r} has {len(table[0][1])} columns; expected {columns}")
    separator = table[1][1]
    if len(separator) != columns or not all(_SEPARATOR_RE.fullmatch(cell) for cell in separator):
        raise CatalogParseError(f"catalog under {heading!r} has a malformed separator row")
    for line_no, cells in table[2:]:
        if len(cells) != columns:
            raise CatalogParseError(f"catalog row at line {line_no} has {len(cells)} columns; expected {columns}")
    return table[2:]


def _table(text: str, heading: str, columns: int) -> list[tuple[int, list[str]]]:
    size = len(text.encode("utf-8"))
    if size > _MAX_CATALOG_BYTES:
        raise CatalogParseError(f"catalog exceeds {_MAX_CATALOG_BYTES}-byte size limit")
    lines = text.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == heading) + 1
    except StopIteration as exc:
        raise CatalogParseError(f"missing catalog heading: {heading}") from exc
    return _validated_table_rows(_table_lines(lines, start), heading, columns)


def _unique(rows: list[Any], key_name: str, label: str) -> None:
    seen: dict[str, int] = {}
    for row in rows:
        key = getattr(row, key_name)
        if key in seen:
            raise CatalogParseError(f"duplicate {label} {key!r} at lines {seen[key]} and {row.line_no}")
        seen[key] = row.line_no


def parse_top_level_catalog(text: str) -> list[TopLevelRow]:
    rows = [
        TopLevelRow(
            field=_unquote(cells[0]),
            kind=cells[1].lower(),
            shape=cells[2].lower(),
            lifecycle=tuple(token.strip().lower() for token in cells[3].split(",") if token.strip()),
            presence=cells[4].strip().lower(),
            identity=_unquote(cells[5]),
            references=cells[6].strip().lower(),
            owner=cells[7].strip(),
            line_no=line_no,
        )
        for line_no, cells in _table(text, _TOP_LEVEL_HEADING, 8)
    ]
    _unique(rows, "field", "top-level field")
    return rows


def parse_reference_catalog(text: str) -> list[ReferenceRow]:
    rows = [
        ReferenceRow(
            source_path=_unquote(cells[0]),
            domain=_unquote(cells[1]),
            phase=cells[2].strip().lower(),
            failure=cells[3].strip().lower(),
            normative_owner=cells[4].strip(),
            evidence=cells[5].strip(),
            line_no=line_no,
        )
        for line_no, cells in _table(text, _REFERENCE_HEADING, 6)
    ]
    _unique(rows, "source_path", "reference edge")
    return rows


def parse_runtime_catalog(text: str) -> list[RuntimeRow]:
    rows = [
        RuntimeRow(
            key=_unquote(cells[0]),
            collection=_unquote(cells[1]),
            primary_id=_unquote(cells[2]),
            child_paths=tuple(token.strip() for token in _unquote(cells[3]).split(",") if token.strip() != "none"),
            owner=cells[4].strip(),
            line_no=line_no,
        )
        for line_no, cells in _table(text, _RUNTIME_HEADING, 5)
    ]
    _unique(rows, "key", "runtime family")
    return rows


def parse_phase_member_catalog(text: str) -> list[PhaseMemberRow]:
    rows = [
        PhaseMemberRow(
            member=_unquote(cells[0]),
            normalized=cells[1].strip().lower(),
            expanded=cells[2].strip().lower(),
            instantiated=cells[3].strip().lower(),
            materialized=cells[4].strip().lower(),
            transfer=cells[5].strip(),
            line_no=line_no,
        )
        for line_no, cells in _table(text, _PHASE_HEADING, 6)
    ]
    _unique(rows, "member", "phase-specific member")
    return rows

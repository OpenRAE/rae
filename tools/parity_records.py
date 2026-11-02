"""Serialized parity records shared by the surface adapters."""

from __future__ import annotations

from collections.abc import Mapping

from tools.parity_support import Case, digest


def case_document(case: Case, result: Mapping[str, object]) -> dict[str, object]:
    """Return the JSON document that records one case and its result."""

    return {
        "name": case.name,
        "surface": case.surface,
        "command": case.command,
        "args": list(case.args),
        "files": {name: digest(content) for name, content in sorted(case.files.items())},
        "result": dict(result),
    }

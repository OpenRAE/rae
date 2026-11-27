"""Load contract fixtures with their derived fields filled (issue #1929).

Fixtures leave out derived fields such as self-digests. This loader fills them the
way the owning contract computes them, so a fixture edit never needs a digest edit.
"""

from __future__ import annotations

import json
from pathlib import Path

from raes_contracts.contract_seals import seal_contract_fixture


def load_contract_fixture(path: Path | str) -> object:
    """Return the decoded fixture at *path*, sealed for its contract and fixture kind."""
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return seal_contract_fixture(path.parent.parent.name, payload, kind=path.parent.name)


def contract_fixture_text(path: Path | str) -> str:
    """Return the sealed fixture at *path* as JSON text, for readers that parse text."""
    return json.dumps(load_contract_fixture(path))

from __future__ import annotations

from pathlib import Path

import pytest
from raes.agent_guidance import agent_guidance
from raes_contracts.errors import OperationalError


def test_agent_guidance_exposes_required_categories() -> None:
    payload = agent_guidance()

    assert payload["status"] == "ok"
    assert payload["profile"] == "raes-agent-guidance"
    assert "AUT-811" in payload["requirement_refs"]
    assert set(payload["guidance"]) == {
        "scope_boundaries",
        "invariants",
        "review_priorities",
        "safe_operating_expectations",
    }


def test_agent_guidance_filters_operator_entries() -> None:
    payload = agent_guidance(audience="operator")

    assert payload["status"] == "ok"
    assert payload["audience"] == "operator"
    for entries in payload["guidance"].values():
        assert entries
        assert all("operator" in entry["audience"] for entry in entries)


def test_agent_guidance_rejects_unknown_audience() -> None:
    payload = agent_guidance(audience="auditor")

    assert payload["status"] == "invalid"
    assert payload["diagnostics"][0]["code"] == "agent_guidance.audience"


class _InstalledLocation(type(Path())):
    """A location with no repository markers, as in an installed distribution."""

    def exists(self, *, follow_symlinks: bool = True) -> bool:
        return False


def test_agent_guidance_outside_a_checkout_is_an_operational_failure(tmp_path: Path) -> None:
    from raes.agent_guidance import _find_repo_root

    with pytest.raises(OperationalError, match="could not locate RAES repo root"):
        _find_repo_root(_InstalledLocation(tmp_path))

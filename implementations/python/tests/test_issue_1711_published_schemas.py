"""Published schemas read as data from the normative corpus (ADR-009, ADR-121; issue #1711)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from raes_contracts.published_schemas import published_contract_ids, published_schema

SCHEMAS_ROOT = Path(__file__).resolve().parents[3] / "contracts" / "schemas"
PUBLISHED_FILES = {path.stem: path for path in SCHEMAS_ROOT.rglob("*.json")}


def test_contract_ids_are_the_published_schema_files() -> None:
    assert published_contract_ids() == frozenset(PUBLISHED_FILES)


@pytest.mark.parametrize("contract_id", ["participant-control-selection-v2", "sdl-authoring-input-v1"])
def test_each_schema_is_the_published_file_content(contract_id: str) -> None:
    assert published_schema(contract_id) == json.loads(PUBLISHED_FILES[contract_id].read_text(encoding="utf-8"))


def test_each_read_returns_an_isolated_copy() -> None:
    first = published_schema("participant-control-evaluation-v2")
    first["title"] = "changed"
    first.setdefault("properties", {}).clear()

    assert published_schema("participant-control-evaluation-v2") == json.loads(
        PUBLISHED_FILES["participant-control-evaluation-v2"].read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    "contract_id",
    [
        "no-such-contract-v1",
        "../schemas/participant-control-selection-v2",
        "control-plane/participant-control-selection-v2",
        "/etc/passwd",
        "",
    ],
)
def test_an_unknown_or_path_shaped_id_is_refused_without_a_file_read(contract_id: str) -> None:
    with pytest.raises(KeyError):
        published_schema(contract_id)


def test_required_contract_schemas_keep_order_and_refuse_a_missing_schema() -> None:
    from raes_conformance.conformance.report import required_contract_schemas
    from raes_contracts.errors import OperationalError

    schemas = required_contract_schemas(["sdl-authoring-input-v1", "participant-control-selection-v2"])

    assert list(schemas) == ["sdl-authoring-input-v1", "participant-control-selection-v2"]
    assert schemas["sdl-authoring-input-v1"] == published_schema("sdl-authoring-input-v1")
    with pytest.raises(OperationalError, match="no-such-contract-v1 has no published schema"):
        required_contract_schemas(["sdl-authoring-input-v1", "no-such-contract-v1"])


def test_the_fixture_suite_fails_when_a_required_contract_has_no_published_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from raes_conformance.conformance import report
    from raes_conformance.conformance.fixture_suite import run_fixture_suite
    from raes_conformance.conformance.profiles import BackendCapabilityProfile
    from raes_contracts.errors import OperationalError

    def missing(contract_id: str) -> dict[str, object]:
        raise KeyError(contract_id)

    monkeypatch.setattr(report, "published_schema", missing)

    with pytest.raises(OperationalError, match="has no published schema"):
        run_fixture_suite(profile=BackendCapabilityProfile.ORCHESTRATION_EVALUATION)

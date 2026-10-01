"""Regression coverage for the portable service-manager contract in issue #1297.

These tests exercise SDL contracts and realization comparison only.  They do
not claim discovery of, or execution against, a live service manager.
"""

from __future__ import annotations

import textwrap
from copy import deepcopy

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes import instantiate_scenario, parse_sdl
from raes.runtime_service_units import ServiceManagerKind, ServiceManagerUnit, ServiceUnitActiveState
from raes_contracts.contracts import schema_bundle
from raes_contracts.realization_structure import evaluate_realization_constraint
from raes_processor.compiler import compile_runtime_model
from raes_processor.semantics.realization_concerns import realization_concern_descriptor


def _authoring_payload(unit: dict[str, object]) -> dict[str, object]:
    return {
        "name": "issue-1297-service-manager-contract",
        "nodes": {
            "host": {
                "type": "compute",
                "resources": {"ram": "1 gib", "cpu": 1},
                "runtime": {"service_manager_units": [unit]},
            }
        },
    }


@pytest.mark.parametrize("manager_kind", ["x-openrc:openrc", "x-private:supervisor"])
def test_private_manager_native_names_round_trip_without_systemd_suffix(manager_kind: str) -> None:
    unit = ServiceManagerUnit(unit_id="web", manager_kind=manager_kind, unit_name="nginx")

    reparsed = ServiceManagerUnit.model_validate_json(unit.model_dump_json())

    assert reparsed.manager_kind == manager_kind
    assert reparsed.unit_name == "nginx"


def test_explicit_systemd_still_requires_a_suffixed_native_name() -> None:
    with pytest.raises(ValidationError, match="unit_name"):
        ServiceManagerUnit(unit_id="web", manager_kind=ServiceManagerKind.SYSTEMD, unit_name="nginx")


def test_partial_unit_omits_manager_and_native_name_without_inventing_author_intent() -> None:
    unit = ServiceManagerUnit(unit_id="web")

    assert unit.manager_kind is ServiceManagerKind.SYSTEMD  # historical read compatibility
    assert unit.unit_name == ""
    assert "manager_kind" not in unit.model_fields_set
    assert "unit_name" not in unit.model_fields_set


def test_private_manager_rejects_explicit_systemd_state() -> None:
    with pytest.raises(ValidationError, match="systemd"):
        ServiceManagerUnit(
            unit_id="web",
            manager_kind="x-openrc:openrc",
            unit_name="nginx",
            active_state="active",
        )


def test_authoring_schema_matches_native_name_and_partiality_rules() -> None:
    validator = Draft202012Validator(schema_bundle()["sdl-authoring-input-v1"])

    assert validator.is_valid(
        _authoring_payload({"unit_id": "web", "manager_kind": "x-openrc:openrc", "unit_name": "nginx"})
    )
    assert validator.is_valid(_authoring_payload({"unit_id": "web"}))
    assert not validator.is_valid(
        _authoring_payload({"unit_id": "web", "manager_kind": "systemd", "unit_name": "nginx"})
    )
    assert not validator.is_valid(
        _authoring_payload({"unit_id": "web", "manager_kind": "SyStEmD", "unit_name": "nginx"})
    )
    assert not validator.is_valid(
        _authoring_payload(
            {
                "unit_id": "web",
                "manager_kind": "x-openrc:openrc",
                "unit_name": "nginx",
                "active_state": "active",
            }
        )
    )
    assert not validator.is_valid(
        _authoring_payload(
            {
                "unit_id": "web",
                "manager_kind": "OtHeR",
                "unit_name": "nginx",
                "active_state": "active",
            }
        )
    )


def test_service_manager_projection_is_keyed_and_presence_sensitive() -> None:
    descriptor = realization_concern_descriptor("runtime-service-manager-units")
    assert descriptor is not None
    assert descriptor.collection_identity_fields == ("unit_id",)

    projected = descriptor.project(
        [
            ServiceManagerUnit(
                unit_id="web",
                manager_kind="x-openrc:openrc",
                unit_name="nginx",
                active_state=ServiceUnitActiveState.UNKNOWN,
            )
        ],
        recursive=True,
    )

    assert projected == [{"unit_id": "web", "manager_kind": "x-openrc:openrc", "unit_name": "nginx"}]


def test_open_parent_compiles_exact_native_name_with_delegated_omissions() -> None:
    source = parse_sdl(
        textwrap.dedent(
            """
            name: issue-1297-open-service-manager
            realization:
              default: closed
              scopes:
                - field_pointer: /nodes/host/runtime/service_manager_units
                  posture: open
            nodes:
              host:
                type: compute
                resources: {ram: 1 gib, cpu: 1}
                runtime:
                  service_manager_units:
                    - unit_id: web
                      unit_name: nginx
            """
        )
    )

    instantiated = instantiate_scenario(source)
    unit = instantiated.nodes["host"].runtime.service_manager_units[0]
    compiled = compile_runtime_model(instantiated)
    requirement = next(
        item for item in compiled.realization_requirements if item.requirement_kind == "runtime-service-manager-units"
    )

    assert unit.unit_name == "nginx"
    assert "manager_kind" not in unit.model_fields_set
    assert requirement.constraint_document is not None
    assert requirement.constraint_document.root.identity_fields == ("unit_id",)
    assert set(requirement.constraint_document.root.members[0].constraint.fields) == {"unit_id", "unit_name"}


def test_declared_and_observed_private_units_compare_by_unit_id() -> None:
    runtime = {
        "service_manager_units": [
            {"unit_id": "web", "manager_kind": "x-openrc:openrc", "unit_name": "nginx"},
            {"unit_id": "jobs", "manager_kind": "x-private:supervisor", "unit_name": "worker"},
        ]
    }
    source = {
        "name": "issue-1297-private-unit-comparison",
        "realization": {
            "default": "closed",
            "scopes": [{"field_pointer": "/nodes/host/runtime/service_manager_units", "posture": "open"}],
        },
        "nodes": {"host": {"type": "compute", "runtime": runtime}},
    }
    compiled = compile_runtime_model(parse_sdl(yaml.safe_dump(source)))
    requirement = next(
        item for item in compiled.realization_requirements if item.requirement_kind == "runtime-service-manager-units"
    )
    assert requirement.constraint_document is not None
    descriptor = realization_concern_descriptor("runtime-service-manager-units")
    assert descriptor is not None

    reordered = {"service_manager_units": list(reversed(runtime["service_manager_units"]))}
    changed = deepcopy(runtime)
    changed["service_manager_units"][0]["unit_name"] = "nginx-renamed"

    assert evaluate_realization_constraint(
        requirement.constraint_document,
        descriptor.project(reordered["service_manager_units"], recursive=True),
    ).conformant
    assert not evaluate_realization_constraint(
        requirement.constraint_document,
        descriptor.project(changed["service_manager_units"], recursive=True),
    ).conformant

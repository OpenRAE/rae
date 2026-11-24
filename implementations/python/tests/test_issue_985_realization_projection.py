"""Issue #985: canonical runtime-concern comparison and disclosure."""

from __future__ import annotations

import copy
from unittest.mock import ANY

import pytest
from raes_contracts.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_processor.semantics.realization import (
    CompiledRealizationRequirement,
    project_realization_concern,
    realization_disclosure,
)


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (
            "runtime-environment",
            [
                {
                    "name": "SECOND",
                    "value": "two",
                    "value_classification": "plain",
                    "provenance": "runtime",
                    "source": "",
                    "description": "ignored",
                },
                {
                    "name": "FIRST",
                    "value": "one",
                    "value_classification": "secret_fixture",
                    "provenance": "operator",
                    "source": "fixture",
                },
            ],
        ),
        (
            "runtime-mounts",
            [
                {
                    "target": "/z",
                    "source": "/srv/z",
                    "source_sensitivity": "plain",
                    "source_kind": "bind",
                    "filesystem_type": "ext4",
                    "read_only": False,
                    "options": ["nosuid", "nodev"],
                    "options_sensitivity": "plain",
                    "propagation": "rprivate",
                    "stability": "stable",
                    "backend_generated": False,
                },
                {
                    "target": "/tmp",
                    "source": "",
                    "source_sensitivity": "unknown",
                    "source_kind": "tmpfs",
                    "filesystem_type": "tmpfs",
                    "read_only": False,
                    "options": [],
                    "options_sensitivity": "unknown",
                    "propagation": "unknown",
                    "stability": "transient",
                    "backend_generated": True,
                },
            ],
        ),
        (
            "published-ports",
            [
                {"host_ip": "", "host_port": 8443, "container_port": 443, "protocol": "tcp"},
                {"host_ip": "127.0.0.1", "host_port": 5353, "container_port": 53, "protocol": "udp"},
            ],
        ),
    ],
)
def test_canonical_projection_is_order_stable_and_omits_annotations(
    kind: str,
    value: list[dict[str, object]],
) -> None:
    reverse = copy.deepcopy(list(reversed(value)))
    for item in reverse:
        item["description"] = "a different annotation"

    first = project_realization_concern(kind, value)
    second = project_realization_concern(kind, reverse)

    assert first == second
    assert project_realization_concern(kind, first, observed=True) == first
    assert "description" not in repr(first)


def test_environment_projection_uses_a_versioned_domain_separated_commitment() -> None:
    projection = project_realization_concern(
        "runtime-environment",
        [
            {
                "name": "TOKEN",
                "value": "do-not-disclose",
                "value_classification": "secret_fixture",
                "provenance": "operator",
                "source": "fixture",
            }
        ],
    )

    assert projection == [
        {
            "name": "TOKEN",
            "value_classification": "secret_fixture",
            "provenance": "operator",
            "source": "fixture",
            "value_present": True,
            "value_commitment": ANY,
        }
    ]
    commitment = projection[0]["value_commitment"]
    assert isinstance(commitment, str)
    assert commitment.startswith("raes-runtime-value-jcs-sha256-v1:")
    assert "do-not-disclose" not in commitment


def test_mount_projection_rejects_raw_material_marked_operator_secret() -> None:
    with pytest.raises(ValueError, match="protected runtime mount source"):
        project_realization_concern(
            "runtime-mounts",
            [
                {
                    "target": "/run/secret",
                    "source": "/operator/private/source",
                    "source_sensitivity": "operator_secret",
                    "source_kind": "bind",
                    "options": [],
                    "options_sensitivity": "plain",
                }
            ],
        )


def test_capability_projection_normalizes_sets_and_keeps_process_scope() -> None:
    first = {
        "required": ["CAP_SYS_PTRACE", "CAP_NET_ADMIN"],
        "effective": ["CAP_NET_ADMIN"],
        "add": ["CAP_SYS_PTRACE", "CAP_NET_ADMIN"],
        "drop": ["CAP_SYS_ADMIN"],
        "process_overrides": [
            {
                "subject": {
                    "name": "worker",
                    "pid": None,
                    "parent_pid": None,
                    "command": ["/usr/bin/worker"],
                    "command_redacted": False,
                    "role": "worker",
                    "user": "app",
                    "group": "app",
                    "working_directory": "/srv/app",
                },
                "scope": "subtree",
                "effective": ["CAP_NET_ADMIN"],
                "add": ["CAP_NET_ADMIN"],
                "drop": ["CAP_SYS_ADMIN"],
            }
        ],
    }
    reordered = copy.deepcopy(first)
    reordered["required"].reverse()
    reordered["add"].reverse()

    assert project_realization_concern("linux-capabilities", first) == (
        project_realization_concern("linux-capabilities", reordered)
    )
    projection = project_realization_concern("linux-capabilities", first)
    assert project_realization_concern("linux-capabilities", projection, observed=True) == projection
    changed = copy.deepcopy(first)
    changed["process_overrides"][0]["scope"] = "process"
    assert project_realization_concern("linux-capabilities", first) != (
        project_realization_concern("linux-capabilities", changed)
    )


def test_listener_projection_excludes_readiness_but_keeps_bind_semantics() -> None:
    listener = {
        "service_listener_id": "https",
        "service": "",
        "address": "*",
        "port": 443,
        "protocol": "tcp",
        "address_family": "ipv4",
        "scope": "wildcard",
        "bind_interface": "",
        "socket_path": "",
        "process_ref": "",
        "process_name": "web",
        "published_port_refs": [],
        "readiness": {"probe": "curl", "criteria": "ready"},
        "evidence_refs": ["evidence.one"],
    }
    different_evidence = copy.deepcopy(listener)
    different_evidence["readiness"]["criteria"] = "different"
    different_evidence["evidence_refs"] = ["evidence.two"]

    assert project_realization_concern("service-listeners", [listener]) == (
        project_realization_concern("service-listeners", [different_evidence])
    )
    different_bind = copy.deepcopy(listener)
    different_bind["port"] = 8443
    assert project_realization_concern("service-listeners", [listener]) != (
        project_realization_concern("service-listeners", [different_bind])
    )
    different_publication = copy.deepcopy(listener)
    different_publication["published_port_refs"] = [
        {
            "host_ip": "127.0.0.1",
            "host_port": 8443,
            "container_port": 443,
            "protocol": "tcp",
        }
    ]
    assert project_realization_concern("service-listeners", [listener]) == (
        project_realization_concern("service-listeners", [different_publication])
    )
    projection = project_realization_concern("service-listeners", [listener])
    assert project_realization_concern("service-listeners", projection, observed=True) == projection


def test_forwarding_projection_commits_settings_and_sorts_stable_ids() -> None:
    agents = [
        {
            "forwarding_agent_id": "agent",
            "implementation": "other",
            "agent_kind": "other",
            "sources": [
                {"source_id": "second", "kind": "tailed_path", "location": "/b"},
                {"source_id": "first", "kind": "tailed_path", "location": "/a"},
            ],
            "transforms": [],
            "ship_targets": [],
            "buffer_policy": None,
            "reload_channels": [],
            "settings": [
                {
                    "setting_id": "token",
                    "name": "token",
                    "value": "fixture-value",
                    "provenance": "configuration_file",
                    "classification": "plain",
                }
            ],
        }
    ]
    reordered = copy.deepcopy(agents)
    reordered[0]["sources"].reverse()

    projection = project_realization_concern("forwarding-agents", agents)
    assert projection == project_realization_concern("forwarding-agents", reordered)
    assert project_realization_concern("forwarding-agents", projection, observed=True) == projection
    assert "fixture-value" not in repr(projection)
    assert projection[0]["settings"][0]["value_commitment"].startswith("raes-runtime-value-jcs-sha256-v1:")


def _runtime_disclosure(
    *,
    declared_value: object,
    realized_value: object,
) -> tuple[list, tuple]:
    requirement = CompiledRealizationRequirement(
        field_path="nodes.worker.runtime.environment",
        address="provision.node.worker",
        domain="runtime-realization",
        requirement_kind="runtime-environment",
        explicitness=ExplicitnessClass.EXACT,
        provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
    )

    def payload(value: object) -> dict[str, object]:
        return {"spec": {"node": {"runtime": {"environment": value}}}}

    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=requirement.address,
                resource_type="node",
                payload=payload(declared_value),
            )
        ]
    )
    snapshot = RuntimeSnapshot(
        entries={
            requirement.address: SnapshotEntry(
                address=requirement.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload=payload(realized_value),
            )
        }
    )
    return realization_disclosure((requirement,), plan, snapshot)


def test_runtime_gate_compares_canonical_meaning_but_rejects_a_real_change() -> None:
    declared = [
        {
            "name": "A",
            "value": "one",
            "value_classification": "plain",
            "provenance": "runtime",
            "source": "",
        },
        {
            "name": "B",
            "value": "two",
            "value_classification": "plain",
            "provenance": "runtime",
            "source": "",
        },
    ]

    diagnostics, provenance = _runtime_disclosure(
        declared_value=declared,
        realized_value=list(reversed(declared)),
    )
    assert diagnostics == []
    assert provenance[0].field_path == "nodes.worker.runtime.environment"

    changed = copy.deepcopy(declared)
    changed[0]["value"] = "different"
    diagnostics, provenance = _runtime_disclosure(
        declared_value=declared,
        realized_value=changed,
    )
    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()
    assert "one" not in diagnostics[0].message
    assert "different" not in diagnostics[0].message


def test_runtime_gate_requires_secret_fixture_readback_to_use_a_commitment() -> None:
    declared = [
        {
            "name": "TOKEN",
            "value": "fixture-secret",
            "value_classification": "secret_fixture",
            "provenance": "operator",
            "source": "fixture",
        }
    ]
    projected = project_realization_concern("runtime-environment", declared)
    committed_observation = [
        {
            "name": "TOKEN",
            "value_classification": "secret_fixture",
            "provenance": "operator",
            "source": "fixture",
            "value_present": True,
            "value_commitment": projected[0]["value_commitment"],
        }
    ]

    diagnostics, provenance = _runtime_disclosure(
        declared_value=declared,
        realized_value=committed_observation,
    )
    assert diagnostics == []
    assert provenance

    diagnostics, provenance = _runtime_disclosure(
        declared_value=declared,
        realized_value=declared,
    )
    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()
    assert "fixture-secret" not in diagnostics[0].message

"""Issue #985: runtime-configuration concerns use the SEM-218 demand graph."""

from __future__ import annotations

import copy
import textwrap
from dataclasses import replace

import pytest
from raes import SDLValidationError, instantiate_scenario, parse_sdl
from raes_backend_stubs.stubs import create_stub_manifest
from raes_contracts.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_contracts.planning import ChangeAction, RuntimeDomain
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import RuntimeModel
from raes_processor.planner import plan
from raes_processor.semantics.realization import (
    CompiledRealizationRequirement,
    project_realization_concern,
    sanitize_realization_snapshot,
)

_RUNTIME_SCENARIO = """
name: issue-985-runtime-concerns
nodes:
  worker:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    runtime:
      environment:
        - name: API_TOKEN
          value: deliberate-fixture-value
          value_classification: secret_fixture
          provenance: operator
          source: harness
      mounts:
        - target: /work
          source: /srv/work
          source_kind: bind
          filesystem_type: ext4
          read_only: true
          options: [nodev, nosuid]
          propagation: rprivate
          stability: stable
          backend_generated: false
      linux_capabilities:
        required: [CAP_NET_ADMIN]
        effective: [CAP_NET_ADMIN]
        add: [CAP_NET_ADMIN]
        drop: [CAP_SYS_ADMIN]
      network:
        published_ports:
          - {host_ip: 127.0.0.1, host_port: 8443, container_port: 443, protocol: tcp}
      forwarding_agents:
        - forwarding_agent_id: telemetry
          implementation: other
          agent_kind: other
          settings:
            - setting_id: endpoint
              name: endpoint
              value: https://collector.invalid
              classification: plain
              provenance: configuration_file
      service_listeners:
        - service_listener_id: https
          address: 0.0.0.0
          port: 443
          protocol: tcp
          address_family: ipv4
          scope: wildcard
          process_name: web
          readiness:
            probe: curl
            criteria: status-200
            evidence_refs: [evidence.not-realization]
"""

_EXPECTED_RUNTIME_CONCERNS = {
    "nodes.worker.runtime.environment": "runtime-environment",
    "nodes.worker.runtime.mounts": "runtime-mounts",
    "nodes.worker.runtime.linux_capabilities": "linux-capabilities",
    "nodes.worker.runtime.network.published_ports": "published-ports",
    "nodes.worker.runtime.forwarding_agents": "forwarding-agents",
    "nodes.worker.runtime.service_listeners": "service-listeners",
}


def _compiled_runtime_requirements() -> dict[str, CompiledRealizationRequirement]:
    model = compile_runtime_model(parse_sdl(textwrap.dedent(_RUNTIME_SCENARIO)))
    return {
        requirement.field_path: requirement
        for requirement in model.realization_requirements
        if requirement.field_path in _EXPECTED_RUNTIME_CONCERNS
    }


def test_compiler_lowers_all_six_runtime_dimensions_with_aggregate_explicitness() -> None:
    requirements = _compiled_runtime_requirements()

    assert {path: requirement.requirement_kind for path, requirement in requirements.items()} == (
        _EXPECTED_RUNTIME_CONCERNS
    )
    assert all(requirement.address == "provision.node.worker" for requirement in requirements.values())
    classified = instantiate_scenario(parse_sdl(textwrap.dedent(_RUNTIME_SCENARIO))).explicitness
    assert all(
        requirement.explicitness is classified[path].classification for path, requirement in requirements.items()
    )
    assert all(
        requirement.provenance is ExplicitnessProvenance.AUTHOR_DECLARED for requirement in requirements.values()
    )


def test_constrained_runtime_dimension_requires_its_manifest_concern_kind() -> None:
    scenario = parse_sdl(
        textwrap.dedent(
            """
            name: issue-985-constrained-environment
            variables:
              token:
                type: string
                default: first
                allowed_values: [first, second]
            nodes:
              worker:
                type: compute
                os: linux
                resources: {ram: 1 gib, cpu: 1}
                runtime:
                  environment:
                    - name: MODE
                      value: ${token}
                      value_classification: plain
                      provenance: runtime
            """
        )
    )
    model = compile_runtime_model(scenario)
    requirement = next(
        item for item in model.realization_requirements if item.requirement_kind == "runtime-environment"
    )

    rejected = plan(model, create_stub_manifest())
    declaration = create_stub_manifest().realization_support[0]
    supported_manifest = replace(
        create_stub_manifest(),
        realization_support=(
            replace(
                declaration,
                supported_constraint_kinds=(
                    declaration.supported_constraint_kinds | frozenset({"runtime-environment"})
                ),
            ),
        ),
    )
    bounded_only_by_private_runtime_values = plan(model, supported_manifest)

    assert requirement.explicitness is ExplicitnessClass.CONSTRAINED
    assert any(
        diagnostic.code == "realization.unsupported-constraint-requirement"
        and "runtime-environment" in diagnostic.message
        for diagnostic in rejected.diagnostics
    )
    supported_codes = {diagnostic.code for diagnostic in bounded_only_by_private_runtime_values.diagnostics}
    assert "realization.unsupported-constraint-requirement" not in supported_codes
    assert "realization.authority-bound-unavailable" in supported_codes
    assert not any(
        entry.requirement_kind == "runtime-environment"
        for entry in bounded_only_by_private_runtime_values.provisioning.realization_authority
    )
    assert not bounded_only_by_private_runtime_values.is_valid


def test_nested_open_designation_lowers_an_omitted_runtime_dimension() -> None:
    model = compile_runtime_model(
        parse_sdl(
            textwrap.dedent(
                """
                name: issue-985-open-runtime
                realization:
                  default: closed
                  scopes:
                    - field_pointer: /nodes/worker/runtime/environment
                      posture: open
                nodes:
                  worker:
                    type: compute
                    os: linux
                    resources: {ram: 1 gib, cpu: 1}
                    runtime: {}
                """
            )
        )
    )

    requirement = next(
        item for item in model.realization_requirements if item.field_path == "nodes.worker.runtime.environment"
    )
    assert requirement.explicitness is ExplicitnessClass.OPEN
    assert requirement.governing_scope == "#/nodes/worker/runtime/environment"


def test_stateful_resource_destination_cannot_also_be_a_runtime_mount() -> None:
    scenario = """
    name: issue-985-mount-overlap
    nodes:
      worker:
        type: compute
        os: linux
        resources: {ram: 1 gib, cpu: 1}
        runtime:
          mounts:
            - {target: /data, source: /srv/data, source_kind: bind}
    persistent_volumes:
      data:
        lifecycle: retain
        access_mode: read_write_once
        consumers:
          - {node: worker, mount_destination: /data, access_mode: read_write}
    """

    source = textwrap.dedent(scenario)
    with pytest.raises(SDLValidationError, match="runtime mount target '/data'.*already consumed"):
        parse_sdl(source)


def _safe_runtime_snapshot() -> tuple[RuntimeModel, RuntimeSnapshot]:
    model = compile_runtime_model(parse_sdl(textwrap.dedent(_RUNTIME_SCENARIO)))
    initial = plan(model, create_stub_manifest())
    operation = next(op for op in initial.provisioning.operations if op.address == "provision.node.worker")
    payload = copy.deepcopy(operation.payload)
    environment = payload["spec"]["node"]["runtime"]["environment"]
    payload["spec"]["node"]["runtime"]["environment"] = project_realization_concern(
        "runtime-environment",
        environment,
    )
    observed = RuntimeSnapshot(
        entries={
            operation.address: SnapshotEntry(
                address=operation.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=operation.resource_type,
                payload=payload,
                ordering_dependencies=operation.ordering_dependencies,
                refresh_dependencies=operation.refresh_dependencies,
            )
        }
    )
    return model, sanitize_realization_snapshot(model.realization_requirements, observed)


def test_planner_reconciles_safe_runtime_observations_without_perpetual_updates() -> None:
    model, snapshot = _safe_runtime_snapshot()

    unchanged = plan(model, create_stub_manifest(), snapshot)
    operation = next(op for op in unchanged.provisioning.operations if op.address == "provision.node.worker")

    assert operation.action is ChangeAction.UNCHANGED


def test_planner_detects_a_real_change_against_a_safe_runtime_observation() -> None:
    _model, snapshot = _safe_runtime_snapshot()
    changed_model = compile_runtime_model(
        parse_sdl(
            textwrap.dedent(_RUNTIME_SCENARIO).replace(
                "deliberate-fixture-value",
                "changed-fixture-value",
            )
        )
    )

    changed = plan(changed_model, create_stub_manifest(), snapshot)
    operation = next(op for op in changed.provisioning.operations if op.address == "provision.node.worker")

    assert operation.action is ChangeAction.UPDATE
    assert operation.payload["spec"]["node"]["runtime"]["environment"][0]["value"] == "changed-fixture-value"


def test_planner_repairs_a_malformed_runtime_observation_with_update() -> None:
    model, snapshot = _safe_runtime_snapshot()
    malformed = copy.deepcopy(snapshot)
    environment = malformed.entries["provision.node.worker"].payload["spec"]["node"]["runtime"]["environment"]
    environment[0]["unknown_backend_field"] = "rejected"

    repaired = plan(model, create_stub_manifest(), malformed)
    operation = next(op for op in repaired.provisioning.operations if op.address == "provision.node.worker")

    assert operation.action is ChangeAction.UPDATE

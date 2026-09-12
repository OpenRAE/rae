"""SEM-218 part 3: runtime non-approximation gate + provenance fields.

These tests exercise the last two enforcement points of the SEM-218 spec
``specs/formal/realization/explicitness-and-realization.md``:

- the runtime non-approximation gate on backend adapters (invariant I2 /
  Execution phase): a backend that silently realizes an exact declaration with
  a weaker value is rejected at the runtime adapter boundary; and
- the SEM-218 provenance fields on the runtime snapshot envelope (invariant
  I5 / Observation phase): realized concerns are recorded with their
  explicitness class and author-declared / processor-derived / backend-realized
  origin.

The gate compares the backend-returned realized value against the
author-declared value the planner emitted; it does not re-classify SDL at
runtime (it consumes ``RuntimeModel.realization_requirements``).
"""

from __future__ import annotations

import textwrap
from dataclasses import replace

from raes import parse_sdl
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_backend_protocols.capabilities import OperatingSystemCompatibility
from raes_backend_stubs.manifest import load_stub_realization_envelope
from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.realization_observation import (
    ObservedOperatingSystemIdentity,
    RealizationObservationDisclosure,
)
from raes_contracts.runtime_state import (
    ApplyResult,
    RealizationProvenanceEntry,
    RuntimeSnapshot,
)
from raes_contracts.versions import RUNTIME_SNAPSHOT_SCHEMA_VERSION
from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope
from raes_runtime.control_plane_store import _snapshot_from_payload, _snapshot_payload
from raes_runtime.manager import RuntimeManager
from raes_runtime.registry import RuntimeTarget

_EXACT_SCENARIO = """
name: sem-218-runtime-exact
nodes:
  web:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
"""

_PARAMETERIZED_SCENARIO = """
name: sem-218-runtime-parameterized
variables:
  os_choice: {type: string, default: linux, allowed_values: [linux, windows]}
nodes:
  web:
    type: compute
    os: ${os_choice}
    resources: {ram: 1 gib, cpu: 1}
"""


def _plan_exact(manager: RuntimeManager):
    return manager.plan(parse_sdl(textwrap.dedent(_EXACT_SCENARIO)))


def _target_with_provisioner(provisioner) -> RuntimeTarget:
    base = create_stub_target()
    manifest = replace(
        base.manifest,
        realization_support=(
            replace(
                base.manifest.realization_support[0],
                observation_capabilities={
                    **base.manifest.realization_support[0].observation_capabilities,
                    "operating-system": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.PRESENCE,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    ),
                },
            ),
        ),
        capabilities=replace(
            base.manifest.capabilities,
            provisioner=replace(
                base.manifest.provisioner,
                operating_systems=(
                    OperatingSystemCompatibility("linux", "ubuntu", frozenset({"22.04"})),
                    OperatingSystemCompatibility("windows", "windows-server", frozenset({"2022"})),
                ),
            ),
        ),
    )
    return RuntimeTarget(
        name=base.name,
        manifest=manifest,
        provisioner=provisioner,
        orchestrator=base.orchestrator,
        evaluator=base.evaluator,
        participant_runtime=base.participant_runtime,
        time_runtime=base.time_runtime,
    )


class _ObservedProvisioner:
    """In-memory provisioner that supplies one typed guest OS identity."""

    def __init__(self, *, family: str = "linux", include_observation: bool = True) -> None:
        self._family = family
        self._include_observation = include_observation

    def validate(self, plan) -> list:
        return []

    def apply(self, plan, snapshot: RuntimeSnapshot) -> ApplyResult:
        result = StubProvisioner(load_stub_realization_envelope()).apply(plan, snapshot)
        if not self._include_observation:
            return result
        operation = next(operation for operation in plan.operations if operation.resource_type == "node")
        distribution, version = ("ubuntu", "22.04") if self._family == "linux" else ("windows-server", "2022")
        observation = RealizationObservationDisclosure(
            address=operation.address,
            field_path="nodes.web.operating-system",
            domain="runtime-realization",
            requirement_kind="operating-system",
            verification_scope=RealizationVerificationScope.PRESENCE,
            observation_strength=ObservationStrength.GUEST_OBSERVED,
            operating_system=ObservedOperatingSystemIdentity(
                family=self._family,
                distribution=distribution,
                version=version,
            ),
            operation_id=plan.operation_id,
            envelope_digest="sha256:" + "a" * 64,
            configuration_digest="sha256:" + "b" * 64,
            observer_version="test-guest-os-release/v1",
            sequence=1,
            binding_verified=True,
        )
        return replace(
            result,
            snapshot=result.snapshot.with_entries(
                result.snapshot.entries,
                realization_observations=(*result.snapshot.realization_observations, observation),
            ),
        )


class _WeakeningProvisioner(_ObservedProvisioner):
    """A provisioner that silently downgrades an exact ``os`` declaration.

    It honours the plan structurally (delegating to the reference stub) but
    realizes the exact ``linux`` os family as the weaker ``other`` sentinel —
    the silent-approximation failure mode the runtime gate must reject.
    """

    def __init__(self) -> None:
        super().__init__(family="windows")


class _OmittingProvisioner(_ObservedProvisioner):
    """A provisioner that realizes the node but silently omits its exact ``os``.

    It drops the ``os_family`` key from the realized entry payload — the
    "absent backend evidence" failure mode, where the exact declaration is
    neither honoured nor visibly weakened, just missing. The gate must treat
    an unrealized exact declaration as an I2 violation, not a non-event.
    """

    def __init__(self) -> None:
        super().__init__(include_observation=False)


def test_runtime_gate_rejects_silently_weakened_exact_value():
    """I2: a backend that weakens an exact realization fails at the adapter boundary."""

    manager = RuntimeManager(_target_with_provisioner(_WeakeningProvisioner()))
    result = manager.apply(_plan_exact(manager))

    assert not result.success
    assert "runtime.backend-contract-invalid" in {diag.code for diag in result.diagnostics}
    # Fail-closed: the weakened snapshot is rejected, baseline (empty) is kept.
    assert result.snapshot.entries == {}


def test_runtime_gate_diagnostic_does_not_leak_exact_value():
    """Security gate: the rejection names the field path and kind, never the value."""

    manager = RuntimeManager(_target_with_provisioner(_WeakeningProvisioner()))
    result = manager.apply(_plan_exact(manager))

    messages = [
        diag.message
        for diag in result.diagnostics
        if diag.code == "runtime.backend-contract-invalid" and "nodes.web.os" in diag.message
    ]
    assert messages
    for message in messages:
        assert "linux" not in message
        assert "other" not in message
        assert "nodes.web.os" in message
        assert "os-family" in message


def test_runtime_gate_rejects_silently_omitted_exact_value():
    """I2: a backend that omits an exact concern (absent evidence) is rejected,
    not silently accepted as a non-event."""

    manager = RuntimeManager(_target_with_provisioner(_OmittingProvisioner()))
    result = manager.apply(_plan_exact(manager))

    assert not result.success
    assert "runtime.backend-contract-invalid" in {diag.code for diag in result.diagnostics}
    messages = [diag.message for diag in result.diagnostics if diag.code == "runtime.backend-contract-invalid"]
    assert any("nodes.web.os" in message for message in messages)


def test_honest_apply_records_realization_provenance():
    """I5: an honoured exact realization is recorded as author-declared/exact."""

    manager = RuntimeManager(_target_with_provisioner(_ObservedProvisioner()))
    result = manager.apply(_plan_exact(manager))

    assert result.success
    by_field = {entry.field_path: entry for entry in result.snapshot.realization_provenance}
    assert by_field["nodes.web.os"].provenance is ExplicitnessProvenance.AUTHOR_DECLARED
    assert by_field["nodes.web.os"].explicitness is ExplicitnessClass.EXACT
    assert by_field["nodes.web.os"].requirement_kind == "os-family"
    assert by_field["nodes.web.type"].provenance is ExplicitnessProvenance.AUTHOR_DECLARED
    assert by_field["nodes.web.type"].explicitness is ExplicitnessClass.EXACT


def test_honoured_parameter_substitution_records_processor_derived_provenance():
    """I5: an honoured substituted value retains its processor-derived origin."""

    manager = RuntimeManager(_target_with_provisioner(_ObservedProvisioner()))
    plan = manager.plan(parse_sdl(textwrap.dedent(_PARAMETERIZED_SCENARIO)))

    result = manager.apply(plan)

    assert result.success
    by_field = {entry.field_path: entry for entry in result.snapshot.realization_provenance}
    assert by_field["nodes.web.os"].provenance is ExplicitnessProvenance.PROCESSOR_DERIVED
    assert by_field["nodes.web.os"].provenance is not ExplicitnessProvenance.AUTHOR_DECLARED


def test_realization_provenance_round_trips_through_control_plane_store():
    """I5: the provenance ledger survives snapshot persistence serialization."""

    entry = RealizationProvenanceEntry(
        address="node.web",
        field_path="nodes.web.os",
        domain="runtime-realization",
        requirement_kind="os-family",
        explicitness=ExplicitnessClass.EXACT,
        provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
    )
    snapshot = RuntimeSnapshot(realization_provenance=(entry,))

    restored = _snapshot_from_payload(_snapshot_payload(snapshot))

    assert restored.realization_provenance == (entry,)


def test_runtime_snapshot_envelope_schema_accepts_realization_provenance():
    """The published runtime-snapshot envelope carries the provenance field."""

    from raes_contracts.contracts import RuntimeSnapshotEnvelopeModel

    model = RuntimeSnapshotEnvelopeModel.model_validate(
        {
            "schema_version": RUNTIME_SNAPSHOT_SCHEMA_VERSION,
            "realization_provenance": [
                {
                    "address": "node.web",
                    "field_path": "nodes.web.os",
                    "domain": "runtime-realization",
                    "requirement_kind": "os-family",
                    "explicitness": "exact",
                    "provenance": "author-declared",
                }
            ],
        }
    )

    assert model.realization_provenance[0].provenance.value == "author-declared"
    assert model.realization_provenance[0].explicitness.value == "exact"

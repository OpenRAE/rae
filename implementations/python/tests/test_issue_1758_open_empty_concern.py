"""Issue #1758: an open concern that the backend leaves empty needs no readback to plan."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_backend_stubs.manifest import create_stub_manifest
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_contracts.planning import RuntimeDomain
from raes_contracts.realization_structure import ExactRealizationValue
from raes_contracts.runtime_state import RealizationObservationDisclosure, RuntimeSnapshot, SnapshotEntry
from raes_contracts.vocabulary import ObservationStrength, RealizationSupportMode, RealizationVerificationScope
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan, realization_disclosure
from raes_processor.semantics.realization import realization_support_diagnostics

_OPEN_EMPTY = """
name: open-empty
realization: {default: open}
nodes:
  host: {type: compute}
"""
_CAPABILITY = RealizationObservationCapability(
    verification_scope=RealizationVerificationScope.CONFIGURATION,
    observation_strength=ObservationStrength.DAEMON_OBSERVED,
)
_MEMBER = [{"name": "COLLECTOR", "value": "enabled"}]


def _model():
    return compile_runtime_model(parse_sdl(_OPEN_EMPTY))


def _requirement(model, kind: str):
    return next(item for item in model.realization_requirements if item.requirement_kind == kind)


def _open_manifest(capabilities=None):
    manifest = create_stub_manifest()
    declaration = manifest.realization_support[0]
    return replace(
        manifest,
        realization_support=(
            replace(
                declaration,
                support_mode=RealizationSupportMode.OPEN_REALIZATION,
                observation_capabilities=capabilities or {},
            ),
        ),
    )


def _snapshot(operation, requirement, *, runtime=None, observed=False) -> RuntimeSnapshot:
    payload = deepcopy(operation.payload)
    if runtime is not None:
        payload["spec"]["node"]["runtime"] = runtime
    observations = (
        (
            RealizationObservationDisclosure(
                address=requirement.address,
                field_path=requirement.field_path,
                domain=requirement.domain,
                requirement_kind=requirement.requirement_kind,
                verification_scope=RealizationVerificationScope.CONFIGURATION,
                observation_strength=ObservationStrength.DAEMON_OBSERVED,
            ),
        )
        if observed
        else ()
    )
    return RuntimeSnapshot(
        entries={
            operation.address: SnapshotEntry(
                address=operation.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=operation.resource_type,
                payload=payload,
                ordering_dependencies=operation.ordering_dependencies,
                refresh_dependencies=operation.refresh_dependencies,
            )
        },
        realization_observations=observations,
    )


@pytest.mark.parametrize("kind", ["runtime-mail-services", "runtime-ssh-servers", "runtime-scheduled-jobs"])
def test_planner_admits_an_empty_open_concern_without_readback(kind: str) -> None:
    requirement = _requirement(_model(), kind)

    assert requirement.explicitness is ExplicitnessClass.OPEN
    assert requirement.verification_scope is RealizationVerificationScope.CONFIGURATION
    assert realization_support_diagnostics((requirement,), _open_manifest()) == []


def test_every_empty_open_runtime_concern_plans_without_readback() -> None:
    diagnostics = realization_support_diagnostics(_model().realization_requirements, _open_manifest())

    # Open process limits still need a typed apparatus domain with guest observation.
    assert [item.code for item in diagnostics] == ["realization.unsupported-process-resource-limits"]


def test_open_concern_with_authored_structure_keeps_its_readback_demand() -> None:
    requirement = replace(
        _requirement(_model(), "runtime-mail-services"),
        structure=ExactRealizationValue(kind="exact"),
    )

    assert [item.code for item in realization_support_diagnostics((requirement,), _open_manifest())] == [
        "realization.under-observed-open-requirement"
    ]
    assert realization_support_diagnostics((requirement,), _open_manifest({"runtime-mail-services": _CAPABILITY})) == []


def test_runtime_gate_rejects_an_unreported_open_concern_and_an_uncorroborated_member() -> None:
    model = _model()
    requirement = _requirement(model, "runtime-environment")
    manifest = _open_manifest()
    provisioning = plan(model, manifest).provisioning
    operation = next(item for item in provisioning.operations if item.address == requirement.address)

    def evaluate(snapshot: RuntimeSnapshot, gate_manifest=manifest):
        return realization_disclosure((requirement,), provisioning, snapshot, manifest=gate_manifest)

    diagnostics, provenance = evaluate(_snapshot(operation, requirement))
    assert [item.code for item in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()
    for snapshot in (
        _snapshot(operation, requirement, runtime={"environment": _MEMBER}),
        _snapshot(operation, requirement, runtime={"environment": _MEMBER}, observed=True),
    ):
        diagnostics, provenance = evaluate(snapshot)
        assert [(item.code, "corroboration" in item.message) for item in diagnostics] == [
            ("runtime.backend-contract-invalid", True)
        ]
        assert provenance == ()

    corroborated = _open_manifest({"runtime-environment": _CAPABILITY})
    diagnostics, provenance = evaluate(
        _snapshot(operation, requirement, runtime={"environment": _MEMBER}, observed=True),
        corroborated,
    )
    assert diagnostics == []
    assert [(entry.requirement_kind, entry.provenance) for entry in provenance] == [
        ("runtime-environment", ExplicitnessProvenance.BACKEND_REALIZED)
    ]

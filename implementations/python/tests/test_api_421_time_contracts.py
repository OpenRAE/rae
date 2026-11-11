"""API-421, ASR-528, and EXP-734 portable shared-time contracts."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from contract_fixtures import contract_fixture_text
from raes.parser import parse_sdl
from raes_backend_protocols.capability_admission import time_model_capability_gaps
from raes_backend_stubs.stubs import create_stub_manifest, create_stub_target
from raes_conformance.time_semantics import time_model_conformance_diagnostics
from raes_contracts.contracts.time_model import (
    RealizedTimeModelProvenanceModel,
    TimeApparatusBindingModel,
    TimeModelDeclarationModel,
    TimeRuntimeStateModel,
    validate_time_runtime_transition,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.compiler.time_model import (
    compiled_time_model_from_contract,
    time_model_contract_model,
)
from raes_runtime import RuntimeManager

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "contracts" / "fixtures" / "time"


def _scenario():
    return parse_sdl(
        textwrap.dedent(
            """
            name: portable-time
            nodes:
              worker:
                type: compute
                resources: {ram: 1 GiB, cpu: 1}
            time_domains:
              scenario:
                kind: simulated
                tick_period_seconds: {numerator: 1, denominator: 1000}
                epoch: scenario_start
                visibility: participant_visible
                description: scenario milliseconds
            clocks:
              scenario-clock:
                time_domain_ref: scenario
                authority_kind: runtime
                authority_ref: runtime.time-coordinator
                monotonicity: non_decreasing
                supports_pause: true
                supports_reset: true
                description: scenario authority
            time_progression_policies:
              scenario-policy:
                clock_ref: scenario-clock
                advancement_mode: stepped
                synchronization_mode: barrier
                step_ticks: 10
                reset_behavior: new_segment_zero
                replay_behavior: restore_recorded_advances
                description: deterministic progression
            temporal_constraints:
              worker-window:
                constraint_kind: window
                clock_ref: scenario-clock
                subject_refs: [nodes.worker]
                start: {tick: 0}
                end: {tick: 100}
                description: activity window
            """
        )
    )


def _declaration() -> TimeModelDeclarationModel:
    declaration = time_model_contract_model(compile_runtime_model(_scenario()).time_model)
    assert declaration is not None
    return declaration


def _provenance(declaration: TimeModelDeclarationModel, *, run_id: str = "run-001"):
    bindings = {
        address: TimeApparatusBindingModel(
            address=address,
            component_ref="apparatus.time-runtime",
            realization_kind="runtime_managed",
            evidence_refs=["evidence:time-readback"],
        )
        for address in set(declaration.clocks) | set(declaration.progression_policies)
    }
    return RealizedTimeModelProvenanceModel(
        run_id=run_id,
        declaration_digest=declaration.canonical_digest(),
        declared_model=declaration,
        realized_model=declaration,
        apparatus_bindings=bindings,
        synchronization_assumptions=["single authoritative runtime coordinator"],
        evidence_refs=["evidence:time-readback"],
    )


def test_portable_time_model_roundtrips_compiled_metadata_and_digest() -> None:
    declaration = _declaration()
    restored = time_model_contract_model(compiled_time_model_from_contract(declaration))

    assert restored == declaration
    assert declaration.canonical_digest().startswith("sha256:")
    assert TimeModelDeclarationModel.model_validate_json(declaration.model_dump_json()) == declaration


def test_time_capability_admission_is_explicit_and_fail_closed() -> None:
    declaration = _declaration()

    assert time_model_capability_gaps(create_stub_manifest(with_time=True), declaration) == ()
    assert time_model_capability_gaps(create_stub_manifest(with_time=False), declaration) == (
        "backend does not declare time capabilities",
    )


def test_runtime_manager_controls_typed_time_state_and_append_only_history() -> None:
    manager = RuntimeManager(create_stub_target())
    result = manager.apply(manager.plan(_scenario()))
    assert result.success

    clock = "time.clock.scenario-clock"
    initial = manager.read_time_state()
    advanced = manager.advance_time(clock, ticks=10)
    paused = manager.pause_time(clock)

    assert advanced.success and paused.success
    final = manager.read_time_state()
    assert final.clocks[clock].coordinate.tick == 10
    assert final.clocks[clock].state == "paused"
    assert [event.kind for event in final.clocks[clock].history] == ["initialize", "advance", "pause"]
    validate_time_runtime_transition(initial, final)

    tampered = final.model_copy(
        update={"clocks": {clock: final.clocks[clock].model_copy(update={"history": final.clocks[clock].history[1:]})}}
    )
    with pytest.raises(ValueError, match="append-only"):
        validate_time_runtime_transition(final, tampered)


def test_conformance_binds_capability_readback_and_run_provenance() -> None:
    declaration = _declaration()
    manager = RuntimeManager(create_stub_target())
    assert manager.apply(manager.plan(_scenario())).success
    provenance = _provenance(declaration)

    assert (
        time_model_conformance_diagnostics(
            create_stub_manifest(with_time=True),
            declaration,
            runtime_state=manager.read_time_state(),
            provenance=provenance,
            run_id="run-001",
        )
        == ()
    )

    diagnostics = time_model_conformance_diagnostics(
        create_stub_manifest(with_time=False),
        declaration,
        runtime_state=None,
        provenance=None,
        run_id="run-001",
    )
    assert {diagnostic.code for diagnostic in diagnostics} == {
        "conformance.time-capability-gap",
        "conformance.time-runtime-state-missing",
        "conformance.realized-time-provenance-missing",
    }


def test_realized_time_provenance_requires_declared_address_coverage() -> None:
    declaration = _declaration()
    payload = _provenance(declaration).model_dump(mode="json")
    payload["apparatus_bindings"] = {}

    with pytest.raises(ValueError, match="at least 1 item"):
        RealizedTimeModelProvenanceModel.model_validate(payload)


@pytest.mark.parametrize(
    ("contract_id", "model"),
    [
        ("time-model-v1", TimeModelDeclarationModel),
        ("time-runtime-state-v1", TimeRuntimeStateModel),
        ("realized-time-model-v1", RealizedTimeModelProvenanceModel),
    ],
)
def test_published_time_fixture_corpora(
    contract_id: str,
    model: type[TimeModelDeclarationModel | TimeRuntimeStateModel | RealizedTimeModelProvenanceModel],
) -> None:
    valid = sorted((FIXTURE_ROOT / contract_id / "valid").glob("*.json"))
    invalid = sorted((FIXTURE_ROOT / contract_id / "invalid").glob("*.json"))

    assert valid and invalid
    for path in valid:
        model.model_validate_json(contract_fixture_text(path))
    for path in invalid:
        payload = path.read_text(encoding="utf-8")
        with pytest.raises(ValueError):
            model.model_validate_json(payload)

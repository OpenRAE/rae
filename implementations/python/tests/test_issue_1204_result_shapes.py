"""Validate returned objects after mutation, with bounded redacted failures."""

from copy import deepcopy
from itertools import repeat

import pytest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_runtime.backend_calls import _call_backend_apply, _call_backend_diagnostics


def _return(result):
    previous = RuntimeSnapshot(metadata={"trusted": ["predecessor"]})
    returned = _call_backend_apply(lambda *_: result, previous, address="runtime.test", snapshot=previous)
    return previous, returned


@pytest.mark.parametrize(
    "field,value",
    [
        ("success", 1),
        ("success", "yes"),
        ("changed_addresses", ["provision.node.web", "provision.node.web"]),
        ("changed_addresses", ["bad address"]),
        ("details", {"invalid": float("nan")}),
        ("details", {"invalid": object()}),
        ("details", {1: "invalid key"}),
        ("diagnostics", [Diagnostic("bad", "runtime", "runtime.test", "", severity="error")]),
    ],
)
def test_mutated_result_shape_is_rejected_without_candidate_data(field, value):
    result = ApplyResult(True, RuntimeSnapshot(metadata={"candidate": "not-accepted"}))
    setattr(result, field, value)
    previous, returned = _return(result)
    assert returned.success is False
    assert returned.snapshot == previous
    assert returned.changed_addresses == []
    assert returned.details == {}
    assert returned.diagnostics[0].code == "runtime.backend-contract-invalid"


@pytest.mark.parametrize(
    "field,value", [("entries", {"provision.node.web": {}}), ("evaluation_history", []), ("metadata", [])]
)
def test_mutated_snapshot_shape_is_rejected_before_traversal(field, value):
    snapshot = RuntimeSnapshot()
    setattr(snapshot, field, value)
    previous, returned = _return(ApplyResult(True, snapshot))
    assert returned.success is False
    assert returned.snapshot == previous
    assert returned.diagnostics[0].code == "runtime.backend-contract-invalid"


def test_generator_diagnostics_are_materialized_once_and_preserved():
    diagnostic = Diagnostic("test.warning", "runtime", "runtime.test", "Backend diagnostic.")
    result = ApplyResult(
        False, RuntimeSnapshot(metadata={"trusted": ["predecessor"]}), diagnostics=(item for item in [diagnostic])
    )
    _, returned = _return(result)
    assert returned.success is False
    assert returned.diagnostics == [diagnostic]


def test_unbounded_diagnostic_iterator_is_rejected_after_bounded_consumption():
    diagnostic = Diagnostic("test.warning", "runtime", "runtime.test", "Backend diagnostic.")
    # Deliberately finite guard so a missing bound fails without hanging the suite.
    result = ApplyResult(False, RuntimeSnapshot(), diagnostics=repeat(diagnostic, 1025))
    previous, returned = _return(result)
    assert returned.snapshot == previous
    assert returned.diagnostics[0].code == "runtime.backend-contract-invalid"


def test_diagnostic_iterator_exception_is_redacted_at_both_boundaries():
    def broken():
        yield Diagnostic("test.warning", "runtime", "runtime.test", "Backend diagnostic.")
        raise RuntimeError("private-backend-value")

    diagnostics = _call_backend_diagnostics(broken, address="runtime.validate")
    assert diagnostics[0].code == "runtime.backend-contract-invalid"
    result = ApplyResult(False, RuntimeSnapshot(), diagnostics=broken())
    previous, returned = _return(result)
    assert returned.snapshot == previous
    assert "private-backend-value" not in repr(returned)


def test_cyclic_result_details_are_rejected_without_recursion_escape():
    details = {}
    details["cycle"] = details
    previous, returned = _return(ApplyResult(True, RuntimeSnapshot(), details=details))
    assert returned.success is False
    assert returned.snapshot == previous
    assert returned.details == {}


def test_accepted_details_do_not_alias_the_backend_result():
    result = ApplyResult(True, RuntimeSnapshot(metadata={"trusted": ["predecessor"]}), details={"selected": ["choice"]})
    _, returned = _return(result)
    assert returned.success, returned.diagnostics
    accepted = deepcopy(returned.details)
    result.details["selected"].append("later")
    assert returned.details == accepted


def test_runtime_payload_admission_preserves_typed_python_carriers():
    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.realization_structure import validate_realization_value

    payload = {"domains": (RuntimeDomain.EVALUATION,)}
    assert validate_realization_value(payload, python_carriers=True).conformant
    assert not validate_realization_value(payload).conformant


def test_backend_service_dependency_is_not_copied_as_if_it_were_authority():
    service = object()
    previous = RuntimeSnapshot()

    def backend(dependency, snapshot):
        assert dependency is service
        return ApplyResult(True, snapshot)

    returned = _call_backend_apply(backend, service, previous, address="runtime.test", snapshot=previous)
    assert returned.success, returned.diagnostics


def test_safe_snapshot_projection_preserves_native_participant_result_type():
    from raes_contracts.participant_binding import ParticipantActionApplyResult
    from raes_runtime.backend_calls import _with_snapshot

    native = ParticipantActionApplyResult(True, RuntimeSnapshot())
    projected = _with_snapshot(native, RuntimeSnapshot(metadata={"accepted": True}))
    assert isinstance(projected, ParticipantActionApplyResult)
    assert projected.action_result == native.action_result


def test_final_sanitized_candidate_must_still_obey_shape_and_effect_ownership(monkeypatch):
    from dataclasses import replace

    from raes_runtime import backend_calls

    def invalid_projection(result, **_):
        return replace(result, snapshot=RuntimeSnapshot(metadata={"unowned-sanitizer-write": True}))

    monkeypatch.setattr(backend_calls, "_sanitize_backend_realization", invalid_projection)
    previous, returned = _return(ApplyResult(True, RuntimeSnapshot(metadata={"trusted": ["predecessor"]})))
    assert not returned.success
    assert returned.snapshot == previous
    assert returned.diagnostics[0].code == "runtime.backend-contract-invalid"


@pytest.mark.parametrize("value_count, admitted", [(200, True), (400, False)])
def test_snapshot_payload_limits_apply_to_the_whole_candidate(value_count, admitted):
    from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
    from raes_contracts.runtime_state import SnapshotEntry

    previous = RuntimeSnapshot()
    entries, operations = {}, []
    for index in range(200):
        address = f"provision.feature.node.f{index}"
        payload = {"name": f"f{index}", "values": list(range(value_count))}
        entries[address] = SnapshotEntry(address, RuntimeDomain.PROVISIONING, "feature-binding", payload)
        operations.append(ProvisionOp(ChangeAction.CREATE, address, "feature-binding", {"name": f"f{index}"}))
    candidate = ApplyResult(True, RuntimeSnapshot(entries=entries), changed_addresses=list(entries))
    returned = _call_backend_apply(
        lambda *_: candidate,
        ProvisioningPlan(operations=operations),
        previous,
        address="runtime.aggregate",
        snapshot=previous,
    )
    assert returned.success is admitted
    if admitted:
        assert returned.snapshot.entries == entries
    else:
        assert returned.snapshot == previous
        assert returned.diagnostics[0].message == "Backend snapshot exceeds the aggregate portable value bounds."


def test_python_carrier_admission_visits_values_without_serializing_models():
    from dataclasses import dataclass

    from pydantic import BaseModel
    from raes_contracts.realization_structure import validate_realization_value

    class Payload(BaseModel):
        values: list[int]

    @dataclass
    class Carrier:
        payload: Payload

    carrier = Carrier(Payload(values=[1, 2]))
    assert validate_realization_value(carrier, python_carriers=True).conformant
    carrier.payload.values.append(carrier)
    assert not validate_realization_value(carrier, python_carriers=True).conformant


def test_value_admission_bounds_record_keys_as_well_as_values():
    from raes_contracts.realization_structure import validate_realization_value

    assert not validate_realization_value({"k" * 4097: None}).conformant


def test_value_admission_has_a_total_scalar_byte_budget():
    from raes_contracts.realization_structure import RealizationConstraintLimits, validate_realization_value

    limits = RealizationConstraintLimits(max_scalar_bytes=256, max_total_scalar_bytes=512)
    assert validate_realization_value(["x" * 200] * 2, limits=limits).conformant
    result = validate_realization_value(["x" * 200] * 3, limits=limits)
    assert not result.conformant
    assert "max_total_scalar_bytes" in result.diagnostics[0].message


def test_native_transition_validation_errors_do_not_expose_candidate_values(monkeypatch):
    from raes_runtime import backend_calls

    def invalid_transition(*_):
        raise ValueError("private-transition-candidate")

    monkeypatch.setattr(backend_calls, "validate_time_runtime_transition", invalid_transition)
    previous, result = _return(ApplyResult(True, RuntimeSnapshot(metadata={"trusted": ["predecessor"]})))
    assert not result.success
    assert result.snapshot == previous
    assert "private-transition-candidate" not in repr(result)
    assert result.diagnostics[0].message == "Backend returned an invalid shared-time transition."


@pytest.mark.parametrize("target", ["request", "predecessor"])
def test_backend_inputs_are_bounded_before_copying_or_invoking(target, monkeypatch):
    from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp

    predecessor = RuntimeSnapshot()
    payload = {"large": "x" * (1048576 + 1)}
    plan = ProvisioningPlan(operations=[ProvisionOp(ChangeAction.CREATE, "provision.node.web", "node", payload)])
    if target == "predecessor":
        predecessor.metadata = payload
        plan = ProvisioningPlan()

    def must_not_copy(*_):
        raise AssertionError("unadmitted input must not be copied")

    monkeypatch.setattr(
        RuntimeSnapshot if target == "predecessor" else ProvisioningPlan, "__deepcopy__", must_not_copy, raising=False
    )
    calls = []

    def backend(*_):
        calls.append(True)
        return ApplyResult(True, predecessor)

    result = _call_backend_apply(backend, plan, predecessor, snapshot=predecessor, address="runtime.inputs")
    assert not result.success
    assert calls == []
    assert result.snapshot is predecessor
    assert result.diagnostics[0].message == "Backend call input exceeds the admitted portable value bounds."

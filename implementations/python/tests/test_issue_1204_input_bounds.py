"""Untrusted value limits precede copying, hashing and native invocation."""

import pytest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_runtime.backend_calls import _call_backend_apply


@pytest.mark.parametrize("in_snapshot", [False, True])
def test_invalid_unicode_input_is_a_bounded_failure(in_snapshot):
    value = {"invalid": chr(0xD800)}
    previous = RuntimeSnapshot(metadata=value if in_snapshot else {})
    calls = []

    def backend(*args):
        calls.append(args)
        return ApplyResult(True, previous)

    result = _call_backend_apply(backend, value, previous, snapshot=previous, address="runtime.input")
    assert not result.success
    assert calls == []
    assert result.diagnostics[0].code == "runtime.backend-contract-invalid"


def test_native_value_argument_is_bounded_before_copy_or_callback():
    class UncopyableList(list):
        def __deepcopy__(self, memo):
            pytest.fail("oversized value reached deep copy")

    value = UncopyableList(range(16385))
    previous = RuntimeSnapshot()
    calls = []

    def backend(*args):
        calls.append(args)
        return ApplyResult(True, previous)

    result = _call_backend_apply(backend, value, previous, snapshot=previous, address="runtime.input")
    assert not result.success
    assert calls == []


def test_runtime_value_budget_can_traverse_its_admitted_node_budget():
    from raes_contracts.realization_structure import validate_realization_value
    from raes_contracts.runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

    # Distinct small records model a multi-node plan's resources and authority;
    # no individual collection or scalar bypasses its independent limit.
    value = [{"name": str(index), "kind": "node"} for index in range(6000)]
    assert validate_realization_value(value, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS).conformant
    assert not validate_realization_value(value * 3, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS).conformant

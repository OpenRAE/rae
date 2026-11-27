"""Materialization byte bounds apply before isolation of a backend proposal."""

from copy import deepcopy

from raes_contracts.materialization import MATERIALIZATION_MAX_BYTES, MaterializationSubmission
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_runtime import backend_apply_results
from raes_runtime.backend_calls import _RealizationApplyContext


def test_unsafe_submission_is_rejected_before_copying_the_candidate(monkeypatch):
    unsafe = MaterializationSubmission.model_construct(sdl="ü" * (MATERIALIZATION_MAX_BYTES // 2 + 1))
    previous = RuntimeSnapshot()
    candidate = ApplyResult(True, previous, materialization_attestation=unsafe)

    def guarded_copy(value):
        assert getattr(value, "materialization_attestation", None) is not unsafe
        return deepcopy(value)

    monkeypatch.setattr(backend_apply_results, "deepcopy", guarded_copy)
    rejected = backend_apply_results._finalize_backend_apply(
        candidate,
        address="runtime.test",
        baseline_snapshot=previous,
        realization=_RealizationApplyContext(),
        information_state_context_resolver=None,
    )
    assert not rejected.success
    assert rejected.snapshot == previous
    assert rejected.changed_addresses == []

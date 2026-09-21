"""Issue #1069 security review: the evaluation history is runtime-owned.

A participant backend returns its own snapshot from an ordinary action apply.
That result may carry the committed API-424 evaluation history forward, and
nothing else: erasing a committed evaluation would silently suppress a
requested supervisory effect, and forging a realization would make the runtime
skip dispatching one. Both are refused on every apply path.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from participant_control_contract_fixtures import evaluation_payload
from participant_control_runtime_fixtures import control_binding
from participant_crossing_fixtures import (
    PARTICIPANT,
    StaticCrossingResolver,
    action_plane,
    admit,
    policy_capable_target,
)
from raes_contracts.runtime_state import OperationState

_CARRIER = "participant_control_evaluation_history"


def _target():
    return policy_capable_target("participant_ingress_admission", "participant_modular_control")


def _plane(target=None):
    return action_plane(
        StaticCrossingResolver(),
        target=target or _target(),
        participant_control=control_binding(),
    )


def _evaluations(plane) -> list[dict]:
    return list(plane.snapshot.participant_control_evaluation_history.get(PARTICIPANT, ()))


def _hostile_backend(target, transform) -> None:
    """Rewrite the evaluation history in every snapshot the backend returns."""

    runtime = target.participant_runtime
    original = runtime.admit_action

    def tampered(*args: object, **kwargs: object):
        result = original(*args, **kwargs)
        snapshot = result.snapshot
        return replace(
            result,
            snapshot=snapshot.with_entries(
                dict(snapshot.entries),
                **{_CARRIER: transform(snapshot.participant_control_evaluation_history)},
            ),
        )

    runtime.admit_action = tampered  # type: ignore[method-assign]


def test_the_carrier_is_runtime_owned_not_participant_owned():
    from raes_runtime.backend_snapshot_contracts import SNAPSHOT_CARRIER_OWNERS

    assert SNAPSHOT_CARRIER_OWNERS[_CARRIER] == "runtime"


def test_a_backend_result_cannot_erase_a_committed_evaluation():
    target = _target()
    _hostile_backend(target, lambda _history: {})
    plane = _plane(target)

    receipt = admit(plane, idempotency_key="hostile-erase")

    status = plane.get_operation(receipt.operation_id)
    assert status is not None
    assert status.state is OperationState.FAILED
    assert _evaluations(plane)  # the committed evaluation survives the refusal


def test_a_backend_result_cannot_forge_an_applied_realization():
    def forge(history):
        records = list(history.get(PARTICIPANT, ()))
        forged = {
            **evaluation_payload(),
            "evaluation_id": "forged-realization",
            "realizations": [
                {
                    "effect_id": "effect-1",
                    "disposition": "applied",
                    "receipt": {
                        "kind": "receipt",
                        "ref": "forged-receipt",
                        "revision": "rev1",
                        "digest": "sha256:" + "b" * 64,
                    },
                    "evidence": [
                        {
                            "kind": "evidence",
                            "ref": "forged-evidence",
                            "revision": "rev1",
                            "digest": "sha256:" + "b" * 64,
                        }
                    ],
                }
            ],
        }
        return {PARTICIPANT: [*records, forged]}

    target = _target()
    _hostile_backend(target, forge)
    plane = _plane(target)

    receipt = admit(plane, idempotency_key="hostile-forge")

    status = plane.get_operation(receipt.operation_id)
    assert status is not None
    assert status.state is OperationState.FAILED
    assert [record["evaluation_id"] for record in _evaluations(plane)] != ["forged-realization"]
    assert all(record["realizations"] == [] for record in _evaluations(plane))


@pytest.mark.parametrize(
    "before,after",
    [
        ({PARTICIPANT: [evaluation_payload()]}, {}),
        ({PARTICIPANT: [evaluation_payload()]}, {PARTICIPANT: []}),
        ({}, {PARTICIPANT: [evaluation_payload()]}),
    ],
)
def test_the_transition_guard_refuses_every_backend_rewrite(before, after):
    from raes_contracts.participant_control_evaluation_history import (
        iter_participant_control_evaluation_transition_violations,
    )

    assert list(iter_participant_control_evaluation_transition_violations(before, after))


def test_the_transition_guard_accepts_an_unchanged_history():
    from raes_contracts.participant_control_evaluation_history import (
        iter_participant_control_evaluation_transition_violations,
    )

    retained = {PARTICIPANT: [evaluation_payload()]}
    assert list(iter_participant_control_evaluation_transition_violations(retained, dict(retained))) == []

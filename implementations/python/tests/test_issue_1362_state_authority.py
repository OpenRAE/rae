"""Supervision shares state authority without sharing an effect's long permit."""

from contextvars import copy_context
from threading import Event, Thread

import pytest
from raes_contracts.runtime_state import OperationKind
from raes_runtime.control_plane_mutation import RuntimeMutationAuthority


def test_control_can_commit_while_external_effect_keeps_conflicting_work_reserved():
    authority = RuntimeMutationAuthority()
    entered, release, conflicting_entered = Event(), Event(), Event()
    failures = []

    def effect():
        try:
            with authority.mutation(OperationKind.PROVISIONING), authority.external_call():
                entered.set()
                assert release.wait(3)
        except BaseException as exc:
            failures.append(exc)

    def conflict():
        try:
            with authority.mutation(OperationKind.EVALUATION):
                conflicting_entered.set()
        except BaseException as exc:
            failures.append(exc)

    worker = Thread(target=effect)
    competitor = Thread(target=conflict)
    worker.start()
    try:
        assert entered.wait(1)
        competitor.start()
        with authority.supervision():
            assert authority.owns_current_thread()
            assert not conflicting_entered.is_set()
        assert not conflicting_entered.wait(0.05)
    finally:
        release.set()
        worker.join(2)
        if competitor.ident is not None:
            competitor.join(2)
    assert not worker.is_alive()
    assert not competitor.is_alive()
    assert not failures
    assert conflicting_entered.is_set()


def test_extension_context_cannot_reenter_state_authority_from_another_thread():
    authority = RuntimeMutationAuthority()
    rejected = Event()

    def callback():
        with pytest.raises(RuntimeError, match="callback"), authority.mutation(OperationKind.PROVISIONING):
            pytest.fail("extension obtained state authority")
        rejected.set()

    with authority.mutation(OperationKind.PROVISIONING):
        with authority.external_call():
            context = copy_context()
            worker = Thread(target=context.run, args=(callback,), daemon=True)
            worker.start()
            assert rejected.wait(1)
        worker.join(1)


def test_supervision_itself_cannot_be_reentered_by_a_backend_callback():
    authority = RuntimeMutationAuthority()
    with (
        authority.mutation(OperationKind.PROVISIONING),
        authority.external_call(),
        pytest.raises(RuntimeError, match="callback"),
        authority.supervision(),
    ):
        pytest.fail("extension obtained supervisory state authority")

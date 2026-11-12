"""Lost state admission cannot become an unowned terminal publication."""

from dataclasses import replace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from test_issue_1181_unified_control_plane_mutations import _running_record


def test_terminal_publication_requires_the_live_state_writer():
    plane = RuntimeControlPlane(create_stub_target(), run_scope="run:issue-1181")
    record = _running_record("unowned-cut")
    plane._store.claim_record(record)
    final = replace(record, status=replace(record.status, state=OperationState.SUCCEEDED))
    try:
        with pytest.raises(RuntimeError):
            plane._commit_terminal_operation(plane._snapshot, final)
        assert plane._store.raw_store.load_records()[record.receipt.operation_id] == record
        assert plane._store.raw_store.read_audit() == []
    finally:
        plane.close()

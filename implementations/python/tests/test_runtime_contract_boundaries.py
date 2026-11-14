"""Runtime/backend contract ownership regression tests."""

from __future__ import annotations

import json

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.evaluation import EvaluationResultContract
from raes_contracts.participant_episode import ParticipantEpisodeInitializeRequest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_contracts.workflow import WorkflowResultContract
from raes_processor import models
from raes_runtime import backend_call_contracts


def test_processor_models_reexports_shared_runtime_contracts() -> None:
    assert models.Diagnostic is Diagnostic
    assert models.ApplyResult is ApplyResult
    assert models.RuntimeSnapshot is RuntimeSnapshot
    assert models.WorkflowResultContract is WorkflowResultContract
    assert models.EvaluationResultContract is EvaluationResultContract
    assert models.ParticipantEpisodeInitializeRequest is ParticipantEpisodeInitializeRequest


def test_backend_details_accept_report_metadata_above_previous_byte_limit() -> None:
    details = {f"attempt-{index}": "x" * 4096 for index in range(32)}
    assert len(json.dumps(details).encode("utf-8")) > 65536
    assert backend_call_contracts._details_payload_violation(details) is None


def test_backend_details_count_escaped_json_bytes_at_the_limit(monkeypatch) -> None:
    details = {"status": "é"}
    encoded_bytes = len(json.dumps(details, allow_nan=False).encode("utf-8"))
    monkeypatch.setattr(backend_call_contracts, "_MAX_DETAILS_BYTES", encoded_bytes)
    assert backend_call_contracts._details_payload_violation(details) is None
    monkeypatch.setattr(backend_call_contracts, "_MAX_DETAILS_BYTES", encoded_bytes - 1)
    assert backend_call_contracts._details_payload_violation(details) == (
        "Backend returned excessive apply-result details."
    )

"""Incremental crossing joins preserve the complete validator's refusals."""

from types import SimpleNamespace

import pytest
from test_api_423_participant_crossing_contracts import (
    KNOWN_AUTHORITY_BASIS_REFS,
    KNOWN_EVIDENCE_REFS,
    _decision,
    _request,
)


def context(record):
    return SimpleNamespace(
        known_subjects=(record.occurrence.subject,),
        policies=(record.occurrence.policy,),
        known_evidence_refs=KNOWN_EVIDENCE_REFS,
        known_authority_basis_refs=KNOWN_AUTHORITY_BASIS_REFS,
    )


def test_crossing_prefix_joins_new_decision_and_rejects_wrong_predecessor():
    from raes_contracts.contracts.participant_crossing_prefix import CrossingPrefix
    from raes_contracts.snapshot_histories import seal_history

    request = _request()
    participant = request.participant_address
    history = seal_history("participant_crossing_history", {participant: [request.model_dump(mode="json")]})
    prefix = CrossingPrefix()
    prefix.refresh(history[participant])
    prefix.validate_extension([_decision(request)], context(request))
    invalid = _decision(request).model_copy(
        update={"occurrence": _decision(request).occurrence.model_copy(update={"request_ref": "missing"})}
    )
    invalid_context = context(request)
    with pytest.raises(ValueError):
        prefix.validate_extension([invalid], invalid_context)
    # A rejected candidate never entered the committed prefix.
    assert len(prefix.indexes.records_by_event_id) == 1
    missing_evidence = context(request)
    missing_evidence.known_evidence_refs = set()
    decision = _decision(request)
    with pytest.raises(ValueError):
        prefix.validate_extension([decision], missing_evidence)

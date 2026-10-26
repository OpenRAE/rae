"""Adversarial contextual checks beyond structural validity."""

from dataclasses import replace

import pytest
from raes_contracts.participant_control_context import validate_control_context_record
from test_act_620_control_context_assets import _context, _cut, _delivered_context, _exposed, _record


def test_incomparable_selection_projection_and_delivery_cuts_fail_closed():
    context = replace(_delivered_context(), cut_precedes=None)
    # These distinct order coordinates need an independently resolved relation.
    assert validate_control_context_record(_exposed(), context)


def test_delivery_cannot_be_replayed_at_another_cut():
    context = replace(_delivered_context(), record_cut=_cut(9))
    assert validate_control_context_record(_exposed(), context)


def test_later_evidence_cannot_overwrite_the_original_selection_record():
    original = _record()
    withheld = _record(disposition="withheld", withholding_authority_ref="authorities.withhold")
    withheld = withheld.model_copy(update={"record_id": original.record_id})
    assert validate_control_context_record(withheld, replace(_context(), selections={original.selection_ref: original}))


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
def test_host_resolver_failure_remains_distinct_from_a_refused_agreement(error_type):
    def unavailable(_request):
        raise error_type("authority resolver unavailable")

    record = _record()
    context = replace(_context(), authorize=unavailable)
    with pytest.raises(error_type, match="authority resolver unavailable"):
        validate_control_context_record(record, context)

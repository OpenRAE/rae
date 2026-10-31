"""SDL authoring input failures stay refusals after the narrowed handlers (ADR-116, issue #1678)."""

from __future__ import annotations

import pytest
import rfc8785
from raes import SDLParseError
from test_issue_1210_semantic_migration import context

# RFC 8785 refuses an integer outside the I-JSON range, so this authored source has no canonical form.
_BEYOND_JCS_INTEGER = "name: legacy\nvariables: {count: {type: integer, default: 9007199254740992}}\n"


def test_semantic_migration_refuses_an_unhashable_source_revision():
    from raes.semantic_migration import migrate_sdl_semantics

    source = "name: old\nsemantic_revision: []\n"
    result = migrate_sdl_semantics(source, context=context(source))

    assert result.output is None
    assert "semantic-migration.source-or-target-invalid" in {item.code for item in result.report.diagnostics}


def test_structured_edit_refuses_an_index_beyond_the_integer_digit_limit():
    from raes.language_service import apply_structured_edit

    index = "1" * 5000
    result = apply_structured_edit("name: x\nlist: [1]\n", operation="set", pointer="/list/" + index, value=2)

    assert result["status"] == "invalid"
    # The refusal names a fixed reason; it does not repeat the unbounded caller index.
    assert [item["message"] for item in result["diagnostics"]] == ["list index is out of range"]


def test_structured_edit_keeps_in_range_and_out_of_range_indexes():
    from raes.language_service import apply_structured_edit

    edited = apply_structured_edit("name: x\nlist: [1, 2]\n", operation="set", pointer="/list/1", value=3)
    assert edited["status"] != "invalid"
    assert "- 3" in edited["content"]
    refused = apply_structured_edit("name: x\nlist: [1, 2]\n", operation="set", pointer="/list/10", value=3)
    assert [item["message"] for item in refused["diagnostics"]] == ["list index is out of range"]


def test_legacy_classification_source_without_a_canonical_form_is_refused():
    from raes._legacy_classification_source import legacy_classification_source_digest
    from raes.classification_migration import migrate_sdl_classifications

    with pytest.raises(SDLParseError) as refused:
        legacy_classification_source_digest(_BEYOND_JCS_INTEGER)
    assert isinstance(refused.value.__cause__.__cause__, rfc8785.CanonicalizationError)

    result = migrate_sdl_classifications(_BEYOND_JCS_INTEGER)
    assert result.output is None
    assert "classification-migration.source-invalid" in {item.code for item in result.report.diagnostics}


def test_legacy_classification_digest_does_not_report_a_defect_as_a_refusal(monkeypatch):
    from raes import _legacy_classification_source
    from raes._legacy_classification_source import legacy_classification_source_digest

    def defect(_payload: object) -> str:
        raise ValueError("SECRET-DEFECT-DETAIL")

    monkeypatch.setattr(_legacy_classification_source, "canonical_json_digest", defect)
    with pytest.raises(ValueError, match="SECRET-DEFECT-DETAIL"):
        legacy_classification_source_digest("name: legacy\n")

"""Review cycle 2 fixes for pointers, edit refusals, opacity ingress and isolation (ADR-116, issue #1678)."""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

DEFECT = "SECRET-DEFECT-DETAIL"
# The interpreter refuses to convert an integer literal with more than 4300 digits.
_TOO_MANY_DIGITS = "1" * 5000
_LEADING_ZERO_TOKENS = pytest.mark.parametrize("token", ["00", "01", "007"], ids=["00", "01", "007"])


# --- One canonical spelling for each array index (RFC 6901) -------------------------------------------------


def test_array_index_rule_agrees_with_the_incumbent_scenario_resolver():
    from raes._scenario_instantiation import resolve_json_pointer
    from raes_contracts.json_pointer import array_index, is_array_index_token

    values = list(range(11))
    for token in ("0", "1", "10"):
        assert is_array_index_token(token)
        assert array_index(token, len(values)) == resolve_json_pointer(values, f"/{token}")
    for token in ("00", "01", "010", "²", "", "-1", "+1"):
        assert not is_array_index_token(token)
        assert array_index(token, len(values)) is None
        with pytest.raises(ValueError, match="canonical"):
            resolve_json_pointer(values, f"/{token}")


def test_array_index_rule_keeps_the_digit_limit_guard():
    from raes_contracts.json_pointer import array_index, is_array_index_token

    assert is_array_index_token(_TOO_MANY_DIGITS)
    assert array_index(_TOO_MANY_DIGITS, 2) is None
    assert not is_array_index_token("0" + _TOO_MANY_DIGITS)
    assert array_index("0" + _TOO_MANY_DIGITS, 2) is None


@_LEADING_ZERO_TOKENS
def test_evidence_selector_and_authority_pointers_do_not_alias_a_leading_zero_index(token):
    from raes_contracts._evidence_content_validation import _json_pointer_resolves
    from raes_contracts.realization_authority import _MISSING_REALIZATION_SELECTION, _planned_pointer_value
    from raes_processor.planner.realization_authority import _MISSING, _pointer_value

    document = {"items": [{"a": 1}, {"a": 2}]}
    assert _json_pointer_resolves(document, "/items/1/a")
    assert not _json_pointer_resolves(document, f"/items/{token}/a")
    assert _planned_pointer_value(document, "/items/1/a") == 2
    assert _planned_pointer_value(document, f"/items/{token}/a") is _MISSING_REALIZATION_SELECTION
    assert _pointer_value(document, "/items/1/a") == 2
    assert _pointer_value(document, f"/items/{token}/a") is _MISSING


@_LEADING_ZERO_TOKENS
def test_realization_structure_walkers_do_not_alias_a_leading_zero_index(token):
    from raes_contracts.realization_structure._normalization_scopes import (
        MISSING_SCOPE_VALUE,
        _advance_plain_scope,
        _ScopeCursor,
    )
    from raes_contracts.realization_structure._semantic_addresses import _resolve_positional_token

    assert _resolve_positional_token(["a", "b"], "1") == (1, "1", 0)
    with pytest.raises(ValueError, match="does not resolve"):
        _resolve_positional_token(["a", "b"], token)
    cursor = _ScopeCursor(source_path=[], semantic_path=[], current=["a", "b"])
    _advance_plain_scope(cursor, token)
    assert cursor.current is MISSING_SCOPE_VALUE


@pytest.mark.parametrize("token", ["01", "²"], ids=["leading-zero", "unicode-digit"])
def test_closed_record_scope_declares_a_non_index_member_like_any_member_name(token):
    from raes_contracts.realization_structure import (
        RealizationConstraintDocument,
        RealizationRecordConstraint,
        RealizationScope,
        evaluate_realization_constraint,
    )
    from test_issue_1678_sweep_c import _PROFILE, _closure, _relation_outcome

    def evaluate(member: str):
        document = RealizationConstraintDocument(
            semantic_profile=_PROFILE,
            default_closure=_closure("open"),
            scopes=tuple(
                RealizationScope(field_pointer=pointer, closure=_closure("closed"))
                for pointer in ("/record", f"/record/{member}")
            ),
            root=RealizationRecordConstraint(kind="recursive-record", fields={}),
        )
        return evaluate_realization_constraint(document, {"record": {member: {}}})

    assert _relation_outcome(evaluate(token)) == _relation_outcome(evaluate("x"))


@_LEADING_ZERO_TOKENS
def test_realization_designation_does_not_alias_a_leading_zero_index(token):
    from raes import parse_sdl
    from raes.realization_designation import resolve_json_pointer_surface

    scenario = parse_sdl("name: x\nnodes:\n  web: {type: compute, services: [{name: http, port: 80}]}\n")
    assert resolve_json_pointer_surface(scenario, "/nodes/web/services/0")[0]
    assert resolve_json_pointer_surface(scenario, f"/nodes/web/services/{token}") == (False, None)


@_LEADING_ZERO_TOKENS
def test_structured_edit_refuses_a_leading_zero_index(token):
    from raes._language_edit import apply_edit
    from raes_contracts.errors import InvalidInputError

    assert apply_edit({"list": [1, 2]}, operation="set", tokens=["list", "1"], value=3) == {"list": [1, 3]}
    with pytest.raises(InvalidInputError, match="^list path segment is not a canonical array index$"):
        apply_edit({"list": [1, 2]}, operation="set", tokens=["list", token], value=3)


def test_structured_edit_creates_a_list_only_for_a_canonical_index():
    from raes._language_edit import apply_edit

    assert apply_edit({}, operation="set", tokens=["a", "01"], value=1) == {"a": {"01": 1}}
    assert apply_edit({}, operation="set", tokens=["b", "²"], value=1) == {"b": {"²": 1}}
    assert apply_edit({}, operation="set", tokens=["c", "-"], value=1) == {"c": {"-": 1}}
    assert apply_edit({}, operation="set", tokens=["d", "x", "y"], value=1) == {"d": {"x": {"y": 1}}}


# --- Structured-edit refusals do not repeat the caller's pointer ---------------------------------------------

_OVERSIZED = "~" + "x" * 5000

_EDIT_REFUSALS = [
    pytest.param("set", ["list", _TOO_MANY_DIGITS], {"list": [1]}, "list index is out of range", id="out-of-range"),
    pytest.param(
        "set", ["list", _OVERSIZED], {"list": [1]}, "list path segment is not a canonical array index", id="list"
    ),
    pytest.param("delete", [_OVERSIZED], {}, "missing path segment", id="missing-final"),
    pytest.param("delete", [_OVERSIZED, "x"], {}, "missing path segment", id="missing-parent"),
    pytest.param(
        "set", ["name", _OVERSIZED], {"name": "x"}, "path segment does not address a mapping or list", id="assign"
    ),
    pytest.param(
        "delete", ["name", _OVERSIZED], {"name": "x"}, "path segment does not address a mapping or list", id="del"
    ),
    pytest.param(
        "append", ["name", _OVERSIZED], {"name": "x"}, "path segment does not address a mapping or list", id="ap"
    ),
    pytest.param(
        "set", ["name", _OVERSIZED, "x"], {"name": "x"}, "path segment does not address a mapping or list", id="walk"
    ),
    pytest.param("append", [_OVERSIZED], {_OVERSIZED: "x"}, "append target is not a list", id="append-target"),
]


@pytest.mark.parametrize(("operation", "tokens", "data", "message"), _EDIT_REFUSALS)
def test_structured_edit_refusals_use_a_fixed_reason(operation, tokens, data, message):
    from raes._language_edit import apply_edit
    from raes_contracts.errors import InvalidInputError

    with pytest.raises(InvalidInputError) as refused:
        apply_edit(data, operation=operation, tokens=tokens, value=1)
    assert str(refused.value) == message


def _mcp_edit(pointer: str) -> dict:
    import asyncio

    from raes_mcp.server import create_server

    arguments = {"sdl_content": "name: x\nlist: [1]\n", "operation": "set", "pointer": pointer, "value_json": "2"}
    result = asyncio.run(create_server().call_tool("sdl_apply_edit", arguments))
    return json.loads(result[0][0].text)


@pytest.mark.parametrize(
    "pointer",
    ["/list/" + _TOO_MANY_DIGITS, "/name/" + _OVERSIZED, "/list/x" + _OVERSIZED],
    ids=["index", "scalar", "list"],
)
def test_mcp_edit_refusal_message_is_bounded_and_omits_the_pointer(pointer):
    from raes_contracts.diagnostics import DiagnosticModel

    result = _mcp_edit(pointer)

    assert result["status"] == "invalid"
    (diagnostic,) = result["diagnostics"]
    metadata = DiagnosticModel.model_fields["message"].metadata
    portable_limit = next(item.max_length for item in metadata if hasattr(item, "max_length"))
    assert len(diagnostic["message"]) <= portable_limit
    assert "x" * 64 not in diagnostic["message"]
    assert "1" * 64 not in diagnostic["message"]


def test_structured_edit_defect_still_propagates(monkeypatch):
    from raes import _language_edit
    from raes.language_service import apply_structured_edit

    def defect(*_args: object, **_kwargs: object) -> object:
        raise ValueError(DEFECT)

    monkeypatch.setattr(_language_edit, "array_index", defect)
    with pytest.raises(ValueError, match=DEFECT):
        apply_structured_edit("name: x\nlist: [1]\n", operation="set", pointer="/list/0", value=2)


# --- Participant-opacity file ingress keeps the failure category ----------------------------------------------

_OPACITY_FILE_READERS = pytest.mark.parametrize(
    ("module", "reader"),
    [
        ("raes_processor.participant_opacity._service", "analyze_participant_opacity_file"),
        ("raes_processor.participant_opacity._model_check", "model_check_participant_opacity_file"),
    ],
    ids=["analysis", "model-check"],
)


@_OPACITY_FILE_READERS
@pytest.mark.parametrize(
    "content", ['{"a": 1, "a": 2}', "[1]", "{", '{"schema_version": "x"}'], ids=["duplicate", "array", "json", "schema"]
)
def test_opacity_file_with_a_bad_document_is_invalid_input(tmp_path, module, reader, content):
    import importlib

    from raes_contracts.errors import InvalidInputError, OperationalError
    from raes_processor.participant_opacity import ParticipantOpacityInputError

    path = tmp_path / "input.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ParticipantOpacityInputError, match="bounded closed-world admission") as refused:
        getattr(importlib.import_module(module), reader)(path)
    assert isinstance(refused.value, InvalidInputError)
    assert not isinstance(refused.value, OperationalError)
    assert refused.value.__suppress_context__ is True


@_OPACITY_FILE_READERS
def test_opacity_file_that_cannot_be_read_is_an_operational_failure(tmp_path, module, reader):
    import importlib

    from raes_processor.participant_opacity import ParticipantOpacityOperationalError

    with pytest.raises(ParticipantOpacityOperationalError, match="bounded closed-world admission"):
        getattr(importlib.import_module(module), reader)(tmp_path / "absent.json")


@_OPACITY_FILE_READERS
def test_opacity_file_ingress_defect_still_propagates(tmp_path, monkeypatch, module, reader):
    import importlib

    target = importlib.import_module(module)

    def defect(*_args: object, **_kwargs: object) -> object:
        raise ValueError(DEFECT)

    monkeypatch.setattr(target, "parse_bounded_json_object", defect)
    path = tmp_path / "input.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match=DEFECT):
        getattr(target, reader)(path)


# --- The archive adapter is isolated with a foreign-failure record ----------------------------------------------


class ArchiveAdapterOnlyError(Exception):
    """A failure type that only the foreign archive adapter defines."""


_ARCHIVE_SECRET = "archive-secret-sentinel-cycle2"
_LINEAGE_LOGGER = "raes_processor.planner.materialization_lineage"


def _predecessor(archive: object):
    from raes_processor.planner.materialization_lineage import admitted_inventory_predecessor

    record = SimpleNamespace(run_id="run-1", artifact=SimpleNamespace(source="backend"), inventory=object())
    request = SimpleNamespace(materialization_source=SimpleNamespace(run_id="run-1"))
    previous = SimpleNamespace(materialization_attestations=(record,))
    return admitted_inventory_predecessor(request, SimpleNamespace(name="backend"), previous, archive)


def test_foreign_archive_failure_logs_only_a_foreign_failure_record(caplog):
    from raes_contracts.materialization_inventory import InventoryInvariant
    from raes_processor.planner.materialization_lineage import InventoryAdmissionError

    class ForeignArchive:
        def read(self, _record):
            raise ArchiveAdapterOnlyError(_ARCHIVE_SECRET)

    with caplog.at_level(logging.WARNING, logger=_LINEAGE_LOGGER), pytest.raises(InventoryAdmissionError) as raised:
        _predecessor(ForeignArchive())

    assert raised.value.invariant is InventoryInvariant.ARCHIVE
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    (record,) = [item for item in caplog.records if item.name == _LINEAGE_LOGGER]
    assert record.levelno == logging.ERROR
    text = record.exc_text or ""
    assert "ForeignCodeFailure" in text
    assert "ArchiveAdapterOnlyError" not in text
    assert _ARCHIVE_SECRET not in text


def test_retained_archive_integrity_refusal_is_not_logged_as_a_foreign_failure(caplog):
    from raes_contracts.errors import EvidenceIntegrityError
    from raes_contracts.materialization_inventory import InventoryInvariant
    from raes_processor.planner.materialization_lineage import InventoryAdmissionError

    refusal = EvidenceIntegrityError("materialization archive is not a bounded protected regular file")

    class RetainedArchive:
        def read(self, _record):
            raise refusal

    with caplog.at_level(logging.DEBUG, logger=_LINEAGE_LOGGER), pytest.raises(InventoryAdmissionError) as raised:
        _predecessor(RetainedArchive())

    assert raised.value.invariant is InventoryInvariant.ARCHIVE
    assert raised.value.__cause__ is refusal
    assert [item for item in caplog.records if item.name == _LINEAGE_LOGGER] == []


def test_retained_archive_validation_defect_still_propagates(monkeypatch):
    from raes_processor.planner import materialization_admission

    def defect(*_args: object, **_kwargs: object) -> None:
        raise ValueError(DEFECT)

    monkeypatch.setattr(materialization_admission, "validate_materialization_archive_record", defect)

    class Archive:
        def read(self, _record):
            return SimpleNamespace(sdl="name: x\n")

    with pytest.raises(ValueError, match=DEFECT):
        _predecessor(Archive())


# --- The base-image import closure follows relative imports ------------------------------------------------------


def test_base_image_import_closure_follows_relative_imports(tmp_path: Path):
    from test_issue_1238_development_container import _import_closure

    package = tmp_path / "pkg"
    (package / "sub").mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "entry.py").write_text("from .sibling import name\nfrom . import peer\n", encoding="utf-8")
    (package / "sibling.py").write_text("from .sub import deep\n", encoding="utf-8")
    (package / "peer.py").write_text("", encoding="utf-8")
    (package / "sub" / "__init__.py").write_text("from .. import parent_only\n", encoding="utf-8")
    (package / "sub" / "deep.py").write_text("from ..sub.leaf import x\n", encoding="utf-8")
    (package / "sub" / "leaf.py").write_text("", encoding="utf-8")
    (package / "parent_only.py").write_text("", encoding="utf-8")
    (package / "unused.py").write_text("", encoding="utf-8")

    closure = _import_closure(("pkg.entry",), {"pkg": tmp_path})

    assert set(closure) == {
        "pkg/__init__.py",
        "pkg/entry.py",
        "pkg/sibling.py",
        "pkg/peer.py",
        "pkg/sub/__init__.py",
        "pkg/sub/deep.py",
        "pkg/sub/leaf.py",
        "pkg/parent_only.py",
    }
    for path in closure.values():
        ast.parse(path.read_text(encoding="utf-8"))


def test_base_image_import_closure_reaches_errors_through_the_logging_module_alone(tmp_path: Path):
    from test_issue_1238_development_container import _import_closure

    packages = Path(__file__).resolve().parents[1] / "packages"
    closure = _import_closure(("raes_contracts.operational_logging",), {"raes_contracts": packages})

    assert "raes_contracts/errors.py" in closure


# --- Packaged behavioral-relation authorities raise typed failures -----------------------------------------------

_PROFILE_ID = "participant-opacity-baseline-v1"


@pytest.mark.parametrize(
    ("profile_id", "revision"),
    [(_PROFILE_ID, "no-such-revision"), ("unpackaged-profile-v1", "rev1"), ("Not Portable", "rev1")],
    ids=["revision", "profile", "identifier"],
)
def test_unsupported_profile_request_is_invalid_input(profile_id, revision):
    from raes_contracts.behavioral_authority_errors import BehavioralAuthorityUnsupportedError
    from raes_contracts.behavioral_relation_profiles import load_behavioral_relation_profile_revision
    from raes_contracts.errors import InvalidInputError

    with pytest.raises(BehavioralAuthorityUnsupportedError, match="requested") as refused:
        load_behavioral_relation_profile_revision(profile_id, revision)
    assert isinstance(refused.value, InvalidInputError)
    assert not isinstance(refused.value, ValueError)


def test_unsupported_catalog_revision_is_invalid_input():
    from raes_contracts.behavioral_authority_errors import BehavioralAuthorityUnsupportedError
    from raes_contracts.behavioral_relations import load_behavioral_relation_catalog_revision

    with pytest.raises(BehavioralAuthorityUnsupportedError, match="requested"):
        load_behavioral_relation_catalog_revision("rev-unpackaged")


@pytest.fixture
def _damaged_catalogs(tmp_path, monkeypatch):
    from raes_contracts import behavioral_relations

    damaged = tmp_path / "catalog.json"
    damaged.write_text("{}", encoding="utf-8")
    monkeypatch.setitem(behavioral_relations._HISTORICAL_CATALOG_PATHS, "rev8", damaged)
    monkeypatch.setattr(behavioral_relations, "behavioral_relation_catalog_path", lambda: damaged)
    behavioral_relations.load_behavioral_relation_catalog.cache_clear()
    behavioral_relations.load_behavioral_relation_catalog_revision.cache_clear()
    yield
    behavioral_relations.load_behavioral_relation_catalog.cache_clear()
    behavioral_relations.load_behavioral_relation_catalog_revision.cache_clear()


@pytest.mark.usefixtures("_damaged_catalogs")
@pytest.mark.parametrize("revision", [None, "rev8"], ids=["current", "historical"])
def test_damaged_packaged_catalog_is_an_operational_failure(caplog, revision):
    from raes_contracts import behavioral_relations
    from raes_contracts.behavioral_authority_errors import BehavioralAuthorityArtifactError
    from raes_contracts.errors import OperationalError

    logger = behavioral_relations.__name__
    with (
        caplog.at_level(logging.ERROR, logger=logger),
        pytest.raises(BehavioralAuthorityArtifactError, match="catalog is invalid") as refused,
    ):
        if revision is None:
            behavioral_relations.load_behavioral_relation_catalog()
        else:
            behavioral_relations.load_behavioral_relation_catalog_revision(revision)
    assert isinstance(refused.value, OperationalError)
    assert refused.value.__suppress_context__ is True
    assert len([item for item in caplog.records if item.name == behavioral_relations.__name__]) == 1


def test_profile_artifact_with_a_foreign_identity_is_an_operational_failure(tmp_path):
    from raes_contracts.behavioral_authority_errors import BehavioralAuthorityArtifactError
    from raes_contracts.behavioral_relation_profiles import (
        behavioral_relation_profile_path,
        load_behavioral_relation_profile_from_path,
    )

    other = tmp_path / "profile.json"
    other.write_text(behavioral_relation_profile_path(_PROFILE_ID).read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(BehavioralAuthorityArtifactError, match="identity"):
        load_behavioral_relation_profile_from_path("participant-opacity-theorem-v1", other)


def _unsupported_claim(**changes: object):
    from raes_contracts.contracts import BehavioralClaimBindingModel
    from test_behavioral_relations import _bounded_empirical_claim

    return BehavioralClaimBindingModel.model_validate({**_bounded_empirical_claim(), **changes})


def test_claim_binding_naming_an_unpackaged_revision_fails_its_field_check():
    from raes_contracts.behavioral_relations import validate_behavioral_claim_binding

    with pytest.raises(ValueError, match="unsupported catalog revision") as refused:
        validate_behavioral_claim_binding(_unsupported_claim(taxonomy_revision="rev99"))
    assert type(refused.value) is ValueError


@pytest.mark.usefixtures("_damaged_catalogs")
def test_claim_binding_against_a_damaged_catalog_propagates_the_operational_failure():
    from raes_contracts.behavioral_authority_errors import BehavioralAuthorityArtifactError
    from raes_contracts.behavioral_relations import validate_behavioral_claim_binding

    with pytest.raises(BehavioralAuthorityArtifactError):
        validate_behavioral_claim_binding(_unsupported_claim())


@pytest.mark.usefixtures("_damaged_catalogs")
def test_pydantic_validators_translate_a_damaged_authority_to_a_validation_error():
    from pydantic import ValidationError
    from raes_contracts.contracts import ExperimentStudyModel
    from raes_contracts.scientific_completeness import ScientificCompletenessTaxonomyModel, scientific_completeness_root
    from test_behavioral_relations import REPO_ROOT, _bounded_empirical_claim

    taxonomy = json.loads(
        (scientific_completeness_root() / "scientific-scenario-completeness-rev1.json").read_text(encoding="utf-8")
    )
    with pytest.raises(ValidationError, match="authority is damaged"):
        ScientificCompletenessTaxonomyModel.model_validate(taxonomy)

    fixture = REPO_ROOT / "contracts/fixtures/experiment-core/experiment-study-v1/valid/reference.json"
    study = json.loads(fixture.read_text(encoding="utf-8"))
    study["behavioral_claims"] = [_bounded_empirical_claim()]
    with pytest.raises(ValidationError, match="authority is damaged"):
        ExperimentStudyModel.model_validate(study)


def _authority_failure(kind: str):
    from raes_contracts.behavioral_authority_errors import (
        BehavioralAuthorityArtifactError,
        BehavioralAuthorityUnsupportedError,
    )

    failures = {
        "unsupported": BehavioralAuthorityUnsupportedError(
            "requested behavioral relation profile revision is unsupported"
        ),
        "damaged": BehavioralAuthorityArtifactError("behavioral relation catalog is invalid"),
        "defect": ValueError(DEFECT),
    }

    def fail(*_args: object, **_kwargs: object) -> object:
        raise failures[kind]

    return fail


def _opacity_request_file(tmp_path: Path, module: str) -> Path:
    if module.endswith("_service"):
        from test_issue_961_participant_opacity import _point, _request

        request, _ = _request(
            (
                _point(0, secret=True, observation="observation:shared"),
                _point(1, secret=False, observation="observation:shared"),
            )
        )
    else:
        from test_issue_962_participant_opacity_model_check import _request, _state

        request, _, _ = _request(
            (
                _state(0, secret=True, observation="observation:shared"),
                _state(1, secret=False, observation="observation:shared"),
            ),
            initial_state_ordinals=(0, 1),
        )
    path = tmp_path / "input.json"
    path.write_text(request.model_dump_json(), encoding="utf-8")
    return path


@_OPACITY_FILE_READERS
@pytest.mark.parametrize(
    ("kind", "expected"),
    [("unsupported", "ParticipantOpacityInputError"), ("damaged", "ParticipantOpacityOperationalError")],
    ids=["unsupported", "damaged"],
)
def test_opacity_file_maps_authority_failures_to_their_category(tmp_path, monkeypatch, module, reader, kind, expected):
    import importlib

    from raes_processor import participant_opacity

    target = importlib.import_module(module)
    path = _opacity_request_file(tmp_path, module)
    monkeypatch.setattr(target, "load_behavioral_relation_profile_revision", _authority_failure(kind))
    with pytest.raises(getattr(participant_opacity, expected)):
        getattr(target, reader)(path)


@_OPACITY_FILE_READERS
def test_opacity_file_authority_defect_still_propagates(tmp_path, monkeypatch, module, reader):
    import importlib

    target = importlib.import_module(module)
    path = _opacity_request_file(tmp_path, module)
    monkeypatch.setattr(target, "load_behavioral_relation_profile_revision", _authority_failure("defect"))
    with pytest.raises(ValueError, match=DEFECT):
        getattr(target, reader)(path)


@pytest.mark.parametrize(
    "loader", ["load_behavioral_relation_catalog_revision", "load_behavioral_relation_profile_revision"]
)
def test_runtime_enforcement_maps_authority_failures(monkeypatch, loader):
    from raes_contracts import participant_opacity_runtime
    from raes_contracts.behavioral_authority_errors import BehavioralAuthorityArtifactError

    binding = SimpleNamespace(taxonomy_revision="rev8", profile_id=_PROFILE_ID, profile_revision="rev1")
    catalog = None if loader.endswith("catalog_revision") else object()

    def validate():
        participant_opacity_runtime.validate_participant_opacity_runtime_enforcement(
            binding, support=object(), participant_address="p", audience_scope_ref="a", catalog=catalog
        )

    monkeypatch.setattr(participant_opacity_runtime, loader, _authority_failure("unsupported"))
    with pytest.raises(ValueError, match="unsupported authority") as refused:
        validate()
    assert type(refused.value) is ValueError
    monkeypatch.setattr(participant_opacity_runtime, loader, _authority_failure("damaged"))
    with pytest.raises(BehavioralAuthorityArtifactError):
        validate()
    monkeypatch.setattr(participant_opacity_runtime, loader, _authority_failure("defect"))
    with pytest.raises(ValueError, match=DEFECT):
        validate()


def test_crossing_export_refuses_an_unpackaged_catalog_revision_as_invalid_input():
    from implementations.formal.participant_crossing import export
    from raes_contracts.behavioral_authority_errors import BehavioralAuthorityUnsupportedError
    from raes_contracts.errors import InvalidInputError

    with pytest.raises(InvalidInputError, match="does not resolve") as refused:
        export._profile_catalog("rev-unpackaged")
    assert isinstance(refused.value.__cause__, BehavioralAuthorityUnsupportedError)


# --- The incumbent resolvers reuse the shared array-index rule ---------------------------------------------------


def test_scenario_resolver_keeps_its_outcomes_with_the_shared_rule():
    from raes import _scenario_instantiation
    from raes._scenario_instantiation import resolve_json_pointer

    payload = {"items": [{"a": 1}, {"a": 2}]}
    assert resolve_json_pointer(payload, "/items/1/a") == 2
    for token in ("01", "00", "²", "-1", ""):
        with pytest.raises(ValueError, match="canonical non-negative integer"):
            resolve_json_pointer(payload, f"/items/{token}")
    with pytest.raises(IndexError):
        resolve_json_pointer(payload, "/items/2")
    assert _scenario_instantiation.is_array_index_token.__module__ == "raes_contracts.json_pointer"


def test_runtime_inventory_lookup_uses_the_shared_rule():
    from raes import runtime_inventory

    assert not hasattr(runtime_inventory, "_canonical_index")
    assert runtime_inventory.is_array_index_token.__module__ == "raes_contracts.json_pointer"
    assert runtime_inventory.runtime_inventory_collection_identity("datastore-services", "/0/nodes") == ("node_id",)
    assert runtime_inventory.runtime_inventory_collection_identity("datastore-services", "/01/nodes") == ()

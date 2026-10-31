"""Repository tool input failures stay refusals after the narrowed handlers (ADR-116, issue #1678)."""

from __future__ import annotations

import ast
import errno
import hashlib
import io
import json
import locale
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from raes_contracts.errors import EvidenceIntegrityError, InvalidInputError, OperationalError
from test_pr_body_guard import GROUND_CONTROL_REQUIREMENT_FREE
from tools.policy.common import PolicyFailure
from tools.verified_tool_installation import ToolInstallationError

ROOT = Path(__file__).resolve().parents[3]
# Python refuses to convert an integer literal with more digits than its default limit (4300).
_BEYOND_DIGIT_LIMIT = "1" * 5000
_SECRET = "SECRET-DEFECT-DETAIL"
# The C JSON decoder and the Python compiler stop deep input at a depth that depends on the stack
# size of the host, so a fixed fixture depth does not fail on every host. These markers identify
# the deep fixtures below, which the stack-limited decoders refuse on every host.
_DEEP_JSON_MARKER = "[" * 50_000
_DEEP_PYTHON_MARKER = "+1" * 50_000


@pytest.fixture(autouse=True)
def _stack_limited_decoders(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the decoder and the parser refuse the deep fixtures as a host with a small stack does."""

    import json.decoder

    raw_decode = json.decoder.JSONDecoder.raw_decode
    parse = ast.parse

    def limited_raw_decode(self: json.decoder.JSONDecoder, text: str, idx: int = 0) -> tuple[object, int]:
        if _DEEP_JSON_MARKER in text:
            raise RecursionError("maximum recursion depth exceeded while decoding a JSON array")
        return raw_decode(self, text, idx)

    def limited_parse(source: str | bytes, *args: object, **kwargs: object) -> ast.AST:
        text = source.decode("utf-8", "replace") if isinstance(source, bytes) else source
        if isinstance(text, str) and _DEEP_PYTHON_MARKER in text:
            raise RecursionError("maximum recursion depth exceeded during compilation")
        return parse(source, *args, **kwargs)

    monkeypatch.setattr(json.decoder.JSONDecoder, "raw_decode", limited_raw_decode)
    monkeypatch.setattr(ast, "parse", limited_parse)


def _crossing_workspace(tmp_path: Path, producer) -> Path:
    for name in (*producer.SOURCE_PATHS, producer.PROFILE_PATH):
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    return tmp_path


def _crossing_producers():
    from implementations.formal.participant_crossing import export, multi_export

    return {"single": export, "multi": multi_export}


@pytest.fixture
def _damaged_crossing_catalog(tmp_path, monkeypatch):
    """Replace the packaged rev8 catalog, which both crossing profiles name, with a damaged file."""

    from raes_contracts import behavioral_relations

    damaged = tmp_path / "damaged-catalog" / "behavioral-relations-v1-rev8.json"
    damaged.parent.mkdir()
    damaged.write_text("{}", encoding="utf-8")
    monkeypatch.setitem(behavioral_relations._HISTORICAL_CATALOG_PATHS, "rev8", damaged)
    behavioral_relations.load_behavioral_relation_catalog_revision.cache_clear()
    yield
    behavioral_relations.load_behavioral_relation_catalog_revision.cache_clear()


@pytest.mark.parametrize("profile", ["single", "multi"])
@pytest.mark.usefixtures("_damaged_crossing_catalog")
def test_crossing_profile_with_a_damaged_catalog_revision_is_an_operational_failure(tmp_path, profile):
    producer = _crossing_producers()[profile]
    root = _crossing_workspace(tmp_path / "root", producer)

    # A damaged packaged catalog is a host failure, not an input that the profile author can correct.
    with pytest.raises(OperationalError, match="catalog is invalid"):
        producer.build_bundle(root)


@pytest.mark.usefixtures("_damaged_crossing_catalog")
def test_crossing_cli_reports_a_damaged_catalog_revision_as_failed_validation(tmp_path, monkeypatch, capsys):
    from implementations.formal.participant_crossing import __main__, export

    root = _crossing_workspace(tmp_path / "root", export)
    check = export.check
    monkeypatch.setattr(export, "check", lambda _root: check(root))

    assert __main__.main([]) == 1
    assert capsys.readouterr().err == "participant-crossing model export failed validation\n"


def test_crossing_cli_keeps_a_build_defect_out_of_the_refusal(tmp_path, monkeypatch, capsys, caplog):
    from implementations.formal.participant_crossing import __main__, export
    from raes_contracts.operational_logging import run_application

    root = _crossing_workspace(tmp_path, export)
    check = export.check

    def defect(*_args):
        raise ValueError(_SECRET)

    monkeypatch.setattr(export, "_validate_graph", defect)
    monkeypatch.setattr(export, "check", lambda _root: check(root))

    assert run_application(lambda: __main__.main([])) == 1
    captured = capsys.readouterr()
    assert "failed validation" not in captured.err
    assert _SECRET not in captured.err + captured.out + caplog.text
    assert "application stopped after an unexpected error" in caplog.text


def test_bounded_json_loader_refuses_an_integer_beyond_the_digit_limit(tmp_path):
    from tools.policy.common import load_bounded_json_object

    (tmp_path / "document.json").write_text(f'{{"value": {_BEYOND_DIGIT_LIMIT}}}', encoding="utf-8")

    with pytest.raises(InvalidInputError, match="digit limit") as refused:
        load_bounded_json_object(tmp_path, "document.json", max_bytes=64 * 1024)
    assert _BEYOND_DIGIT_LIMIT not in str(refused.value)


def test_bounded_json_loader_keeps_valid_integers(tmp_path):
    from tools.policy.common import load_bounded_json_object

    (tmp_path / "document.json").write_text(
        '{"small": -0, "large": 9007199254740993, "list": [1, 2]}', encoding="utf-8"
    )

    assert load_bounded_json_object(tmp_path, "document.json", max_bytes=1024) == {
        "small": 0,
        "large": 9007199254740993,
        "list": [1, 2],
    }


def test_bounded_json_loader_refuses_nesting_beyond_the_decoder_depth(tmp_path):
    from tools.policy.common import load_bounded_json_object

    depth = 100_000
    (tmp_path / "document.json").write_text('{"value": ' + "[" * depth + "]" * depth + "}", encoding="utf-8")

    with pytest.raises(InvalidInputError, match="depth limit"):
        load_bounded_json_object(tmp_path, "document.json", max_bytes=512 * 1024)


def test_formal_production_replay_refuses_a_fixture_beyond_the_decoder_depth(tmp_path):
    from tools.formal_semantic_validation import _production

    depth = 100_000
    fixture = _write(tmp_path, "fixture.json", '{"value": ' + "[" * depth + "]" * depth + "}")
    case = {"replay_mode": "exploit-path", "fixture_path": "fixture.json"}

    # The production replay boundary reports InvalidInputError as a replay failure.
    with pytest.raises(InvalidInputError, match="depth limit"):
        _production._replay_production_evidence(tmp_path, case, {}, fixture, "evidence.json", [], replay_current=False)


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _digit_limit_document() -> str:
    return f'{{"schema_version": {_BEYOND_DIGIT_LIMIT}}}'


_SCHEMA_PUBLICATION_MANIFEST = "contracts/schema-publication-manifest.json"


def _sharded_schema_publication(root: Path, entry_text: str) -> None:
    _write(
        root,
        _SCHEMA_PUBLICATION_MANIFEST,
        json.dumps(
            {
                "schema_version": "schema-publication-manifest/v2",
                "hash_algorithm": "sha256-canonical-json",
                "entries_directory": "contracts/schema-publication/entries",
                "tombstones_directory": "contracts/schema-publication/tombstones",
            }
        ),
    )
    _write(root, "contracts/schema-publication/entries/example-contract.json", entry_text)
    (root / "contracts/schema-publication/tombstones").mkdir(parents=True)


@pytest.mark.parametrize("location", ["manifest", "record"])
def test_schema_publication_catalog_refuses_an_integer_beyond_the_digit_limit(tmp_path, location):
    from tools.check_schema_publication import load_schema_publication_catalog

    if location == "manifest":
        _write(tmp_path, _SCHEMA_PUBLICATION_MANIFEST, _digit_limit_document())
    else:
        _sharded_schema_publication(tmp_path, f'{{"contract_id": "example-contract", "n": {_BEYOND_DIGIT_LIMIT}}}')

    with pytest.raises(InvalidInputError, match="digit limit") as refused:
        load_schema_publication_catalog(tmp_path)
    assert _BEYOND_DIGIT_LIMIT not in str(refused.value)


def test_schema_publication_catalog_keeps_a_valid_sharded_catalog(tmp_path):
    from tools.check_schema_publication import load_schema_publication_catalog

    _sharded_schema_publication(tmp_path, '{"contract_id": "example-contract", "revision": 12}')

    catalog = load_schema_publication_catalog(tmp_path)
    assert catalog["schemas"] == [{"contract_id": "example-contract", "revision": 12}]
    assert catalog["removed_schemas"] == []


def test_deprecation_lifecycle_reads_an_undecodable_publication_catalog_as_no_tombstones(tmp_path):
    from tools import check_deprecation_lifecycle

    _write(tmp_path, _SCHEMA_PUBLICATION_MANIFEST, _digit_limit_document())

    assert check_deprecation_lifecycle._load_removed_schema_paths(tmp_path) == set()


def test_sdl_lineage_reports_an_undecodable_publication_catalog(tmp_path):
    from raes_contracts.provenance import SDLLineageLedgerModel
    from tools import check_sdl_lineage

    _write(tmp_path, _SCHEMA_PUBLICATION_MANIFEST, _digit_limit_document())
    ledger = SDLLineageLedgerModel.model_validate(
        json.loads((ROOT / check_sdl_lineage.LEDGER_PATH).read_text(encoding="utf-8"))
    )

    failures = check_sdl_lineage._validate_authorities(tmp_path, ledger)
    assert [failure.rule_id for failure in failures] == ["lineage-schema-publication-manifest-invalid"]


def test_scientific_completeness_reports_an_undecodable_publication_catalog(tmp_path):
    from tools import check_scientific_scenario_completeness

    _write(tmp_path, _SCHEMA_PUBLICATION_MANIFEST, _digit_limit_document())

    failures = check_scientific_scenario_completeness.evaluate(tmp_path)
    invalid = [failure for failure in failures if failure.rule_id == "scientific-completeness-manifest-invalid"]
    assert len(invalid) == 1
    assert _BEYOND_DIGIT_LIMIT not in invalid[0].message


def test_sdl_lineage_reports_a_ledger_with_an_integer_beyond_the_digit_limit(tmp_path):
    from tools import check_sdl_lineage

    _write(tmp_path, check_sdl_lineage.LEDGER_PATH, _digit_limit_document())

    failures = check_sdl_lineage.evaluate(tmp_path)
    assert [failure.rule_id for failure in failures] == ["lineage-ledger-invalid"]
    assert _BEYOND_DIGIT_LIMIT not in failures[0].message


def test_sdl_lineage_reports_a_canonical_catalog_with_an_integer_beyond_the_digit_limit(tmp_path):
    from tools import check_sdl_lineage

    ledger = check_sdl_lineage.LEDGER_PATH
    _write(tmp_path, ledger, (ROOT / ledger).read_text(encoding="utf-8"))
    _write(tmp_path, check_sdl_lineage.AUTHORING_SCHEMA_PATH, _digit_limit_document())

    failures = check_sdl_lineage.evaluate(tmp_path)
    assert [failure.rule_id for failure in failures] == ["lineage-canonical-catalog-invalid"]
    assert _BEYOND_DIGIT_LIMIT not in failures[0].message


@pytest.mark.parametrize(
    ("document", "pointer"),
    [
        (_digit_limit_document(), "#/schema_version"),
        ('{"items": [0, 1]}', "#/items/" + _BEYOND_DIGIT_LIMIT),
    ],
    ids=["document", "pointer"],
)
def test_sdl_lineage_claim_pointer_beyond_the_digit_limit_does_not_resolve(tmp_path, document, pointer):
    from tools import check_sdl_lineage

    _write(tmp_path, "claims/authority.json", document)

    failures = check_sdl_lineage._validate_claim_pointers(tmp_path, {("claims/authority.json", pointer)})
    assert [failure.rule_id for failure in failures] == ["lineage-claim-pointer-missing"]


def test_sdl_lineage_pointer_keeps_canonical_ascii_list_positions():
    from tools import check_sdl_lineage

    document = {"items": [0, 1, 2]}
    assert check_sdl_lineage._resolve_json_pointer(document, "#/items/2") is True
    # RFC 6901 gives each index one ASCII spelling, so a leading zero or a non-ASCII digit names no position.
    assert check_sdl_lineage._resolve_json_pointer(document, "#/items/0002") is False
    assert check_sdl_lineage._resolve_json_pointer(document, "#/items/٢") is False
    assert check_sdl_lineage._resolve_json_pointer(document, "#/items/3") is False
    assert check_sdl_lineage._resolve_json_pointer(document, "#/items/" + _BEYOND_DIGIT_LIMIT) is False


def test_json_artifact_routing_reads_undecodable_historical_records_as_no_exclusions(tmp_path):
    from tools import check_json_artifacts

    _write(tmp_path, check_json_artifacts._HISTORICAL_IDENTITY_RECORDS_PATH, _digit_limit_document())

    assert check_json_artifacts._frozen_historical_records(tmp_path) == frozenset()


def test_json_artifact_routing_keeps_valid_historical_records(tmp_path):
    from tools import check_json_artifacts

    _write(
        tmp_path,
        check_json_artifacts._HISTORICAL_IDENTITY_RECORDS_PATH,
        '{"records": [{"path": "contracts/a.json", "revision": 2}, {"path": 3}]}',
    )

    assert check_json_artifacts._frozen_historical_records(tmp_path) == frozenset({"contracts/a.json"})


def test_public_docs_redirect_map_with_an_integer_beyond_the_digit_limit_is_a_redirect_failure(tmp_path):
    from tools import check_public_docs

    _write(tmp_path, "docs/public/redirects.json", f'{{"old": "new", "n": {_BEYOND_DIGIT_LIMIT}}}')

    with pytest.raises(InvalidInputError, match="digit limit"):
        check_public_docs._load_redirects(tmp_path / "docs/public")
    failures = check_public_docs.evaluate_public_sources(tmp_path)
    redirect = [failure for failure in failures if failure.rule_id == "public-docs-redirect-map"]
    assert len(redirect) == 1
    assert _BEYOND_DIGIT_LIMIT not in redirect[0].message


def test_public_docs_search_index_with_an_integer_beyond_the_digit_limit_is_a_search_index_failure(tmp_path):
    from tools import check_public_docs

    (tmp_path / "docs/public").mkdir(parents=True)
    index = _write(tmp_path, "out/searchindex.js", f'Search.setIndex({{"docnames": [], "n": {_BEYOND_DIGIT_LIMIT}}})')

    with pytest.raises(InvalidInputError, match="digit limit"):
        check_public_docs._search_docnames(index)
    failures = check_public_docs.evaluate_public_output(tmp_path, tmp_path / "out")
    search = [failure for failure in failures if failure.rule_id == "public-docs-search-index"]
    assert len(search) == 1
    assert _BEYOND_DIGIT_LIMIT not in search[0].message


def test_public_docs_search_index_keeps_valid_docnames(tmp_path):
    from tools import check_public_docs

    index = _write(tmp_path, "searchindex.js", 'Search.setIndex({"docnames": ["index", "guide"], "envversion": 63})')

    assert check_public_docs._search_docnames(index) == {"index", "guide"}


def test_related_work_bundle_with_an_integer_beyond_the_digit_limit_is_an_invalid_bundle(tmp_path):
    from tools import check_related_work_comparison

    _write(tmp_path, check_related_work_comparison.PROTOCOL_PATH, _digit_limit_document())

    failures = check_related_work_comparison.evaluate(tmp_path)
    assert [failure.rule_id for failure in failures] == ["related-work-bundle-invalid"]
    assert _BEYOND_DIGIT_LIMIT not in failures[0].message


def test_dsl_evaluation_manifest_with_an_integer_beyond_the_digit_limit_is_an_invalid_bundle(tmp_path):
    from tools import check_dsl_language_evaluation
    from tools.dsl_language_evaluation._keys import MANIFEST_PATH

    _write(tmp_path, MANIFEST_PATH, _digit_limit_document())

    failures = check_dsl_language_evaluation.evaluate(tmp_path)
    assert [failure.rule_id for failure in failures] == ["dsl-evaluation-bundle-invalid"]
    assert _BEYOND_DIGIT_LIMIT not in failures[0].message


@pytest.mark.parametrize(
    "scalar",
    ["2024-13-01", _BEYOND_DIGIT_LIMIT, "!!bool maybe", "!!timestamp later", '!!int ""'],
    ids=["impossible-date", "digit-limit", "unknown-bool", "unmatched-timestamp", "empty-int"],
)
def test_policy_yaml_loader_refuses_an_unconstructable_scalar(tmp_path, scalar):
    from tools.policy.common import load_yaml

    path = _write(tmp_path, "policy.yaml", f"value: {scalar}\n")

    with pytest.raises(InvalidInputError, match="cannot be constructed") as refused:
        load_yaml(path)
    assert _BEYOND_DIGIT_LIMIT not in str(refused.value)


def test_policy_yaml_loader_keeps_decode_syntax_and_valid_outcomes(tmp_path):
    from tools.policy.common import load_yaml

    undecodable = tmp_path / "undecodable.yaml"
    undecodable.write_bytes(b"value: \xff\n")
    with pytest.raises(UnicodeDecodeError):
        load_yaml(undecodable)
    # The parser keeps reading the file stream, so a syntax error still names the file.
    path = _write(tmp_path, "syntax.yaml", "value: [unclosed\n")
    with pytest.raises(yaml.YAMLError, match="syntax.yaml"):
        load_yaml(path)
    valid = _write(tmp_path, "valid.yaml", "when: 2024-12-01\ncount: 3\n")
    assert load_yaml(valid) == {"when": date(2024, 12, 1), "count": 3}
    assert load_yaml(_write(tmp_path, "empty.yaml", "")) == {}


def test_policy_yaml_loader_keeps_a_parser_defect_out_of_the_refusal(tmp_path, monkeypatch):
    from tools.policy import common

    def defect(_stream):
        raise TypeError(_SECRET)

    monkeypatch.setattr(common.yaml, "safe_load", defect)
    path = _write(tmp_path, "policy.yaml", "value: 1\n")
    with pytest.raises(TypeError, match=_SECRET):
        common.load_yaml(path)


def test_public_docs_keep_a_redirect_loader_defect_out_of_the_refusal(tmp_path, monkeypatch):
    from tools import check_public_docs

    (tmp_path / "docs/public").mkdir(parents=True)

    def defect(_public_root):
        raise ValueError(_SECRET)

    monkeypatch.setattr(check_public_docs, "_load_redirects", defect)
    with pytest.raises(ValueError, match=_SECRET):
        check_public_docs.evaluate_public_sources(tmp_path)


def test_related_work_keeps_a_bundle_loader_defect_out_of_the_refusal(tmp_path, monkeypatch):
    from tools import check_related_work_comparison

    def defect(_repo_root):
        raise ValueError(_SECRET)

    monkeypatch.setattr(check_related_work_comparison, "load_bundle", defect)
    with pytest.raises(ValueError, match=_SECRET):
        check_related_work_comparison.evaluate(tmp_path)


def test_schema_publication_catalog_keeps_a_record_loader_defect_out_of_the_refusal(tmp_path, monkeypatch):
    from tools import check_deprecation_lifecycle, check_schema_publication

    _sharded_schema_publication(tmp_path, '{"contract_id": "example-contract"}')

    def defect(*_args, **_kwargs):
        raise ValueError(_SECRET)

    monkeypatch.setattr(check_schema_publication, "_load_record_directory", defect)
    with pytest.raises(ValueError, match=_SECRET):
        check_deprecation_lifecycle._load_removed_schema_paths(tmp_path)


@pytest.mark.parametrize(
    "value",
    [_BEYOND_DIGIT_LIMIT, "[" * 3000 + "]" * 3000],
    ids=["integer-beyond-digit-limit", "nesting-beyond-parser-depth"],
)
def test_example_library_reports_an_unparseable_worked_example(tmp_path, value):
    from tools import example_library_checks

    path = _write(tmp_path, "worked.sdl.yaml", f"name: worked\nvariables: {{n: {value}}}\n")

    failures = example_library_checks.check_worked_example_file(
        path, "worked.sdl.yaml", {"validation_status": example_library_checks.VALIDATED}
    )
    assert [failure.rule_id for failure in failures] == ["example-library-worked-example-body"]
    assert _BEYOND_DIGIT_LIMIT not in failures[0].message


def test_example_library_keeps_a_parser_defect_out_of_the_refusal(tmp_path, monkeypatch):
    from tools import example_library_checks

    path = _write(tmp_path, "worked.sdl.yaml", "name: worked\n")

    def defect(_source):
        raise ValueError(_SECRET)

    monkeypatch.setattr(example_library_checks, "parse_sdl_file", defect)
    with pytest.raises(ValueError, match=_SECRET):
        example_library_checks.check_worked_example_file(
            path, "worked.sdl.yaml", {"validation_status": example_library_checks.VALIDATED}
        )


def test_example_library_reports_a_template_with_an_integer_beyond_the_digit_limit(tmp_path):
    from tools import example_library_checks

    path = _write(tmp_path, "template.yaml", f"name: template\nbody: {{n: {_BEYOND_DIGIT_LIMIT}}}\n")

    body, failures = example_library_checks.load_template_file(path, "template.yaml")
    assert body is None
    assert [failure.rule_id for failure in failures] == ["example-library-parse"]
    assert _BEYOND_DIGIT_LIMIT not in failures[0].message


# "²" passes str.isdigit() but int() refuses it; "٣" is a decimal digit that int() accepts.
_NON_INDEX_TOKENS = ["²", "٣", _BEYOND_DIGIT_LIMIT]


@pytest.mark.parametrize("token", _NON_INDEX_TOKENS, ids=["superscript", "arabic-indic", "digit-limit"])
def test_schema_coverage_pointer_with_a_non_index_token_resolves_to_nothing(token):
    from tools.schema_coverage._evidence import resolve_pointer

    assert resolve_pointer({"items": [0, 1, 2, 3]}, f"/items/{token}") == (None, False)


def test_schema_coverage_pointer_keeps_ascii_list_indexes():
    from tools.schema_coverage._evidence import resolve_pointer

    document = {"items": [0, 1, 2], "empty": []}
    assert resolve_pointer(document, "/items/2") == (2, True)
    assert resolve_pointer(document, "/items/0002") == (None, False)
    assert resolve_pointer(document, "/items/3") == (None, False)
    assert resolve_pointer(document, "/empty/0") == (None, False)
    assert resolve_pointer(document, "/items/-1") == (None, False)


def test_schema_coverage_embedded_source_with_a_non_index_token_is_unresolved_evidence(tmp_path):
    from tools.schema_coverage._evidence import check_embedded_source

    _write(tmp_path, "contracts/carrier.json", '{"items": [0, 1, 2]}')

    reason = check_embedded_source(tmp_path, "contracts/carrier.json", "contracts/schemas/x.json", "/items/²", None)
    assert reason == "embedded pointer /items/² resolves to nothing in contracts/carrier.json"


@pytest.mark.parametrize("token", _NON_INDEX_TOKENS, ids=["superscript", "arabic-indic", "digit-limit"])
def test_specification_coverage_pointer_with_a_non_index_token_resolves_to_nothing(token):
    from tools.specification_coverage._primitives import _json_pointer_get

    assert _json_pointer_get({"items": [0, 1, 2, 3]}, f"/items/{token}") == (False, None)


def test_specification_coverage_pointer_keeps_ascii_list_indexes():
    from tools.specification_coverage._primitives import _json_pointer_get

    document = {"items": [0, 1, 2], "pair": (5, 6)}
    assert _json_pointer_get(document, "/items/2") == (True, 2)
    assert _json_pointer_get(document, "/items/0002") == (False, None)
    assert _json_pointer_get(document, "/pair/1") == (True, 6)
    assert _json_pointer_get(document, "/items/3") == (False, None)
    assert _json_pointer_get(document, "/items/-1") == (False, None)


# Installer and toolchain tools.

_INSTALLERS_DEFECT_DETAIL = "SECRET-DEFECT-DETAIL"
_INSTALLERS_BEYOND_DIGIT_LIMIT = "1" * 5000
_INSTALLERS_TREE_INTEGRITY_FAILURE = "tool-installation: tree-integrity-failure"


def _installers_manifest(entries: str) -> bytes:
    return ('{"entries":[' + entries + '],"format":"tar.gz","schema":"raes-installed-tree/v1"}').encode("ascii")


# A retained manifest fails closed as tree-integrity-failure, the reason the parser reported before the narrowing.
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            ('{"entries":' + _INSTALLERS_BEYOND_DIGIT_LIMIT + "}").encode("ascii"), id="integer-beyond-digit-limit"
        ),
        pytest.param(b"[" * 100_000 + b"]" * 100_000, id="nesting-beyond-decoder-depth"),
        pytest.param(_installers_manifest('{"kind":"directory","path":"\\ud800"}'), id="unpaired-surrogate-path"),
        pytest.param(
            _installers_manifest('{"kind":"symlink","path":"link","target":"\\ud800"}'),
            id="unpaired-surrogate-link-target",
        ),
    ],
)
def test_retained_tree_manifest_input_failures_stay_tree_integrity_failures(payload: bytes) -> None:
    from tools.verified_tree_manifest import parse_manifest

    descriptor = SimpleNamespace()
    with pytest.raises(ToolInstallationError) as refused:
        parse_manifest(payload, descriptor)
    assert str(refused.value) == _INSTALLERS_TREE_INTEGRITY_FAILURE


def test_retained_tree_manifest_parser_does_not_report_a_defect_as_tree_integrity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools import verified_tree_manifest

    def defective(_value: object) -> None:
        raise ValueError(_INSTALLERS_DEFECT_DETAIL)

    monkeypatch.setattr(verified_tree_manifest, "tree_path", defective)
    payload = _installers_manifest('{"kind":"directory","path":"a"}')
    descriptor = SimpleNamespace()
    with pytest.raises(ValueError, match=_INSTALLERS_DEFECT_DETAIL):
        verified_tree_manifest.parse_manifest(payload, descriptor)


def test_closure_lock_with_an_integer_beyond_the_digit_limit_is_invalid_input(tmp_path: Path) -> None:
    from tools.generate_python_closures import _load_toml_lock

    lock = tmp_path / "uv.lock"
    lock.write_text(f"revision = {_INSTALLERS_BEYOND_DIGIT_LIMIT}\n", encoding="utf-8")
    with pytest.raises(InvalidInputError, match="uv.lock is not valid UTF-8 TOML"):
        _load_toml_lock(lock)


def test_artifact_lock_with_an_integer_beyond_the_digit_limit_is_invalid_input(tmp_path: Path) -> None:
    from tools.generate_python_closures import reviewed_python_full_version

    lock = tmp_path / "implementations" / "tooling" / "artifacts.lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(f'{{"artifacts": [], "revision": {_INSTALLERS_BEYOND_DIGIT_LIMIT}}}', encoding="utf-8")
    with pytest.raises(InvalidInputError, match="artifact lock contains an integer beyond the digit limit"):
        reviewed_python_full_version("3.14", repo_root=tmp_path)


def test_locked_wheel_with_a_malformed_url_is_invalid_input() -> None:
    from tools.generate_python_closures import _select_wheel, _supported_tags

    package = {"name": "example", "version": "1.0", "wheels": [{"url": "https://[::1/example-1.0-py3-none-any.whl"}]}
    tags = _supported_tags("3.14", "cp314", "x86_64-unknown-linux-gnu")
    with pytest.raises(InvalidInputError, match=r"example==1\.0 has an invalid wheel URL"):
        _select_wheel(package, tags)


def test_existing_projection_that_is_not_utf8_is_invalid_input(tmp_path: Path) -> None:
    from tools.generate_python_closures import _write_if_changed

    projection = tmp_path / "closure.txt"
    projection.write_bytes(b"\xff\xfe")
    with pytest.raises(InvalidInputError, match="closure.txt is not valid UTF-8"):
        _write_if_changed(projection, "pinned==1\n", check=True)
    assert projection.read_bytes() == b"\xff\xfe"


def test_projection_policy_reports_an_unparseable_closure_lock_as_a_policy_failure(tmp_path: Path) -> None:
    from tools.tooling_artifact_policy_python import _projection_generation_failures

    lock = tmp_path / "implementations" / "tooling" / "python" / "uv.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(f"revision = {_INSTALLERS_BEYOND_DIGIT_LIMIT}\n", encoding="utf-8")
    failures = _projection_generation_failures(tmp_path)
    assert [failure.rule_id for failure in failures] == ["tooling-python-projection-generation"]


def test_projection_policy_does_not_report_a_generator_defect_as_a_policy_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import generate_python_closures
    from tools.tooling_artifact_policy_python import _projection_generation_failures

    def defective(*_args: object, **_kwargs: object) -> str:
        raise ValueError(_INSTALLERS_DEFECT_DETAIL)

    lock = tmp_path / "implementations" / "tooling" / "python" / "uv.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("", encoding="utf-8")
    monkeypatch.setattr(generate_python_closures, "render_build_constraints", defective)
    with pytest.raises(ValueError, match=_INSTALLERS_DEFECT_DETAIL):
        _projection_generation_failures(tmp_path)


def test_devcontainer_setup_refuses_when_the_home_directory_cannot_be_determined(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools import devcontainer_setup

    def no_home(cls: type[pathlib.Path]) -> pathlib.Path:
        raise RuntimeError(_INSTALLERS_DEFECT_DETAIL)

    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(pathlib.Path, "home", classmethod(no_home))
    assert devcontainer_setup.main([]) == 1
    error = capsys.readouterr().err
    assert error == "devcontainer-setup: the user cache directory could not be determined\n"
    assert _INSTALLERS_DEFECT_DETAIL not in error


def test_devcontainer_kit_root_keeps_the_cache_home_and_home_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.devcontainer_setup import default_kit_root

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert default_kit_root() == tmp_path / "cache" / "raes-bootstrap"
    monkeypatch.setenv("XDG_CACHE_HOME", "")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert default_kit_root() == tmp_path / "home" / ".cache" / "raes-bootstrap"


def test_devcontainer_hooks_refuse_a_checkout_path_git_reports_as_undecodable(tmp_path: Path) -> None:
    from tools.devcontainer_setup import DevcontainerSetupError, install_git_hooks

    checkout = tmp_path / os.fsdecode(b"checkout-\xff")
    try:
        checkout.mkdir()
    except OSError:
        pytest.skip("the filesystem refuses a file name that is not UTF-8")
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    with pytest.raises(DevcontainerSetupError, match="the checkout's git directory could not be resolved"):
        install_git_hooks(checkout, tmp_path / "kit")


def _installers_bootstrap_selection(raw: dict[str, object], source_url: str) -> tuple[dict, dict, str]:
    artifact = {
        "artifact_id": "payload",
        "artifact_class": "bootstrap",
        "platform": {"raw_manifest": [raw], "source_urls": [source_url]},
        "source": {"locator_refs": ["primary"]},
    }
    return {"bootstrap_payload_ids": ["payload"]}, {"payload": artifact}, "0" * 64


@pytest.mark.parametrize(
    ("size_offset", "source_url"),
    [
        pytest.param(1, "https://example.test/payload.tar.gz", id="size-beyond-transfer-budget"),
        pytest.param(0, "https:///payload.tar.gz", id="locator-without-host"),
    ],
)
def test_bootstrap_fetch_refuses_a_lock_selection_outside_the_transfer_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    size_offset: int,
    source_url: str,
) -> None:
    from tools import bootstrap_profile, devcontainer_setup, maintained_client_acquisition

    size = maintained_client_acquisition.GENERIC_TRANSFER_BUDGET.max_bytes + size_offset
    raw = {"path": "payload.tar.gz", "sha256": "0" * 64, "size": size}
    monkeypatch.setattr(
        bootstrap_profile, "_load_host_selection", lambda _host_id: _installers_bootstrap_selection(raw, source_url)
    )
    with pytest.raises(InvalidInputError, match="bootstrap payload lock selection is outside the transfer contract"):
        bootstrap_profile.fetch_bootstrap_payloads("host", tmp_path, ["payload"])

    monkeypatch.setattr(
        devcontainer_setup,
        "setup",
        lambda: bootstrap_profile.fetch_bootstrap_payloads("host", tmp_path, ["payload"]),
    )
    assert devcontainer_setup.main([]) == 1
    assert capsys.readouterr().err == (
        "devcontainer-setup: bootstrap payload lock selection is outside the transfer contract\n"
    )


def test_bootstrap_fetch_does_not_report_a_transfer_defect_as_invalid_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import bootstrap_profile

    def defective(*_args: object, **_kwargs: object) -> dict[str, str]:
        raise ValueError(_INSTALLERS_DEFECT_DETAIL)

    raw = {"path": "payload.tar.gz", "sha256": "0" * 64, "size": 1024}
    monkeypatch.setattr(
        bootstrap_profile,
        "_load_host_selection",
        lambda _host_id: _installers_bootstrap_selection(raw, "https://example.test/payload.tar.gz"),
    )
    monkeypatch.setattr(bootstrap_profile, "run_curl_qualification", defective)
    with pytest.raises(ValueError, match=_INSTALLERS_DEFECT_DETAIL):
        bootstrap_profile.fetch_bootstrap_payloads("host", tmp_path, ["payload"])


def test_curl_preflight_refuses_a_version_banner_that_is_not_text(tmp_path: Path) -> None:
    from tools.maintained_client_acquisition import _curl_preflight_failure

    client = tmp_path / "curl"
    client.write_text("#!/bin/sh\nprintf 'curl 8.5.0 \\377\\n'\n", encoding="ascii")
    client.chmod(0o700)
    assert _curl_preflight_failure(client) == "curl-version-inadequate"


# Nox, policy, pull request and release evidence tools.

_NOX_SENTINEL = "SECRET-SENTINEL-VALUE"
_NOX_DEFECT = "SECRET-DEFECT-DETAIL"
_NOX_LONG_INTEGER = "1" * 5000
# PyYAML's safe constructor raises ValueError, KeyError or AttributeError, not a
# YAMLError, for these scalars: an impossible date, an integer beyond the digit
# limit, a bad explicit boolean and a bad explicit timestamp.
_NOX_UNCONSTRUCTABLE_SCALARS = pytest.mark.parametrize(
    "scalar",
    ("2024-13-01", _NOX_LONG_INTEGER, "!!bool maybe", "!!timestamp later"),
    ids=("impossible-date", "integer-beyond-digit-limit", "bad-explicit-bool", "bad-explicit-timestamp"),
)


def _nox_write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _nox_messages(failures: list[PolicyFailure]) -> str:
    return "\n".join(failure.render() for failure in failures)


@_NOX_UNCONSTRUCTABLE_SCALARS
def test_repo_policy_reports_an_unconstructable_policy_scalar_as_malformed(tmp_path: Path, scalar: str) -> None:
    from tools.policy.repo_policy import evaluate_repo_policy

    _nox_write(tmp_path / "tools/policy/adr_policy.yaml", f"note: {_NOX_SENTINEL}\nvalue: {scalar}\n")

    failures = evaluate_repo_policy(tmp_path, [], structural_runner=lambda _document: [])

    assert [failure.rule_id for failure in failures] == ["policy-config-malformed"]
    assert failures[0].message == "tools/policy/adr_policy.yaml could not be parsed (missing or invalid YAML)"
    assert _NOX_SENTINEL not in _nox_messages(failures)


@_NOX_UNCONSTRUCTABLE_SCALARS
def test_repo_policy_reports_an_unconstructable_allowlist_scalar_as_malformed(tmp_path: Path, scalar: str) -> None:
    from tools.policy.repo_policy import _validate_allowlist

    _nox_write(tmp_path / "allowlist.yaml", f"note: {_NOX_SENTINEL}\nfiles: [{scalar}]\n")

    allowlist, failures = _validate_allowlist(tmp_path, "allowlist.yaml")

    assert allowlist is None
    assert [failure.rule_id for failure in failures] == ["policy-config-malformed"]
    assert failures[0].message == "allowlist.yaml could not be parsed (invalid YAML)"
    assert _NOX_SENTINEL not in _nox_messages(failures)


def test_repo_policy_does_not_report_a_value_error_defect_as_malformed_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.policy.repo_policy as repo_policy_module

    def defective(_repo_root: Path) -> dict:
        raise ValueError(_NOX_DEFECT)

    monkeypatch.setattr(repo_policy_module, "load_policy", defective)
    with pytest.raises(ValueError, match=_NOX_DEFECT):
        repo_policy_module.evaluate_repo_policy(tmp_path, [], structural_runner=lambda _document: [])


@_NOX_UNCONSTRUCTABLE_SCALARS
def test_adr_pin_gate_reports_an_unconstructable_manifest_scalar_as_malformed(tmp_path: Path, scalar: str) -> None:
    import tools.check_adr_immutability as adr_gate

    _nox_write(
        tmp_path / adr_gate.MANIFEST_PATH,
        f"hash_algorithm: sha256\nnote: {_NOX_SENTINEL}\nadrs: [{{id: ADR-001, date: {scalar}}}]\n",
    )

    failures = adr_gate.evaluate_adr_immutability(tmp_path)

    assert failures == [
        PolicyFailure(adr_gate.RULE_MALFORMED, "ADR pin manifest is not valid YAML", adr_gate.MANIFEST_PATH)
    ]
    assert _NOX_SENTINEL not in _nox_messages(failures)


def test_adr_pin_gate_does_not_report_a_value_error_defect_as_invalid_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.check_adr_immutability as adr_gate

    _nox_write(tmp_path / adr_gate.MANIFEST_PATH, "hash_algorithm: sha256\nadrs: []\n")

    def defective(_path: Path) -> dict:
        raise ValueError(_NOX_DEFECT)

    monkeypatch.setattr(adr_gate, "load_yaml", defective)
    with pytest.raises(ValueError, match=_NOX_DEFECT):
        adr_gate.evaluate_adr_immutability(tmp_path)


def _nox_digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_release_admission_refuses_an_evidence_integer_beyond_the_digit_limit(tmp_path: Path) -> None:
    from tools.release_evidence_admission import AdmissionError, _load_bounded_json

    evidence = _nox_write(tmp_path / "wheel.cdx.json", f'{{"note": "{_NOX_SENTINEL}", "size": {_NOX_LONG_INTEGER}}}')

    digest = _nox_digest(evidence)
    with pytest.raises(AdmissionError) as refused:
        _load_bounded_json(evidence, digest)

    assert refused.value.code == "admission-evidence-unparsable"
    assert str(refused.value) == "wheel.cdx.json could not be parsed"
    assert _NOX_SENTINEL not in str(refused.value)


def test_release_admission_keeps_valid_evidence_integers(tmp_path: Path) -> None:
    from tools.release_evidence_admission import _load_bounded_json

    evidence = _nox_write(tmp_path / "wheel.cdx.json", '{"size": 12, "negative": -0, "nested": [9007199254740993]}')

    assert _load_bounded_json(evidence, _nox_digest(evidence)) == {
        "size": 12,
        "negative": 0,
        "nested": [9007199254740993],
    }


def test_release_admission_does_not_report_a_decoder_hook_defect_as_unparsable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.release_evidence_admission as admission

    evidence = _nox_write(tmp_path / "wheel.cdx.json", '{"size": 12}')

    def defective(_pairs: object) -> dict:
        raise ValueError(_NOX_DEFECT)

    monkeypatch.setattr(admission, "_reject_duplicate_keys", defective)
    digest = _nox_digest(evidence)
    with pytest.raises(ValueError, match=_NOX_DEFECT):
        admission._load_bounded_json(evidence, digest)


def test_attestation_verifier_refuses_output_with_an_integer_beyond_the_digit_limit() -> None:
    from tools.release_evidence_verifier import VerifierError, parse_verifier_output

    with pytest.raises(VerifierError) as refused:
        parse_verifier_output(f'[{{"note": "{_NOX_SENTINEL}", "size": {_NOX_LONG_INTEGER}}}]')

    assert refused.value.code == "verifier-output-unparsable"
    assert str(refused.value) == "attestation verifier output could not be parsed"
    assert _NOX_SENTINEL not in str(refused.value)


def test_attestation_verifier_does_not_report_a_decoder_defect_as_unparsable(monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.release_evidence_verifier as verifier

    class _DefectiveJson:
        JSONDecodeError = verifier.json.JSONDecodeError

        @staticmethod
        def loads(*_args: object, **_kwargs: object) -> object:
            raise ValueError(_NOX_DEFECT)

    monkeypatch.setattr(verifier, "json", _DefectiveJson)
    with pytest.raises(ValueError, match=_NOX_DEFECT):
        verifier.parse_verifier_output("[]")


def test_identity_cutover_reports_a_manifest_integer_beyond_the_digit_limit(tmp_path: Path) -> None:
    import tools.check_identity_cutover as cutover

    _nox_write(tmp_path / cutover.MANIFEST_PATH, f'{{"note": "{_NOX_SENTINEL}", "records": {_NOX_LONG_INTEGER}}}')

    records, bindings, generated, failures = cutover._load_historical_records(tmp_path)

    assert (records, bindings, generated) == ({}, {}, {})
    assert [failure.rule_id for failure in failures] == [cutover.RULE_MANIFEST]
    assert "digit limit" in failures[0].message
    assert _NOX_SENTINEL not in _nox_messages(failures)


def test_requirement_scope_reports_a_scope_integer_beyond_the_digit_limit(tmp_path: Path) -> None:
    from tools.policy.requirement_scope import RequirementScopeError, load_requirement_scope

    _nox_write(
        tmp_path / "docs/governance/requirement-scopes/7.json",
        f'{{"note": "{_NOX_SENTINEL}", "issue_number": {_NOX_LONG_INTEGER}}}',
    )

    with pytest.raises(RequirementScopeError) as refused:
        load_requirement_scope(tmp_path, "7-scope")

    assert str(refused.value) == "Requirement scope cannot be read and validated."
    # The refusal comes from the bounded JSON loader, not from an earlier path check.
    assert "digit limit" in str(refused.value.__cause__)
    assert _NOX_SENTINEL not in str(refused.value)


# Research evidence tools.

REPO_ROOT = Path(__file__).resolve().parents[3]
# int() refuses a decimal string beyond the interpreter digit limit (4300 digits by default).
_RESEARCH_HUGE_REVISION = "1" * 5000 + ".0.0"
_RESEARCH_DEFECT_SENTINEL = "SECRET-DEFECT-DETAIL"
_RESEARCH_RETAINED_EVIDENCE = "docs/research/formal-semantic-validation/evidence/finite-domain-satisfiable-v2.json"


def _research_release(revision: str):
    from tools.formal_semantic_validation._types import EvidenceRelease

    return EvidenceRelease(
        manifest_path="manifest.json",
        manifest={"revision": revision},
        protocol={},
        corpus={},
        snapshot={},
        analysis={},
    )


def test_research_revision_beyond_the_integer_digit_limit_is_invalid_input():
    from tools.evidence_bundle_index import revision_key

    with pytest.raises(InvalidInputError) as refused:
        revision_key(_RESEARCH_HUGE_REVISION)
    assert "1" * 64 not in str(refused.value)
    assert revision_key("12.0.3") == (12, 0, 3)


def test_research_retest_release_with_an_oversized_revision_is_refused():
    from tools.formal_semantic_validation._releases import validate_retest_bundle

    failures = validate_retest_bundle(REPO_ROOT, _research_release(_RESEARCH_HUGE_REVISION), {}, {}, {}, {})

    assert [(failure.rule_id, failure.message) for failure in failures] == [
        ("formal-validation-retest-release", "invalid evidence identity")
    ]


def test_research_release_selection_refuses_an_oversized_revision():
    from tools.research_evidence import current_release_path

    with pytest.raises(InvalidInputError):
        current_release_path([("manifest.json", {"revision": _RESEARCH_HUGE_REVISION})])


def test_research_publication_receipt_refuses_an_oversized_revision(tmp_path):
    from tools.research_capture import _validate_publication_receipt

    receipt = {"revision": _RESEARCH_HUGE_REVISION, "capture_path": "capture.json", "capture_sha256": "0" * 64}
    with pytest.raises(InvalidInputError):
        _validate_publication_receipt(tmp_path, tmp_path / "v1.json", receipt, [], set(), set())


def test_research_retest_release_revision_defect_still_propagates(monkeypatch):
    from tools.formal_semantic_validation import _releases

    def defect(_value):
        raise ValueError(_RESEARCH_DEFECT_SENTINEL)

    monkeypatch.setattr(_releases, "evidence_key", defect)
    release = _research_release("1.0.0")
    with pytest.raises(ValueError, match=_RESEARCH_DEFECT_SENTINEL):
        _releases.validate_retest_bundle(REPO_ROOT, release, {}, {}, {}, {})


def _research_historical_archive(tmp_path: Path, content_base64: str) -> str:
    digest = "a" * 64
    archive = tmp_path / "docs/research/specification-coverage/historical-artifacts" / f"{digest}.json"
    archive.parent.mkdir(parents=True)
    archive.write_text(
        json.dumps({"artifact_path": "spec.md", "recovered_from_revision": "b" * 40, "content_base64": content_base64}),
        encoding="utf-8",
    )
    return digest


def test_research_historical_archive_with_non_ascii_base64_is_a_digest_failure(tmp_path):
    from tools.specification_coverage._artifacts import _historical_artifact_failures

    digest = _research_historical_archive(tmp_path, "QUJD\u00e9")
    failures = []
    _historical_artifact_failures(tmp_path, {"sha256": digest, "path": "spec.md"}, failures)

    assert [(failure.rule_id, failure.message, failure.path) for failure in failures] == [
        (
            "specification-coverage-artifact-digest",
            "historical source archive is missing or does not match its exact pin",
            "spec.md",
        )
    ]


def test_research_historical_archive_decoder_defect_still_propagates(monkeypatch, tmp_path):
    from tools.specification_coverage import _artifacts

    def defect(*_args, **_kwargs):
        raise ValueError(_RESEARCH_DEFECT_SENTINEL)

    digest = _research_historical_archive(tmp_path, "QUJD")
    monkeypatch.setattr(_artifacts.base64, "b64decode", defect)
    with pytest.raises(ValueError, match=_RESEARCH_DEFECT_SENTINEL):
        _artifacts._historical_artifact_failures(tmp_path, {"sha256": digest, "path": "spec.md"}, [])


def _research_cli_output(monkeypatch, tmp_path: Path, stdout: str) -> dict[str, object]:
    from tools.formal_semantic_validation import _production

    (tmp_path / "raes").write_text("", encoding="utf-8")

    def completed(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(_production.subprocess, "run", completed)
    return _production._run_production_evidence_cli(tmp_path, ["raes", "processor"])


@pytest.mark.parametrize(
    "stdout",
    [
        '{"value": ' + "7" * 5000 + ', "note": "' + _RESEARCH_DEFECT_SENTINEL + '"}',
        "[" * 100_000 + "]" * 100_000,
    ],
    ids=["integer-beyond-digit-limit", "nesting-beyond-decoder-depth"],
)
def test_research_production_cli_output_beyond_decoder_limits_is_an_operational_failure(monkeypatch, tmp_path, stdout):
    with pytest.raises(OperationalError) as refused:
        _research_cli_output(monkeypatch, tmp_path, stdout)
    assert _RESEARCH_DEFECT_SENTINEL not in str(refused.value)
    assert "7777" not in str(refused.value)


def test_research_production_cli_output_keeps_valid_integers(monkeypatch, tmp_path):
    assert _research_cli_output(monkeypatch, tmp_path, '{"value": 12, "other": -3}') == {"value": 12, "other": -3}


def test_research_production_cli_output_that_is_not_utf8_is_an_operational_failure(tmp_path):
    from tools.formal_semantic_validation import _production

    executable = tmp_path / "raes"
    executable.write_text("#!/bin/sh\nprintf '\\377'\n", encoding="utf-8")
    executable.chmod(0o755)
    with pytest.raises(OperationalError):
        _production._run_production_evidence_cli(tmp_path, ["raes", "processor"])


def test_research_production_cli_defect_still_propagates(monkeypatch, tmp_path):
    from tools.formal_semantic_validation import _production

    def defect(*_args, **_kwargs):
        raise ValueError(_RESEARCH_DEFECT_SENTINEL)

    (tmp_path / "raes").write_text("", encoding="utf-8")
    monkeypatch.setattr(_production.subprocess, "run", defect)
    with pytest.raises(ValueError, match=_RESEARCH_DEFECT_SENTINEL):
        _production._run_production_evidence_cli(tmp_path, ["raes", "processor"])


def _research_uncanonical_historical_evidence() -> dict[str, object]:
    from tools.formal_semantic_validation._archival_shape import validate_archival_evidence_shape

    payload = json.loads((REPO_ROOT / _RESEARCH_RETAINED_EVIDENCE).read_text(encoding="utf-8"))
    # An unpaired surrogate satisfies the frozen JSON shape, but it has no RFC 8785 form.
    payload["normalized_model"]["clauses"][0]["allowed_values"][0] += "\ud800"
    validate_archival_evidence_shape(REPO_ROOT, payload, "satisfiability")
    return payload


def test_research_historical_evidence_without_a_canonical_form_is_an_integrity_failure():
    from tools.formal_semantic_validation._archival_invariants import validate_archival_evidence_invariants

    evidence = _research_uncanonical_historical_evidence()
    with pytest.raises(EvidenceIntegrityError) as refused:
        validate_archival_evidence_invariants(evidence, "satisfiability")
    assert "\ud800" not in str(refused.value)


def test_research_historical_production_replay_refuses_evidence_without_a_canonical_form():
    from tools.formal_semantic_validation._production import _historical_production_replay

    evidence = _research_uncanonical_historical_evidence()
    with pytest.raises(EvidenceIntegrityError):
        _historical_production_replay(evidence, {}, "satisfiability", repo_root=REPO_ROOT)


def test_research_schema_catalog_with_an_oversized_integer_is_a_catalog_failure(tmp_path):
    from tools.schema_coverage._classify import _catalog_entries
    from tools.schema_coverage._keys import CATALOG_RULE_ID, MANIFEST_RELATIVE_PATH

    manifest = tmp_path / MANIFEST_RELATIVE_PATH
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"schema_version": ' + "9" * 5000 + "}", encoding="utf-8")
    entries, failures = _catalog_entries(tmp_path)

    assert entries == []
    assert [(failure.rule_id, failure.path) for failure in failures] == [(CATALOG_RULE_ID, MANIFEST_RELATIVE_PATH)]
    assert "9999" not in failures[0].message


def test_research_schema_catalog_defect_still_propagates(monkeypatch, tmp_path):
    from tools.schema_coverage import _classify

    def defect(_repo_root):
        raise ValueError(_RESEARCH_DEFECT_SENTINEL)

    monkeypatch.setattr(_classify, "load_schema_publication_catalog", defect)
    with pytest.raises(ValueError, match=_RESEARCH_DEFECT_SENTINEL):
        _classify._catalog_entries(tmp_path)


def test_research_historical_evidence_digest_defect_still_propagates(monkeypatch):
    from tools.formal_semantic_validation import _archival_invariants

    def defect(_value):
        raise ValueError(_RESEARCH_DEFECT_SENTINEL)

    payload = json.loads((REPO_ROOT / _RESEARCH_RETAINED_EVIDENCE).read_text(encoding="utf-8"))
    monkeypatch.setattr(_archival_invariants, "canonical_json_digest", defect)
    with pytest.raises(ValueError, match=_RESEARCH_DEFECT_SENTINEL):
        _archival_invariants.validate_archival_evidence_invariants(payload, "satisfiability")


# A YAML escape can produce an unpaired surrogate, and deep flow nesting exceeds the recursive YAML scanner.
_RESEARCH_SDL_FIXTURES = {
    "unpaired-surrogate": 'name: fixture\ndescription: "x\\ud800"\n',
    "deep-nesting": "name: fixture\nvariables: " + "[" * 3000 + "]" * 3000 + "\n",
}


@pytest.mark.parametrize("source", list(_RESEARCH_SDL_FIXTURES.values()), ids=list(_RESEARCH_SDL_FIXTURES))
def test_research_retained_replay_of_an_invalid_sdl_fixture_is_a_replay_failure(tmp_path, source):
    from tools.formal_semantic_validation import _retest

    (tmp_path / "fixture.yaml").write_text(source, encoding="utf-8")
    case = {"case_id": "control", "replay_mode": "compile-stability", "fixture_path": "fixture.yaml"}
    failures = []
    _retest._validate_retained_retest_observation(tmp_path, case, {"case_id": "control"}, failures, "snapshot.json")

    assert [(failure.rule_id, failure.path) for failure in failures] == [
        ("formal-validation-replay-error", "snapshot.json")
    ]


@pytest.mark.parametrize("source", list(_RESEARCH_SDL_FIXTURES.values()), ids=list(_RESEARCH_SDL_FIXTURES))
def test_research_satisfiability_control_of_an_invalid_sdl_fixture_is_a_replay_failure(tmp_path, source):
    from tools.formal_semantic_validation import _satisfiability

    fixture = tmp_path / "fixture.yaml"
    fixture.write_text(source, encoding="utf-8")
    scope = _satisfiability._SatisfiabilityScope(tmp_path, {}, {}, "analysis.json", "snapshot.json", True)
    failures = []
    _satisfiability._current_control_failures(scope, {"case_id": "control"}, fixture, failures)

    assert [(failure.rule_id, failure.path) for failure in failures] == [
        ("formal-satisfiability-replay-error", "analysis.json")
    ]


@pytest.mark.parametrize("source", list(_RESEARCH_SDL_FIXTURES.values()), ids=list(_RESEARCH_SDL_FIXTURES))
def test_research_coverage_artifact_with_an_invalid_sdl_source_is_an_execution_failure(tmp_path, source):
    from tools.specification_coverage._artifacts import _record_artifact_execution

    artifact = tmp_path / "artifact.yaml"
    artifact.write_text(source, encoding="utf-8")
    executed, failures = {}, []
    _record_artifact_execution(
        tmp_path, {"kind": "sdl", "artifact_id": "artifact"}, "artifact.yaml", artifact, executed, failures
    )

    assert executed == {}
    assert [(failure.rule_id, failure.path) for failure in failures] == [
        ("specification-coverage-artifact-execution", "artifact.yaml")
    ]


# Tooling policy tools.

_TOOLING_ROOT = Path(__file__).resolve().parents[3]
# Python refuses to convert an integer literal with more digits than its default limit (4300).
_TOOLING_BEYOND_DIGIT_LIMIT = "1" * 5000
_TOOLING_SECRET = "SECRET-DEFECT-DETAIL"
_TOOLING_INVALID_AUTHORITY = "tooling authority is missing, unsafe, or malformed"


def _tooling_copy(root: Path, relative_paths) -> Path:
    for relative in relative_paths:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_TOOLING_ROOT / relative, destination)
    return root


def _tooling_json_with_long_integer(path: Path) -> None:
    """Add a top-level member whose integer literal exceeds the interpreter digit limit."""

    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("{", '{"sweep_value": ' + _TOOLING_BEYOND_DIGIT_LIMIT + ", ", 1), encoding="utf-8")


def test_python_closure_toml_beyond_the_integer_digit_limit_is_refused(tmp_path):
    from tools import tooling_artifact_policy_python as python_policy

    _tooling_copy(tmp_path, python_policy.PYTHON_AUTHORITY_PATHS)
    lock = tmp_path / python_policy.PYTHON_TOOL_LOCK_PATH
    lock.write_text(
        lock.read_text(encoding="utf-8")
        + f'\n[sweep]\nlabel = "{_TOOLING_SECRET}"\nvalue = {_TOOLING_BEYOND_DIGIT_LIMIT}\n',
        encoding="utf-8",
    )

    assert python_policy._toml(tmp_path, python_policy.PYTHON_TOOL_LOCK_PATH) is None
    authorities, failures = python_policy._python_authorities(tmp_path)
    assert authorities is None
    assert [(item.rule_id, item.message, item.path) for item in failures] == [
        ("tooling-python-toml", "Python closure TOML authority could not be parsed safely", None)
    ]


def test_python_closure_toml_keeps_valid_and_invalid_authority_outcomes(tmp_path):
    from tools import tooling_artifact_policy_python as python_policy

    for relative in python_policy.PYTHON_AUTHORITY_PATHS[:4]:
        expected = tomllib.loads((_TOOLING_ROOT / relative).read_text(encoding="utf-8"))
        assert python_policy._toml(_TOOLING_ROOT, relative) == expected
    _tooling_copy(tmp_path, python_policy.PYTHON_AUTHORITY_PATHS)
    (tmp_path / python_policy.PYTHON_PROJECT_PATH).write_bytes(b"\xff not utf-8")
    (tmp_path / python_policy.PYTHON_TOOL_PROJECT_PATH).write_text("[project\n", encoding="utf-8")
    assert python_policy._toml(tmp_path, python_policy.PYTHON_PROJECT_PATH) is None
    assert python_policy._toml(tmp_path, python_policy.PYTHON_TOOL_PROJECT_PATH) is None


def test_python_closure_toml_does_not_report_defects_as_untrusted_input(tmp_path, monkeypatch):
    from tools import tooling_artifact_policy_python as python_policy

    _tooling_copy(tmp_path, python_policy.PYTHON_AUTHORITY_PATHS)

    def parser_defect(_text):
        raise KeyError(_TOOLING_SECRET)

    monkeypatch.setattr(
        python_policy, "tomllib", SimpleNamespace(loads=parser_defect, TOMLDecodeError=tomllib.TOMLDecodeError)
    )
    with pytest.raises(KeyError, match=_TOOLING_SECRET):
        python_policy._toml(tmp_path, python_policy.PYTHON_TOOL_LOCK_PATH)

    def reader_defect(*_args, **_kwargs):
        raise ValueError(_TOOLING_SECRET)

    monkeypatch.setattr(python_policy, "_bounded_repo_bytes", reader_defect)
    with pytest.raises(ValueError, match=_TOOLING_SECRET):
        python_policy._toml(tmp_path, python_policy.PYTHON_TOOL_LOCK_PATH)


def test_tooling_authority_beyond_the_integer_digit_limit_is_malformed(tmp_path):
    from tools.tooling_artifact_policy_common import PROFILES_PATH, read_tooling_document

    _tooling_copy(tmp_path, [PROFILES_PATH])
    _tooling_json_with_long_integer(tmp_path / PROFILES_PATH)

    with pytest.raises(InvalidInputError) as refused:
        read_tooling_document(tmp_path, PROFILES_PATH)
    assert str(refused.value) == _TOOLING_INVALID_AUTHORITY


@pytest.mark.parametrize(
    ("arguments", "damaged"),
    [
        (
            [
                "--select-artifact",
                "tool-a",
                "--version",
                "1.0.0",
                "--platform-id",
                "linux-x86_64",
                "--profile-id",
                "public-linux-x86_64",
            ],
            "implementations/tooling/artifacts.lock.json",
        ),
        (
            ["--select-host-profile", "fixture-linux-x86_64"],
            "implementations/tooling/profiles/development-profiles.json",
        ),
    ],
)
def test_selection_cli_refuses_an_authority_beyond_the_integer_digit_limit(tmp_path, capsys, arguments, damaged):
    from test_tooling_artifact_policy import _seed_policy
    from tools import check_tooling_artifact_policy

    _seed_policy(tmp_path)
    _tooling_json_with_long_integer(tmp_path / damaged)

    assert check_tooling_artifact_policy.main(["--repo-root", str(tmp_path), *arguments]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == _TOOLING_INVALID_AUTHORITY + "\n"


def test_policy_documents_beyond_the_integer_digit_limit_are_parse_failures(tmp_path):
    from test_tooling_artifact_policy import _seed_policy
    from tools.tooling_artifact_policy_common import ARTIFACT_LOCK_PATH, load_documents

    _seed_policy(tmp_path)
    _tooling_json_with_long_integer(tmp_path / ARTIFACT_LOCK_PATH)

    documents, failures = load_documents(tmp_path)
    assert ARTIFACT_LOCK_PATH not in documents
    assert [(item.rule_id, item.path) for item in failures] == [("tooling-json-parse", ARTIFACT_LOCK_PATH)]
    assert all(_TOOLING_BEYOND_DIGIT_LIMIT[:64] not in item.message for item in failures)


def test_devcontainer_config_beyond_the_integer_digit_limit_is_a_shape_failure(tmp_path):
    from tools.tooling_artifact_policy_devcontainer import (
        DEVCONTAINER_CONFIG_PATH,
        RULE_SHAPE,
        load_devcontainer_config,
    )

    _tooling_copy(tmp_path, [DEVCONTAINER_CONFIG_PATH])
    _tooling_json_with_long_integer(tmp_path / DEVCONTAINER_CONFIG_PATH)

    document, refusal = load_devcontainer_config(tmp_path)
    assert document is None
    assert (refusal.rule_id, refusal.message, refusal.path) == (
        RULE_SHAPE,
        "dev-container configuration could not be parsed safely",
        DEVCONTAINER_CONFIG_PATH,
    )


def test_python_projection_manifest_beyond_the_integer_digit_limit_is_unparsed(tmp_path):
    from tools.tooling_artifact_policy_python_profiles import _projection_drift_failures

    manifest = "implementations/tooling/python/smoke/linux-x86_64-cp314.wheelhouse-manifest.json"
    requirements = "implementations/tooling/python/smoke/linux-x86_64-cp314.txt"
    _tooling_copy(tmp_path, [manifest, requirements])
    _tooling_json_with_long_integer(tmp_path / manifest)

    failures = _projection_drift_failures(
        tmp_path,
        manifest_path=manifest,
        requirements_path=requirements,
        profile_id="public-linux-x86_64-cp314-all-extras",
        project_scoped=True,
    )
    assert [(item.rule_id, item.message, item.path) for item in failures] == [
        ("tooling-python-projection", "Python closure projection could not be parsed", manifest)
    ]


# Pre-existing input crashes (issue #1678 review follow-up).

_DEEP_YAML_FLOW = "[" * 100_000 + "]" * 100_000


def test_policy_yaml_loader_refuses_nesting_beyond_the_parser_depth(tmp_path):
    from tools.policy.common import load_yaml

    path = _write(tmp_path, "policy.yaml", f"value: {_DEEP_YAML_FLOW}\n")
    with pytest.raises(InvalidInputError, match="nests beyond the YAML parser depth"):
        load_yaml(path)


_EXCEPTIONS_PATH = "tools/policy/exceptions.yaml"


@pytest.mark.parametrize(
    "content",
    ["exceptions: [unclosed\n", f"exceptions: {_DEEP_YAML_FLOW}\n", "- rule_id: example\n"],
    ids=["syntax", "nesting", "list-root"],
)
def test_policy_exceptions_loader_refuses_a_malformed_exceptions_file(tmp_path, content):
    from tools.policy.common import load_exceptions

    _write(tmp_path, _EXCEPTIONS_PATH, content)

    with pytest.raises(InvalidInputError, match="exceptions"):
        load_exceptions(tmp_path)


@pytest.mark.parametrize(
    "content",
    [
        "exceptions: example\n",
        "exceptions: [example]\n",
        "exceptions: [{rule_id: example, requirement_uid: [GOV-1]}]\n",
        "exceptions: [{rule_id: example, paths: 5}]\n",
        "exceptions: [{rule_id: example, paths: [5]}]\n",
    ],
    ids=["scalar-exceptions", "scalar-entry", "list-requirement", "scalar-paths", "non-text-path"],
)
def test_policy_exceptions_matching_refuses_an_entry_it_cannot_read(tmp_path, content):
    from tools.policy.common import PolicyFailure, apply_exceptions, load_exceptions

    _write(tmp_path, _EXCEPTIONS_PATH, content)
    entries = load_exceptions(tmp_path)

    # Matching reads the entries only for a failure, so an unused malformed list keeps its old outcome.
    assert apply_exceptions([], entries) == []
    failures = [PolicyFailure("example", "x", "docs/a.md")]
    with pytest.raises(InvalidInputError, match="exceptions"):
        apply_exceptions(failures, entries, requirement_uid="GOV-1")


def test_policy_exceptions_loader_refuses_an_undecodable_exceptions_file(tmp_path):
    from tools.policy.common import load_exceptions

    path = tmp_path / _EXCEPTIONS_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(b"exceptions: [\xff]\n")

    with pytest.raises(InvalidInputError, match="exceptions"):
        load_exceptions(tmp_path)


def test_policy_exceptions_loader_keeps_valid_entries(tmp_path):
    from tools.policy.common import PolicyFailure, apply_exceptions, load_exceptions

    _write(
        tmp_path,
        _EXCEPTIONS_PATH,
        "exceptions:\n"
        "  - {rule_id: example, paths: [docs], requirement_uid: GOV-1, expires_at: 2999-01-01}\n"
        "  - {rule_id: other}\n",
    )

    entries = load_exceptions(tmp_path)
    assert entries == [
        {"rule_id": "example", "paths": ["docs"], "requirement_uid": "GOV-1", "expires_at": date(2999, 1, 1)},
        {"rule_id": "other"},
    ]
    failures = [PolicyFailure("example", "x", "docs/a.md"), PolicyFailure("example", "y", "src/b.py")]
    assert apply_exceptions(failures, entries, requirement_uid="GOV-1") == [failures[1]]
    assert load_exceptions(ROOT) == []


def test_deprecation_gate_refuses_a_malformed_exceptions_file(tmp_path, capsys):
    from tools import check_deprecation_lifecycle

    _write(tmp_path, _EXCEPTIONS_PATH, "exceptions: [unclosed\n")

    assert check_deprecation_lifecycle.main(["--repo-root", str(tmp_path)]) == 1
    assert capsys.readouterr().err.startswith("deprecation-lifecycle: ")


_DEEP_JSON = '{"value": ' + "[" * 100_000 + "]" * 100_000 + "}"
_UNDECODABLE_JSON = {"digit-limit": _digit_limit_document(), "nesting": _DEEP_JSON}


@pytest.mark.parametrize("document", list(_UNDECODABLE_JSON.values()), ids=list(_UNDECODABLE_JSON))
def test_schema_publication_gate_reports_an_undecodable_manifest(tmp_path, document):
    from tools.check_schema_publication import validate_schema_publication_manifest

    _write(tmp_path, _SCHEMA_PUBLICATION_MANIFEST, document)

    failures = validate_schema_publication_manifest(tmp_path)
    assert len(failures) == 1
    assert failures[0].startswith("schema publication manifest is not valid JSON: ")
    assert _BEYOND_DIGIT_LIMIT not in failures[0]


@pytest.mark.parametrize("document", list(_UNDECODABLE_JSON.values()), ids=list(_UNDECODABLE_JSON))
def test_schema_publication_gate_reports_an_undecodable_record(tmp_path, document):
    from tools.check_schema_publication import validate_schema_publication_manifest

    _sharded_schema_publication(tmp_path, document)

    failures = validate_schema_publication_manifest(tmp_path)
    assert len(failures) == 1
    assert failures[0].startswith("schema publication entry is not valid JSON: ")


@pytest.mark.parametrize("document", list(_UNDECODABLE_JSON.values()), ids=list(_UNDECODABLE_JSON))
def test_schema_publication_gate_reports_an_undecodable_published_schema(tmp_path, document):
    from tools.check_schema_publication import _load_schema

    path = _write(tmp_path, "contracts/schemas/example.json", document)

    schema, reason = _load_schema(path, "contracts/schemas/example.json")
    assert schema is None
    assert reason.startswith("schema manifest path is not valid JSON: contracts/schemas/example.json: ")


@pytest.mark.parametrize("document", list(_UNDECODABLE_JSON.values()), ids=list(_UNDECODABLE_JSON))
def test_schema_publication_gate_reports_an_undecodable_base_manifest(tmp_path, monkeypatch, document):
    from tools import check_schema_publication

    monkeypatch.setattr(check_schema_publication, "_git_show", lambda _root, _ref: document)

    entries, reason = check_schema_publication._load_base_manifest(tmp_path, "base")
    assert entries is None
    assert reason == "base schema publication manifest at base is not valid JSON"


def test_schema_publication_gate_reports_a_schema_without_a_utf8_form(tmp_path, monkeypatch, capsys):
    from tools import check_schema_publication

    path = _write(tmp_path, "contracts/schemas/example.json", '{"title": "\\ud800"}')
    schema, reason = check_schema_publication._load_schema(path, "contracts/schemas/example.json")
    assert reason is None
    with pytest.raises(InvalidInputError, match="UTF-8"):
        check_schema_publication._schema_content_digest(schema)

    def refuse(*_args, **_kwargs):
        raise InvalidInputError("published schema text has no UTF-8 form")

    monkeypatch.setattr(check_schema_publication, "validate_schema_publication_manifest", refuse)
    assert check_schema_publication.main([]) == 1
    assert capsys.readouterr().err == "[schema-publication] published schema text has no UTF-8 form\n"


def _write_bytes(root: Path, relative: str, content: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# JSON that the decoder cannot build: an integer beyond the digit limit, deep nesting, or text that is not UTF-8.
_UNREADABLE_JSON = {
    "digit-limit": _digit_limit_document().encode("ascii"),
    "nesting": _DEEP_JSON.encode("ascii"),
    "not-utf8": b'{"value": "\xff"}',
}
# YAML that the safe loader cannot build: constructor failures, deep nesting, or text that is not UTF-8.
_UNREADABLE_YAML = {
    "impossible-date": b"value: 2024-13-01\n",
    "digit-limit": f"value: {_BEYOND_DIGIT_LIMIT}\n".encode("ascii"),
    "unknown-bool": b"value: !!bool maybe\n",
    "unmatched-timestamp": b"value: !!timestamp later\n",
    "empty-int": b'value: !!int ""\n',
    "nesting": f"value: {_DEEP_YAML_FLOW}\n".encode("ascii"),
    "not-utf8": b"value: \xff\n",
}
_JSON_CASES = pytest.mark.parametrize("content", list(_UNREADABLE_JSON.values()), ids=list(_UNREADABLE_JSON))
_YAML_CASES = pytest.mark.parametrize("content", list(_UNREADABLE_YAML.values()), ids=list(_UNREADABLE_YAML))


def _rules(failures) -> list[tuple[str, str | None]]:
    return [(failure.rule_id, failure.path) for failure in failures]


@_JSON_CASES
def test_concept_authority_reports_unreadable_catalogs(tmp_path, content):
    from tools import check_concept_authority_governance as gate

    _write_bytes(tmp_path, gate.CONCEPT_FAMILIES_RELATIVE_PATH, content)
    _write_bytes(tmp_path, gate.CONTROLLED_VOCABULARIES_RELATIVE_PATH, content)

    families, family_failures = gate._load_families(tmp_path)
    vocabularies, vocabulary_failures = gate._load_vocabularies(tmp_path)
    assert (families, vocabularies) == (None, None)
    assert _rules(family_failures) == [(gate.RULE_FAMILIES_INVALID, gate.CONCEPT_FAMILIES_RELATIVE_PATH)]
    assert _rules(vocabulary_failures) == [(gate.RULE_VOCAB_INVALID, gate.CONTROLLED_VOCABULARIES_RELATIVE_PATH)]
    assert _BEYOND_DIGIT_LIMIT not in family_failures[0].message + vocabulary_failures[0].message


@_JSON_CASES
def test_sdl_catalog_parity_reports_an_unreadable_authoring_schema(tmp_path, content):
    from tools import check_sdl_catalog_parity as gate

    for relative in (
        gate.SECTIONS_PATH,
        gate.REFERENCES_PATH,
        gate.RUNTIME_PATH,
        gate.DOCUMENT_MODEL_PATH,
        gate.VARIABLES_PATH,
        gate.DIAGNOSTICS_PATH,
        gate.PHASES_PATH,
    ):
        _write(tmp_path, relative, "")
    _write_bytes(tmp_path, gate.SCHEMA_PATH, content)

    failures = gate.evaluate_sdl_catalog_parity(tmp_path)
    assert _rules(failures) == [("sdl-catalog-schema-parse", gate.SCHEMA_PATH)]
    assert _BEYOND_DIGIT_LIMIT not in failures[0].message


@pytest.mark.parametrize("content", [_digit_limit_document(), _DEEP_JSON], ids=["digit-limit", "nesting"])
def test_behavioral_claims_scan_skips_structured_bindings_of_undecodable_json(tmp_path, content):
    from tools import check_behavioral_relation_claims as gate

    _write(tmp_path, gate.CATALOG_RELATIVE_PATH, (ROOT / gate.CATALOG_RELATIVE_PATH).read_text(encoding="utf-8"))
    _write(tmp_path, "docs/evidence.json", content)

    assert gate.evaluate(tmp_path) == []


@_JSON_CASES
def test_scientific_completeness_reports_an_unreadable_witness(tmp_path, content):
    from tools import check_scientific_scenario_completeness as gate

    _write_bytes(tmp_path, "witness.json", content)
    concern = SimpleNamespace(
        concern_id="concern", evidence=[], satisfiability_witness_refs={"contract": "witness.json"}
    )

    failures = gate._validate_evidence_paths(tmp_path, SimpleNamespace(concerns=[concern]))
    assert _rules(failures) == [("scientific-completeness-witness-invalid", "witness.json")]
    assert _BEYOND_DIGIT_LIMIT not in failures[0].message


@_JSON_CASES
def test_sdl_lineage_reports_an_unreadable_authority(tmp_path, content):
    from raes_contracts.provenance import LineageDisposition, SDLLineageLedgerModel
    from tools import check_sdl_lineage

    ledger = SDLLineageLedgerModel.model_validate(
        json.loads((ROOT / check_sdl_lineage.LEDGER_PATH).read_text(encoding="utf-8"))
    )
    subject = next(
        item
        for item in ledger.subjects
        if item.disposition is LineageDisposition.CURRENT and item.authority.artifact.endswith(".json")
    )
    _write(
        tmp_path, _SCHEMA_PUBLICATION_MANIFEST, '{"schema_version": "schema-publication-manifest/v1", "schemas": []}'
    )
    _write_bytes(tmp_path, subject.authority.artifact, content)

    failures = check_sdl_lineage._validate_authorities(tmp_path, ledger)
    invalid = [failure.message for failure in failures if failure.rule_id == "lineage-authority-invalid"]
    assert f"{subject.subject_id}: invalid JSON authority" in invalid


def test_sdl_lineage_reports_a_ledger_beyond_the_decoder_depth(tmp_path):
    from tools import check_sdl_lineage

    _write(tmp_path, check_sdl_lineage.LEDGER_PATH, _DEEP_JSON)

    assert [failure.rule_id for failure in check_sdl_lineage.evaluate(tmp_path)] == ["lineage-ledger-invalid"]


@_YAML_CASES
def test_example_library_reports_an_unreadable_catalog(tmp_path, content):
    from tools import check_example_library

    path = _write_bytes(tmp_path, "catalog.yaml", content)

    raw, failures = check_example_library._load_yaml_file(path, "catalog.yaml")
    assert raw is None
    assert _rules(failures) == [("example-library-parse", "catalog.yaml")]
    assert "maybe" not in failures[0].message
    assert _BEYOND_DIGIT_LIMIT not in failures[0].message


@_YAML_CASES
def test_assurance_policy_reports_unreadable_yaml_authorities(tmp_path, content):
    from tools import check_assurance_policy as gate

    for relative in (
        gate.ASSURANCE_POLICY_RELATIVE_PATH,
        gate.FM_CLASSIFICATION_LEDGER_RELATIVE_PATH,
        gate.ASSURANCE_FULFILLMENT_RELATIVE_PATH,
    ):
        _write_bytes(tmp_path, relative, content)

    assert _rules(gate.evaluate_assurance_policy(tmp_path)) == [
        ("assurance-policy-parse", gate.ASSURANCE_POLICY_RELATIVE_PATH)
    ]
    assert _rules(gate._check_fm_classification_ledger(tmp_path, [])) == [
        ("fm-classification-ledger-parse", gate.FM_CLASSIFICATION_LEDGER_RELATIVE_PATH)
    ]
    assert _rules(gate._check_assurance_fulfillment(tmp_path, [])) == [
        ("assurance-fulfillment-parse", gate.ASSURANCE_FULFILLMENT_RELATIVE_PATH)
    ]


@_YAML_CASES
def test_authority_boundary_reports_an_unreadable_policy(tmp_path, content):
    from tools import check_authority_boundary as gate

    _write_bytes(tmp_path, gate.AUTHORITY_BOUNDARY_RELATIVE_PATH, content)

    failures = gate.evaluate_authority_boundary(tmp_path)
    assert _rules(failures) == [("authority-boundary-parse", gate.AUTHORITY_BOUNDARY_RELATIVE_PATH)]


@_YAML_CASES
def test_deprecation_lifecycle_reports_unreadable_records(tmp_path, content):
    from tools import check_deprecation_lifecycle as gate

    _write_bytes(tmp_path, gate.DEPRECATION_RECORDS_RELATIVE_PATH, content)

    failures = gate.evaluate_deprecation_records(tmp_path)
    assert _rules(failures) == [("deprecation-records-parse", gate.DEPRECATION_RECORDS_RELATIVE_PATH)]


@pytest.mark.parametrize(
    ("pyproject", "catalog"),
    [
        (f"[project]\nversion = {_BEYOND_DIGIT_LIMIT}\n", f"description: {_BEYOND_DIGIT_LIMIT}\n"),
        ("[project]\nkeywords = " + "[" * 100_000 + "]" * 100_000 + "\n", f"description: {_DEEP_YAML_FLOW}\n"),
    ],
    ids=["digit-limit", "nesting"],
)
def test_project_positioning_reports_unreadable_metadata(tmp_path, pyproject, catalog):
    from tools import check_project_positioning as gate

    _write(tmp_path, "implementations/python/pyproject.toml", pyproject)
    _write(tmp_path, "examples/library/catalog.yaml", catalog)
    failures: list[object] = []

    gate._validate_structured_metadata(tmp_path, failures)
    metadata = {failure.path for failure in failures if failure.rule_id == gate.RULE_METADATA}
    assert {"implementations/python/pyproject.toml", "examples/library/catalog.yaml"} <= metadata


@pytest.mark.parametrize(
    "content",
    [*_UNREADABLE_JSON.values(), b"[]", b'{"schema_version": 5}', b"{}"],
    ids=[*_UNREADABLE_JSON, "list", "number-version", "no-version"],
)
def test_json_artifact_routing_refuses_an_artifact_without_a_readable_schema_version(tmp_path, content):
    from tools import check_json_artifacts

    path = _write_bytes(tmp_path, "contracts/records/example.json", content)

    with pytest.raises(InvalidInputError, match="contracts/records/example.json"):
        check_json_artifacts._versioned_schema(tmp_path, path, "records")


def test_json_artifact_gate_reports_an_unroutable_artifact(monkeypatch, capsys):
    from tools import check_json_artifacts

    def refuse(*_args, **_kwargs):
        raise InvalidInputError("contracts/records/example.json does not name a string schema_version")

    monkeypatch.setattr(check_json_artifacts.sys, "argv", ["check_json_artifacts.py", "contracts/records/example.json"])
    monkeypatch.setattr(check_json_artifacts, "collect_validation_targets", refuse)
    assert check_json_artifacts.main() == 1
    assert capsys.readouterr().err == (
        "[json-schema-validation] contracts/records/example.json does not name a string schema_version\n"
    )


_VOCABULARY_GATES = (
    "check_atlas_tactic_vocabulary",
    "check_attack_tactic_vocabulary",
    "check_autonomous_behavior_vocabularies",
    "check_nist_csf_defensive_vocabulary",
)


@pytest.mark.parametrize("module_name", _VOCABULARY_GATES)
@pytest.mark.parametrize("content", [_digit_limit_document(), _DEEP_JSON], ids=["digit-limit", "nesting"])
def test_vocabulary_gate_refuses_an_undecodable_source(tmp_path, monkeypatch, capsys, module_name, content):
    import importlib

    gate = importlib.import_module(f"tools.{module_name}")
    path = _write(tmp_path, "source.json", content)
    load_json = gate._load_json
    with pytest.raises(InvalidInputError, match="source.json"):
        load_json(path)

    monkeypatch.setattr(gate.sys, "argv", [module_name])
    monkeypatch.setattr(gate, "_load_json", lambda _path: load_json(path))
    assert gate.main() == 1
    assert _BEYOND_DIGIT_LIMIT not in capsys.readouterr().err


@pytest.mark.parametrize(
    "module_name",
    ["check_atlas_tactic_vocabulary", "check_attack_tactic_vocabulary", "check_nist_csf_defensive_vocabulary"],
)
def test_vocabulary_remote_check_refuses_a_malformed_locked_url(module_name):
    import importlib

    gate = importlib.import_module(f"tools.{module_name}")
    failure = gate._remote_url_failure(SimpleNamespace(source_url="https://[::1/x"), "https://[::1/x")
    assert failure is not None
    assert failure.startswith(f"{gate.SOURCE_RELATIVE_PATH}: remote verification URL")


def test_autonomous_vocabulary_remote_check_refuses_a_malformed_locked_url():
    from tools import check_autonomous_behavior_vocabularies as gate

    failure = gate._remote_host_failure("https://[::1/x", allowed_host="www.w3.org", relative_path="source.json")
    assert failure == "source.json: remote verification URL must stay on the allowlisted official HTTPS host"


@pytest.mark.parametrize(
    "sitemap",
    [
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://[::1/page</loc></url></urlset>',
        '<!DOCTYPE urlset [<!ENTITY page "index.html">]><urlset><url><loc>&page;</loc></url></urlset>',
    ],
    ids=["malformed-url", "entity-declaration"],
)
def test_public_docs_reports_an_unreadable_sitemap(tmp_path, sitemap):
    from tools import check_public_docs

    (tmp_path / "docs/public").mkdir(parents=True)
    _write(tmp_path, "out/sitemap.xml", sitemap)

    failures = check_public_docs.evaluate_public_output(tmp_path, tmp_path / "out")
    sitemap_failures = [failure for failure in failures if failure.rule_id == "public-docs-sitemap"]
    assert len(sitemap_failures) == 1


def test_public_docs_guard_refuses_a_url_that_urllib_cannot_parse():
    from tools import public_docs_guard

    class _GuardWarning(Exception):
        pass

    rereads = []
    directive = SimpleNamespace(
        name="raw",
        options={"url": "https://[::1/page"},
        state=SimpleNamespace(
            document=SimpleNamespace(
                settings=SimpleNamespace(env=SimpleNamespace(note_reread=lambda: rereads.append(1)))
            )
        ),
        warning=_GuardWarning,
    )

    with pytest.raises(_GuardWarning, match="cannot parse"):
        public_docs_guard._refuse_file_url(directive)
    assert rereads == [1]


@pytest.mark.parametrize(
    ("module_name", "function_name", "rule_id"),
    [
        ("dsl_language_evaluation._shape", "_validate_https_locator", "dsl-evaluation-source-locator"),
        ("check_related_work_comparison", "_validate_locator", "related-work-source-locator"),
    ],
)
def test_source_locator_that_urllib_cannot_parse_is_a_locator_failure(module_name, function_name, rule_id):
    import importlib

    validate = getattr(importlib.import_module(f"tools.{module_name}"), function_name)
    failures: list[object] = []

    validate("https://[::1/source", failures, "source-a")
    assert [failure.rule_id for failure in failures] == [rule_id]


@pytest.mark.parametrize(
    "level_id",
    ["FM²", "FMx", "custom", 5, ["FM0"], None],
    ids=["superscript", "letter-suffix", "not-fm", "number", "list", "null"],
)
def test_assurance_policy_reports_a_malformed_level_id(level_id):
    from tools import check_assurance_policy as gate

    policy = yaml.safe_load((ROOT / gate.ASSURANCE_POLICY_RELATIVE_PATH).read_text(encoding="utf-8"))
    levels = [*policy["levels"], {**policy["levels"][-1], "id": level_id}]

    failures = gate._check_levels(levels, gate.ASSURANCE_POLICY_RELATIVE_PATH)
    assert _rules(failures) == [("assurance-policy-level-id", gate.ASSURANCE_POLICY_RELATIVE_PATH)]
    assert failures[0].message == f"level {len(levels) - 1} id must be FM followed by ASCII digits"


def test_assurance_policy_orders_a_long_fm_level_id_without_converting_it():
    from tools import check_assurance_policy as gate

    policy = yaml.safe_load((ROOT / gate.ASSURANCE_POLICY_RELATIVE_PATH).read_text(encoding="utf-8"))
    canonical = policy["levels"]
    long_level = {**canonical[-1], "id": "FM" + _BEYOND_DIGIT_LIMIT}

    assert gate._check_levels([*canonical, long_level], gate.ASSURANCE_POLICY_RELATIVE_PATH) == []
    out_of_order = gate._check_levels([long_level, *canonical], gate.ASSURANCE_POLICY_RELATIVE_PATH)
    assert [failure.rule_id for failure in out_of_order] == ["assurance-policy-level-order"]


def test_assurance_policy_keeps_the_canonical_policy_clean():
    from tools import check_assurance_policy as gate

    assert gate.evaluate_assurance_policy(ROOT) == []


def test_sdl_catalog_summary_with_a_count_beyond_the_digit_limit_is_stale():
    from tools.sdl_catalog_parity._checks import _summary_failures

    counts = {"top-level": _BEYOND_DIGIT_LIMIT, "metadata-composition": "0", "sections": "0", "maps": "0"}
    text = "<!-- sdl-catalog-summary " + " ".join(f"{key}={value}" for key, value in counts.items()) + " lists=0 -->"

    failures = _summary_failures(text, [])
    assert [failure.rule_id for failure in failures] == ["sdl-catalog-summary"]
    assert _summary_failures(text.replace(_BEYOND_DIGIT_LIMIT, "00"), []) == []


def _nested_objects(depth: int) -> dict[str, object]:
    # The C JSON decoder builds this depth, but a recursive Python walker stops at the recursion limit.
    value: dict[str, object] = {"leaf": True}
    for _ in range(depth):
        value = {"child": value}
    return value


def test_behavioral_claims_walk_structured_json_of_any_depth():
    from tools import check_behavioral_relation_claims as gate

    objects = list(gate._iter_objects([{"a": [{"b": 1}, {"c": {"d": 2}}]}, {"e": 3}]))
    assert objects == [
        {"a": [{"b": 1}, {"c": {"d": 2}}]},
        {"b": 1},
        {"c": {"d": 2}},
        {"d": 2},
        {"e": 3},
    ]
    assert len(list(gate._iter_objects(_nested_objects(5000)))) == 5001


def test_schema_publication_gate_reports_a_stable_schema_beyond_the_comparison_depth(tmp_path, monkeypatch):
    from tools import check_schema_publication as gate

    deep = _nested_objects(5000)
    base = json.dumps({"properties": {"value": deep}})
    entry = gate.ManifestEntry(
        "example-contract", "contracts/schemas/example-contract.json", "stable", "0" * 64, {"properties": {}}
    )
    base_entry = {"contract_id": "example-contract", "schema_path": entry.schema_path, "stability": "stable"}
    monkeypatch.setattr(gate, "_load_base_manifest", lambda _root, _rev: ({"example-contract": base_entry}, None))
    monkeypatch.setattr(gate, "_git_show", lambda _root, _ref: base)

    failures = gate._check_stable_schema_changes(tmp_path, [entry], base_rev="base")
    assert failures == [
        "stable schema example-contract nests beyond the depth that the compatibility check can compare"
    ]


def test_adr_amendment_check_keeps_distinct_bytes_of_a_revision_that_is_not_utf8_distinct(tmp_path):
    from tools import check_adr_immutability as gate

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    texts = []
    for raw in (b"# ADR\n\xff\n", b"# ADR\n\xfe\n"):
        blob = (
            subprocess.run(
                ["git", "hash-object", "-w", "--stdin"], cwd=tmp_path, input=raw, capture_output=True, check=True
            )
            .stdout.decode("ascii")
            .strip()
        )
        texts.append(gate._git_show(tmp_path, blob))

    # A lossy decoding would make these two revisions hash alike and hide an edit from the amendment check.
    assert gate.content_hash(texts[0]) != gate.content_hash(texts[1])
    assert (
        gate.content_hash("# ADR\nvalid\n")
        == gate.hashlib.sha256(gate.canonical_content("# ADR\nvalid\n").encode("utf-8")).hexdigest()
    )


def test_release_evidence_refuses_an_operator_path_the_host_cannot_resolve(monkeypatch, capsys):
    from tools import release_evidence

    def unresolvable(_path, *, purpose):
        raise OperationalError(f"{purpose} cannot be resolved without a working directory")

    monkeypatch.setattr(release_evidence, "operator_path", unresolvable)

    arguments = ["--distribution-dir", "dist", "--evidence-dir", "evidence", "--signer-workflow", "release.yml"]
    assert release_evidence.main(["verify", *arguments, "--release-tag", "v1.0.0", "--repo-root", "relative"]) == 1
    assert capsys.readouterr().err == (
        "release evidence refused: repository root cannot be resolved without a working directory\n"
    )


# Installer and toolchain tools: input crashes that existed before the branch.

_INSTALLERS2_DEFECT_DETAIL = "SECRET-DEFECT-DETAIL"
_INSTALLERS2_DEEP_TOML = "revision = " + "[" * 5000 + "]" * 5000 + "\n"
_INSTALLERS2_DEEP_JSON = "[" * 100_000 + "]" * 100_000
_INSTALLERS2_UNSAFE_MEMBER = "tool-installation: unsafe-archive-member"
_INSTALLERS2_RUNS_AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
# Captured at import, before any test replaces tempfile.TemporaryDirectory with a failing double.
_INSTALLERS2_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory


def _installers2_client(tmp_path: Path, name: str, body: str) -> Path:
    client = tmp_path / name
    client.write_text("#!/bin/sh\n" + body, encoding="ascii")
    client.chmod(0o700)
    return client


def _installers2_unreadable(path: Path) -> Path:
    if _INSTALLERS2_RUNS_AS_ROOT:
        pytest.skip("file permissions do not restrict the superuser")
    path.chmod(0)
    return path


# --- Python closure generator: nesting beyond the decoder depth is invalid lock input.


def test_closure_lock_nesting_beyond_the_decoder_depth_is_invalid_input(tmp_path: Path) -> None:
    from tools.generate_python_closures import _load_toml_lock

    lock = tmp_path / "uv.lock"
    lock.write_text(_INSTALLERS2_DEEP_TOML, encoding="utf-8")
    with pytest.raises(InvalidInputError, match="uv.lock is not valid UTF-8 TOML"):
        _load_toml_lock(lock)


def test_artifact_lock_nesting_beyond_the_decoder_depth_is_invalid_input(tmp_path: Path) -> None:
    from tools.generate_python_closures import reviewed_python_full_version

    lock = tmp_path / "implementations" / "tooling" / "artifacts.lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(_INSTALLERS2_DEEP_JSON, encoding="utf-8")
    with pytest.raises(InvalidInputError, match="artifact lock exceeds the decoder nesting limit"):
        reviewed_python_full_version("3.14", repo_root=tmp_path)


def _installers2_artifact_lock(root: Path, text: str) -> None:
    lock = root / "implementations" / "tooling" / "artifacts.lock.json"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("text", ["[]", '{"artifacts": 5}'], ids=["root-not-an-object", "artifacts-not-an-array"])
def test_artifact_lock_with_an_invalid_shape_is_invalid_input(tmp_path: Path, text: str) -> None:
    from tools.generate_python_closures import reviewed_python_full_version

    _installers2_artifact_lock(tmp_path, text)
    with pytest.raises(InvalidInputError, match="artifact lock must be an object with an artifacts array"):
        reviewed_python_full_version("3.14", repo_root=tmp_path)


_INSTALLERS2_TARGET = {"python_version": "3.14", "sys_platform": "linux"}


@pytest.mark.parametrize(
    ("lock", "message"),
    [
        pytest.param({"package": 5}, "lock packages must be an array", id="packages-not-an-array"),
        pytest.param(
            {"package": [{"name": "root", "dependencies": 5}]},
            "lock root dependencies must be an array",
            id="root-dependencies-not-an-array",
        ),
        pytest.param(
            {"package": [{"name": "root", "optional-dependencies": "extra"}]},
            "lock root optional dependencies must be a table",
            id="root-optional-dependencies-not-a-table",
        ),
        pytest.param(
            {"package": [{"name": "root", "optional-dependencies": {"extra": 5}}]},
            "lock root optional dependency group must be an array",
            id="root-optional-group-not-an-array",
        ),
        pytest.param(
            {"package": [{"name": "root", "dependencies": [{"name": "dep", "extra": 5}]}, {"name": "dep"}]},
            "lock dependency extras must be an array",
            id="dependency-extras-not-an-array",
        ),
        pytest.param(
            {
                "package": [
                    {"name": "root", "dependencies": [{"name": "dep", "extra": ["cli"]}]},
                    {"name": "dep", "optional-dependencies": [5]},
                ]
            },
            "lock package optional dependencies must be a table",
            id="package-optional-dependencies-not-a-table",
        ),
    ],
)
def test_closure_lock_with_an_invalid_shape_is_invalid_input(lock: dict, message: str) -> None:
    from tools.generate_python_closures_locks import locked_closure

    with pytest.raises(InvalidInputError, match=message):
        locked_closure(lock, _INSTALLERS2_TARGET, root_name="root", include_root_optional=True)


@pytest.mark.parametrize(
    ("package", "wheel", "message"),
    [
        pytest.param(
            {"name": "dep", "version": "1.0"}, {}, "dep has a non-SHA256 wheel identity", id="wheel-without-hash"
        ),
        pytest.param(
            {"name": "dep", "version": "1.0"},
            {"hash": "sha256:" + "0" * 64},
            "dep has no locked version or wheel byte size",
            id="wheel-without-size",
        ),
        pytest.param(
            {"name": "dep"},
            {"hash": "sha256:" + "0" * 64, "size": 1},
            "dep has no locked version or wheel byte size",
            id="package-without-version",
        ),
    ],
)
def test_closure_wheel_without_its_locked_identity_is_invalid_input(package: dict, wheel: dict, message: str) -> None:
    from tools.generate_python_closures import _artifact

    with pytest.raises(InvalidInputError, match=message):
        _artifact(package, {"url": "https://files.example/dep-1.0-py3-none-any.whl", **wheel})


def test_closure_package_wheels_that_are_not_an_array_are_invalid_input() -> None:
    from tools.generate_python_closures import _select_wheel, _supported_tags

    tags = _supported_tags("3.14", "cp314", "x86_64-unknown-linux-gnu")
    with pytest.raises(InvalidInputError, match="lock package wheels must be an array"):
        _select_wheel({"name": "dep", "wheels": 5}, tags)


def test_build_constraint_without_a_locked_version_is_invalid_input(tmp_path: Path) -> None:
    from tools.generate_python_closures import render_build_constraints

    _installers2_artifact_lock(tmp_path, '{"artifacts": [{"artifact_id": "cpython-3.14", "version": "3.14.0"}]}')
    lock = {
        "package": [
            {"name": "raes-development-tools", "dev-dependencies": {"build": [{"name": "hatchling"}]}},
            {"name": "hatchling", "wheels": [{"url": "https://files.example/h.whl", "hash": "sha256:" + "0" * 64}]},
        ]
    }
    with pytest.raises(InvalidInputError, match="build constraint hatchling has no locked version"):
        render_build_constraints(lock, repo_root=tmp_path)


def test_projection_policy_reports_a_closure_lock_with_an_invalid_shape_as_a_policy_failure(tmp_path: Path) -> None:
    from tools.tooling_artifact_policy_python import _projection_generation_failures

    lock = tmp_path / "implementations" / "tooling" / "python" / "uv.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("package = 5\n", encoding="utf-8")
    failures = _projection_generation_failures(tmp_path)
    assert [failure.rule_id for failure in failures] == ["tooling-python-projection-generation"]


# --- Conftest: output that is not a conftest JSON result is the existing evaluation failure.


def _installers2_conftest(monkeypatch: pytest.MonkeyPatch, client: Path) -> None:
    from tools.policy import conftest_tool

    monkeypatch.setattr(conftest_tool, "ensure_conftest", lambda *_args, **_kwargs: client)


@pytest.mark.parametrize(
    "stdout",
    [
        pytest.param("[" + "1" * 5000 + "]", id="integer-beyond-digit-limit"),
        pytest.param(_INSTALLERS2_DEEP_JSON, id="nesting-beyond-decoder-depth"),
        pytest.param("not json", id="not-json"),
        pytest.param('"text"', id="top-level-text"),
        pytest.param("{}", id="top-level-object"),
        pytest.param("[5]", id="result-not-an-object"),
        pytest.param('[{"failures": {}}]', id="failures-not-a-list"),
        pytest.param('[{"failures": [5]}]', id="failure-not-an-object"),
        pytest.param('[{"failures": [{"metadata": {}}]}]', id="failure-without-message"),
        pytest.param('[{"failures": [{"msg": "m", "metadata": []}]}]', id="metadata-not-an-object"),
        pytest.param(
            '[{"failures": [{"msg": "a", "metadata": {"rule_id": 1, "path": "p"}},'
            ' {"msg": "b", "metadata": {"rule_id": "r", "path": "p"}}]}]',
            id="rule-id-not-text",
        ),
    ],
)
def test_conftest_result_that_is_not_a_conftest_json_result_fails_the_policy_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stdout: str
) -> None:
    from tools.policy.conftest_tool import ConftestPolicyError, run_conftest_policy

    report = tmp_path / "report.json"
    report.write_text(stdout, encoding="utf-8")
    _installers2_conftest(monkeypatch, _installers2_client(tmp_path, "conftest", f"cat '{report}'\nexit 1\n"))
    with pytest.raises(
        ConftestPolicyError, match="^conftest repo policy evaluation failed: the JSON result is invalid$"
    ):
        run_conftest_policy({"changed": []}, repo_root=tmp_path, policy_dir=tmp_path)


def test_conftest_result_defaults_and_order_stay_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.policy.conftest_tool import run_conftest_policy

    report = tmp_path / "report.json"
    report.write_text(
        '[{"filename": "input.json", "successes": 2},'
        ' {"failures": [{"msg": "second", "metadata": {"rule_id": "rule-b", "path": "z.py"}}, {"msg": "first"}]}]',
        encoding="utf-8",
    )
    _installers2_conftest(monkeypatch, _installers2_client(tmp_path, "conftest", f"cat '{report}'\nexit 1\n"))
    failures = run_conftest_policy({"changed": []}, repo_root=tmp_path, policy_dir=tmp_path)
    assert [(item.path, item.rule_id, item.message) for item in failures] == [
        (None, "conftest-policy-failure", "first"),
        ("z.py", "rule-b", "second"),
    ]


def test_conftest_policy_run_refuses_output_that_is_not_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.policy.conftest_tool import ConftestPolicyError, run_conftest_policy

    _installers2_conftest(monkeypatch, _installers2_client(tmp_path, "conftest", "printf '[\\377]'\nexit 1\n"))
    with pytest.raises(
        ConftestPolicyError, match="^conftest repo policy evaluation failed: the client output is not text$"
    ):
        run_conftest_policy({"changed": []}, repo_root=tmp_path, policy_dir=tmp_path)


def test_conftest_policy_run_refuses_a_client_that_cannot_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.policy.conftest_tool import ConftestPolicyError, run_conftest_policy

    _installers2_conftest(monkeypatch, tmp_path / "missing-conftest")
    with pytest.raises(ConftestPolicyError, match="^conftest repo policy evaluation failed: the client could not run$"):
        run_conftest_policy({"changed": []}, repo_root=tmp_path, policy_dir=tmp_path)


def test_conftest_policy_verification_refuses_output_that_is_not_text_or_a_missing_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.policy.conftest_tool import ConftestPolicyError, verify_conftest_policy

    _installers2_conftest(monkeypatch, _installers2_client(tmp_path, "conftest", "printf '\\377' >&2\nexit 1\n"))
    with pytest.raises(
        ConftestPolicyError, match="^conftest policy verification failed: the client output is not text$"
    ):
        verify_conftest_policy(repo_root=tmp_path, policy_dir=tmp_path)
    _installers2_conftest(monkeypatch, tmp_path / "missing-conftest")
    with pytest.raises(ConftestPolicyError, match="^conftest policy verification failed: the client could not run$"):
        verify_conftest_policy(repo_root=tmp_path, policy_dir=tmp_path)


def test_conftest_result_parsing_does_not_report_a_defect_as_an_evaluation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.policy import conftest_tool

    def defective(*_args: object) -> None:
        raise ValueError(_INSTALLERS2_DEFECT_DETAIL)

    report = tmp_path / "report.json"
    report.write_text('[{"failures": [{"msg": "m", "metadata": {"rule_id": "r", "path": "p"}}]}]', encoding="utf-8")
    _installers2_conftest(monkeypatch, _installers2_client(tmp_path, "conftest", f"cat '{report}'\nexit 1\n"))
    monkeypatch.setattr(conftest_tool, "PolicyFailure", defective)
    with pytest.raises(ValueError, match=_INSTALLERS2_DEFECT_DETAIL):
        conftest_tool.run_conftest_policy({"changed": []}, repo_root=tmp_path, policy_dir=tmp_path)


# --- Bootstrap host probes: a banner that is not text cannot show the reviewed version.


@pytest.mark.parametrize("probe", ["observe_executable", "inspect_executable"])
def test_bootstrap_probe_reports_a_banner_that_is_not_text_as_a_version_failure(tmp_path: Path, probe: str) -> None:
    from tools import bootstrap_profile

    client = _installers2_client(tmp_path, "client", "printf 'client 1.2.3 \\377\\n'\n")
    arguments = {"expected_version": "1.2.3"} if probe == "inspect_executable" else {}
    result = getattr(bootstrap_profile, probe)("client", client, ("--version",), **arguments)
    assert result == {"capability_id": "client", "outcome": "failed", "reason_code": "native-client-version"}


# --- Development container: git and cache failures get the existing setup refusal or refetch.


def test_devcontainer_hooks_refuse_when_git_cannot_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.devcontainer_setup import DevcontainerSetupError, install_git_hooks

    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    with pytest.raises(DevcontainerSetupError, match="the checkout's git directory could not be resolved"):
        install_git_hooks(tmp_path, tmp_path / "kit")


def test_devcontainer_hooks_refuse_when_git_exceeds_its_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import devcontainer_setup

    def hung(command: list[str], **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(command, 60)

    monkeypatch.setattr(devcontainer_setup.subprocess, "run", hung)
    with pytest.raises(devcontainer_setup.DevcontainerSetupError, match="git directory could not be resolved"):
        devcontainer_setup.install_git_hooks(tmp_path, tmp_path / "kit")


def test_devcontainer_cache_treats_an_unreadable_archive_as_unverified(tmp_path: Path) -> None:
    from tools.devcontainer_setup import _verified_archive

    archive = tmp_path / "payload.tar.gz"
    archive.write_bytes(b"payload")
    raw = {"size": len(b"payload"), "sha256": hashlib.sha256(b"payload").hexdigest()}
    assert _verified_archive(archive, raw) is True
    assert _verified_archive(_installers2_unreadable(archive), raw) is False


# --- Lock selections: a manifest path without a UTF-8 form is an unsafe member path.


def _installers2_entry(path: str, *, executable: bool = True) -> SimpleNamespace:
    return SimpleNamespace(path=path, sha256="0" * 64, size=1, executable=executable)


def test_tool_selection_with_an_unpaired_surrogate_path_is_an_unsafe_member(tmp_path: Path) -> None:
    from tools.verified_tool_installation import installation_tree_path

    selection = SimpleNamespace(
        artifact_id="tool",
        platform_id="linux-x86_64",
        policy_refs=("policy",),
        raw_manifest=(_installers2_entry("tool.tar.gz", executable=False),),
        installed_manifest=(_installers2_entry("bin/\ud800"),),
    )
    with pytest.raises(ToolInstallationError) as refused:
        installation_tree_path(tmp_path, selection)
    assert str(refused.value) == _INSTALLERS2_UNSAFE_MEMBER


def test_tree_selection_with_an_unpaired_surrogate_path_is_an_unsafe_member() -> None:
    from tools.verified_tree_archive import symlink_target_shape_is_safe
    from tools.verified_tree_validation import validated_descriptor

    descriptor = SimpleNamespace(
        format="tar.gz",
        manifest_sha256="0" * 64,
        file_count=1,
        directory_count=1,
        symlink_count=0,
        expanded_bytes=1,
    )
    selection = SimpleNamespace(
        installed_tree=descriptor,
        raw_manifest=(_installers2_entry("tool.tar.gz", executable=False),),
        installed_manifest=(_installers2_entry("bin/\ud800"),),
        policy_refs=("policy",),
    )
    with pytest.raises(ToolInstallationError) as refused:
        validated_descriptor(selection)
    assert str(refused.value) == _INSTALLERS2_UNSAFE_MEMBER
    assert symlink_target_shape_is_safe("\ud800") is False


# --- Participant-opacity proof gate: malformed evidence is a proof evidence refusal.


def _installers2_manifest() -> dict:
    from tools.check_participant_opacity_proof import load_proof_manifest

    return deepcopy(load_proof_manifest())


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    [
        pytest.param(
            "semantic_sources",
            "requirement",
            ["SEM-230"],
            "proof evidence semantic sources do not cover SEM-230 and SEM-231",
            id="unhashable-requirement",
        ),
        pytest.param(
            "dependencies", "issue", [810], "proof evidence dependency set is incomplete", id="unhashable-issue"
        ),
        pytest.param(
            "semantic_sources",
            "path",
            "specs/formal/a\x00b",
            "proof evidence contains an unsafe repository path",
            id="path-with-nul",
        ),
        pytest.param(
            "semantic_sources",
            "path",
            "specs/formal/\ud800",
            "proof evidence contains an unsafe repository path",
            id="path-without-utf8-form",
        ),
    ],
)
def test_proof_gate_refuses_malformed_source_bindings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    section: str,
    field: str,
    value: object,
    message: str,
) -> None:
    from tools import check_participant_opacity_proof as proof

    manifest = _installers2_manifest()
    manifest[section][0][field] = value
    with pytest.raises(proof.ProofEvidenceError, match=message):
        proof.validate_proof_manifest(manifest, run_prover=False)
    monkeypatch.setattr(proof, "load_proof_manifest", lambda: manifest)
    assert proof.main() == 1
    assert capsys.readouterr().err == f"participant-opacity-proof: {message}\n"


def test_proof_gate_refuses_an_unhashable_negative_theorem_id() -> None:
    from tools.check_participant_opacity_proof import ProofEvidenceError, _validate_theorem_inventory

    manifest = _installers2_manifest()
    manifest["negative_theorems"][0]["theorem_id"] = ["theorem"]
    with pytest.raises(ProofEvidenceError, match="negative theorem mutation binding is invalid"):
        _validate_theorem_inventory(manifest, "")


def test_proof_gate_refuses_a_session_source_that_is_not_utf8(tmp_path: Path) -> None:
    from tools.check_participant_opacity_proof import (
        ROOT_RELATIVE_PATH,
        THEORY_RELATIVE_PATH,
        ProofEvidenceError,
        _validate_session,
    )

    root = tmp_path / ROOT_RELATIVE_PATH
    theory = tmp_path / THEORY_RELATIVE_PATH
    root.parent.mkdir(parents=True)
    root.write_text("session Participant_Opacity = HOL +\n", encoding="utf-8")
    theory.write_bytes(b"theory Participant_Opacity imports Main begin \xff\n")
    manifest = _installers2_manifest()
    manifest["session"]["root_digest"] = "sha256:" + hashlib.sha256(root.read_bytes()).hexdigest()
    manifest["session"]["theory_digest"] = "sha256:" + hashlib.sha256(theory.read_bytes()).hexdigest()
    with pytest.raises(ProofEvidenceError, match="proof session source is unreadable or not UTF-8"):
        _validate_session(manifest, tmp_path)


def test_proof_gate_refuses_an_unreadable_bound_source(tmp_path: Path) -> None:
    from tools.check_participant_opacity_proof import ProofEvidenceError, _validate_digest_bound_path

    source = tmp_path / "source.md"
    source.write_text("text", encoding="utf-8")
    _installers2_unreadable(source)
    with pytest.raises(ProofEvidenceError, match="semantic source repository file is unreadable"):
        _validate_digest_bound_path(tmp_path, {"path": "source.md", "digest": "sha256:0"}, "semantic source")


# --- Python closure: operator paths and client output get the existing closure refusals.


def test_closure_destination_that_is_a_file_is_refused(tmp_path: Path) -> None:
    from tools.python_closure_wheelhouse import require_empty_destination

    destination = tmp_path / "environment"
    destination.write_text("not a directory", encoding="utf-8")
    with pytest.raises(InvalidInputError, match="smoke environment must be an empty non-symlink directory"):
        require_empty_destination(destination, "smoke environment")


def test_closure_candidate_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    from tools.python_closure_wheelhouse import candidate_digest

    candidate = tmp_path / "raes-1.0.tar.gz"
    candidate.write_bytes(b"candidate")
    unreadable = _installers2_unreadable(candidate)
    with pytest.raises(InvalidInputError, match="candidate distribution is unreadable"):
        candidate_digest(unreadable)


def test_closure_wheelhouse_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    from tools.python_closure_wheelhouse import verify_wheelhouse

    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    wheel = wheelhouse / "example-1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    manifest = {
        "artifacts": [{"filename": wheel.name, "size": len(b"wheel"), "sha256": hashlib.sha256(b"wheel").hexdigest()}]
    }
    verify_wheelhouse(wheelhouse, manifest)
    _installers2_unreadable(wheel)
    with pytest.raises(InvalidInputError, match=f"wheelhouse artifact is unreadable: {wheel.name}"):
        verify_wheelhouse(wheelhouse, manifest)
    wheel.chmod(0o600)
    wheelhouse.chmod(0)
    try:
        with pytest.raises(InvalidInputError, match="wheelhouse is unreadable"):
            verify_wheelhouse(wheelhouse, manifest)
    finally:
        wheelhouse.chmod(0o700)


def test_closure_client_output_that_is_not_text_is_refused(tmp_path: Path) -> None:
    from tools.python_closure import _run

    with pytest.raises(OperationalError, match="Python closure client output is not text"):
        _run(["/bin/sh", "-c", "printf '\\377'"], cwd=tmp_path, environment={"PATH": "/usr/bin:/bin"})


# --- Isabelle replay: a sandbox that cannot start is the existing proof tool failure.


def test_isabelle_replay_refuses_a_sandbox_that_cannot_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import isabelle_tool

    monkeypatch.setattr(isabelle_tool.platform, "system", lambda: "Linux")
    monkeypatch.setattr(isabelle_tool.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(isabelle_tool, "_require_fontconfig_runtime", lambda: None)
    monkeypatch.setattr(isabelle_tool, "_require_locale_runtime", lambda: None)
    monkeypatch.setattr(isabelle_tool, "require_isabelle", lambda _root: tmp_path / "isabelle")
    monkeypatch.setattr(isabelle_tool, "_proof_sandbox_command", lambda **_kwargs: [str(tmp_path / "missing-bwrap")])
    (tmp_path / isabelle_tool.ISABELLE_SESSION_RELATIVE_PATH).mkdir(parents=True)
    with pytest.raises(isabelle_tool.IsabelleToolError, match="the offline proof sandbox could not start"):
        isabelle_tool.run_isabelle_build(tmp_path, bwrap=Path(sys.executable))


# --- Host resource failures: each tool refuses with its existing operational error, not a crash.


def _installers2_host_failure(*_args: object, **_kwargs: object) -> None:
    raise OSError(errno.EACCES, "simulated host failure")


def _installers2_failing_for(method_name: str, match: str):
    original = getattr(Path, method_name)

    def failing(self: Path, *args: object, **kwargs: object) -> object:
        if self.name == match:
            raise OSError(errno.EACCES, "simulated host failure")
        return original(self, *args, **kwargs)

    return failing


def _installers2_fetch_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import bootstrap_profile

    raw = {"path": "payload.tar.gz", "sha256": hashlib.sha256(b"payload").hexdigest(), "size": len(b"payload")}
    artifact = {
        "artifact_id": "payload",
        "artifact_class": "bootstrap",
        "platform": {"raw_manifest": [raw], "source_urls": ["https://example.test/payload.tar.gz"]},
        "source": {"locator_refs": ["primary"]},
    }
    selection = ({"bootstrap_payload_ids": ["payload"]}, {"payload": artifact}, "0" * 64)
    monkeypatch.setattr(bootstrap_profile, "_load_host_selection", lambda _host_id: selection)


def _installers2_transfer(outcome: str, payload: bytes | None):
    def transfer(_client: Path, _url: str, output: Path, **_kwargs: object) -> dict[str, str]:
        if payload is not None:
            output.write_bytes(payload)
        return {"outcome": outcome, "reason_code": "curl-transfer-qualified"}

    return transfer


def test_bootstrap_fetch_refuses_a_cache_directory_the_host_cannot_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import bootstrap_profile

    _installers2_fetch_selection(monkeypatch)
    monkeypatch.setattr(bootstrap_profile, "safe_tooling_cache_parent", _installers2_host_failure)
    with pytest.raises(OperationalError, match="^bootstrap payload cache directory could not be created$"):
        bootstrap_profile.fetch_bootstrap_payloads("host", tmp_path, ["payload"])


def test_bootstrap_fetch_refuses_a_transfer_output_the_host_cannot_remove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import bootstrap_profile

    _installers2_fetch_selection(monkeypatch)
    monkeypatch.setattr(bootstrap_profile, "run_curl_qualification", _installers2_host_failure)
    with pytest.raises(OperationalError, match="raw payload could not be removed after its transfer$"):
        bootstrap_profile.fetch_bootstrap_payloads("host", tmp_path, ["payload"])


def test_bootstrap_fetch_refuses_a_payload_it_cannot_read_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import bootstrap_profile

    _installers2_fetch_selection(monkeypatch)
    monkeypatch.setattr(bootstrap_profile, "run_curl_qualification", _installers2_transfer("passed", b"payload"))
    monkeypatch.setattr(bootstrap_profile, "_sha256", _installers2_host_failure)
    with pytest.raises(OperationalError, match="^bootstrap payload raw payload failed exact verification$"):
        bootstrap_profile.fetch_bootstrap_payloads("host", tmp_path, ["payload"])
    assert not (tmp_path / "archives" / "payload" / "payload.tar.gz").exists()


def test_bootstrap_fetch_refuses_a_failed_payload_it_cannot_remove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import bootstrap_profile

    _installers2_fetch_selection(monkeypatch)
    monkeypatch.setattr(bootstrap_profile, "run_curl_qualification", _installers2_transfer("failed", b"partial"))
    monkeypatch.setattr(Path, "unlink", _installers2_failing_for("unlink", "payload.tar.gz"))
    with pytest.raises(OperationalError, match="failed exact verification and could not be removed$"):
        bootstrap_profile.fetch_bootstrap_payloads("host", tmp_path, ["payload"])


def _installers2_archive(members: dict[str, bytes], directories: tuple[str, ...] = ()) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        for name in directories:
            info = tarfile.TarInfo(name)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            bundle.addfile(info)
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o755
            bundle.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _installers2_kit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, artifact_id: str, archive: bytes) -> Path:
    from tools import bootstrap_profile

    kit = tmp_path / "kit"
    stored = kit / "archives" / artifact_id / "payload.tar.gz"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(archive)
    raw = {"path": "payload.tar.gz", "size": len(archive), "sha256": hashlib.sha256(archive).hexdigest()}
    artifact = {"artifact_id": artifact_id, "version": "1.0", "platform": {"raw_manifest": [raw]}}
    monkeypatch.setattr(bootstrap_profile, "_load_host_selection", lambda _host_id: ({}, {artifact_id: artifact}, ""))
    return kit


_INSTALLERS2_PYTHON_ARCHIVE = {"python/bin/python3": b"#!/bin/sh\n"}
_INSTALLERS2_UV_ARCHIVE = {"uv-x86_64/uv": b"#!/bin/sh\n", "uv-x86_64/uvx": b"#!/bin/sh\n"}


def test_bootstrap_python_install_refuses_an_archive_it_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import bootstrap_profile

    kit = _installers2_kit(tmp_path, monkeypatch, "cpython", _installers2_archive(_INSTALLERS2_PYTHON_ARCHIVE))
    monkeypatch.setattr(bootstrap_profile, "_sha256", _installers2_host_failure)
    with pytest.raises(OperationalError, match="^bootstrap Python archive could not be read$"):
        bootstrap_profile.install_python_payload("host", kit, "cpython")


def test_bootstrap_python_install_refuses_a_destination_the_host_cannot_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import bootstrap_profile

    kit = _installers2_kit(tmp_path, monkeypatch, "cpython", _installers2_archive(_INSTALLERS2_PYTHON_ARCHIVE))
    (kit / "python").write_text("not a directory", encoding="utf-8")
    with pytest.raises(OperationalError, match="^bootstrap Python destination could not be created$"):
        bootstrap_profile.install_python_payload("host", kit, "cpython")


def test_bootstrap_python_install_refuses_a_payload_the_host_cannot_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import bootstrap_profile

    kit = _installers2_kit(tmp_path, monkeypatch, "cpython", _installers2_archive(_INSTALLERS2_PYTHON_ARCHIVE))
    monkeypatch.setattr(Path, "rename", _installers2_failing_for("rename", "python"))
    with pytest.raises(OperationalError, match="^bootstrap Python payload could not be moved into the kit root$"):
        bootstrap_profile.install_python_payload("host", kit, "cpython")


def test_bootstrap_python_install_refuses_an_extraction_directory_the_host_cannot_create_or_remove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import bootstrap_profile

    kit = _installers2_kit(tmp_path, monkeypatch, "cpython", _installers2_archive(_INSTALLERS2_PYTHON_ARCHIVE))
    monkeypatch.setattr(bootstrap_profile.tempfile, "TemporaryDirectory", _installers2_host_failure)
    with pytest.raises(OperationalError, match="^bootstrap kit extraction directory could not be created$"):
        bootstrap_profile.install_python_payload("host", kit, "cpython")

    class _Installers2Stage:
        def __init__(self, *, prefix: str, dir: Path | None) -> None:
            self._stage = _INSTALLERS2_TEMPORARY_DIRECTORY(prefix=prefix, dir=dir)
            self.name = self._stage.name

        def cleanup(self) -> None:
            self._stage.cleanup()
            raise OSError(errno.EBUSY, "simulated host failure")

    monkeypatch.setattr(bootstrap_profile.tempfile, "TemporaryDirectory", _Installers2Stage)
    with pytest.raises(OperationalError, match="^bootstrap kit extraction directory could not be removed$"):
        bootstrap_profile.install_python_payload("host", kit, "cpython")


def test_bootstrap_python_install_keeps_its_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import bootstrap_profile

    kit = _installers2_kit(tmp_path, monkeypatch, "cpython", _installers2_archive(_INSTALLERS2_PYTHON_ARCHIVE))
    assert bootstrap_profile.install_python_payload("host", kit, "cpython") == {
        "artifact_id": "cpython",
        "path": "python/cpython-1.0",
    }
    assert (kit / "python" / "cpython-1.0" / "bin" / "python3").is_file()
    assert not list(kit.glob(".python-extract-*"))


def test_bootstrap_uv_install_refuses_host_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import bootstrap_profile

    kit = _installers2_kit(tmp_path, monkeypatch, "uv", _installers2_archive(_INSTALLERS2_UV_ARCHIVE))
    (kit / "bin").write_text("not a directory", encoding="utf-8")
    with pytest.raises(OperationalError, match="^bootstrap uv destination could not be created$"):
        bootstrap_profile.install_uv_payload("host", kit, "uv")
    (kit / "bin").unlink()
    monkeypatch.setattr(Path, "chmod", _installers2_failing_for("chmod", "uv"))
    with pytest.raises(
        OperationalError, match="^bootstrap uv payload could not install its uv client in the kit root$"
    ):
        bootstrap_profile.install_uv_payload("host", kit, "uv")


def test_bootstrap_uv_install_refuses_an_archive_member_without_a_root_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import bootstrap_profile

    kit = _installers2_kit(tmp_path, monkeypatch, "uv", _installers2_archive({}, directories=(".",)))
    with pytest.raises(InvalidInputError, match="^bootstrap uv archive has an unexpected shape$"):
        bootstrap_profile.install_uv_payload("host", kit, "uv")


def test_bootstrap_generic_tools_refuse_a_probe_directory_the_host_cannot_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools import bootstrap_profile

    monkeypatch.setattr(bootstrap_profile.tempfile, "TemporaryDirectory", _installers2_host_failure)
    with pytest.raises(OperationalError, match="^bootstrap generic-tool probe directory could not be created$"):
        bootstrap_profile.qualify_generic_tools(selections=[("tool", Path(sys.executable), ("--version",), "1")])


# --- Python closure: output roots, the reviewed manifest and private workspaces.


def _installers2_closure_profile():
    from tools.python_closure_profiles import REPO_ROOT, load_python_closure_profile

    return load_python_closure_profile(REPO_ROOT, "public-linux-x86_64-cp314-all-extras")


def test_closure_build_refuses_an_output_directory_the_host_cannot_create(tmp_path: Path) -> None:
    from tools.python_closure import REPO_ROOT, _build

    (tmp_path / "file").write_text("not a directory", encoding="utf-8")
    profile = _installers2_closure_profile()
    with pytest.raises(OperationalError, match="^candidate build output could not be created$"):
        _build(
            profile,
            REPO_ROOT / "implementations" / "python",
            tmp_path / "file" / "out",
            context_id="python-public",
        )


def test_closure_build_refuses_a_private_workspace_the_host_cannot_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import python_closure

    monkeypatch.setattr(python_closure.tempfile, "TemporaryDirectory", _installers2_host_failure)
    profile = _installers2_closure_profile()
    with pytest.raises(OperationalError, match="^Python closure private workspace could not be created$"):
        python_closure._build(
            profile,
            python_closure.REPO_ROOT / "implementations" / "python",
            tmp_path / "out",
            context_id="python-public",
        )


def test_closure_materialize_refuses_a_wheelhouse_the_host_cannot_create(tmp_path: Path) -> None:
    from tools.python_closure import _materialize

    (tmp_path / "file").write_text("not a directory", encoding="utf-8")
    profile = _installers2_closure_profile()
    with pytest.raises(OperationalError, match="^wheelhouse destination could not be created$"):
        _materialize(profile, tmp_path / "file" / "wheelhouse")


def test_closure_manifest_show_refuses_a_manifest_the_host_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from dataclasses import replace

    from tools import python_closure

    unreadable = replace(_installers2_closure_profile(), wheelhouse_manifest=tmp_path / "missing.json")
    monkeypatch.setattr(python_closure, "load_python_closure_profile", lambda _root, _profile_id: unreadable)
    assert python_closure.main(["manifest-show", "--profile", "public-linux-x86_64-cp314-all-extras"]) == 1
    assert capsys.readouterr().err == "python-closure: the reviewed wheelhouse manifest could not be read\n"


def test_closure_operator_path_refuses_an_unavailable_working_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.python_closure_wheelhouse import operator_path

    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: _installers2_host_failure()))
    with pytest.raises(OperationalError, match="^smoke candidate cannot be resolved without a working directory$"):
        operator_path(Path("candidate.whl"), purpose="smoke candidate")


# --- Development container: kit staging and environment replacement.


def _installers2_container_kit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, link_exists: bool = False):
    from tools import bootstrap_profile, tooling_policy_gate

    def artifact(artifact_id: str, implementation: str) -> dict[str, object]:
        raw = {"path": f"{artifact_id}.tar.gz", "size": 7, "sha256": hashlib.sha256(b"payload").hexdigest()}
        return {
            "artifact_id": artifact_id,
            "platform": {"raw_manifest": [raw], "installed_identity": {"implementation": implementation}},
        }

    selection = {"artifacts": [artifact("cpython", "CPython"), artifact("uv", "uv")]}
    monkeypatch.setattr(
        tooling_policy_gate, "load_tooling_host_profile_selection_with_current_interpreter", lambda _host: selection
    )

    def fetch(_host: str, staging: Path, missing: list[str]) -> list[dict[str, object]]:
        for artifact_id in missing:
            stored = staging / "archives" / artifact_id / f"{artifact_id}.tar.gz"
            stored.parent.mkdir(parents=True, exist_ok=True)
            stored.write_bytes(b"payload")
        return []

    def install_python(_host: str, staging: Path, _artifact_id: str) -> dict[str, str]:
        (staging / "python" / "cpython-1.0").mkdir(parents=True)
        if link_exists:
            (staging / "python" / "current").write_text("occupied", encoding="utf-8")
        return {"artifact_id": "cpython", "path": "python/cpython-1.0"}

    monkeypatch.setattr(bootstrap_profile, "fetch_bootstrap_payloads", fetch)
    monkeypatch.setattr(bootstrap_profile, "install_uv_payload", lambda *_args: {"path": "bin/uv"})
    monkeypatch.setattr(bootstrap_profile, "install_python_payload", install_python)
    return tmp_path / "cache" / "raes-bootstrap"


def _installers2_assert_no_staging(kit_root: Path) -> None:
    if kit_root.parent.is_dir():
        assert not list(kit_root.parent.glob(".raes-bootstrap-staging-*"))


def test_devcontainer_kit_refuses_a_kit_directory_the_host_cannot_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.devcontainer_setup import DevcontainerSetupError, prepare_kit

    kit_root = _installers2_container_kit(tmp_path, monkeypatch)
    kit_root.parent.write_text("not a directory", encoding="utf-8")
    with pytest.raises(DevcontainerSetupError, match="^the bootstrap kit directory could not be created$"):
        prepare_kit("host", kit_root)


def test_devcontainer_kit_refuses_a_staging_directory_the_host_cannot_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import devcontainer_setup

    kit_root = _installers2_container_kit(tmp_path, monkeypatch)
    monkeypatch.setattr(devcontainer_setup.tempfile, "mkdtemp", _installers2_host_failure)
    with pytest.raises(
        devcontainer_setup.DevcontainerSetupError, match="^the bootstrap kit staging directory could not be created$"
    ):
        devcontainer_setup.prepare_kit("host", kit_root)


def test_devcontainer_kit_refuses_a_cached_archive_the_host_cannot_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import devcontainer_setup

    kit_root = _installers2_container_kit(tmp_path, monkeypatch)
    cached = kit_root / "archives" / "cpython" / "cpython.tar.gz"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"payload")
    monkeypatch.setattr(devcontainer_setup.shutil, "copyfile", _installers2_host_failure)
    with pytest.raises(
        devcontainer_setup.DevcontainerSetupError, match="^a cached bootstrap archive could not be copied into staging$"
    ):
        devcontainer_setup.prepare_kit("host", kit_root)
    _installers2_assert_no_staging(kit_root)


def test_devcontainer_kit_refuses_an_interpreter_link_the_host_cannot_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.devcontainer_setup import DevcontainerSetupError, prepare_kit

    kit_root = _installers2_container_kit(tmp_path, monkeypatch, link_exists=True)
    with pytest.raises(DevcontainerSetupError, match="^the bootstrap kit interpreter link could not be created$"):
        prepare_kit("host", kit_root)
    _installers2_assert_no_staging(kit_root)


def test_devcontainer_kit_refuses_a_kit_the_host_cannot_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.devcontainer_setup import DevcontainerSetupError, prepare_kit

    kit_root = _installers2_container_kit(tmp_path, monkeypatch)
    kit_root.mkdir(parents=True)
    kit_root.with_name(f".{kit_root.name}-previous").write_text("occupied", encoding="utf-8")
    with pytest.raises(DevcontainerSetupError, match="^the bootstrap kit could not be replaced$"):
        prepare_kit("host", kit_root)
    _installers2_assert_no_staging(kit_root)


def test_devcontainer_kit_keeps_its_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.devcontainer_setup import prepare_kit

    kit_root = _installers2_container_kit(tmp_path, monkeypatch)
    assert prepare_kit("host", kit_root) == {
        "host_profile_id": "host",
        "python": "cpython",
        "uv": "uv",
        "fetched": "cpython,uv",
    }
    assert (kit_root / "python" / "current").is_symlink()
    _installers2_assert_no_staging(kit_root)


def test_devcontainer_sync_refuses_an_environment_the_host_cannot_remove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import devcontainer_setup

    monkeypatch.setattr(devcontainer_setup, "environment_is_relocated", lambda _venv: True)
    monkeypatch.setattr(devcontainer_setup.shutil, "rmtree", _installers2_host_failure)
    monkeypatch.setattr(devcontainer_setup, "_run", lambda *_args: None)
    with pytest.raises(
        devcontainer_setup.DevcontainerSetupError, match="^a relocated project environment could not be removed$"
    ):
        devcontainer_setup.sync_projects(tmp_path, tmp_path / "kit")


# --- Isabelle: the private proof state and the bounded build output.


def test_isabelle_replay_refuses_build_output_the_host_cannot_read(tmp_path: Path) -> None:
    from tools.isabelle_tool import IsabelleToolError, _read_bounded_output

    with pytest.raises(IsabelleToolError, match="^Isabelle build output could not be read$"):
        _read_bounded_output(tmp_path / "missing.log")


def test_isabelle_replay_refuses_a_proof_state_the_host_cannot_prepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import isabelle_tool

    monkeypatch.setattr(isabelle_tool.platform, "system", lambda: "Linux")
    monkeypatch.setattr(isabelle_tool.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(isabelle_tool, "_require_fontconfig_runtime", lambda: None)
    monkeypatch.setattr(isabelle_tool, "_require_locale_runtime", lambda: None)
    monkeypatch.setattr(isabelle_tool, "require_isabelle", lambda _root: tmp_path / "isabelle")
    (tmp_path / isabelle_tool.ISABELLE_SESSION_RELATIVE_PATH).mkdir(parents=True)
    monkeypatch.setattr(isabelle_tool.tempfile, "TemporaryDirectory", _installers2_host_failure)
    with pytest.raises(isabelle_tool.IsabelleToolError, match="^the private proof state could not be prepared$"):
        isabelle_tool.run_isabelle_build(tmp_path, bwrap=Path(sys.executable))

    class _Installers2OccupiedState:
        def __init__(self, *, prefix: str) -> None:
            self._stage = _INSTALLERS2_TEMPORARY_DIRECTORY(prefix=prefix)
            self.name = self._stage.name
            (Path(self.name) / "user").write_text("occupied", encoding="utf-8")

        def cleanup(self) -> None:
            self._stage.cleanup()

    monkeypatch.setattr(isabelle_tool.tempfile, "TemporaryDirectory", _Installers2OccupiedState)
    with pytest.raises(isabelle_tool.IsabelleToolError, match="^the private proof state could not be prepared$"):
        isabelle_tool.run_isabelle_build(tmp_path, bwrap=Path(sys.executable))


# --- OSV-Scanner: the report sink and the scanner client.


def test_osv_scan_refuses_a_report_or_client_the_host_cannot_use(tmp_path: Path) -> None:
    from tools.osv_scanner_tool import run_osv_scanner

    lockfile = tmp_path / "uv.lock"
    lockfile.write_text("", encoding="utf-8")
    (tmp_path / "file").write_text("not a directory", encoding="utf-8")
    with pytest.raises(OperationalError, match="^osv-scanner report could not be written$"):
        run_osv_scanner(lockfile, tmp_path / "file" / "report.json", binary=Path(sys.executable))
    with pytest.raises(OperationalError, match="^osv-scanner could not run or finish its report$"):
        run_osv_scanner(lockfile, tmp_path / "reports" / "report.json", binary=tmp_path / "missing-osv-scanner")


class _Installers2UnremovableStage:
    def __init__(self, *, prefix: str, dir: Path | None = None) -> None:
        self._stage = _INSTALLERS2_TEMPORARY_DIRECTORY(prefix=prefix, dir=dir)
        self.name = self._stage.name

    def cleanup(self) -> None:
        self._stage.cleanup()
        raise OSError(errno.EBUSY, "simulated host failure")


@pytest.mark.parametrize(
    ("module_name", "stage", "message"),
    [
        pytest.param(
            "python_closure",
            lambda module: module._private_workspace("raes-test-"),
            "^Python closure private workspace could not be removed$",
            id="python-closure-workspace",
        ),
        pytest.param(
            "isabelle_tool",
            lambda module: module._private_proof_state(),
            "^the private proof state could not be removed$",
            id="isabelle-proof-state",
        ),
        pytest.param(
            "bootstrap_profile",
            lambda module: module._private_stage("raes-test-", None, "generic-tool probe"),
            "^bootstrap generic-tool probe directory could not be removed$",
            id="bootstrap-probe",
        ),
    ],
)
def test_private_directories_report_a_cleanup_failure_and_keep_body_defects(
    monkeypatch: pytest.MonkeyPatch, module_name: str, stage, message: str
) -> None:
    import importlib

    module = importlib.import_module(f"tools.{module_name}")
    with pytest.raises(ValueError, match=_INSTALLERS2_DEFECT_DETAIL), stage(module):
        raise ValueError(_INSTALLERS2_DEFECT_DETAIL)
    monkeypatch.setattr(module.tempfile, "TemporaryDirectory", _Installers2UnremovableStage)
    with pytest.raises(OperationalError, match=message), stage(module) as root:
        assert root.is_dir()


# Repository workflow and nox tools: input crashes that existed before the branch.

_NOX2_LONG_INTEGER = "1" * 5000
_NOX2_SENTINEL = "SECRET-SENTINEL-VALUE"
_NOX2_DEFECT = "SECRET-DEFECT-DETAIL"
_NOX2_DIGIT_LIMIT_JSON = '{"note": "' + _NOX2_SENTINEL + '", "value": ' + _NOX2_LONG_INTEGER + "}"
_NOX2_DEEP_JSON = '{"note": "' + _NOX2_SENTINEL + '", "value": ' + "[" * 100_000 + "]" * 100_000 + "}"
_NOX2_UNDECODABLE_JSON = pytest.mark.parametrize(
    "payload",
    (_NOX2_DIGIT_LIMIT_JSON.encode(), _NOX2_DEEP_JSON.encode(), b'{"value": "\xff"}'),
    ids=("integer-beyond-digit-limit", "nesting-beyond-decoder-depth", "not-utf8"),
)
# PyYAML's safe constructor raises ValueError, KeyError, AttributeError or
# IndexError, not a YAMLError, for these scalars, and its composer stops at the
# recursion limit.
_NOX2_UNCONSTRUCTABLE_YAML = pytest.mark.parametrize(
    "document",
    (
        "value: 2024-13-01\n",
        f"value: {_NOX2_LONG_INTEGER}\n",
        "value: !!bool maybe\n",
        "value: !!timestamp later\n",
        'value: !!int ""\n',
        "value: " + "[" * 100_000 + "]" * 100_000 + "\n",
    ),
    ids=(
        "impossible-date",
        "integer-beyond-digit-limit",
        "bad-explicit-bool",
        "bad-explicit-timestamp",
        "empty-tagged-integer",
        "nesting-beyond-composer-depth",
    ),
)


def _nox2_write(path: Path, content: str | bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


# tools/check_pr_body.py


@pytest.mark.parametrize("keyword", ["Closes", "Refs"])
def test_pr_body_issue_reference_beyond_the_digit_limit_is_an_issue_tracking_violation(keyword: str) -> None:
    import tools.check_pr_body as pr_body

    body = GROUND_CONTROL_REQUIREMENT_FREE.replace("Closes #123", f"{keyword} #{_NOX2_LONG_INTEGER}")

    def lookup(_number: int) -> pr_body.IssueFacts:
        raise AssertionError("a reference beyond the digit limit names no issue to look up")

    violations = pr_body.validate_pr_body(body, lookup, repository="OpenRAE/rae")

    assert violations
    assert {violation.rule_id for violation in violations} == {pr_body.RULE_ISSUES}
    assert pr_body.closing_issue_numbers(body) == ()
    assert "No issue-tracking declaration was found." in pr_body._open_issue_report(body, lookup, 7)


def test_pr_body_cli_rejects_a_reference_beyond_the_digit_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools.check_pr_body import main

    body = GROUND_CONTROL_REQUIREMENT_FREE.replace("Closes #123", f"Closes #{_NOX2_LONG_INTEGER}")
    event = _nox2_write(
        tmp_path / "event.json",
        json.dumps({"repository": {"full_name": "OpenRAE/rae"}, "pull_request": {"number": 7, "body": body}}),
    )
    issues = _nox2_write(tmp_path / "issues.json", json.dumps({"123": "open"}))

    assert main(["--event-path", str(event), "--issues-file", str(issues)]) == 1
    error = capsys.readouterr().err
    assert "pr-body-guard: rejected pull request body" in error
    assert "configuration error" not in error


def test_pr_body_cli_reports_an_event_beyond_the_decoder_depth_as_a_configuration_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools.check_pr_body import main

    event = _nox2_write(tmp_path / "event.json", _NOX2_DEEP_JSON)

    assert main(["--event-path", str(event)]) == 2
    error = capsys.readouterr().err
    assert error.startswith("pr-body-guard: configuration error: ")
    assert _NOX2_SENTINEL not in error


# tools/ci_latency_report.py


@_NOX2_UNDECODABLE_JSON
def test_latency_report_refuses_a_cohort_the_decoder_cannot_read(
    capsys: pytest.CaptureFixture[str], payload: bytes
) -> None:
    from tools.ci_latency_report import main

    stdin = io.TextIOWrapper(io.BytesIO(b"[" + payload + b"]"), encoding="utf-8")

    assert main([], stdin=stdin) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ci-latency-report: cohort payload on stdin is not valid JSON\n"


def test_latency_report_refuses_timestamps_with_and_without_a_utc_offset(capsys: pytest.CaptureFixture[str]) -> None:
    from tools.ci_latency_report import main

    cohort = [
        {
            "run": {"id": 1, "created_at": "2026-09-16T00:00:00Z", "run_started_at": "2026-09-16T00:01:00"},
            "jobs": [],
        }
    ]

    assert main([], stdin=io.StringIO(json.dumps(cohort))) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ci-latency-report: ")
    assert "UTC offset" in captured.err


def test_latency_report_refuses_a_job_that_is_not_an_object(capsys: pytest.CaptureFixture[str]) -> None:
    from tools.ci_latency_report import main

    cohort = [{"run": {"id": 1, "run_started_at": "2026-09-16T00:01:00Z"}, "jobs": [_NOX2_SENTINEL]}]

    assert main([], stdin=io.StringIO(json.dumps(cohort))) == 1
    captured = capsys.readouterr()
    assert captured.err == "ci-latency-report: cohort entry 'jobs' must contain only objects\n"
    assert _NOX2_SENTINEL not in captured.err


def test_latency_report_keeps_aware_and_naive_runs_that_are_each_consistent() -> None:
    from tools.ci_latency_report import parse_run

    aware = parse_run({"created_at": "2026-09-16T00:00:00Z", "run_started_at": "2026-09-16T00:01:00Z"}, [], ())
    naive = parse_run({"created_at": "2026-09-16T00:00:00", "run_started_at": "2026-09-16T00:01:00"}, [], ())

    assert aware.queue_s == naive.queue_s == 60.0


# tools/release_evidence.py


@_NOX2_UNDECODABLE_JSON
def test_release_evidence_index_the_decoder_cannot_read_is_unparsable(tmp_path: Path, payload: bytes) -> None:
    from tools.release_evidence import INDEX_FILENAME, ReleaseEvidenceError, _load_index

    _nox2_write(tmp_path / INDEX_FILENAME, payload)

    with pytest.raises(ReleaseEvidenceError) as refused:
        _load_index(tmp_path)

    assert refused.value.code == "evidence-index-unparsable"
    assert str(refused.value) == "release evidence index could not be parsed"


@pytest.mark.skipif(
    locale.getpreferredencoding(False).lower().replace("-", "") != "utf8",
    reason="subprocess text mode decodes the verifier output with the locale encoding",
)
def test_release_evidence_verifier_output_that_is_not_utf8_is_unparsable() -> None:
    import sys

    from tools.release_evidence_verifier import VerifierError, run_verifier

    command = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'[\\xff]')"]

    with pytest.raises(VerifierError) as refused:
        run_verifier(command)

    assert refused.value.code == "verifier-output-unparsable"


# tools/release_evidence_sbom.py


@pytest.mark.parametrize(
    "field",
    ["Requires-Dist: ???invalid", "Provides-Extra: !!!", "Version: not a version"],
    ids=["requirement", "extra", "version"],
)
def test_runtime_closure_refuses_a_wheel_metadata_field_it_cannot_parse(tmp_path: Path, field: str) -> None:
    from tools.release_evidence_sbom import RuntimeClosureError, wheel_metadata

    header = "Metadata-Version: 2.3\nName: raes\n"
    version = "" if field.startswith("Version:") else "Version: 1.2.3\n"
    wheel = tmp_path / "raes-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("raes-1.2.3.dist-info/METADATA", f"{header}{version}{field}\n")

    with pytest.raises(RuntimeClosureError) as refused:
        wheel_metadata(wheel)

    assert refused.value.code == "wheel-metadata-invalid"


# tools/check_pr_title.py


@_NOX2_UNDECODABLE_JSON
def test_pr_title_event_the_decoder_cannot_read_is_an_unreadable_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], payload: bytes
) -> None:
    from tools.check_pr_title import main

    event = _nox2_write(tmp_path / "event.json", payload)

    assert main(["--event-path", str(event)]) == 2
    error = capsys.readouterr().err
    assert "pr-title-guard: could not read event JSON from " in error
    assert "pr-title-guard: could not resolve a PR title to validate." in error
    assert _NOX2_SENTINEL not in error


@pytest.mark.parametrize(
    "event",
    [[{"pull_request": {"title": "feat: ok"}}], {"pull_request": ["feat: ok"]}, {"pull_request": "feat: ok"}],
    ids=["event-array", "pull-request-array", "pull-request-text"],
)
def test_pr_title_event_without_a_pull_request_object_has_no_title(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], event: object
) -> None:
    from tools.check_pr_title import main

    path = _nox2_write(tmp_path / "event.json", json.dumps(event))

    assert main(["--event-path", str(path)]) == 2
    error = capsys.readouterr().err
    assert "pr-title-guard: no pull_request.title in event payload." in error
    assert "pr-title-guard: could not resolve a PR title to validate." in error


@pytest.mark.parametrize("title", [5, True, ["feat: ok"], {"text": "feat: ok"}], ids=["number", "bool", "list", "map"])
def test_pr_title_that_is_not_text_is_an_empty_title(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], title: object
) -> None:
    from tools.check_pr_title import RULE_EMPTY, main, validate_pr_title

    path = _nox2_write(tmp_path / "event.json", json.dumps({"pull_request": {"title": title}}))

    assert main(["--event-path", str(path)]) == 1
    assert f"[{RULE_EMPTY}] PR title is empty." in capsys.readouterr().err
    assert [violation.rule_id for violation in validate_pr_title(title)] == [RULE_EMPTY]


def test_pr_title_commit_messages_that_are_not_utf8_are_unreadable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools.check_pr_title import main

    messages = _nox2_write(tmp_path / "commits.txt", b"fix: x\n\n\xff\n")

    assert main(["--title", "fix: a clean title", "--commit-messages-file", str(messages)]) == 2
    assert "pr-title-guard: could not read commit messages from " in capsys.readouterr().err


# tools/check_agent_guidance.py


@_NOX2_UNCONSTRUCTABLE_YAML
def test_agent_guidance_reports_an_unconstructable_profile_as_a_parse_failure(tmp_path: Path, document: str) -> None:
    from tools.check_agent_guidance import AGENT_GUIDANCE_RELATIVE_PATH, evaluate_agent_guidance

    _nox2_write(tmp_path / AGENT_GUIDANCE_RELATIVE_PATH, f"note: {_NOX2_SENTINEL}\n{document}")

    failures = evaluate_agent_guidance(tmp_path)

    assert [failure.rule_id for failure in failures] == ["agent-guidance-parse"]
    assert _NOX2_SENTINEL not in failures[0].message


def test_agent_guidance_reports_a_profile_that_is_not_utf8_as_a_parse_failure(tmp_path: Path) -> None:
    from tools.check_agent_guidance import AGENT_GUIDANCE_RELATIVE_PATH, evaluate_agent_guidance

    _nox2_write(tmp_path / AGENT_GUIDANCE_RELATIVE_PATH, b"profile: \xff\n")

    assert [failure.rule_id for failure in evaluate_agent_guidance(tmp_path)] == ["agent-guidance-parse"]


def test_agent_guidance_keeps_a_parser_defect_out_of_the_parse_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.check_agent_guidance as guidance

    _nox2_write(tmp_path / guidance.AGENT_GUIDANCE_RELATIVE_PATH, "profile: raes-agent-guidance\n")

    def defective(_text: str) -> object:
        raise TypeError(_NOX2_DEFECT)

    monkeypatch.setattr(guidance.yaml, "safe_load", defective)
    with pytest.raises(TypeError, match=_NOX2_DEFECT):
        guidance.evaluate_agent_guidance(tmp_path)


# tools/policy/repository_requirements.py


@pytest.mark.parametrize(
    "status",
    ["2024-13-01", _NOX2_LONG_INTEGER, "!!bool maybe", "!!timestamp later", '!!int ""', '!!float ""'],
    ids=[
        "impossible-date",
        "integer-beyond-digit-limit",
        "bad-explicit-bool",
        "bad-explicit-timestamp",
        "empty-tagged-integer",
        "empty-tagged-float",
    ],
)
def test_repository_requirement_with_an_unconstructable_status_is_unreadable_authority(
    tmp_path: Path, status: str
) -> None:
    from tools.policy.repository_requirements import RepositoryRequirementClient, RepositoryRequirementError

    _nox2_write(tmp_path / "docs/requirements/SEM-001/requirement.md", f"---\nid: SEM-001\nstatus: {status}\n---\n")

    client = RepositoryRequirementClient(tmp_path)
    with pytest.raises(RepositoryRequirementError) as refused:
        client.get_requirement("", "SEM-001")

    assert str(refused.value) == "Requirement authority cannot be read and validated."


def test_repository_requirement_keeps_a_record_defect_out_of_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.policy.repository_requirements as requirements

    _nox2_write(tmp_path / "docs/requirements/SEM-001/requirement.md", "---\nid: SEM-001\nstatus: ACTIVE\n---\n")

    def defective(_metadata: object, _uid: str) -> dict[str, object]:
        raise ValueError(_NOX2_DEFECT)

    monkeypatch.setattr(requirements, "_governed_requirement", defective)
    client = requirements.RepositoryRequirementClient(tmp_path)
    with pytest.raises(ValueError, match=_NOX2_DEFECT):
        client.get_requirement("", "SEM-001")


def test_repository_requirement_keeps_a_loader_defect_out_of_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.policy.repository_requirements as requirements

    _nox2_write(tmp_path / "docs/requirements/SEM-001/requirement.md", "---\nid: SEM-001\nstatus: ACTIVE\n---\n")

    def defective(_loader: object, _node: object, deep: bool = False) -> dict[object, object]:
        raise ValueError(_NOX2_DEFECT)

    monkeypatch.setattr(requirements._RequirementLoader, "construct_mapping", defective)
    client = requirements.RepositoryRequirementClient(tmp_path)
    with pytest.raises(ValueError, match=_NOX2_DEFECT):
        client.get_requirement("", "SEM-001")


# tools/policy/requirement_scope.py


def test_requirement_scope_branch_issue_number_beyond_the_digit_limit_is_refused(tmp_path: Path) -> None:
    from tools.policy.requirement_scope import RequirementScopeError, load_requirement_scope

    with pytest.raises(RequirementScopeError) as refused:
        load_requirement_scope(tmp_path, f"{_NOX2_LONG_INTEGER}-scope")

    assert str(refused.value) == "Requirement scope cannot be read and validated."


# tools/policy/requirement_governance.py


@_NOX2_UNDECODABLE_JSON
def test_ground_control_mcp_config_the_decoder_cannot_read_is_an_empty_mapping(tmp_path: Path, payload: bytes) -> None:
    from tools.policy.requirement_governance import _mcp_ground_control_env

    _nox2_write(tmp_path / ".mcp.json", payload)

    assert _mcp_ground_control_env(tmp_path) == {}


class _Nox2Response:
    def __init__(self, payload: bytes | BaseException) -> None:
        self._payload = payload

    def __enter__(self) -> _Nox2Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


@_NOX2_UNDECODABLE_JSON
def test_ground_control_response_the_decoder_cannot_read_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    import tools.policy.requirement_governance as governance

    monkeypatch.setattr(governance, "urlopen", lambda _request, *, timeout: _Nox2Response(payload))

    client = governance.GroundControlHttpClient("http://ground-control.invalid")
    with pytest.raises(governance.GroundControlUnavailable) as refused:
        client.get_requirement("project", "ASR-1")

    assert str(refused.value) == "malformed response"
    assert _NOX2_SENTINEL not in str(refused.value)


def test_ground_control_connection_that_breaks_during_the_response_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import http.client

    import tools.policy.requirement_governance as governance

    def broken(_request: object, *, timeout: float) -> _Nox2Response:
        raise http.client.RemoteDisconnected(_NOX2_SENTINEL)

    client = governance.GroundControlHttpClient("http://ground-control.invalid")
    monkeypatch.setattr(governance, "urlopen", broken)
    with pytest.raises(governance.GroundControlUnavailable) as disconnected:
        client.get_requirement("project", "ASR-1")
    monkeypatch.setattr(
        governance, "urlopen", lambda _request, *, timeout: _Nox2Response(ConnectionResetError(_NOX2_SENTINEL))
    )
    with pytest.raises(governance.GroundControlUnavailable) as reset:
        client.get_requirement("project", "ASR-1")

    assert str(disconnected.value) == "connection failed (RemoteDisconnected)"
    assert str(reset.value) == "connection failed (ConnectionResetError)"


def test_ground_control_response_defect_is_not_reported_as_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.policy.requirement_governance as governance

    monkeypatch.setattr(governance, "urlopen", lambda _request, *, timeout: _Nox2Response(ValueError(_NOX2_DEFECT)))

    client = governance.GroundControlHttpClient("http://ground-control.invalid")
    with pytest.raises(ValueError, match=_NOX2_DEFECT):
        client.get_requirement("project", "ASR-1")


# tools/check_identity_cutover.py


@pytest.mark.parametrize(
    ("section", "class_field", "extra"),
    [
        ("records", "record_class", {}),
        ("operational_bindings", "binding_class", {}),
        ("generated_history_records", "record_class", {"classified_suffix_bytes": 1}),
    ],
)
@pytest.mark.parametrize("value", [[], {"class": "accepted-adr"}], ids=["list", "map"])
def test_identity_cutover_record_with_an_unhashable_class_is_a_manifest_failure(
    tmp_path: Path, section: str, class_field: str, extra: dict[str, object], value: object
) -> None:
    import tools.check_identity_cutover as cutover

    entry = {
        "path": "docs/history.md",
        class_field: value,
        "rationale": "retained history",
        "occurrences": 1,
        "content_sha256": "0" * 64,
        **extra,
    }
    manifest = {
        "schema_version": cutover.MANIFEST_SCHEMA,
        "hash_algorithm": "sha256",
        "records": [],
        "operational_bindings": [],
        "generated_history_records": [],
        section: [entry],
    }
    _nox2_write(tmp_path / cutover.MANIFEST_PATH, json.dumps(manifest))

    records, bindings, generated, failures = cutover._load_historical_records(tmp_path)

    assert (records, bindings, generated) == ({}, {}, {})
    assert [failure.rule_id for failure in failures] == [cutover.RULE_MANIFEST]
    assert failures[0].message.startswith(f"{section}[0].{class_field} must be one of ")


# tools/policy/repo_policy.py


def test_oversized_source_check_counts_the_lines_of_a_file_that_is_not_utf8(tmp_path: Path) -> None:
    from tools.policy.repo_policy import _file_line_count

    undecodable = _nox2_write(tmp_path / "legacy.py", b"a = 1\n# \xff\nb = 2")
    mixed_breaks = _nox2_write(tmp_path / "mixed.py", "a = 1\r\nb = 2\rc = 3\n d = 4\n")

    assert _file_line_count(undecodable) == 3
    assert _file_line_count(mixed_breaks) == 4


@pytest.mark.parametrize(
    "document",
    [
        "generated: 2024-01-01\n",
        "keys: {1: one, two: 2}\n",
        "cycle: &loop [*loop]\n",
        "tags: !!set {first: null}\n",
        "blob: !!binary aGk=\n",
    ],
    ids=["timestamp", "mixed-key-types", "recursive-alias", "set", "binary"],
)
def test_repo_policy_reports_a_policy_without_a_json_form_as_malformed(tmp_path: Path, document: str) -> None:
    from tools.policy.repo_policy import _load_policy_guarded

    _nox2_write(tmp_path / "tools/policy/adr_policy.yaml", f"note: {_NOX2_SENTINEL}\n{document}")

    policy, failures = _load_policy_guarded(tmp_path)

    assert policy is None
    assert [failure.rule_id for failure in failures] == ["policy-config-malformed"]
    assert failures[0].message == "tools/policy/adr_policy.yaml must contain only JSON data"
    assert _NOX2_SENTINEL not in failures[0].message


def test_repo_policy_refuses_a_policy_without_a_json_form_before_the_structural_runner(tmp_path: Path) -> None:
    from tools.policy.repo_policy import evaluate_repo_policy

    _nox2_write(tmp_path / "tools/policy/adr_policy.yaml", "generated: 2024-01-01\n")

    def structural_runner(document: dict) -> list:
        # The conftest runner serializes its input in exactly this way.
        json.dumps(document, indent=2, sort_keys=True)
        raise AssertionError("a policy without a JSON form must not reach the structural runner")

    failures = evaluate_repo_policy(tmp_path, ["tools/example.py"], structural_runner=structural_runner)

    assert [failure.rule_id for failure in failures] == ["policy-config-malformed"]


def test_repo_policy_keeps_a_policy_that_has_a_json_form(tmp_path: Path) -> None:
    from tools.policy.repo_policy import _load_policy_guarded

    _nox2_write(
        tmp_path / "tools/policy/adr_policy.yaml", "a: [1, x, {b: null}]\nc: 1.5\nd: true\nshared: &s [1]\nu: *s\n"
    )

    policy, failures = _load_policy_guarded(tmp_path)

    assert failures == []
    assert policy == {"a": [1, "x", {"b": None}], "c": 1.5, "d": True, "shared": [1], "u": [1]}


def test_repo_policy_and_adr_gate_report_an_empty_tagged_number_as_malformed(tmp_path: Path) -> None:
    import tools.check_adr_immutability as adr_gate
    from tools.policy.repo_policy import _load_policy_guarded

    _nox2_write(tmp_path / "tools/policy/adr_policy.yaml", 'value: !!int ""\n')
    _nox2_write(tmp_path / adr_gate.MANIFEST_PATH, 'hash_algorithm: sha256\nadrs: [{id: ADR-001, pin: !!float ""}]\n')

    policy, failures = _load_policy_guarded(tmp_path)

    assert policy is None
    assert [failure.rule_id for failure in failures] == ["policy-config-malformed"]
    assert [failure.rule_id for failure in adr_gate.evaluate_adr_immutability(tmp_path)] == [adr_gate.RULE_MALFORMED]


_NOX2_UNPARSEABLE_PYTHON = pytest.mark.parametrize(
    "source",
    [b"def broken(:\n", b"text = '\xff'\n", "+".join(["1"] * 100_000).encode(), b"-" * 100_000 + b"1"],
    ids=["syntax-error", "not-utf8", "nesting-beyond-the-recursion-limit", "nesting-beyond-the-parser-stack"],
)


@_NOX2_UNPARSEABLE_PYTHON
def test_repo_policy_layering_check_refuses_a_changed_file_it_cannot_parse(tmp_path: Path, source: bytes) -> None:
    from raes_contracts.errors import InvalidInputError
    from tools.policy.repo_policy import _check_layering

    _nox2_write(tmp_path / "pkg/module.py", source)
    rules = [{"id": "no-tools", "scope_root": "pkg", "forbidden_top_level": "tools"}]

    with pytest.raises(InvalidInputError) as refused:
        _check_layering(tmp_path, rules, ["pkg/module.py"])

    assert "pkg/module.py" in str(refused.value)


@_NOX2_UNPARSEABLE_PYTHON
def test_repo_policy_module_boundary_check_refuses_a_changed_file_it_cannot_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: bytes
) -> None:
    import tools.policy.repo_policy as repo_policy
    from raes_contracts.errors import InvalidInputError

    _nox2_write(tmp_path / "pkg/module.py", source)
    rule = {"id": "pkg", "root": "pkg", "allowed_top_level_imports": []}
    monkeypatch.setattr(repo_policy, "_validate_module_boundary_config", lambda _root, _config: ([rule], []))

    with pytest.raises(InvalidInputError) as refused:
        repo_policy._check_module_boundaries(tmp_path, {}, ["pkg/module.py"], check_set="file-local")

    assert "pkg/module.py" in str(refused.value)


# tools/policy/requirement_governance.py: Ground Control record shapes


@pytest.mark.parametrize(
    "payload",
    [
        b"[]",
        b"{}",
        b'{"id": "req-1", "uid": "ASR-1", "status": ["ACTIVE"]}',
        b'{"uid": "ASR-1", "status": "ACTIVE"}',
        b'{"id": "req-1", "status": "ACTIVE"}',
    ],
    ids=["list", "empty", "status-not-text", "no-id", "no-uid"],
)
def test_ground_control_requirement_record_of_the_wrong_shape_is_a_malformed_response(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    import tools.policy.requirement_governance as governance

    monkeypatch.setattr(governance, "urlopen", lambda _request, *, timeout: _Nox2Response(payload))

    client = governance.GroundControlHttpClient("http://ground-control.invalid")
    with pytest.raises(governance.GroundControlUnavailable) as refused:
        client.get_requirement("project", "ASR-1")

    assert str(refused.value) == "malformed response"


@pytest.mark.parametrize(
    "payload",
    [b"{}", b'["link"]', b'[{"artifact_identifier": ["code.py"]}]', b'[{"linkType": 7}]'],
    ids=["mapping", "link-not-object", "identifier-not-text", "type-not-text"],
)
def test_ground_control_traceability_of_the_wrong_shape_is_a_malformed_response(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    import tools.policy.requirement_governance as governance

    monkeypatch.setattr(governance, "urlopen", lambda _request, *, timeout: _Nox2Response(payload))

    client = governance.GroundControlHttpClient("http://ground-control.invalid")
    with pytest.raises(governance.GroundControlUnavailable) as refused:
        client.get_traceability("req-1")

    assert str(refused.value) == "malformed response"


def test_ground_control_keeps_well_formed_records(monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.policy.requirement_governance as governance

    record = b'{"id": "req-1", "uid": "ASR-1", "status": "ACTIVE", "title": "t"}'
    links = b'[{"link_type": "IMPLEMENTS", "artifact_type": "CODE_FILE", "artifact_identifier": "a.py", "x": 1}]'
    client = governance.GroundControlHttpClient("http://ground-control.invalid")
    monkeypatch.setattr(governance, "urlopen", lambda _request, *, timeout: _Nox2Response(record))
    assert client.get_requirement("project", "ASR-1") == json.loads(record)
    monkeypatch.setattr(governance, "urlopen", lambda _request, *, timeout: _Nox2Response(links))
    assert client.get_traceability("req-1") == json.loads(links)


def test_requirement_gate_reports_a_malformed_ground_control_record_as_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import tools.check_requirement_governance as gate
    import tools.policy.requirement_governance as governance

    monkeypatch.setattr(gate, "resolve_base_url", lambda _root: "http://ground-control.invalid")
    monkeypatch.setattr(gate, "resolve_token", lambda _root: None)
    monkeypatch.setattr(
        governance,
        "urlopen",
        lambda _request, *, timeout: _Nox2Response(b'{"id": "r", "uid": "API-412", "status": ["ACTIVE"]}'),
    )

    status = gate.evaluate_against_ground_control([], "API-412", require_governance=True, as_json=False)

    assert status == 1
    assert "ground-control-unavailable" in capsys.readouterr().err


# tools/policy/requirement_governance.py: requirement order policy shapes

_NOX2_VALID_ORDER = {
    "project": "example",
    "phases": [
        {"id": "foundation", "requirements": ["EXP-701"], "patterns": ["^EXP-"]},
        {"id": "evidence", "requirements": ["EXP-708"], "blocked_until": ["foundation"], "manual_release": True},
    ],
    "ownership": {"evidence": ["implementations/python/packages"]},
    "traceability": {"required_code_roots": ["implementations/python/packages"], "required_test_roots": []},
}


def _nox2_order(**changes: object) -> dict[str, object]:
    order = json.loads(json.dumps(_NOX2_VALID_ORDER))
    for key, value in changes.items():
        if value is None:
            order.pop(key)
        else:
            order[key] = value
    return order


@pytest.mark.parametrize(
    "order",
    [
        ["project"],
        _nox2_order(project=None),
        _nox2_order(project=7),
        _nox2_order(phases={"id": "foundation"}),
        _nox2_order(phases=[{"requirements": ["EXP-701"]}]),
        _nox2_order(phases=[{"id": "foundation", "requirements": 7}]),
        _nox2_order(phases=[{"id": "foundation", "patterns": ["(unclosed"]}]),
        _nox2_order(phases=[{"id": "foundation", "patterns": [7]}]),
        _nox2_order(phases=[{"id": "evidence", "blocked_until": ["missing"]}]),
        _nox2_order(ownership=["evidence"]),
        _nox2_order(ownership={"evidence": [7]}),
        _nox2_order(traceability=None),
        _nox2_order(traceability={"required_code_roots": []}),
    ],
    ids=[
        "root-list",
        "project-missing",
        "project-not-text",
        "phases-mapping",
        "phase-without-id",
        "requirements-not-list",
        "pattern-not-regex",
        "pattern-not-text",
        "unknown-predecessor",
        "ownership-list",
        "ownership-root-not-text",
        "traceability-missing",
        "traceability-roots-missing",
    ],
)
def test_requirement_order_policy_of_the_wrong_shape_is_invalid_input(tmp_path: Path, order: object) -> None:
    from raes_contracts.errors import InvalidInputError
    from tools.policy.requirement_governance import load_policy

    _nox2_write(tmp_path / "tools/policy/requirement_order.yaml", json.dumps(order))

    with pytest.raises(InvalidInputError) as refused:
        load_policy(tmp_path)

    assert str(refused.value).startswith("tools/policy/requirement_order.yaml ")


def test_requirement_order_policy_keeps_valid_policies(tmp_path: Path) -> None:
    from tools.policy.requirement_governance import load_policy

    _nox2_write(tmp_path / "tools/policy/requirement_order.yaml", json.dumps(_NOX2_VALID_ORDER))

    assert load_policy(tmp_path) == _NOX2_VALID_ORDER
    assert load_policy(Path(__file__).resolve().parents[3])["project"]


def test_requirement_gate_reports_an_unknown_predecessor_phase_as_a_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import tools.check_requirement_governance as gate

    order = _nox2_order(
        requirement_source="repository",
        phases=[{"id": "evidence", "requirements": ["EXP-708"], "blocked_until": ["missing"]}],
    )
    _nox2_write(tmp_path / "tools/policy/requirement_order.yaml", json.dumps(order))
    _nox2_write(tmp_path / "docs/requirements/EXP-708/requirement.md", "---\nid: EXP-708\nstatus: ACTIVE\n---\n")
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate, "current_branch", lambda _root: None)
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setattr(
        gate.sys,
        "argv",
        ["check_requirement_governance.py", "--requirement-uid", "EXP-708", "implementations/python/packages/x.py"],
    )

    assert gate.main() == 1
    assert "requirement-governance: tools/policy/requirement_order.yaml " in capsys.readouterr().err


# tools/release_evidence_sbom.py: wheel archive reads


def _nox2_wheel(tmp_path: Path, *, compress_type: int = zipfile.ZIP_DEFLATED) -> tuple[Path, bytearray]:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("raes-1.2.3.dist-info/METADATA")
        info.compress_type = compress_type
        archive.writestr(info, b"Metadata-Version: 2.3\nName: raes\nVersion: 1.2.3\n" * 20)
    return tmp_path / "raes-1.2.3-py3-none-any.whl", bytearray(buffer.getvalue())


def _nox2_member_data_start(data: bytearray) -> int:
    import struct

    local = data.find(b"PK\x03\x04")
    name_length, extra_length = struct.unpack_from("<HH", data, local + 26)
    return local + 30 + name_length + extra_length


def _nox2_encrypted(data: bytearray) -> bytearray:
    import struct

    local, central = data.find(b"PK\x03\x04"), data.find(b"PK\x01\x02")
    struct.pack_into("<H", data, local + 6, struct.unpack_from("<H", data, local + 6)[0] | 1)
    struct.pack_into("<H", data, central + 8, struct.unpack_from("<H", data, central + 8)[0] | 1)
    return data


def _nox2_unsupported_method(data: bytearray) -> bytearray:
    import struct

    struct.pack_into("<H", data, data.find(b"PK\x03\x04") + 8, 99)
    struct.pack_into("<H", data, data.find(b"PK\x01\x02") + 10, 99)
    return data


def _nox2_corrupted_deflate(data: bytearray) -> bytearray:
    # Damage the first deflate block header, so the decompressor itself fails.
    start = _nox2_member_data_start(data)
    for index in range(start, start + 8):
        data[index] ^= 0xFF
    return data


def _nox2_corrupted_lzma(data: bytearray) -> bytearray:
    # Keep the four-byte zip LZMA header and damage the compressed stream after it.
    start = _nox2_member_data_start(data)
    for index in range(start + 4, start + 20):
        data[index] ^= 0xFF
    return data


@pytest.mark.parametrize(
    ("compress_type", "damage"),
    [
        (zipfile.ZIP_STORED, _nox2_encrypted),
        (zipfile.ZIP_STORED, _nox2_unsupported_method),
        (zipfile.ZIP_DEFLATED, _nox2_corrupted_deflate),
        (zipfile.ZIP_LZMA, _nox2_corrupted_lzma),
    ],
    ids=["encrypted-member", "unsupported-compression", "corrupt-deflate", "corrupt-lzma"],
)
def test_runtime_closure_refuses_a_wheel_member_it_cannot_read(tmp_path: Path, compress_type: int, damage) -> None:
    from tools.release_evidence_sbom import RuntimeClosureError, wheel_metadata

    wheel, data = _nox2_wheel(tmp_path, compress_type=compress_type)
    wheel.write_bytes(bytes(damage(data)))

    with pytest.raises(RuntimeClosureError) as refused:
        wheel_metadata(wheel)

    assert refused.value.code == "wheel-metadata-unreadable"


# tools/check_adr_immutability.py: base revisions that are not UTF-8


def test_adr_pin_gate_compares_a_base_revision_that_is_not_utf8(tmp_path: Path) -> None:
    import subprocess

    import tools.check_adr_immutability as adr_gate

    relative = "docs/decisions/adrs/adr-001-example.md"
    head = "# ADR-001: Example 001\n\n## Status\n\naccepted\n\n## Date\n\n2026-04-05\n\n## Context\n\nBody.\n"
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    _nox2_write(tmp_path / relative, head.replace("Body.", "Body \xff.").encode("latin-1"))
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    base_tree = subprocess.run(
        ["git", "write-tree"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    _nox2_write(tmp_path / relative, head)
    manifest = {
        "hash_algorithm": "sha256",
        "adrs": [{"id": "ADR-001", "path": relative, "pin": adr_gate.content_hash(head)}],
    }
    _nox2_write(tmp_path / adr_gate.MANIFEST_PATH, json.dumps(manifest))

    failures = adr_gate.evaluate_adr_immutability(tmp_path, base_rev=base_tree)

    assert [failure.rule_id for failure in failures] == [adr_gate.RULE_AMENDMENT_UNRECORDED]


@pytest.mark.parametrize("revision", ["", "--output=/tmp/adr-gate-probe"])
def test_adr_pin_gate_refuses_a_base_revision_that_git_reads_as_an_option(revision: str) -> None:
    import tools.check_adr_immutability as adr_gate

    with pytest.raises(SystemExit) as refused:
        adr_gate.parse_args([f"--base-rev={revision}"])

    assert refused.value.code == 2


def test_adr_pin_gate_git_reader_refuses_a_reference_that_starts_with_a_dash(tmp_path: Path) -> None:
    import tools.check_adr_immutability as adr_gate
    from raes_contracts.errors import InvalidInputError

    with pytest.raises(InvalidInputError, match="must not start with '-'"):
        adr_gate._git_show(tmp_path, "--output=/tmp/adr-gate-probe:docs/a.md")


# tools/nox_support/runner.py and tools/pytest_shard.py


@pytest.fixture
def _nox2_runner(monkeypatch: pytest.MonkeyPatch):
    import importlib
    import sys
    from types import SimpleNamespace

    monkeypatch.setitem(sys.modules, "nox", SimpleNamespace(Session=object))
    for module_name in ("tools.nox_support.runner",):
        monkeypatch.setitem(sys.modules, module_name, None)
        monkeypatch.delitem(sys.modules, module_name)
    return importlib.import_module("tools.nox_support.runner")


@_NOX2_UNDECODABLE_JSON
def test_line_coverage_gate_reports_a_report_the_decoder_cannot_read(
    tmp_path: Path, _nox2_runner, payload: bytes
) -> None:
    from raes_contracts.errors import OperationalError

    report = _nox2_write(tmp_path / "coverage.json", payload)

    with pytest.raises(OperationalError, match="could not read line coverage totals"):
        _nox2_runner._enforce_line_coverage(report)


@_NOX2_UNDECODABLE_JSON
def test_shard_manifest_the_decoder_cannot_read_is_a_manifest_failure(tmp_path: Path, payload: bytes) -> None:
    from tools.pytest_shard import ShardManifestError, read_manifest

    manifest = _nox2_write(tmp_path / "shard-0.json", payload)

    with pytest.raises(ShardManifestError, match="could not read shard manifest"):
        read_manifest(manifest)


# Research evidence tools: input crashes that existed before the branch.

_RESEARCH2_REPO_ROOT = Path(__file__).resolve().parents[3]
_RESEARCH2_LIVE_DIGEST = "live"


def test_research2_inventory_refuses_an_unhashable_revision(tmp_path):
    from tools.research_evidence import validate_inventory

    records = [("docs/research/formal-semantic-validation/bundles/a.json", {"revision": []})]
    with pytest.raises(InvalidInputError, match="invalid evidence manifest revision"):
        validate_inventory(tmp_path, "formal-semantic-validation", records)


def test_research2_publication_receipt_refuses_an_unhashable_capture_path(tmp_path):
    from tools.research_capture import _validate_publication_receipt

    receipt = {"revision": "1.0.0", "capture_path": [], "capture_sha256": "0" * 64}
    with pytest.raises(InvalidInputError, match="invalid evidence publication receipt"):
        _validate_publication_receipt(tmp_path, tmp_path / "v1.json", receipt, [], set(), set())


@pytest.mark.parametrize("path_value", [7, [], {"path": "x"}])
def test_research2_capture_template_refuses_a_document_path_that_is_not_text(tmp_path, path_value):
    from tools.research_capture import _pinned_capture_documents

    with pytest.raises(InvalidInputError, match="capture document path is unsafe or oversized"):
        _pinned_capture_documents(tmp_path, {"protocol_path": path_value, "protocol_sha256": "0" * 64})


def test_research2_capture_template_refuses_a_document_without_its_pin(tmp_path):
    from tools.research_capture import _pinned_capture_documents

    (tmp_path / "protocol.json").write_text("{}", encoding="utf-8")
    with pytest.raises(InvalidInputError, match="capture document pin is stale"):
        _pinned_capture_documents(tmp_path, {"protocol_path": "protocol.json"})


def _research2_live_capture(tmp_path: Path, monkeypatch, name: str, pins: dict[str, object]) -> tuple[str, dict]:
    from tools import research_evidence

    monkeypatch.setattr(research_evidence, "implementation_digest", lambda _root: _RESEARCH2_LIVE_DIGEST)
    snapshot = {
        "source_state": {"profile": research_evidence.SOURCE_PROFILE, "implementation_digest": _RESEARCH2_LIVE_DIGEST},
        "captured_at": "2026-01-01T00:00:00+00:00",
    }
    (tmp_path / f"{name}.json").write_text(json.dumps(snapshot), encoding="utf-8")
    return name, {"revision": "capture-" + name * 64, "snapshot_path": f"{name}.json", **pins}


def test_research2_release_selection_tolerates_unhashable_document_pins(tmp_path, monkeypatch):
    from tools.research_evidence import current_release_path

    record = _research2_live_capture(tmp_path, monkeypatch, "a", {"snapshot_sha256": [], "analysis_sha256": {}})

    # The selection does not judge the pins; the release validators refuse malformed pins afterwards.
    assert current_release_path([record], tmp_path) == "a"


def test_research2_release_selection_keeps_ambiguity_for_different_pins(tmp_path, monkeypatch):
    from tools.research_evidence import current_release_path

    records = [
        _research2_live_capture(tmp_path, monkeypatch, "a", {"snapshot_sha256": [], "analysis_sha256": "a" * 64}),
        _research2_live_capture(tmp_path, monkeypatch, "b", {"snapshot_sha256": "b" * 64, "analysis_sha256": []}),
    ]
    with pytest.raises(InvalidInputError, match="ambiguous"):
        current_release_path(records, tmp_path)


_RESEARCH2_FULFILLMENT_DOCUMENTS = {
    "impossible-date": "entries:\n  - delivered_artifacts:\n      - path: 2026-02-30\n",
    "deep-nesting": "entries: " + "[" * 3000 + "]" * 3000 + "\n",
}


@pytest.mark.parametrize(
    "document", list(_RESEARCH2_FULFILLMENT_DOCUMENTS.values()), ids=list(_RESEARCH2_FULFILLMENT_DOCUMENTS)
)
def test_research2_unconstructable_fulfillment_map_is_a_catalog_failure(tmp_path, document):
    from tools.schema_coverage._evidence import formal_artifact_paths
    from tools.schema_coverage._keys import ASSURANCE_FULFILLMENT_RELATIVE_PATH, CATALOG_RULE_ID

    target = tmp_path / ASSURANCE_FULFILLMENT_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    target.write_text(document, encoding="utf-8")
    paths, failures = formal_artifact_paths(tmp_path)

    assert paths == frozenset()
    assert [(failure.rule_id, failure.message) for failure in failures] == [
        (CATALOG_RULE_ID, "assurance fulfillment map is not readable valid YAML")
    ]


@pytest.mark.parametrize(
    "document",
    ["- a\n- b\n", "just text\n", "entries:\n  - delivered_artifacts: 7\n"],
    ids=["list-document", "scalar-document", "scalar-artifacts"],
)
def test_research2_fulfillment_map_without_its_structure_delivers_no_artifacts(tmp_path, document):
    from tools.schema_coverage._evidence import formal_artifact_paths
    from tools.schema_coverage._keys import ASSURANCE_FULFILLMENT_RELATIVE_PATH

    target = tmp_path / ASSURANCE_FULFILLMENT_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    target.write_text(document, encoding="utf-8")

    assert formal_artifact_paths(tmp_path) == (frozenset(), [])


def _research2_declaration(tmp_path: Path, source: dict[str, object]) -> dict[str, object]:
    carrier = tmp_path / "contracts" / "carrier.json"
    carrier.parent.mkdir(parents=True, exist_ok=True)
    carrier.write_text(json.dumps({"schema_version": ["list"], "node": {}}), encoding="utf-8")
    return {
        "rationale": "an authored rationale that is long enough",
        "sources": [{"path": "contracts/carrier.json", "supports": "the published contract shape", **source}],
    }


def test_research2_embedded_source_with_an_unhashable_pointer_is_a_declaration_failure(tmp_path):
    from tools.schema_coverage._declaration import evaluate_declaration
    from tools.schema_coverage._keys import DECLARATION_RULE_ID

    declaration = _research2_declaration(tmp_path, {"kind": "embedded", "pointer": ["/node"]})
    qualified, failures = evaluate_declaration(tmp_path, declaration, "contract-v1", "contracts/schemas/x.json")

    assert qualified is False
    assert [(failure.rule_id, failure.message) for failure in failures] == [
        (
            DECLARATION_RULE_ID,
            "embedded source needs an RFC 6901 pointer into the carrier: contracts/carrier.json",
        )
    ]


def test_research2_fixture_with_an_unhashable_schema_version_carries_no_contract_payload(tmp_path):
    from tools.schema_coverage._declaration import evaluate_declaration
    from tools.schema_coverage._keys import DECLARATION_RULE_ID

    declaration = _research2_declaration(tmp_path, {"kind": "fixture"})
    qualified, failures = evaluate_declaration(tmp_path, declaration, "contract-v1", "contracts/schemas/x.json")

    assert qualified is False
    assert [(failure.rule_id, failure.message) for failure in failures] == [
        (DECLARATION_RULE_ID, "fixture source does not carry a payload of this contract: contracts/carrier.json")
    ]


@pytest.mark.parametrize("locator", ["https://[::1", "https://[not-an-address]/x"])
def test_research2_malformed_https_locator_is_an_invalid_locator(locator):
    from tools.specification_coverage._primitives import _validate_https_locator

    assert _validate_https_locator(locator) is False
    assert _validate_https_locator("https://example.org/spec?draft=1") is True


def test_research2_coverage_source_with_a_malformed_locator_reports_the_locator_failure(tmp_path):
    from tools.specification_coverage._protocol import _source_entry_failures

    failures = []
    source = {"source_id": "s", "stratum_id": "a", "locator": "https://[::1", "content_sha256": "0" * 64}
    _source_entry_failures(tmp_path, source, {"a"}, failures, "protocol.json")

    assert ("specification-coverage-source-locator", "protocol.json") in {
        (failure.rule_id, failure.path) for failure in failures
    }


def _research2_set(document: object, pointer: tuple[object, ...], value: object) -> None:
    target = document
    for part in pointer[:-1]:
        target = target[part]
    target[pointer[-1]] = value


_RESEARCH2_FORMAL_HISTORICAL = (
    "docs/research/formal-semantic-validation/captures/"
    "capture-ff4efffbda81608386c7643058a187a602cbcbf6fda0a5826f5adb30ddd37464/manifest.json"
)
_RESEARCH2_FORMAL_LEGACY = "docs/research/formal-semantic-validation/bundles/satisfiability-v1.json"
# Each authored value raised TypeError before the fix; each now gets the existing refusal.
_RESEARCH2_FORMAL_CASES = [
    ("analysis", ("claim_results", 0, "claim_class_id"), [], "formal-validation-analysis-result-join"),
    ("analysis", ("claim", "evidence_artifacts"), 7, "formal-validation-claim-record"),
    ("snapshot", ("observations", 0, "case_id"), [], "formal-validation-observation-coverage"),
    ("corpus", ("cases", 0, "case_id"), [], "formal-validation-case-ids"),
    ("protocol", ("claim_classes", 0, "claim_class_id"), [], "formal-validation-claim-coverage"),
    ("corpus", ("cases", 0, "claim_class_id"), [], "formal-validation-case-claim"),
    ("corpus", ("cases", 0, "polarity"), [], "formal-validation-case-polarity"),
    ("corpus", ("cases", 0, "replay_mode"), [], "formal-validation-replay-mode"),
    ("protocol", ("participant_obligations",), 7, "formal-validation-participant-coverage"),
    ("protocol", ("revision",), [], "formal-validation-protocol-scope"),
    ("protocol", ("evidence_status_values",), 7, "formal-validation-evidence-status"),
    ("protocol", ("claim_classes",), 7, "formal-validation-claim-coverage"),
    ("protocol", ("claim_classes", 0, "expected_evidence_status"), [], "formal-validation-evidence-status"),
    ("manifest", ("artifacts", 0, "kind"), [], "formal-validation-production-evidence-join"),
    ("snapshot", ("commands", 0, "command_id"), [], "formal-validation-commands"),
    ("manifest", ("artifacts",), 7, "formal-validation-release-artifacts"),
    ("protocol", ("participant_obligations", 0, "obligation_id"), [], "formal-validation-participant-coverage"),
]
_RESEARCH2_FORMAL_LEGACY_CASES = [
    ("manifest", ("artifacts", 0, "kind"), [], "formal-validation-release-artifacts"),
    (
        "snapshot",
        ("participant_observations", 0, "obligation_id"),
        [],
        "formal-validation-participant-observation-join",
    ),
    ("snapshot", ("observations", 0, "case_id"), [], "formal-validation-observation-coverage"),
    ("protocol", ("participant_obligations", 0, "obligation_id"), [], "formal-validation-participant-coverage"),
]


@pytest.fixture(scope="module")
def _research2_formal_releases():
    from tools.formal_semantic_validation._loading import load_release_bundles

    return {release.manifest_path: release for release in load_release_bundles(_RESEARCH2_REPO_ROOT)}


@pytest.mark.parametrize(
    ("release_path", "document", "pointer", "value", "rule_id"),
    [(_RESEARCH2_FORMAL_HISTORICAL, *case) for case in _RESEARCH2_FORMAL_CASES]
    + [(_RESEARCH2_FORMAL_LEGACY, *case) for case in _RESEARCH2_FORMAL_LEGACY_CASES],
    ids=[f"integrated-{case[0]}-{'-'.join(map(str, case[1]))}" for case in _RESEARCH2_FORMAL_CASES]
    + [f"legacy-{case[0]}-{'-'.join(map(str, case[1]))}" for case in _RESEARCH2_FORMAL_LEGACY_CASES],
)
def test_research2_formal_release_refuses_a_malformed_authored_value(
    _research2_formal_releases, release_path, document, pointer, value, rule_id
):
    import copy

    from tools.formal_semantic_validation import _releases
    from tools.formal_semantic_validation._types import EvidenceRelease

    release = _research2_formal_releases[release_path]
    documents = {
        name: copy.deepcopy(getattr(release, name))
        for name in ("manifest", "protocol", "corpus", "snapshot", "analysis")
    }
    _research2_set(documents[document], pointer, value)
    # Select another release, so the historical checks run without a live-source selection.
    token = _releases._SELECTED_RELEASE.set((_RESEARCH2_REPO_ROOT, "another-release"))
    try:
        failures = _releases.validate_release_bundle(
            _RESEARCH2_REPO_ROOT, EvidenceRelease(manifest_path=release_path, **documents)
        )
    finally:
        _releases._SELECTED_RELEASE.reset(token)

    assert rule_id in {failure.rule_id for failure in failures}


_RESEARCH2_COVERAGE_HISTORICAL = (
    "docs/research/specification-coverage/captures/"
    "capture-ff764524455bafe2cd35c7d71a76e379f9b0f7a10810bb691a72880010a5f2b1/manifest.json"
)
# Each authored value raised TypeError or UnicodeEncodeError before the fix.
_RESEARCH2_COVERAGE_CASES = [
    ("snapshot", ("concept_results", 0, "backend_vocabulary_occurrences"), 7, "specification-coverage-backend-leakage"),
    ("protocol", ("requests",), 7, "specification-coverage-requests"),
    ("protocol", ("concepts",), 7, "specification-coverage-concepts"),
    ("snapshot", ("concept_results", 0, "stage_results"), 7, "specification-coverage-stage-coverage"),
    ("protocol", ("requests", 0, "concept_ids"), 7, "specification-coverage-concepts"),
    ("snapshot", ("implementation_surfaces", 0, "surface_id"), [], "specification-coverage-implementation-identity"),
    ("snapshot", ("implementation_surfaces", 0, "path"), [], "specification-coverage-implementation-identity"),
    ("protocol", ("sources", 0, "stratum_id"), [], "specification-coverage-sources"),
    ("protocol", ("coverage_strata", 0, "stratum_id"), [], "specification-coverage-strata"),
    ("protocol", ("requests", 0, "source_refs", 0), [], "specification-coverage-requests"),
    ("protocol", ("requests", 0, "stratum_id"), [], "specification-coverage-requests"),
    ("protocol", ("concepts", 0, "artifact_stage_ids", 0), [], "specification-coverage-concepts"),
    ("protocol", ("requests", 0, "concept_ids", 0), [], "specification-coverage-concepts"),
    ("protocol", ("concepts", 0, "request_id"), [], "specification-coverage-concepts"),
    ("protocol", ("concepts", 0, "expected_carrier_id"), [], "specification-coverage-concepts"),
    ("protocol", ("concepts", 0, "expected_classification"), [], "specification-coverage-classification-boundary"),
    ("protocol", ("carriers", 0, "kind"), [], "specification-coverage-classification-boundary"),
    ("snapshot", ("concept_results", 0, "stage_results", 0, "outcome"), [], "specification-coverage-stage-coverage"),
    (
        "snapshot",
        ("concept_results", 0, "stage_results", 0, "validation_strength"),
        [],
        "specification-coverage-stage-coverage",
    ),
    ("snapshot", ("concept_results", 0, "stage_results", 0, "stage_id"), [], "specification-coverage-stage-coverage"),
    ("protocol", ("carriers", 0, "artifact_id"), [], "specification-coverage-carriers"),
    ("protocol", ("carriers",), 7, "specification-coverage-carriers"),
    ("protocol", ("execution_rules", "stage_outcomes"), 7, "specification-coverage-stage-coverage"),
    ("protocol", ("execution_rules", "validation_strength_values"), 7, "specification-coverage-stage-coverage"),
    ("snapshot", ("concept_results", 0, "concept_id"), [], "specification-coverage-concept-results"),
    ("snapshot", ("concept_results", 0, "classification"), [], "specification-coverage-classifications"),
    ("snapshot", ("artifacts", 0, "artifact_id"), "\ud800", "specification-coverage-analysis-join"),
]


@pytest.fixture(scope="module")
def _research2_coverage_bundle():
    import tools.check_specification_coverage as coverage

    manifest = dict(coverage._load_bundle_index(_RESEARCH2_REPO_ROOT))[_RESEARCH2_COVERAGE_HISTORICAL]
    return coverage._load_bundle_record(_RESEARCH2_REPO_ROOT, _RESEARCH2_COVERAGE_HISTORICAL, manifest)


@pytest.mark.parametrize(
    ("document", "pointer", "value", "rule_id"),
    _RESEARCH2_COVERAGE_CASES,
    ids=[f"{case[0]}-{'-'.join(map(str, case[1]))}" for case in _RESEARCH2_COVERAGE_CASES],
)
def test_research2_coverage_bundle_refuses_a_malformed_authored_value(
    _research2_coverage_bundle, document, pointer, value, rule_id
):
    import copy

    import tools.check_specification_coverage as coverage

    documents = dict(
        zip(("manifest", "protocol", "snapshot", "analysis"), copy.deepcopy(_research2_coverage_bundle), strict=True)
    )
    _research2_set(documents[document], pointer, value)
    failures = coverage.validate_historical_bundle(_RESEARCH2_REPO_ROOT, *documents.values())

    assert rule_id in {failure.rule_id for failure in failures}


def test_research2_passed_stage_with_an_unhashable_artifact_path_is_an_unknown_artifact(tmp_path):
    from tools.specification_coverage._snapshot import _SnapshotContext, _stage_outcome_failures

    context = _SnapshotContext(repo_root=tmp_path, executed={}, valid_outcomes={"passed"}, valid_strengths={"exact"})
    stage = {"stage_id": [], "outcome": "passed", "validation_strength": "exact", "artifact_path": [], "pointer": "/a"}
    failures = []
    _stage_outcome_failures(context, stage, "concept", failures, "snapshot.json")

    assert [failure.rule_id for failure in failures] == [
        "specification-coverage-artifact-path",
        "specification-coverage-typed-evidence",
    ]


def test_research2_coverage_recomputation_keeps_a_deeply_nested_authored_value():
    from tools.specification_coverage._analysis import recompute_analysis

    deep: list[object] = []
    cursor = deep
    for _ in range(3000):
        cursor.append([])
        cursor = cursor[0]
    result = recompute_analysis({}, {}, {"claim": deep})

    assert result["claim"] is deep


@pytest.fixture(scope="module")
def _research2_satisfiability_documents():
    from tools.formal_semantic_validation._loading import load_release_bundles
    from tools.policy.common import load_bounded_json_object

    release = next(
        item for item in load_release_bundles(_RESEARCH2_REPO_ROOT) if item.manifest_path == _RESEARCH2_FORMAL_LEGACY
    )
    pins = {item["kind"]: item["path"] for item in release.manifest["artifacts"]}
    manifest = {
        "revision": "2.0.0",
        "satisfiability_snapshot_path": pins["satisfiability-snapshot"],
        "satisfiability_analysis_path": pins["satisfiability-analysis"],
    }
    documents = {
        name: load_bounded_json_object(
            _RESEARCH2_REPO_ROOT, manifest[f"satisfiability_{name}_path"], max_bytes=512 * 1024
        )
        for name in ("snapshot", "analysis")
    }
    return manifest, documents["snapshot"], documents["analysis"]


@pytest.mark.parametrize(
    ("pointer", "rule_id"),
    [
        (("cases", 0, "control"), "formal-satisfiability-control-coverage"),
        (("cases", 0, "case_id"), "formal-satisfiability-snapshot-drift"),
    ],
    ids=["control", "case-id"],
)
def test_research2_satisfiability_supplement_refuses_an_unhashable_case_value(
    _research2_satisfiability_documents, pointer, rule_id
):
    import copy

    from tools.formal_semantic_validation._satisfiability import validate_satisfiability_analysis

    manifest, snapshot, analysis = copy.deepcopy(_research2_satisfiability_documents)
    _research2_set(analysis, pointer, [])
    failures = validate_satisfiability_analysis(
        _RESEARCH2_REPO_ROOT, manifest, snapshot, analysis, replay_current=False
    )

    assert rule_id in {failure.rule_id for failure in failures}


@pytest.mark.parametrize("cases", [7, [{"case_id": []}]], ids=["scalar-cases", "unhashable-case-id"])
def test_research2_malformed_historical_corpus_fails_retention(tmp_path, cases):
    from tools.formal_semantic_validation._releases import _retained_historical_cases

    corpus = tmp_path / "docs/research/formal-semantic-validation/corpus/manifest-v1.json"
    corpus.parent.mkdir(parents=True)
    corpus.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    failures = []
    _retained_historical_cases(tmp_path, {}, failures, "corpus.json")

    assert [failure.rule_id for failure in failures] == ["formal-validation-historical-retention"]


def test_research2_participant_test_reference_to_non_utf8_source_is_invalid(tmp_path):
    from tools.formal_semantic_validation._replay import _validate_test_ref

    (tmp_path / "test_fixture.py").write_bytes(b"def test_case():\n    pass\n\xff\n")

    assert _validate_test_ref(tmp_path, "test_fixture.py::test_case") is False


_RESEARCH2_MALFORMED_SCHEMAS = {
    "keyword-type": {"type": 7},
    "invalid-pattern": {"properties": {"schema_version": {"type": "string", "pattern": "("}}},
    "unresolvable-reference": {"$ref": "#/$defs/missing"},
}


@pytest.mark.parametrize("schema", list(_RESEARCH2_MALFORMED_SCHEMAS.values()), ids=list(_RESEARCH2_MALFORMED_SCHEMAS))
def test_research2_fixture_checked_against_a_malformed_published_schema_is_refused(tmp_path, schema):
    from tools.schema_coverage._evidence import check_fixture_source

    contracts = tmp_path / "contracts"
    (contracts / "schemas").mkdir(parents=True)
    (contracts / "schemas" / "contract-v1.json").write_text(json.dumps(schema), encoding="utf-8")
    (contracts / "fixture.json").write_text(json.dumps({"schema_version": "contract-v1"}), encoding="utf-8")

    reason = check_fixture_source(
        tmp_path, "contracts/fixture.json", frozenset({"contract-v1"}), "contracts/schemas/contract-v1.json"
    )

    assert reason == "published schema is not a valid JSON Schema: contracts/schemas/contract-v1.json"


# Tooling artifact policy tools: input crashes that existed before the branch.

_TOOLING2_ROOT = Path(__file__).resolve().parents[3]
_TOOLING2_LONG_INTEGER = "1" * 5000
_TOOLING2_DEFECT = "SECRET-DEFECT-DETAIL"
_TOOLING2_WORKFLOW = ".github/workflows/sweep.yml"
_TOOLING2_UNCONSTRUCTABLE_YAML = {
    "integer-beyond-digit-limit": f"value: {_TOOLING2_LONG_INTEGER}\n",
    "binary-integer-without-digits": "value: 0b_\n",
    "impossible-date": "value: 2024-13-01\n",
    "offset-beyond-a-day": "value: 2024-01-01 10:00:00 +25:00\n",
    "tagged-integer-text": "value: !!int text\n",
    "tagged-empty-integer": 'value: !!int ""\n',
    "tagged-empty-float": 'value: !!float ""\n',
    "tagged-unknown-boolean": "value: !!bool maybe\n",
    "tagged-unmatched-timestamp": "value: !!timestamp later\n",
    "flow-nesting-beyond-parser-depth": "value: " + "[" * 5000 + "]" * 5000 + "\n",
    "block-nesting-beyond-parser-depth": "- " * 5000 + "x\n",
}
_TOOLING2_YAML_CASES = pytest.mark.parametrize(
    "document", list(_TOOLING2_UNCONSTRUCTABLE_YAML.values()), ids=list(_TOOLING2_UNCONSTRUCTABLE_YAML)
)
_TOOLING2_SELECTION_REJECTED = "development artifact policy failed before acquisition: selection rejected"
_TOOLING2_VALIDATOR_INCOMPLETE = (
    "development artifact policy failed before acquisition: the frozen project validator could not complete"
)


def _tooling2_write(path: Path, content: str | bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def _tooling2_workflow(tmp_path: Path, document: str) -> tuple[object, list[tuple[str, str, str | None]]]:
    from implementations.tooling.action_policy_yaml import parse_yaml_mapping

    _tooling2_write(tmp_path / _TOOLING2_WORKFLOW, document)
    parsed, failures = parse_yaml_mapping(tmp_path, _TOOLING2_WORKFLOW)
    return parsed, [(item.rule_id, item.message, item.path) for item in failures]


@_TOOLING2_YAML_CASES
def test_tooling2_workflow_yaml_that_cannot_be_constructed_is_a_parse_failure(tmp_path, document):
    parsed, failures = _tooling2_workflow(tmp_path, document)

    assert parsed is None
    assert failures == [("tooling-action-scan", "workflow policy input could not be parsed safely", _TOOLING2_WORKFLOW)]


@pytest.mark.parametrize("document", ["value: !!map text\n", "value: !!map [1, 2]\n", "!!map text\n"])
def test_tooling2_workflow_yaml_mapping_tag_on_another_node_is_a_parse_failure(tmp_path, document):
    parsed, failures = _tooling2_workflow(tmp_path, document)

    assert parsed is None
    assert failures == [("tooling-action-scan", "workflow policy input could not be parsed safely", _TOOLING2_WORKFLOW)]


def test_tooling2_workflow_yaml_keeps_valid_documents_and_existing_refusals(tmp_path):
    workflow = (_TOOLING2_ROOT / ".github/workflows/pr-body-policy.yml").read_text(encoding="utf-8")
    parsed, failures = _tooling2_workflow(tmp_path, workflow)
    assert failures == []
    assert parsed == yaml.safe_load(workflow)

    scalars = "count: 12\nflag: yes\nratio: 1.5\nday: 2024-02-29\nwhen: 2024-01-01 10:00:00 +05:30\nmask: 0x1F\n"
    parsed, failures = _tooling2_workflow(tmp_path, scalars)
    assert failures == []
    assert parsed == yaml.safe_load(scalars)

    refusals = {
        "anchor: &one 1\nalias: *one\n": "workflow policy input could not be parsed safely",
        "key: 1\nkey: 2\n": "workflow policy input could not be parsed safely",
        "- item\n": "workflow policy input must be a mapping",
    }
    for document, message in refusals.items():
        parsed, failures = _tooling2_workflow(tmp_path, document)
        assert parsed is None
        assert failures == [("tooling-action-scan", message, _TOOLING2_WORKFLOW)]


def test_tooling2_workflow_yaml_loader_defects_still_propagate(tmp_path, monkeypatch):
    from implementations.tooling import action_policy_yaml

    def defect(*_args, **_kwargs):
        raise ValueError(_TOOLING2_DEFECT)

    monkeypatch.setattr(action_policy_yaml._ClosedWorkflowLoader, "flatten_mapping", defect)
    with pytest.raises(ValueError, match=_TOOLING2_DEFECT):
        _tooling2_workflow(tmp_path, "value: 1\n")


@pytest.mark.parametrize(
    ("document", "path"),
    [
        *[(document, "sweep.yaml") for document in _TOOLING2_UNCONSTRUCTABLE_YAML.values()],
        (f"value = {_TOOLING2_LONG_INTEGER}\n", "sweep.toml"),
        ("value = " + "[" * 5000 + "]" * 5000 + "\n", "sweep.toml"),
    ],
    ids=[*(f"yaml-{name}" for name in _TOOLING2_UNCONSTRUCTABLE_YAML), "toml-digit-limit", "toml-nesting"],
)
def test_tooling2_structured_scan_reports_an_unbuildable_document_as_unparsed(document, path):
    from tools.tooling_artifact_policy_discovery import structured_acquisition

    assert structured_acquisition(document, path) == (0, False, 0)


def test_tooling2_structured_scan_keeps_valid_documents():
    from tools.tooling_artifact_policy_discovery import structured_acquisition

    assert structured_acquisition("run: |\n  curl https://example.invalid\nflag: yes\n", "step.yml") == (1, True, 0)
    assert structured_acquisition('command = "wget https://example.invalid"\n', "tool.toml") == (1, True, 0)
    assert structured_acquisition("value: [unclosed\n", "step.yaml") == (0, False, 0)
    assert structured_acquisition("value = \n", "tool.toml") == (0, False, 0)


def test_tooling2_structured_scan_parser_defects_still_propagate(monkeypatch):
    from tools import tooling_artifact_policy_discovery as discovery

    def yaml_defect(_text):
        raise TypeError(_TOOLING2_DEFECT)

    def toml_defect(_text):
        raise KeyError(_TOOLING2_DEFECT)

    monkeypatch.setattr(discovery, "yaml", SimpleNamespace(safe_load=yaml_defect, YAMLError=yaml.YAMLError))
    with pytest.raises(TypeError, match=_TOOLING2_DEFECT):
        discovery.structured_acquisition("value: 1\n", "step.yaml")
    monkeypatch.setattr(
        discovery, "tomllib", SimpleNamespace(loads=toml_defect, TOMLDecodeError=tomllib.TOMLDecodeError)
    )
    with pytest.raises(KeyError, match=_TOOLING2_DEFECT):
        discovery.structured_acquisition("value = 1\n", "tool.toml")


@pytest.mark.parametrize(
    "source",
    ["value = " + "-" * 100_000 + "1\n", "value = " + "+".join(["1"] * 100_000) + "\n"],
    ids=["parser-stack", "compiler-stack"],
)
def test_tooling2_python_scan_reports_a_source_too_complex_to_compile_as_unparsed(source):
    from tools.tooling_artifact_policy_discovery import python_scan

    scan = python_scan(source)
    assert not scan.parsed
    assert (scan.acquisition_count, scan.unknown_executable_count, scan.network_call_count) == (0, 0, 0)


def test_tooling2_python_scan_names_a_long_attribute_chain_without_recursion():
    from tools.tooling_artifact_policy_discovery import ast_name, python_scan

    chain = "receiver" + ".step" * 2000
    scan = python_scan(f"import subprocess\nvalue = {chain}\nsubprocess.run(['curl', 'https://example.invalid'])\n")
    assert scan.parsed
    assert (scan.acquisition_count, scan.network_call_count) == (1, 0)
    assert ast_name(ast.parse(chain, mode="eval").body) == chain


@pytest.mark.parametrize(
    ("expression", "name"),
    [("name", "name"), ("package.module.call", "package.module.call"), ("factory().open", "open"), ("call()", None)],
)
def test_tooling2_ast_name_keeps_its_dotted_names(expression, name):
    from tools.tooling_artifact_policy_discovery import ast_name

    assert ast_name(ast.parse(expression, mode="eval").body) == name


def _tooling2_python_authorities(tmp_path: Path) -> Path:
    from tools.tooling_artifact_policy_python import PYTHON_AUTHORITY_PATHS

    for relative in PYTHON_AUTHORITY_PATHS:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_TOOLING2_ROOT / relative, destination)
    return tmp_path


def test_tooling2_python_closure_toml_nested_beyond_the_parser_depth_is_untrusted(tmp_path):
    from tools import tooling_artifact_policy_python as python_policy

    root = _tooling2_python_authorities(tmp_path)
    lock = root / python_policy.PYTHON_TOOL_LOCK_PATH
    lock.write_text(lock.read_text(encoding="utf-8") + "\n[sweep]\nvalue = " + "[" * 5000 + "]" * 5000 + "\n")

    assert python_policy._toml(root, python_policy.PYTHON_TOOL_LOCK_PATH) is None
    authorities, failures = python_policy._python_authorities(root)
    assert authorities is None
    assert [item.rule_id for item in failures] == ["tooling-python-toml"]


def _tooling2_project() -> dict:
    from tools.tooling_artifact_policy_python import PYTHON_PROJECT_PATH

    return tomllib.loads((_TOOLING2_ROOT / PYTHON_PROJECT_PATH).read_text(encoding="utf-8"))


def test_tooling2_governed_pins_keep_the_checked_in_project_clean():
    from tools.tooling_artifact_policy_python import _governed_pin_failures

    assert _governed_pin_failures(_TOOLING2_ROOT, _tooling2_project()) == []


def test_tooling2_governed_pins_report_an_unparseable_dependency_as_an_unverified_z3_pin(tmp_path):
    from tools.tooling_artifact_policy_python import _governed_pin_failures

    root = _tooling2_python_authorities(tmp_path)
    project = _tooling2_project()
    project["project"]["dependencies"] = [*project["project"]["dependencies"], "not a requirement !!"]

    failures = _governed_pin_failures(root, project)
    assert [(item.rule_id, item.message) for item in failures] == [
        ("tooling-python-z3", "the governed Z3 dependency pin must remain exact")
    ]


def test_tooling2_governed_pins_report_undecodable_build_constraints_as_incomplete(tmp_path):
    from tools.tooling_artifact_policy_python import PYTHON_BUILD_CONSTRAINTS_PATH, _governed_pin_failures

    root = _tooling2_python_authorities(tmp_path)
    (root / PYTHON_BUILD_CONSTRAINTS_PATH).write_bytes(b"setuptools==80.0.0 \\\n    --hash=sha256:\xff\n")

    failures = _governed_pin_failures(root, _tooling2_project())
    assert [(item.rule_id, item.message, item.path) for item in failures] == [
        (
            "tooling-python-build-constraints",
            "build constraints must be exact and hash-complete",
            PYTHON_BUILD_CONSTRAINTS_PATH,
        )
    ]


def test_tooling2_governed_pin_defects_still_propagate(tmp_path, monkeypatch):
    from tools import tooling_artifact_policy_python as python_policy

    root = _tooling2_python_authorities(tmp_path)

    def requirement_defect(_value):
        raise KeyError(_TOOLING2_DEFECT)

    monkeypatch.setattr(python_policy, "Requirement", requirement_defect)
    project = _tooling2_project()
    with pytest.raises(KeyError, match=_TOOLING2_DEFECT):
        python_policy._governed_pin_failures(root, project)
    monkeypatch.undo()

    def constraints_defect(_text):
        raise ValueError(_TOOLING2_DEFECT)

    monkeypatch.setattr(python_policy, "_constraint_records", constraints_defect)
    project = _tooling2_project()
    with pytest.raises(ValueError, match=_TOOLING2_DEFECT):
        python_policy._governed_pin_failures(root, project)


_TOOLING2_UNUSABLE_LOCKS = {
    "not-json": b"{not json",
    "not-utf8": b'{"artifacts": [], "note": "\xff"}',
    "integer-beyond-digit-limit": b'{"artifacts": [], "value": ' + _TOOLING2_LONG_INTEGER.encode() + b"}",
    "nesting-beyond-decoder-depth": b'{"artifacts": [], "value": ' + b"[" * 100_000 + b"]" * 100_000 + b"}",
    "no-artifact-list": b"{}",
    "artifacts-not-objects": b'{"artifacts": ["temporal-cli-runtime-test"]}',
    "no-temporal-artifact": b'{"artifacts": [{"artifact_id": "other", "version": "1"}]}',
}


@pytest.mark.parametrize("content", list(_TOOLING2_UNUSABLE_LOCKS.values()), ids=list(_TOOLING2_UNUSABLE_LOCKS))
def test_tooling2_temporal_input_refuses_an_unusable_artifact_lock(tmp_path, monkeypatch, capsys, content):
    from implementations.tooling import runtime_execution_ci

    _tooling2_write(tmp_path / "implementations/tooling/artifacts.lock.json", content)

    def selection_must_not_run(*_args, **_kwargs):
        raise AssertionError("the lock must be refused before selection")

    monkeypatch.setattr(runtime_execution_ci, "select_tooling_artifact", selection_must_not_run)
    monkeypatch.setattr(runtime_execution_ci, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["runtime_execution_ci", str(tmp_path / "input.tar.gz"), str(tmp_path / "bin")])

    assert runtime_execution_ci.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("runtime-execution-ci: ")
    assert _TOOLING2_LONG_INTEGER[:64] not in captured.err
    assert not (tmp_path / "bin").exists()


def test_tooling2_temporal_input_refuses_a_selection_without_an_executable_manifest(tmp_path, monkeypatch):
    from implementations.tooling import runtime_execution_ci

    _tooling2_write(
        tmp_path / "implementations/tooling/artifacts.lock.json",
        '{"artifacts": [{"artifact_id": "temporal-cli-runtime-test", "version": "fixture"}]}',
    )
    selection = {"platform": {"raw_manifest": [{"size": 1, "sha256": "a" * 64}], "installed_identity": {}}}
    monkeypatch.setattr(runtime_execution_ci, "select_tooling_artifact", lambda *_args, **_kwargs: selection)

    with pytest.raises(InvalidInputError):
        runtime_execution_ci.install_temporal_cli(tmp_path / "input.tar.gz", tmp_path / "bin", repo_root=tmp_path)
    assert not (tmp_path / "bin").exists()


def test_tooling2_temporal_input_selection_defects_still_propagate(tmp_path, monkeypatch):
    from implementations.tooling import runtime_execution_ci

    _tooling2_write(
        tmp_path / "implementations/tooling/artifacts.lock.json",
        '{"artifacts": [{"artifact_id": "temporal-cli-runtime-test", "version": "fixture"}]}',
    )

    def defect(*_args, **_kwargs):
        raise KeyError(_TOOLING2_DEFECT)

    monkeypatch.setattr(runtime_execution_ci, "select_tooling_artifact", defect)
    with pytest.raises(KeyError, match=_TOOLING2_DEFECT):
        runtime_execution_ci.install_temporal_cli(tmp_path / "input.tar.gz", tmp_path / "bin", repo_root=tmp_path)


@pytest.mark.parametrize("identity", ["host\x00profile", "host\ud800profile"], ids=["nul", "lone-surrogate"])
def test_tooling2_validator_launch_refuses_an_argument_that_cannot_reach_the_process(identity):
    from tools import tooling_policy_gate

    command = [sys.executable, "-c", "raise SystemExit(0)"]
    with pytest.raises(tooling_policy_gate.ArtifactPolicyError) as host:
        tooling_policy_gate._validator_host_stdout(command, host_profile_id=identity)
    with pytest.raises(tooling_policy_gate.ArtifactPolicyError) as artifact:
        tooling_policy_gate._validator_stdout(
            command, artifact_id=identity, version="1", platform_id="linux-x86_64", profile_id="public-linux-x86_64"
        )
    assert str(host.value) == str(artifact.value) == _TOOLING2_SELECTION_REJECTED


def test_tooling2_validator_launch_reports_a_response_that_is_not_text_as_incomplete(monkeypatch):
    from tools import tooling_policy_gate

    def undecodable(*_args, **_kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(tooling_policy_gate.subprocess, "run", undecodable)
    with pytest.raises(tooling_policy_gate.ArtifactPolicyError) as host:
        tooling_policy_gate._validator_host_stdout(["python", "validator"], host_profile_id="host")
    with pytest.raises(tooling_policy_gate.ArtifactPolicyError) as artifact:
        tooling_policy_gate._validator_stdout(
            ["python", "validator"],
            artifact_id="tool",
            version="1",
            platform_id="linux-x86_64",
            profile_id="public-linux-x86_64",
        )
    assert str(host.value) == str(artifact.value) == _TOOLING2_VALIDATOR_INCOMPLETE


def test_tooling2_validator_launch_defects_still_propagate(monkeypatch):
    from tools import tooling_policy_gate

    def defect(*_args, **_kwargs):
        raise ValueError(_TOOLING2_DEFECT)

    monkeypatch.setattr(tooling_policy_gate.subprocess, "run", defect)
    with pytest.raises(ValueError, match=_TOOLING2_DEFECT):
        tooling_policy_gate._validator_host_stdout(["python", "validator"], host_profile_id="host")


def _tooling2_edit_json(path: Path, edit) -> None:
    import json

    document = json.loads(path.read_text(encoding="utf-8"))
    edit(document)
    path.write_text(json.dumps(document), encoding="utf-8")


_TOOLING2_WRONG_TYPED_AUTHORITIES = {
    "authenticity-status-list": (
        "implementations/tooling/artifacts.lock.json",
        lambda lock: lock["artifacts"][0]["authenticity"].update(status=["verified"]),
        "tooling-authenticity-unreviewed",
    ),
    "policy-subject-list": (
        "implementations/tooling/admission-policy.json",
        lambda admission: admission["policies"][0].update(subject=["artifact"]),
        "tooling-policy-subject",
    ),
    "selector-artifact-list": (
        "implementations/tooling/selector-bindings.json",
        lambda bindings: bindings["bindings"].append({"binding_id": "sweep", "artifact_id": ["tool-a"]}),
        "tooling-selector-authority",
    ),
}


@pytest.mark.parametrize(
    ("relative", "edit", "rule_id"),
    list(_TOOLING2_WRONG_TYPED_AUTHORITIES.values()),
    ids=list(_TOOLING2_WRONG_TYPED_AUTHORITIES),
)
def test_tooling2_repository_policy_reports_a_wrong_typed_authority_value(tmp_path, relative, edit, rule_id):
    from test_tooling_artifact_policy import _seed_policy
    from tools.check_tooling_artifact_policy import evaluate_tooling_artifact_policy

    _seed_policy(tmp_path)
    _tooling2_edit_json(tmp_path / relative, edit)

    failures = evaluate_tooling_artifact_policy(tmp_path, tracked_paths=["tools/acquire_tool_a.py"])
    assert rule_id in {item.rule_id for item in failures}


def test_tooling2_oci_graph_layer_digests_that_are_not_text_are_compared_without_hashing():
    from tools.tooling_artifact_policy_oci import RULE_LAYER_DUPLICATE, _layer_failures

    graph = {"layers": [{"digest": ["sha256:a"]}, {"digest": ["sha256:a"]}], "diff_ids": ["sha256:b", "sha256:c"]}
    assert [item.rule_id for item in _layer_failures("image", graph)] == [RULE_LAYER_DUPLICATE]
    distinct = {"layers": [{"digest": "sha256:a"}, {"digest": ["sha256:a"]}], "diff_ids": ["sha256:b", "sha256:c"]}
    assert _layer_failures("image", distinct) == []


@pytest.mark.parametrize(
    ("document", "rule_ids"),
    [
        ("on: [[push]]\npermissions: {contents: read}\njobs: {}\n", set()),
        ("on: !!set {push}\npermissions: {contents: read}\njobs: {}\n", set()),
        (
            "on: [pull_request, {push: {}}]\npermissions: {contents: read}\njobs: {build: {runs-on: x}}\n",
            set(),
        ),
        (
            "on: push\npermissions: {contents: [read]}\njobs: {build: {runs-on: x}}\n",
            {"tooling-action-permissions"},
        ),
    ],
    ids=["trigger-list-in-list", "trigger-set", "trigger-mapping-in-list", "permission-level-list"],
)
def test_tooling2_workflow_policy_reports_wrong_typed_triggers_and_permissions(tmp_path, document, rule_ids):
    from tools.tooling_artifact_policy_actions import action_failures

    _tooling2_write(tmp_path / _TOOLING2_WORKFLOW, document)
    assert {item.rule_id for item in action_failures(tmp_path, {}, [_TOOLING2_WORKFLOW])} == rule_ids


def test_tooling2_python_closure_pins_report_wrong_typed_tables(tmp_path):
    from tools import tooling_artifact_policy_python as python_policy

    root = _tooling2_python_authorities(tmp_path)
    assert python_policy._lock_versions({"package": 5}) == {}
    failures = python_policy._dependency_pin_failures(
        {"build-system": "requires"}, {"project": "dependencies", "dependency-groups": 5}, {"package": 5}
    )
    assert [item.rule_id for item in failures] == ["tooling-python-direct-pins"]
    for project in ({"project": "dependencies", "build-system": 5}, {"project": {"dependencies": 5}}):
        failures = python_policy._governed_pin_failures(root, project)
        assert [item.rule_id for item in failures] == ["tooling-python-z3", "tooling-python-build-constraints"]


def test_tooling2_python_closure_profiles_report_wrong_typed_values(tmp_path):
    from tools.tooling_artifact_policy_python_profiles import profile_semantic_failures

    profiles = {
        "python_package_contexts": 5,
        "host_profiles": 5,
        "python_closure_profiles": [
            {
                "host_profile_id": ["host"],
                "purposes": 5,
                "project_extras": [["dev"]],
                "tool_groups": 7,
                "acquisition_context_ids": [{}],
            }
        ],
    }
    assert {item.rule_id for item in profile_semantic_failures(tmp_path, profiles)} == {
        "tooling-python-contexts",
        "tooling-python-host",
        "tooling-python-abi",
        "tooling-python-purposes",
        "tooling-python-extras",
        "tooling-python-groups",
        "tooling-python-context-binding",
    }


# The JSON decoder accepts nesting far beyond the interpreter recursion limit.
_TOOLING2_DEEP_VALUE = "[" * 3000 + "]" * 3000


def _tooling2_deepen(path: Path, key: str) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("{", "{" + f'"{key}": {_TOOLING2_DEEP_VALUE}, ', 1), encoding="utf-8")


def test_tooling2_repository_policy_reports_an_authority_nested_beyond_the_recursion_limit(tmp_path):
    from test_tooling_artifact_policy import _seed_policy
    from tools.check_tooling_artifact_policy import evaluate_tooling_artifact_policy

    _seed_policy(tmp_path)
    for relative in (
        "implementations/tooling/artifacts.lock.json",
        "implementations/tooling/admission-policy.json",
        "implementations/tooling/profiles/development-profiles.json",
    ):
        _tooling2_deepen(tmp_path / relative, "sweep")

    failures = evaluate_tooling_artifact_policy(tmp_path, tracked_paths=["tools/acquire_tool_a.py"])
    assert "tooling-schema" in {item.rule_id for item in failures}


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        # The metaschema accepts any value for an annotation such as "default".
        ("default", []),
        # The metaschema requires "$comment" to be a string, so the schema is malformed.
        (
            "$comment",
            [("tooling-schema", "internal tooling schema is malformed or nested too deeply")],
        ),
    ],
)
def test_tooling2_policy_schema_nested_beyond_the_recursion_limit_is_scanned_for_references(tmp_path, key, expected):
    from test_tooling_artifact_policy import _seed_policy
    from tools.tooling_artifact_policy_common import ARTIFACT_LOCK_PATH, POLICY_SCHEMAS, load_documents

    _seed_policy(tmp_path)
    _tooling2_deepen(tmp_path / POLICY_SCHEMAS[ARTIFACT_LOCK_PATH], key)

    documents, failures = load_documents(tmp_path)
    assert ARTIFACT_LOCK_PATH in documents
    assert [(item.rule_id, item.message) for item in failures] == expected


def _tooling2_chain(length: int, *, closed: bool) -> dict:
    artifacts = [
        {
            "artifact_id": f"tool-{index}",
            "platforms": [{"platform_id": "linux-x86_64", "dependencies": [f"tool-{index + 1}"]}],
        }
        for index in range(length)
    ]
    artifacts[-1]["platforms"][0]["dependencies"] = ["tool-0"] if closed else []
    return {"artifacts": artifacts}


@pytest.mark.parametrize("closed", [False, True], ids=["chain", "cycle"])
def test_tooling2_dependency_graph_longer_than_the_recursion_limit_is_checked(tmp_path, closed):
    from tools.tooling_artifact_policy_artifacts import artifact_failures
    from tools.tooling_artifact_policy_common import ARTIFACT_LOCK_PATH

    failures = artifact_failures(tmp_path, {ARTIFACT_LOCK_PATH: _tooling2_chain(1500, closed=closed)})
    assert ("tooling-dependency-cycle" in {item.rule_id for item in failures}) is closed


@pytest.mark.parametrize(
    ("graph", "cyclic"),
    [
        ({"a": {"b"}, "b": {"c"}, "c": set()}, False),
        ({"a": {"b", "c"}, "b": {"d"}, "c": {"d"}, "d": set()}, False),
        ({"a": {"a"}}, True),
        ({"a": {"b"}, "b": {"a"}}, True),
        ({"a": {"b"}, "b": {"outside"}, "outside": {"a"}}, False),
    ],
    ids=["chain", "diamond", "self", "pair", "through-unknown"],
)
def test_tooling2_dependency_cycle_detection_keeps_its_answers(graph, cyclic):
    from tools.tooling_artifact_policy_artifacts import _has_dependency_cycle

    known = {name for name in graph if name != "outside"}
    assert _has_dependency_cycle(known, graph) is cyclic


def test_tooling2_forbidden_key_walk_keeps_its_findings_and_order():
    from tools.tooling_artifact_policy_common import walk_forbidden_keys

    document = {
        "Command": "x",
        "nested": {"hooks": [], "items": [{"script": 1}, [{"Shell": 2}]], "argv": None},
        "list": [{"exec": {"post_install": True}}],
        "safe": "value",
    }
    assert [(item.path, item.message) for item in walk_forbidden_keys(document, path="doc")] == [
        ("doc", "declarative policy contains forbidden executable field 'Command'"),
        ("doc.nested", "declarative policy contains forbidden executable field 'hooks'"),
        ("doc.nested.items[0]", "declarative policy contains forbidden executable field 'script'"),
        ("doc.nested.items[1][0]", "declarative policy contains forbidden executable field 'Shell'"),
        ("doc.nested", "declarative policy contains forbidden executable field 'argv'"),
        ("doc.list[0]", "declarative policy contains forbidden executable field 'exec'"),
        ("doc.list[0].exec", "declarative policy contains forbidden executable field 'post_install'"),
    ]
    assert walk_forbidden_keys([[{"hook": 1}]] * 2) == [
        walk_forbidden_keys({"hook": 1}, path="<root>[0][0]")[0],
        walk_forbidden_keys({"hook": 1}, path="<root>[1][0]")[0],
    ]


# Repository policy text reads and tooling policy schemas: input crashes found while closing the open items.

_SWEEP_T_ADR_RELATIVE = "docs/decisions/adrs/adr-001-example.md"
_SWEEP_T_ADR_TEXT = "# ADR-001: Example\n\n## Status\n\naccepted\n\n## Date\n\n2026-01-01\n"
_SWEEP_T_ADR_INDEX_POLICY = {"adr_index": {"index_path": "docs/decisions/adrs/README.md"}}


def _sweep_t_unreadable_text(monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    original = Path.read_text

    def read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == target:
            raise PermissionError(errno.EACCES, "simulated host failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)


def _sweep_t_adr_repository(tmp_path: Path) -> Path:
    adr = tmp_path / _SWEEP_T_ADR_RELATIVE
    adr.parent.mkdir(parents=True)
    adr.write_text(_SWEEP_T_ADR_TEXT, encoding="utf-8")
    return adr


def test_repo_policy_import_checks_refuse_a_changed_file_the_host_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.policy.repo_policy as repo_policy

    source = tmp_path / "pkg" / "module.py"
    source.parent.mkdir()
    source.write_text("import os\n", encoding="utf-8")
    _sweep_t_unreadable_text(monkeypatch, source)
    rule = {"id": "pkg", "root": "pkg", "allowed_top_level_imports": []}
    monkeypatch.setattr(repo_policy, "_validate_module_boundary_config", lambda _root, _config: ([rule], []))
    layering = [{"id": "no-tools", "scope_root": "pkg", "forbidden_top_level": "tools"}]

    with pytest.raises(OperationalError, match="^pkg/module.py could not be read$"):
        repo_policy._check_layering(tmp_path, layering, ["pkg/module.py"])
    with pytest.raises(OperationalError, match="^pkg/module.py could not be read$"):
        repo_policy._check_module_boundaries(tmp_path, {}, ["pkg/module.py"], check_set="file-local")


@pytest.mark.parametrize(
    ("relative", "check"),
    [
        pytest.param(
            "CHANGELOG.md", lambda repo_policy, root: repo_policy._check_changelog_versioned(root), id="changelog"
        ),
        pytest.param(
            "docs/decisions/adrs/TEMPLATE.md",
            lambda repo_policy, root: repo_policy._check_adr_template(root, [_SWEEP_T_ADR_RELATIVE]),
            id="adr-template",
        ),
        pytest.param(
            "docs/decisions/adrs/README.md",
            lambda repo_policy, root: repo_policy._check_adr_index(
                root, _SWEEP_T_ADR_INDEX_POLICY, [_SWEEP_T_ADR_RELATIVE]
            ),
            id="adr-index",
        ),
    ],
)
def test_repo_policy_refuses_a_repository_document_that_is_not_utf8(tmp_path: Path, relative: str, check) -> None:
    import tools.policy.repo_policy as repo_policy

    _sweep_t_adr_repository(tmp_path)
    (tmp_path / relative).write_bytes(b"## Status\n\xff\n")

    with pytest.raises(InvalidInputError, match=f"^{relative} is not UTF-8 text$"):
        check(repo_policy, tmp_path)


def test_repo_policy_refuses_a_repository_document_the_host_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.policy.repo_policy as repo_policy

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    _sweep_t_unreadable_text(monkeypatch, changelog)

    with pytest.raises(OperationalError, match="^CHANGELOG.md could not be read$"):
        repo_policy._check_changelog_versioned(tmp_path)


def test_adr_parser_refuses_an_adr_that_is_not_utf8_or_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.check_adr_immutability as adr_gate
    import tools.policy.repo_policy as repo_policy
    from tools.policy.adr import parse_adr_file

    adr = _sweep_t_adr_repository(tmp_path)
    assert parse_adr_file(adr) == ("001", "Example", "accepted", "2026-01-01")
    adr.write_bytes(_SWEEP_T_ADR_TEXT.encode("utf-8").replace(b"Example", b"Example \xff"))

    with pytest.raises(InvalidInputError, match="adr-001-example.md is not UTF-8 text$"):
        parse_adr_file(adr)
    with pytest.raises(InvalidInputError, match="adr-001-example.md is not UTF-8 text$"):
        repo_policy._check_adr_index(tmp_path, _SWEEP_T_ADR_INDEX_POLICY, [_SWEEP_T_ADR_RELATIVE])
    # The ADR pin gate leaves an unparseable ADR to the repository policy, as before.
    assert adr_gate._accepted_adrs(tmp_path) == {}
    _sweep_t_unreadable_text(monkeypatch, adr)
    with pytest.raises(OperationalError, match="adr-001-example.md could not be read$"):
        parse_adr_file(adr)


def test_repo_policy_text_reads_keep_defects_out_of_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.policy.repo_policy as repo_policy
    from tools.policy.adr import parse_adr_file

    adr = _sweep_t_adr_repository(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    def defective(self: Path, *_args: object, **_kwargs: object) -> str:
        raise ValueError(_SECRET)

    monkeypatch.setattr(Path, "read_text", defective)
    with pytest.raises(ValueError, match=_SECRET):
        repo_policy._check_changelog_versioned(tmp_path)
    with pytest.raises(ValueError, match=_SECRET):
        parse_adr_file(adr)


def _sweep_t_deep_schema(depth: int) -> dict:
    node: dict = {"type": "object"}
    for _ in range(depth):
        node = {"type": "object", "properties": {"deep": node}}
    return node


def _sweep_t_deep_value(depth: int) -> dict:
    value: dict = {}
    for _ in range(depth):
        value = {"deep": value}
    return value


def _sweep_t_recursive_schema(schema: dict) -> None:
    node = {"type": "object", "properties": {"deep": {"$ref": "#/$defs/sweepNode"}}}
    schema.setdefault("$defs", {})["sweepNode"] = node
    schema.setdefault("properties", {})["deep"] = {"$ref": "#/$defs/sweepNode"}


def _sweep_t_tooling_failures(tmp_path: Path, edit_schema, edit_lock=None) -> set[tuple[str, str, str | None]]:
    from test_tooling_artifact_policy import _seed_policy
    from tools.check_tooling_artifact_policy import evaluate_tooling_artifact_policy
    from tools.tooling_artifact_policy_common import ARTIFACT_LOCK_PATH, POLICY_SCHEMAS

    _seed_policy(tmp_path)
    for relative, edit in ((POLICY_SCHEMAS[ARTIFACT_LOCK_PATH], edit_schema), (ARTIFACT_LOCK_PATH, edit_lock)):
        if edit is not None:
            path = tmp_path / relative
            document = json.loads(path.read_text(encoding="utf-8"))
            edit(document)
            path.write_text(json.dumps(document), encoding="utf-8")
    failures = evaluate_tooling_artifact_policy(tmp_path, tracked_paths=["tools/acquire_tool_a.py"])
    return {(item.rule_id, item.message, item.path) for item in failures}


_SWEEP_T_TOOLING_SCHEMA_EDITS = {
    "keyword-type": lambda schema: schema.update({"type": 7}),
    "invalid-pattern": lambda schema: schema.setdefault("properties", {}).update(
        {"schema_version": {"type": "string", "pattern": "("}}
    ),
    "unresolvable-reference": lambda schema: schema.setdefault("properties", {}).update(
        {"schema_version": {"$ref": "#/$defs/missing"}}
    ),
    "nesting-beyond-the-recursion-limit": lambda schema: schema.setdefault("properties", {}).update(
        {"deep": _sweep_t_deep_schema(1500)}
    ),
}


@pytest.mark.parametrize("edit", list(_SWEEP_T_TOOLING_SCHEMA_EDITS.values()), ids=list(_SWEEP_T_TOOLING_SCHEMA_EDITS))
def test_tooling_policy_reports_a_malformed_or_deep_policy_schema_as_a_schema_failure(tmp_path: Path, edit) -> None:
    from tools.tooling_artifact_policy_common import ARTIFACT_LOCK_PATH, POLICY_SCHEMAS

    failures = _sweep_t_tooling_failures(tmp_path, edit)

    expected = ("tooling-schema", "internal tooling schema is malformed or nested too deeply")
    assert (*expected, POLICY_SCHEMAS[ARTIFACT_LOCK_PATH]) in failures


def test_tooling_policy_reports_a_document_too_deep_for_a_recursive_schema_as_a_schema_failure(
    tmp_path: Path,
) -> None:
    from tools.tooling_artifact_policy_common import ARTIFACT_LOCK_PATH

    failures = _sweep_t_tooling_failures(
        tmp_path, _sweep_t_recursive_schema, lambda lock: lock.update({"deep": _sweep_t_deep_value(1500)})
    )

    assert ("tooling-schema", "policy document nests too deeply to validate", ARTIFACT_LOCK_PATH) in failures


def test_tooling_policy_keeps_valid_documents_under_the_schema_checks(tmp_path: Path) -> None:
    shallow = _sweep_t_tooling_failures(
        tmp_path, _sweep_t_recursive_schema, lambda lock: lock.update({"deep": _sweep_t_deep_value(3)})
    )

    assert shallow == set()


@pytest.mark.parametrize("method", ["check_schema", "iter_errors"])
def test_tooling_policy_schema_checks_keep_defects_out_of_the_schema_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    import jsonschema

    def defective(*_args: object, **_kwargs: object) -> None:
        raise ValueError(_SECRET)

    monkeypatch.setattr(jsonschema.Draft202012Validator, method, defective)
    with pytest.raises(ValueError, match=_SECRET):
        _sweep_t_tooling_failures(tmp_path, None)

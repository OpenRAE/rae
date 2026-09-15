"""Regression tests for issue #1221 maintained-client vocabulary acquisition.

These cover the migration of the opt-in ``--verify-remote`` acquisition in the
vocabulary source checkers from ``urllib`` to the qualified native client
(``tools.maintained_client_acquisition.acquire_locked_bytes``): URL pinning
before any transport, admission of an approved local raw object with no network
fallback, threading of the reviewed lock selection into the acquirer, and clean
surfacing of acquisition failures. The full canonical/offline comparison logic
is unchanged and covered by the per-source offline tests.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from raes_contracts.vocabulary_sources import (
    load_activitystreams_activity_types_source,
    load_atlas_tactics_source,
    load_attack_enterprise_tactics_source,
    load_fipa_communicative_acts_source,
    load_nist_csf_defensive_categories_source,
)
from tools import (
    check_atlas_tactic_vocabulary,
    check_attack_tactic_vocabulary,
    check_autonomous_behavior_vocabularies,
    check_nist_csf_defensive_vocabulary,
    tooling_policy_gate,
)
from tools import maintained_client_acquisition as acquisition

REPO_ROOT = Path(__file__).resolve().parents[3]

ACTIVITYSTREAMS_SNAPSHOT = "w3c-activitystreams-activity-types-snapshot"
FIPA_SNAPSHOT = "fipa-communicative-acts-snapshot"

SINGLE_SOURCE_CHECKERS = [
    pytest.param(
        check_attack_tactic_vocabulary,
        "attack-enterprise-tactics-snapshot",
        load_attack_enterprise_tactics_source,
        id="attack",
    ),
    pytest.param(
        check_atlas_tactic_vocabulary,
        "atlas-tactics-snapshot",
        load_atlas_tactics_source,
        id="atlas",
    ),
    pytest.param(
        check_nist_csf_defensive_vocabulary,
        "nist-csf-defensive-categories-snapshot",
        load_nist_csf_defensive_categories_source,
        id="nist-csf",
    ),
]

ALL_CHECKER_PATHS = [
    REPO_ROOT / "tools" / "check_attack_tactic_vocabulary.py",
    REPO_ROOT / "tools" / "check_atlas_tactic_vocabulary.py",
    REPO_ROOT / "tools" / "check_nist_csf_defensive_vocabulary.py",
    REPO_ROOT / "tools" / "check_autonomous_behavior_vocabularies.py",
]


def _raw(payload: bytes) -> SimpleNamespace:
    return SimpleNamespace(path="raw-object", sha256=hashlib.sha256(payload).hexdigest(), size=len(payload))


def _selection(url: str, payload: bytes) -> SimpleNamespace:
    return SimpleNamespace(source_urls=[url], raw_manifest=[_raw(payload)])


def _fail_if_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("network transport must not run")


@pytest.mark.parametrize("checker_path", ALL_CHECKER_PATHS, ids=lambda path: path.name)
def test_checkers_carry_no_custom_network_code(checker_path: Path) -> None:
    source = checker_path.read_text(encoding="utf-8")

    assert "urllib.request" not in source
    assert "build_opener" not in source
    assert "http.client" not in source
    assert "acquire_locked_bytes" in source


@pytest.mark.parametrize(("module", "artifact_id", "loader"), SINGLE_SOURCE_CHECKERS)
def test_verify_remote_rejects_non_pinned_url_before_transport(monkeypatch, module, artifact_id, loader) -> None:
    source = loader()
    monkeypatch.setattr(
        tooling_policy_gate,
        "load_tooling_artifact_selection",
        lambda **_kwargs: _selection("https://example.test/not-the-pinned-source", b"unused"),
    )
    monkeypatch.setattr(acquisition, "run_curl_transfer", _fail_if_network)

    failures = module._check_remote(source)

    assert failures == [f"{module.SOURCE_RELATIVE_PATH}: source URL differs from the reviewed lock selection"]


@pytest.mark.parametrize(("module", "artifact_id", "loader"), SINGLE_SOURCE_CHECKERS)
def test_verify_remote_local_input_mismatch_is_terminal_without_network(
    monkeypatch, tmp_path, module, artifact_id, loader
) -> None:
    source = loader()
    local_input = tmp_path / "approved-replica"
    local_input.write_bytes(b"tampered bytes")
    monkeypatch.setattr(
        tooling_policy_gate,
        "load_tooling_artifact_selection",
        lambda **_kwargs: _selection(source.source_url, b"reviewed raw bytes"),
    )
    monkeypatch.setattr(acquisition, "run_curl_transfer", _fail_if_network)

    failures = module._check_remote(source, local_input=local_input)

    assert len(failures) == 1
    assert failures[0].startswith(f"{module.SOURCE_RELATIVE_PATH}: ")
    assert "local input failed locked identity validation" in failures[0]
    assert str(local_input) not in failures[0]


@pytest.mark.parametrize(("module", "artifact_id", "loader"), SINGLE_SOURCE_CHECKERS)
def test_verify_remote_threads_selection_and_local_input_to_acquire(
    monkeypatch, tmp_path, module, artifact_id, loader
) -> None:
    source = loader()
    selection = _selection(source.source_url, b"reviewed raw bytes")
    approved_replica = tmp_path / "approved-replica"
    captured: dict[str, object] = {}

    def _capture(**kwargs: object) -> bytes:
        captured.update(kwargs)
        raise RuntimeError("acquired bytes differ from the reviewed lock")

    monkeypatch.setattr(tooling_policy_gate, "load_tooling_artifact_selection", lambda **_kwargs: selection)
    monkeypatch.setattr(acquisition, "acquire_locked_bytes", _capture)

    failures = module._check_remote(source, local_input=approved_replica)

    assert captured["artifact_id"] == artifact_id
    assert captured["source_url"] == source.source_url
    assert captured["expected"] is selection.raw_manifest[0]
    assert captured["local_input"] is approved_replica
    assert failures == [f"{module.SOURCE_RELATIVE_PATH}: acquired bytes differ from the reviewed lock"]


def test_autonomous_activitystreams_rejects_non_pinned_url(monkeypatch) -> None:
    module = check_autonomous_behavior_vocabularies
    source = load_activitystreams_activity_types_source()
    monkeypatch.setattr(acquisition, "run_curl_transfer", _fail_if_network)

    failures = module._check_activitystreams_remote(source, _selection("https://example.test/x", b"unused"))

    assert failures == [f"{module.ACTIVITYSTREAMS_RELATIVE_PATH}: source URL differs from the reviewed lock selection"]


def test_autonomous_fipa_rejects_non_pinned_url(monkeypatch) -> None:
    module = check_autonomous_behavior_vocabularies
    source = load_fipa_communicative_acts_source()
    monkeypatch.setattr(acquisition, "run_curl_transfer", _fail_if_network)

    failures = module._check_fipa_remote(source, _selection("https://example.test/x", b"unused"))

    assert failures == [f"{module.FIPA_RELATIVE_PATH}: source artifact URL differs from the reviewed lock selection"]


def test_autonomous_activitystreams_local_input_mismatch_is_terminal(monkeypatch, tmp_path) -> None:
    module = check_autonomous_behavior_vocabularies
    source = load_activitystreams_activity_types_source()
    local_input = tmp_path / "activitystreams-replica"
    local_input.write_bytes(b"tampered")
    monkeypatch.setattr(acquisition, "run_curl_transfer", _fail_if_network)

    failures = module._check_activitystreams_remote(
        source, _selection(source.source_url, b"reviewed raw bytes"), local_input=local_input
    )

    assert len(failures) == 1
    assert "local input failed locked identity validation" in failures[0]
    assert str(local_input) not in failures[0]


def test_autonomous_fipa_local_input_mismatch_is_terminal(monkeypatch, tmp_path) -> None:
    module = check_autonomous_behavior_vocabularies
    source = load_fipa_communicative_acts_source()
    local_input = tmp_path / "fipa-replica"
    local_input.write_bytes(b"tampered")
    monkeypatch.setattr(acquisition, "run_curl_transfer", _fail_if_network)

    failures = module._check_fipa_remote(
        source, _selection(source.source_artifact_url, b"reviewed raw bytes"), local_input=local_input
    )

    assert len(failures) == 1
    assert "local input failed locked identity validation" in failures[0]
    assert str(local_input) not in failures[0]


def test_autonomous_fipa_threads_selection_and_local_input_to_acquire(monkeypatch, tmp_path) -> None:
    module = check_autonomous_behavior_vocabularies
    source = load_fipa_communicative_acts_source()
    selection = _selection(source.source_artifact_url, b"reviewed raw bytes")
    approved_replica = tmp_path / "fipa-replica"
    captured: dict[str, object] = {}

    def _capture(**kwargs: object) -> bytes:
        captured.update(kwargs)
        raise RuntimeError("acquired bytes differ from the reviewed lock")

    monkeypatch.setattr(acquisition, "acquire_locked_bytes", _capture)

    failures = module._check_fipa_remote(source, selection, local_input=approved_replica)

    assert captured["artifact_id"] == FIPA_SNAPSHOT
    assert captured["source_url"] == source.source_artifact_url
    assert captured["expected"] is selection.raw_manifest[0]
    assert captured["local_input"] is approved_replica
    assert failures == [f"{module.FIPA_RELATIVE_PATH}: acquired bytes differ from the reviewed lock"]


def test_autonomous_check_remote_selects_both_locked_snapshots(monkeypatch, tmp_path) -> None:
    module = check_autonomous_behavior_vocabularies
    activitystreams = load_activitystreams_activity_types_source()
    fipa = load_fipa_communicative_acts_source()
    activitystreams_replica = tmp_path / "as-replica"
    requested: list[str] = []

    def _selection_for(*, artifact_id: str, **_kwargs: object) -> SimpleNamespace:
        requested.append(artifact_id)
        url = activitystreams.source_url if artifact_id == ACTIVITYSTREAMS_SNAPSHOT else fipa.source_artifact_url
        return _selection(url, b"reviewed raw bytes")

    captured: dict[str, object] = {}

    def _capture(**kwargs: object) -> bytes:
        captured.update(kwargs)
        raise RuntimeError("acquired bytes differ from the reviewed lock")

    monkeypatch.setattr(tooling_policy_gate, "load_tooling_artifact_selection", _selection_for)
    monkeypatch.setattr(acquisition, "acquire_locked_bytes", _capture)

    failures = module._check_remote(
        activitystreams,
        fipa,
        activitystreams_local_input=activitystreams_replica,
        fipa_local_input=tmp_path / "fipa-replica",
    )

    assert set(requested) == {ACTIVITYSTREAMS_SNAPSHOT, FIPA_SNAPSHOT}
    assert captured["artifact_id"] == ACTIVITYSTREAMS_SNAPSHOT
    assert captured["local_input"] is activitystreams_replica
    assert failures == [f"{module.ACTIVITYSTREAMS_RELATIVE_PATH}: acquired bytes differ from the reviewed lock"]


@pytest.mark.parametrize(("module", "artifact_id", "loader"), SINGLE_SOURCE_CHECKERS)
def test_local_input_without_verify_remote_is_rejected(monkeypatch, module, artifact_id, loader) -> None:
    monkeypatch.setattr(sys, "argv", [module.__name__, "--local-input", "/tmp/approved-replica"])

    with pytest.raises(SystemExit):
        module.parse_args()


@pytest.mark.parametrize(("module", "artifact_id", "loader"), SINGLE_SOURCE_CHECKERS)
def test_verify_remote_with_local_input_parses(monkeypatch, module, artifact_id, loader) -> None:
    monkeypatch.setattr(sys, "argv", [module.__name__, "--verify-remote", "--local-input", "/tmp/approved-replica"])

    args = module.parse_args()

    assert args.verify_remote is True
    assert args.local_input == Path("/tmp/approved-replica")


@pytest.mark.parametrize("flag", ["--activitystreams-local-input", "--fipa-local-input"])
def test_autonomous_local_input_without_verify_remote_is_rejected(monkeypatch, flag) -> None:
    module = check_autonomous_behavior_vocabularies
    monkeypatch.setattr(sys, "argv", [module.__name__, flag, "/tmp/approved-replica"])

    with pytest.raises(SystemExit):
        module.parse_args()


def test_autonomous_verify_remote_with_local_inputs_parses(monkeypatch) -> None:
    module = check_autonomous_behavior_vocabularies
    monkeypatch.setattr(
        sys,
        "argv",
        [
            module.__name__,
            "--verify-remote",
            "--activitystreams-local-input",
            "/tmp/as-replica",
            "--fipa-local-input",
            "/tmp/fipa-replica",
        ],
    )

    args = module.parse_args()

    assert args.verify_remote is True
    assert args.activitystreams_local_input == Path("/tmp/as-replica")
    assert args.fipa_local_input == Path("/tmp/fipa-replica")

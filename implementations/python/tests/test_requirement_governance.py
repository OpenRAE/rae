from __future__ import annotations

import json
import shutil
import sys
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_requirement_governance import (
    _env_flag,
    classify_ground_control_error,
    emit_failures,
    evaluate_against_ground_control,
    governed_requirement_paths,
    is_dev_to_main_promotion,
    report_missing_uid,
    report_unevaluated,
)
from tools.policy import requirement_governance
from tools.policy.common import PolicyFailure
from tools.policy.requirement_governance import (
    GroundControlAuthRequired,
    GroundControlHttpClient,
    GroundControlUnavailable,
    detect_requirement_uid,
    evaluate_requirement_governance,
    requirement_uid_from_context,
    resolve_base_url,
    resolve_timeout_seconds,
    resolve_token,
)


class FakeClient:
    def __init__(self, requirements: dict[str, dict], traceability: dict[str, list[dict]]) -> None:
        self.requirements = requirements
        self.traceability = traceability

    def get_requirement(self, project: str, uid: str) -> dict:
        return self.requirements[uid]

    def get_traceability(self, requirement_id: str) -> list[dict]:
        return self.traceability.get(requirement_id, [])


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def setup_policy_repo(tmp_path: Path) -> Path:
    policy_dir = tmp_path / "tools" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / "tools" / "policy" / "requirement_order.yaml", policy_dir / "requirement_order.yaml")
    return tmp_path


def make_client(*, requirement_status: str = "DRAFT", api_412_status: str = "DRAFT") -> FakeClient:
    requirements = {
        "GOV-918": {"id": "req-gov-918", "uid": "GOV-918", "status": requirement_status},
        "API-412": {"id": "req-api-412", "uid": "API-412", "status": api_412_status},
        "RUN-300": {"id": "req-run-300", "uid": "RUN-300", "status": "ACTIVE"},
        "RUN-311": {"id": "req-run-311", "uid": "RUN-311", "status": "ACTIVE"},
        "RUN-313": {"id": "req-run-313", "uid": "RUN-313", "status": "DRAFT"},
        "EXP-701": {"id": "req-exp-701", "uid": "EXP-701", "status": "ACTIVE"},
        "GOV-917": {"id": "req-gov-917", "uid": "GOV-917", "status": "ACTIVE"},
        "GOV-919": {"id": "req-gov-919", "uid": "GOV-919", "status": "ACTIVE"},
        "GOV-920": {"id": "req-gov-920", "uid": "GOV-920", "status": "ACTIVE"},
        "GOV-921": {"id": "req-gov-921", "uid": "GOV-921", "status": "ACTIVE"},
        "GOV-922": {"id": "req-gov-922", "uid": "GOV-922", "status": "ACTIVE"},
    }
    traceability = {
        "req-gov-918": [
            {
                "artifact_identifier": "implementations/python/packages/raes_processor/bindings.py",
                "artifact_type": "CODE_FILE",
                "link_type": "IMPLEMENTS",
            },
            {
                "artifact_identifier": "implementations/python/tests/test_concept_authority.py",
                "artifact_type": "TEST",
                "link_type": "TESTS",
            },
        ],
        "req-api-412": [
            {
                "artifact_identifier": "implementations/python/packages/raes_processor/manifest.py",
                "artifact_type": "CODE_FILE",
                "link_type": "IMPLEMENTS",
            }
        ],
        "req-run-313": [],
        "req-exp-701": [
            {
                "artifact_identifier": "implementations/python/packages/raes_contracts/contracts.py",
                "artifact_type": "CODE_FILE",
                "link_type": "IMPLEMENTS",
            },
            {
                "artifact_identifier": "implementations/python/tests/test_runtime_contracts.py",
                "artifact_type": "TEST",
                "link_type": "TESTS",
            },
        ],
    }
    return FakeClient(requirements=requirements, traceability=traceability)


def test_detect_requirement_uid_from_branch_name() -> None:
    assert detect_requirement_uid("feature/GOV-918-cross-artifact-binding") == "GOV-918"
    assert detect_requirement_uid("15-gov-918-cross-artifact-concept-binding") == "GOV-918"
    assert detect_requirement_uid("feature/no-uid-here") is None


def test_ground_control_http_client_bounds_external_requests(monkeypatch) -> None:
    observed: dict[str, float] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return b'{"status":"ACTIVE"}'

    def fake_urlopen(request, *, timeout: float):
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr(requirement_governance, "urlopen", fake_urlopen)

    client = GroundControlHttpClient("http://ground-control.invalid")

    assert client.get_requirement("project", "ASR-535") == {"status": "ACTIVE"}
    assert observed["timeout"] == 5.0


@pytest.mark.parametrize(
    ("error", "message"),
    (
        (HTTPError("http://ground-control.invalid", 503, "unavailable", None, BytesIO(b"offline")), "503: offline"),
        (URLError("connection refused"), "connection refused"),
        (TimeoutError(), "request timed out"),
    ),
)
def test_ground_control_http_client_maps_transport_failures_to_runtime_error(
    monkeypatch,
    error: Exception,
    message: str,
) -> None:
    def failing_urlopen(_request, *, timeout: float):
        assert timeout == 5.0
        raise error

    monkeypatch.setattr(requirement_governance, "urlopen", failing_urlopen)
    client = GroundControlHttpClient("http://ground-control.invalid")

    with pytest.raises(RuntimeError, match=message):
        client.get_requirement("project", "ASR-535")


def test_requirement_uid_context_precedence(monkeypatch) -> None:
    monkeypatch.setenv("RAES_REQUIREMENT_UID", "API-412")

    assert requirement_uid_from_context("feature/GOV-918-work", "ASR-535") == "ASR-535"
    assert requirement_uid_from_context("feature/GOV-918-work", None) == "API-412"

    monkeypatch.delenv("RAES_REQUIREMENT_UID")
    assert requirement_uid_from_context("feature/GOV-918-work", None) == "GOV-918"


def test_governed_requirement_paths_excludes_exempt_tooling_files() -> None:
    assert governed_requirement_paths(
        [
            "implementations/python/packages/raes_processor/manifest.py",
            "implementations/python/tests/test_repo_policy_tools.py",
            ".pre-commit-config.yaml",
            "tools/check_json_artifacts.py",
        ]
    ) == ["implementations/python/packages/raes_processor/manifest.py"]


def test_dev_to_main_promotion_is_detected(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_HEAD_REF", "dev")
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    assert is_dev_to_main_promotion()


def test_dev_to_non_main_is_not_a_promotion(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_HEAD_REF", "dev")
    monkeypatch.setenv("GITHUB_BASE_REF", "release")

    assert not is_dev_to_main_promotion()


def test_archived_requirements_are_rejected(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    client = make_client(requirement_status="ARCHIVED")

    failures = evaluate_requirement_governance(
        repo_root,
        ["implementations/python/packages/raes_processor/bindings.py"],
        client=client,
        requirement_uid="GOV-918",
    )

    assert [failure.rule_id for failure in failures] == ["requirement-invalid-status"]


def test_blocked_phase_requires_previous_phase_completion(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    client = make_client(api_412_status="DRAFT")
    write_text(
        repo_root / "implementations" / "python" / "packages" / "raes_processor" / "manifest.py",
        "VALUE = 1\n",
    )

    failures = evaluate_requirement_governance(
        repo_root,
        ["implementations/python/packages/raes_processor/manifest.py"],
        client=client,
        requirement_uid="API-412",
    )

    assert [failure.rule_id for failure in failures] == ["requirement-order-blocked"]


def test_manual_release_phase_blocks_without_status_lookup(tmp_path: Path, monkeypatch) -> None:
    repo_root = setup_policy_repo(tmp_path)
    client = make_client()
    canonical_project = requirement_governance.load_policy(repo_root)["project"]
    policy = {
        "project": canonical_project,
        "phases": [
            {"id": "manual-gate", "manual_release": True},
            {
                "id": "governed",
                "requirements": ["GOV-918"],
                "blocked_until": ["manual-gate"],
            },
        ],
        "ownership": {},
        "traceability": {
            "required_code_roots": [],
            "required_test_roots": [],
        },
    }
    monkeypatch.setattr(requirement_governance, "load_policy", lambda _repo_root: policy)

    failures = evaluate_requirement_governance(
        repo_root,
        [],
        client=client,
        requirement_uid="GOV-918",
    )

    assert [failure.rule_id for failure in failures] == ["requirement-order-blocked"]
    assert "explicitly released" in failures[0].message


def test_unmapped_requirement_is_rejected(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    client = make_client()
    client.requirements["ASR-999"] = {"id": "req-asr-999", "uid": "ASR-999", "status": "ACTIVE"}

    failures = evaluate_requirement_governance(
        repo_root,
        [],
        client=client,
        requirement_uid="ASR-999",
    )

    assert [failure.rule_id for failure in failures] == ["requirement-policy-missing"]


def test_ownership_mismatch_is_reported(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    client = make_client()
    write_text(
        repo_root / "implementations" / "python" / "packages" / "raes_backend_libvirt" / "driver.py",
        "VALUE = 1\n",
    )

    failures = evaluate_requirement_governance(
        repo_root,
        ["implementations/python/packages/raes_backend_libvirt/driver.py"],
        client=client,
        requirement_uid="GOV-918",
    )

    assert {failure.rule_id for failure in failures} == {
        "requirement-ownership-mismatch",
        "traceability-missing-implements",
    }


def test_missing_traceability_links_are_reported(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    client = make_client()
    write_text(
        repo_root / "implementations" / "python" / "packages" / "raes_processor" / "new_binding.py",
        "VALUE = 1\n",
    )
    write_text(
        repo_root / "implementations" / "python" / "tests" / "test_new_binding.py",
        "def test_value():\n    assert True\n",
    )

    failures = evaluate_requirement_governance(
        repo_root,
        [
            "implementations/python/packages/raes_processor/new_binding.py",
            "implementations/python/tests/test_new_binding.py",
        ],
        client=client,
        requirement_uid="RUN-313",
    )

    assert {failure.rule_id for failure in failures} == {
        "traceability-missing-implements",
        "traceability-missing-tests",
    }


def test_requirement_governance_passes_for_allowed_paths_and_traceability(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    client = make_client()
    write_text(
        repo_root / "implementations" / "python" / "packages" / "raes_processor" / "bindings.py",
        "VALUE = 1\n",
    )
    write_text(
        repo_root / "implementations" / "python" / "tests" / "test_concept_authority.py",
        "def test_value():\n    assert True\n",
    )

    failures = evaluate_requirement_governance(
        repo_root,
        [
            "implementations/python/packages/raes_processor/bindings.py",
            "implementations/python/tests/test_concept_authority.py",
        ],
        client=client,
        requirement_uid="GOV-918",
    )

    assert failures == []


def test_experiment_core_requirement_maps_allowed_contract_paths(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    client = make_client()
    write_text(
        repo_root / "implementations" / "python" / "packages" / "raes_contracts" / "contracts.py",
        "VALUE = 1\n",
    )
    write_text(
        repo_root / "implementations" / "python" / "tests" / "test_runtime_contracts.py",
        "def test_value():\n    assert True\n",
    )

    failures = evaluate_requirement_governance(
        repo_root,
        [
            "contracts/schema-publication-manifest.json",
            "contracts/schemas/backend-manifest/backend-manifest-v2.json",
            "contracts/schemas/experiment-core/experiment-task-v1.json",
            "docs/research/experiment-core/traceability-matrix-exp-701-705.md",
            "implementations/python/packages/raes_contracts/contracts.py",
            "implementations/python/tests/test_runtime_contracts.py",
            "specs/formal/experiment-core/README.md",
        ],
        client=client,
        requirement_uid="EXP-701",
    )

    assert failures == []


def test_requirement_governance_accepts_camel_case_traceability_payload(tmp_path: Path) -> None:
    repo_root = setup_policy_repo(tmp_path)
    requirements = {
        "GOV-918": {"id": "req-gov-918", "uid": "GOV-918", "status": "ACTIVE"},
    }
    client = FakeClient(
        requirements=requirements,
        traceability={
            "req-gov-918": [
                {
                    "artifactIdentifier": "implementations/python/packages/raes_contracts/contracts.py",
                    "artifactType": "CODE_FILE",
                    "linkType": "IMPLEMENTS",
                },
                {
                    "artifactIdentifier": "implementations/python/tests/test_requirement_governance.py",
                    "artifactType": "TEST",
                    "linkType": "TESTS",
                },
            ]
        },
    )
    write_text(
        repo_root / "implementations" / "python" / "packages" / "raes_contracts" / "contracts.py",
        "VALUE = 1\n",
    )
    write_text(
        repo_root / "implementations" / "python" / "tests" / "test_requirement_governance.py",
        "def test_value():\n    assert True\n",
    )

    failures = evaluate_requirement_governance(
        repo_root,
        [
            "implementations/python/packages/raes_contracts/contracts.py",
            "implementations/python/tests/test_requirement_governance.py",
        ],
        client=client,
        requirement_uid="GOV-918",
    )

    assert failures == []


class _StubResponse:
    def __init__(self, payload: bytes = b'{"status":"ACTIVE"}') -> None:
        self._payload = payload

    def __enter__(self) -> _StubResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_resolve_timeout_seconds_defaults_and_env_override(monkeypatch) -> None:
    monkeypatch.delenv("GC_HTTP_TIMEOUT_SECONDS", raising=False)
    assert resolve_timeout_seconds() == 5.0

    monkeypatch.setenv("GC_HTTP_TIMEOUT_SECONDS", "12.5")
    assert resolve_timeout_seconds() == 12.5

    # A non-numeric or non-positive override falls back to the safe default
    # rather than disabling the timeout.
    monkeypatch.setenv("GC_HTTP_TIMEOUT_SECONDS", "not-a-number")
    assert resolve_timeout_seconds() == 5.0
    monkeypatch.setenv("GC_HTTP_TIMEOUT_SECONDS", "0")
    assert resolve_timeout_seconds() == 5.0


def test_ground_control_http_client_sends_bearer_auth(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_urlopen(request, *, timeout: float):
        captured["auth"] = request.get_header("Authorization")
        return _StubResponse()

    monkeypatch.setattr(requirement_governance, "urlopen", fake_urlopen)
    client = GroundControlHttpClient("http://ground-control.invalid", token="secret-token")

    assert client.get_requirement("project", "ASR-535") == {"status": "ACTIVE"}
    assert captured["auth"] == "Bearer secret-token"


def test_ground_control_http_client_omits_auth_without_token(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_urlopen(request, *, timeout: float):
        captured["auth"] = request.get_header("Authorization")
        return _StubResponse(b"{}")

    monkeypatch.setattr(requirement_governance, "urlopen", fake_urlopen)

    GroundControlHttpClient("http://ground-control.invalid").get_requirement("project", "ASR-1")
    assert captured["auth"] is None


@pytest.mark.parametrize("code", (401, 403))
def test_auth_rejection_raises_auth_required(monkeypatch, code: int) -> None:
    def failing_urlopen(_request, *, timeout: float):
        raise HTTPError("http://ground-control.invalid", code, "auth", None, BytesIO(b"authentication_required"))

    monkeypatch.setattr(requirement_governance, "urlopen", failing_urlopen)
    client = GroundControlHttpClient("http://ground-control.invalid", token="token")

    with pytest.raises(GroundControlAuthRequired, match=str(code)):
        client.get_requirement("project", "ASR-1")


def test_non_auth_http_error_raises_unavailable(monkeypatch) -> None:
    def failing_urlopen(_request, *, timeout: float):
        raise HTTPError("http://ground-control.invalid", 503, "down", None, BytesIO(b"offline"))

    monkeypatch.setattr(requirement_governance, "urlopen", failing_urlopen)
    client = GroundControlHttpClient("http://ground-control.invalid")

    # A 503 is transport-unavailable, not an auth rejection.
    with pytest.raises(GroundControlUnavailable, match="503: offline"):
        client.get_requirement("project", "ASR-1")
    # The two conditions are disjoint: an unavailable error must not be
    # catchable as an auth-required error.
    assert not issubclass(GroundControlUnavailable, GroundControlAuthRequired)


def test_resolve_base_url_prefers_env_then_mcp(monkeypatch, tmp_path: Path) -> None:
    write_text(
        tmp_path / ".mcp.json",
        json.dumps({"mcpServers": {"ground-control": {"env": {"GC_BASE_URL": "http://from-mcp:8000"}}}}),
    )

    monkeypatch.setenv("GC_BASE_URL", "http://from-env:8000")
    assert resolve_base_url(tmp_path) == "http://from-env:8000"

    monkeypatch.delenv("GC_BASE_URL")
    assert resolve_base_url(tmp_path) == "http://from-mcp:8000"


def test_resolve_base_url_is_none_without_env_or_mcp(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GC_BASE_URL", raising=False)
    # No .mcp.json in tmp_path and no baked-in gc-dev default.
    assert resolve_base_url(tmp_path) is None


def test_resolve_token_prefers_env_then_mcp(monkeypatch, tmp_path: Path) -> None:
    write_text(
        tmp_path / ".mcp.json",
        json.dumps({"mcpServers": {"ground-control": {"env": {"GROUND_CONTROL_API_TOKEN": "mcp-token"}}}}),
    )

    monkeypatch.setenv("GROUND_CONTROL_API_TOKEN", "env-token")
    assert resolve_token(tmp_path) == "env-token"

    monkeypatch.delenv("GROUND_CONTROL_API_TOKEN")
    assert resolve_token(tmp_path) == "mcp-token"


def test_report_unevaluated_skips_by_default(capsys) -> None:
    exit_code = report_unevaluated(
        rule_id="ground-control-unavailable",
        message="connection refused",
        require_governance=False,
        as_json=False,
    )
    assert exit_code == 0
    err = capsys.readouterr().err
    assert "ground-control-unavailable" in err
    assert "skipping governance check" in err


def test_report_unevaluated_fails_when_governance_required(capsys) -> None:
    exit_code = report_unevaluated(
        rule_id="ground-control-unavailable",
        message="connection refused",
        require_governance=True,
        as_json=False,
    )
    assert exit_code == 1
    assert "failing" in capsys.readouterr().err


def test_report_unevaluated_json_status_separates_skip_from_pass(capsys) -> None:
    exit_code = report_unevaluated(
        rule_id="ground-control-auth-required",
        message="401: authentication_required",
        require_governance=False,
        as_json=True,
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == [
        {
            "rule_id": "ground-control-auth-required",
            "message": "401: authentication_required",
            "path": None,
            "status": "skipped-unavailable",
        }
    ]


def test_env_flag_parses_truthy_and_falsy_values(monkeypatch) -> None:
    for truthy in ("1", "true", "YES", "on"):
        monkeypatch.setenv("GC_REQUIRE_GOVERNANCE", truthy)
        assert _env_flag("GC_REQUIRE_GOVERNANCE")

    monkeypatch.setenv("GC_REQUIRE_GOVERNANCE", "0")
    assert not _env_flag("GC_REQUIRE_GOVERNANCE")
    monkeypatch.delenv("GC_REQUIRE_GOVERNANCE")
    assert not _env_flag("GC_REQUIRE_GOVERNANCE")


def test_report_missing_uid_text_and_json(capsys) -> None:
    assert report_missing_uid(False) == 1
    assert "requirement-context-missing" in capsys.readouterr().err

    assert report_missing_uid(True) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["rule_id"] == "requirement-context-missing"


def test_classify_ground_control_error_distinguishes_auth_from_unavailable() -> None:
    auth_rule, auth_message = classify_ground_control_error(GroundControlAuthRequired("401: nope"))
    assert auth_rule == "ground-control-auth-required"
    assert "401" in auth_message

    down_rule, down_message = classify_ground_control_error(GroundControlUnavailable("connection refused"))
    assert down_rule == "ground-control-unavailable"
    assert down_message == "connection refused"


def test_emit_failures_returns_zero_when_empty(capsys) -> None:
    assert emit_failures([], as_json=False) == 0
    assert capsys.readouterr().err == ""


def test_emit_failures_reports_and_returns_one(capsys) -> None:
    assert emit_failures([PolicyFailure("rule-x", "boom")], as_json=False) == 1
    assert "rule-x" in capsys.readouterr().err


def test_evaluate_against_ground_control_config_missing_skips_by_default(monkeypatch, capsys) -> None:
    monkeypatch.setattr("tools.check_requirement_governance.resolve_base_url", lambda _root: None)
    exit_code = evaluate_against_ground_control([], "GOV-918", require_governance=False, as_json=False)
    assert exit_code == 0
    assert "ground-control-config-missing" in capsys.readouterr().err


def test_evaluate_against_ground_control_config_missing_fails_when_required(monkeypatch, capsys) -> None:
    monkeypatch.setattr("tools.check_requirement_governance.resolve_base_url", lambda _root: None)
    exit_code = evaluate_against_ground_control([], "GOV-918", require_governance=True, as_json=False)
    assert exit_code == 1
    assert "ground-control-config-missing" in capsys.readouterr().err

"""Tests for admitting exactly one declared reusable-workflow secret (#935).

These cover the narrow validator change that lets a caller pass one declared,
non-`inherit` secret to a local reusable workflow whose consuming job is itself
trust-gated, without weakening the untrusted-secret gate for step or OIDC
credentials.
"""

from __future__ import annotations

from implementations.tooling.action_policy_conditions import job_credential_classes
from implementations.tooling.action_policy_main import _local_call_differs, _target_contract_invalid

_USES = "./.github/workflows/reusable.yml"
_TARGET_PATH = ".github/workflows/reusable.yml"


def _target(*, secret_required: bool = False, declare_secret: bool = True) -> dict:
    call: dict = {"inputs": {"ref": {"required": True}}}
    if declare_secret:
        call["secrets"] = {"sonar_token": {"required": secret_required}}
    return {"on": {"workflow_call": call}, "jobs": {}}


def _caller_workflow() -> dict:
    return {"on": {"pull_request": {}}, "permissions": {"contents": "read"}}


def _caller_job(secrets: object = "declared") -> dict:
    job = {
        "uses": _USES,
        "with": {"ref": "x"},
        "permissions": {"contents": "read"},
    }
    if secrets == "declared":
        job["secrets"] = {"sonar_token": "${{ secrets.SONAR_TOKEN }}"}
    elif secrets is not None:
        job["secrets"] = secrets
    return job


def _expected(*, with_secret: bool = True) -> dict:
    expected = {
        "path": _USES,
        "inputs": {"ref": "x"},
        "permissions": {"contents": "read"},
    }
    if with_secret:
        expected["secrets"] = {"sonar_token": "${{ secrets.SONAR_TOKEN }}"}
    return expected


def _differs(job: dict, expected: dict, *, target: dict | None = None) -> bool:
    workflows = {_TARGET_PATH: target if target is not None else _target()}
    return _local_call_differs(workflows, _caller_workflow(), job, expected, _USES)


def test_declared_secret_mapping_is_admitted() -> None:
    assert _differs(_caller_job(), _expected()) is False


def test_secret_inherit_is_rejected() -> None:
    assert _differs(_caller_job(secrets="inherit"), _expected()) is True


def test_unlisted_secret_is_rejected() -> None:
    job = _caller_job(secrets={"enterprise_token": "${{ secrets.ENTERPRISE }}"})
    assert _differs(job, _expected()) is True


def test_passing_a_secret_the_policy_did_not_record_is_rejected() -> None:
    assert _differs(_caller_job(), _expected(with_secret=False)) is True


def test_recorded_secret_not_passed_is_rejected() -> None:
    assert _differs(_caller_job(secrets=None), _expected()) is True


def test_call_without_secrets_is_admitted() -> None:
    target = _target(declare_secret=False)
    assert _differs(_caller_job(secrets=None), _expected(with_secret=False), target=target) is False


def test_target_contract_admits_declared_optional_secret() -> None:
    assert _target_contract_invalid(_target(), _caller_job()) is False


def test_target_contract_requires_every_required_secret() -> None:
    assert _target_contract_invalid(_target(secret_required=True), _caller_job(secrets=None)) is True


def test_target_contract_rejects_undeclared_secret() -> None:
    job = _caller_job(secrets={"undeclared": "${{ secrets.X }}"})
    assert _target_contract_invalid(_target(declare_secret=False), job) is True


def test_reusable_caller_secret_is_not_a_caller_credential() -> None:
    # The declared reusable secret flows to a separately admitted workflow, so it
    # is not attributed to the untrusted caller's credential set.
    credentials, unsupported = job_credential_classes({}, _caller_job(), {"contents": "read"})
    assert "secret:sonar-token" not in credentials
    assert credentials == {"github-token"}
    assert unsupported is False


def test_non_reusable_job_env_secret_is_still_a_credential() -> None:
    # A secret in an ordinary job body (no `uses:`) is still scanned and flagged.
    job = {"runs-on": "ubuntu-24.04", "env": {"TOKEN": "${{ secrets.SONAR_TOKEN }}"}}
    credentials, _ = job_credential_classes({}, job, {"contents": "read"})
    assert "secret:sonar-token" in credentials

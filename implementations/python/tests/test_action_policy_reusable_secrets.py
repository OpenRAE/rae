"""Reusable workflow calls use the target's own input/secret contract."""

from tools.tooling_artifact_policy_actions import _target_contract_invalid


def _target(*, required: bool = False) -> dict:
    return {
        "on": {"workflow_call": {"inputs": {"ref": {"required": True}}, "secrets": {"token": {"required": required}}}}
    }


def test_declared_optional_secret_is_admitted() -> None:
    assert not _target_contract_invalid(_target(), {"with": {"ref": "sha"}, "secrets": {"token": "value"}})


def test_optional_secret_can_be_omitted() -> None:
    assert not _target_contract_invalid(_target(), {"with": {"ref": "sha"}})


def test_missing_required_secret_is_rejected() -> None:
    assert _target_contract_invalid(_target(required=True), {"with": {"ref": "sha"}})


def test_undeclared_secret_is_rejected() -> None:
    assert _target_contract_invalid(_target(), {"with": {"ref": "sha"}, "secrets": {"other": "value"}})


def test_secret_inherit_is_rejected() -> None:
    assert _target_contract_invalid(_target(), {"with": {"ref": "sha"}, "secrets": "inherit"})


def test_missing_required_input_is_rejected() -> None:
    assert _target_contract_invalid(_target(), {})


def test_undeclared_input_is_rejected() -> None:
    assert _target_contract_invalid(_target(), {"with": {"ref": "sha", "other": "value"}})


def test_non_reusable_target_is_rejected() -> None:
    assert _target_contract_invalid({"on": "push"}, {})

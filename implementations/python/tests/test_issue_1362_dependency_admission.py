"""The distributed extra participates in the governed installed closure."""

import json
from pathlib import Path

import pytest
from raes_contracts.errors import InvalidInputError
from tools.tooling_artifact_policy_common import validate_tooling_record
from tools.tooling_artifact_policy_python_profiles import _closure_binding_failures


def test_distributed_extra_is_admitted_while_unknown_extra_is_rejected():
    repo = Path(__file__).resolve().parents[3]
    profiles = json.loads((repo / "implementations/tooling/profiles/development-profiles.json").read_text())
    profile = profiles["python_closure_profiles"][0]
    assert "distributed" in profile["project_extras"]
    assert (
        _closure_binding_failures(
            profile, host_ids={profile["host_profile_id"]}, context_ids=["python-public"], project_scoped=True
        )
        == []
    )
    validate_tooling_record(repo, profiles, "implementations/tooling/profiles/development-profiles.json")
    profile["project_extras"].append("unreviewed-extra")
    with pytest.raises(InvalidInputError, match="invalid shape"):
        validate_tooling_record(repo, profiles, "implementations/tooling/profiles/development-profiles.json")

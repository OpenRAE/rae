"""Mapping work stays within the participant-crossing formal boundary."""

from pathlib import Path

import pytest
from test_requirement_governance import make_client, setup_policy_repo
from tools.policy.requirement_governance import evaluate_requirement_governance


@pytest.mark.parametrize(
    ("uid", "path", "allowed"),
    [
        ("SEM-232", "implementations/formal/participant_crossing/runtime_mapping.py", True),
        ("SEM-232", "implementations/formal/other_proof/unchecked.py", False),
        ("SEM-232", "implementations/python/packages/raes_runtime/participant_decision_surface_control_v2.py", False),
        ("API-404", "implementations/python/packages/raes_runtime/participant_decision_surface_control_v2.py", True),
    ],
)
def test_mapping_requirement_enforces_its_ownership_boundary(tmp_path: Path, uid: str, path: str, allowed: bool):
    root = setup_policy_repo(tmp_path)
    client = make_client()
    client.requirements["SEM-232"] = {"id": "req-sem-232", "uid": "SEM-232", "status": "DRAFT"}
    client.traceability["req-sem-232"] = []
    for name in ("RUN-314", "RUN-315", "API-404"):
        client.requirements[name] = {"id": "req-" + name, "uid": name, "status": "ACTIVE"}
        client.traceability["req-" + name] = []
    failures = evaluate_requirement_governance(root, [path], client=client, requirement_uid=uid)
    assert ("requirement-ownership-mismatch" not in {failure.rule_id for failure in failures}) is allowed

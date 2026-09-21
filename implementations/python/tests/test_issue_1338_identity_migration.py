"""Legacy participant migration requires source-bound organizational intent."""

from __future__ import annotations

import pytest
import yaml
from raes import parse_sdl
from raes.semantic_revisions import source_byte_digest
from raes_processor.compiler import compile_scenario_runtime_model
from test_issue_1338_participant_identity import _payload


def _legacy(*, organizational=True):
    payload = _payload()
    for agent in payload["agents"].values():
        agent["entity"] = agent.pop("affiliations")[0]
    objective = payload["objectives"]["goal"]
    objective.pop("owner")
    objective["entity" if organizational else "agent"] = "team" if organizational else "one"
    return payload


def _migrate(payload, *, decisions=None, digest=None):
    from raes.participant_migration import ParticipantIdentityMigrationContext, migrate_participant_identity

    source = yaml.safe_dump(payload)
    context = (
        None
        if decisions is None
        else ParticipantIdentityMigrationContext(
            source_digest=digest or source_byte_digest(source), entity_objectives=decisions
        )
    )
    return migrate_participant_identity(source, context=context)


def test_deterministic_legacy_assignment_and_affiliation_preserve_identity():
    payload = _legacy(organizational=False)
    result = _migrate(payload)
    assert result.succeeded
    assert result.output.agents["one"].affiliations == ["team"]
    assert result.output.objectives["goal"].assigned_participant == "one"
    assert result.output.objectives["goal"].owner is None
    assert payload["agents"]["one"]["entity"] == "team"
    assert result.report == _migrate(payload).report
    model = compile_scenario_runtime_model(result.output)
    assert model.participant_behaviors["participant.behavior.one"].role == "red"


@pytest.mark.parametrize("assignment", [None, "one"])
def test_organizational_intent_is_an_explicit_source_bound_decision(assignment):
    result = _migrate(_legacy(), decisions={"/objectives/goal": assignment})
    assert result.succeeded
    assert result.output.objectives["goal"].owner == "team"
    assert result.output.objectives["goal"].assigned_participant == assignment
    assert result.report.source_digest.startswith("sha256:")
    assert result.report.target_digest.startswith("sha256:")


@pytest.mark.parametrize(
    ("decisions", "digest", "code"),
    [
        (None, None, "decision-required"),
        ({}, None, "decision-required"),
        ({"/objectives/goal": None}, "sha256:" + "0" * 64, "source-mismatch"),
        ({"/objectives/goal": None, "/objectives/extra": None}, None, "decision-mismatch"),
    ],
)
def test_migration_refuses_absent_stale_or_extra_decisions_atomically(decisions, digest, code):
    result = _migrate(_legacy(), decisions=decisions, digest=digest)
    assert not result.succeeded
    assert result.output is None
    assert result.report.target_digest is None
    assert result.report.diagnostics[0].code == f"participant-migration.{code}"


@pytest.mark.parametrize("change", ["conflict", "unknown", "action", "assignment", "both-legacy", "import"])
def test_migration_never_guesses_or_drops_invalid_source(change):
    payload = _legacy()
    if change == "conflict":
        payload["agents"]["one"]["affiliations"] = ["team"]
    elif change == "unknown":
        payload["agents"]["one"]["hidden_field"] = "private-value-do-not-echo"
    elif change == "action":
        payload["objectives"]["goal"]["actions"] = ["private-value-do-not-echo"]
    elif change == "assignment":
        payload["objectives"]["goal"]["actions"] = ["observe"]
    elif change == "both-legacy":
        payload["objectives"]["goal"]["agent"] = "one"
    else:
        payload["imports"] = [{"path": "external.yaml", "namespace": "other"}]
    result = _migrate(payload, decisions={"/objectives/goal": "two" if change == "assignment" else None})
    assert result.output is None
    assert not result.succeeded
    assert "private-value-do-not-echo" not in result.report.model_dump_json()


def test_current_artifact_migration_is_idempotent():
    payload = _payload()
    result = _migrate(payload)
    assert result.succeeded
    assert result.output == parse_sdl(yaml.safe_dump(payload))
    second = _migrate(result.output.model_dump(mode="json", exclude_unset=True))
    assert second.succeeded
    assert second.report.target_digest == result.report.target_digest


def test_non_string_legacy_identifier_refuses_without_crashing():
    payload = _legacy()
    payload["objectives"][7] = payload["objectives"].pop("goal")
    result = _migrate(payload)
    assert not result.succeeded
    assert result.output is None


def test_unresolved_legacy_affiliation_requires_an_author_decision_before_migration():
    payload = _legacy(organizational=False)
    payload["variables"] = {"team": {"type": "string", "default": "team"}}
    payload["agents"]["one"]["entity"] = "${team}"
    result = _migrate(payload)
    assert not result.succeeded
    assert result.output is None
    assert result.report.diagnostics[0].code == "participant-migration.unresolved-reference"


def test_aliased_objectives_keep_independent_author_decisions():
    payload = _legacy()
    payload["objectives"]["second"] = payload["objectives"]["goal"]
    result = _migrate(payload, decisions={"/objectives/goal": "one", "/objectives/second": "two"})
    assert result.succeeded
    assert result.output.objectives["goal"].assigned_participant == "one"
    assert result.output.objectives["second"].assigned_participant == "two"

"""Issue #802 participant-control compatibility and migration tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from participant_crossing_fixtures import (
    PARTICIPANT,
    StaticCrossingResolver,
    action_plane,
    evidence,
    identity,
    policy_capable_target,
)
from raes import parse_sdl_file
from raes_backend_protocols.manifest import backend_manifest_from_v2_model
from raes_contracts.backend_profiles import BackendProfileModel
from raes_contracts.contracts import (
    BackendManifestV2Model,
    ParticipantImplementationManifestModel,
    RuntimeSnapshotEnvelopeModel,
)
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import (
    ControlPlaneSecurityConfig,
    ParticipantAudienceSubjectBinding,
)
from raes_runtime.control_plane_store import (
    ParticipantCrossingHistoryPresence,
    participant_crossing_history_presence,
)
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
HEADERS = {"authorization": "Bearer participant-reader"}


class _TrustedViewEvidenceResolver(StaticCrossingResolver):
    def resolve_participant_view_evidence(self, **coordinates: object):
        self.view_evidence_coordinates = coordinates
        return evidence()


class _AudienceAwareViewEvidenceResolver(StaticCrossingResolver):
    def __init__(self) -> None:
        super().__init__()
        self.audience_bindings: list[ParticipantAudienceSubjectBinding] = []

    def resolve_participant_view_evidence(
        self,
        *,
        audience_binding: ParticipantAudienceSubjectBinding,
        **coordinates: object,
    ):
        del coordinates
        self.audience_bindings.append(audience_binding)
        return evidence().model_copy(
            update={
                "audience_scope_ref": audience_binding.audience_scope_ref,
                "evidence_refs": [f"evidence:{audience_binding.audience_scope_ref}"],
            }
        )


class _MissingViewEvidenceResolver(StaticCrossingResolver):
    pass


def _security(*, audience_bound: bool) -> ControlPlaneSecurityConfig:
    return ControlPlaneSecurityConfig(
        bearer_tokens={
            "participant-reader": identity(
                audience_bound=audience_bound,
                participant_address=PARTICIPANT,
            )
        }
    )


def _governed_client(
    resolver: StaticCrossingResolver,
    *,
    audience_bound: bool = True,
) -> tuple[TestClient, object]:
    plane = action_plane(
        resolver,
        target=policy_capable_target(
            "participant_egress_projection",
            "participant_transformation",
        ),
    )
    return (
        TestClient(create_control_plane_app(plane, security=_security(audience_bound=audience_bound))),
        plane,
    )


@pytest.mark.parametrize(
    ("path", "interaction_kind", "projection_kind"),
    [
        (f"/participants/{PARTICIPANT}/status", "status-projection", "status"),
        (
            f"/participants/{PARTICIPANT}/episodes/episode-1/history",
            "history-projection",
            "history",
        ),
        (
            f"/participants/{PARTICIPANT}/context?view_ref=views.context.network.v1&episode_id=episode-1",
            "decision-surface-projection",
            "context",
        ),
    ],
)
def test_governed_http_views_use_authenticated_audience_and_trusted_evidence(
    path: str,
    interaction_kind: str,
    projection_kind: str,
) -> None:
    resolver = _TrustedViewEvidenceResolver()
    client, plane = _governed_client(resolver)
    source_snapshot = plane.snapshot

    response = client.get(
        path,
        headers={
            **HEADERS,
            "idempotency-key": f"issue-802-{projection_kind}",
            # Caller-authored policy/evidence coordinates are ignored.
            "x-participant-audience": "audience:attacker",
            "x-participant-policy-cut": "policy:attacker",
        },
    )

    assert response.status_code == 200
    assert resolver.view_evidence_coordinates == {
        "snapshot": source_snapshot,
        "participant_address": PARTICIPANT,
        "episode_id": "episode-1",
        "interaction_kind": interaction_kind,
        "projection_ref": f"runtime.visibility-projection.{projection_kind}.{PARTICIPANT}.v1",
        "audience_binding": identity(
            audience_bound=True,
            participant_address=PARTICIPANT,
        ).participant_audience_subjects[0],
    }
    crossing = plane.snapshot.participant_crossing_history[PARTICIPANT]
    assert [record["occurrence"]["stage"] for record in crossing] == ["requested", "decided"]
    assert crossing[-1]["occurrence"]["audience_scope_ref"] == evidence().audience_scope_ref


def test_governed_http_status_denies_unbound_reader_before_existence_disclosure() -> None:
    resolver = _TrustedViewEvidenceResolver()
    client, plane = _governed_client(resolver, audience_bound=False)

    known = client.get(f"/participants/{PARTICIPANT}/status", headers=HEADERS)
    unknown = client.get("/participants/participant.unknown/status", headers=HEADERS)

    assert known.status_code == unknown.status_code == 403
    assert known.json() == unknown.json() == {"detail": "forbidden"}
    assert plane.snapshot.participant_crossing_history == {}


def test_governed_http_evidence_selection_is_bound_to_authenticated_audience() -> None:
    resolver = _AudienceAwareViewEvidenceResolver()
    plane = action_plane(
        resolver,
        target=policy_capable_target(
            "participant_egress_projection",
            "participant_transformation",
        ),
    )
    audience_refs = ("audience:red-primary", "audience:red-observer")
    security = ControlPlaneSecurityConfig(
        bearer_tokens={
            "primary-reader": identity(audience_bound=True, audience_scope_ref=audience_refs[0]),
            "observer-reader": identity(audience_bound=True, audience_scope_ref=audience_refs[1]),
        }
    )
    client = TestClient(create_control_plane_app(plane, security=security))

    for index, token in enumerate(("primary-reader", "observer-reader")):
        response = client.get(
            f"/participants/{PARTICIPANT}/status",
            headers={
                "authorization": f"Bearer {token}",
                "idempotency-key": f"issue-802-audience-{index}",
            },
        )
        assert response.status_code == 200

    assert [binding.audience_scope_ref for binding in resolver.audience_bindings] == list(audience_refs)
    decisions = [
        item["occurrence"]
        for item in plane.snapshot.participant_crossing_history[PARTICIPANT]
        if item["occurrence"]["stage"] == "decided"
    ]
    assert [item["audience_scope_ref"] for item in decisions] == list(audience_refs)


def test_governed_http_rejects_ambiguous_authenticated_audience_before_resolution() -> None:
    resolver = _AudienceAwareViewEvidenceResolver()
    base_identity = identity(audience_bound=True)
    ambiguous_identity = replace(
        base_identity,
        participant_audience_subjects=(
            *base_identity.participant_audience_subjects,
            ParticipantAudienceSubjectBinding(
                participant_address=PARTICIPANT,
                audience_scope_ref="audience:red-observer",
            ),
        ),
    )
    plane = action_plane(
        resolver,
        target=policy_capable_target(
            "participant_egress_projection",
            "participant_transformation",
        ),
    )
    client = TestClient(
        create_control_plane_app(
            plane,
            security=ControlPlaneSecurityConfig(bearer_tokens={"ambiguous-reader": ambiguous_identity}),
        )
    )

    response = client.get(
        f"/participants/{PARTICIPANT}/status",
        headers={"authorization": "Bearer ambiguous-reader"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "participant audience binding is ambiguous"}
    assert resolver.audience_bindings == []
    assert plane.snapshot.participant_crossing_history == {}


def test_governed_http_status_fails_closed_without_trusted_resolver_evidence() -> None:
    client, plane = _governed_client(_MissingViewEvidenceResolver())

    response = client.get(f"/participants/{PARTICIPANT}/status", headers=HEADERS)

    assert response.status_code == 409
    assert response.json() == {"detail": "participant view crossing evidence is unavailable"}
    assert plane.snapshot.participant_crossing_history == {}


def test_runtime_snapshot_legacy_absence_is_distinct_from_explicit_empty() -> None:
    absent = {"entries": {}, "metadata": {}}
    explicit_empty = {"entries": {}, "participant_crossing_history": {}, "metadata": {}}
    governed = {
        "entries": {},
        "participant_crossing_history": {PARTICIPANT: [{"event_id": "crossing.1"}]},
        "metadata": {},
    }

    assert participant_crossing_history_presence(absent) is ParticipantCrossingHistoryPresence.ABSENT
    assert participant_crossing_history_presence(explicit_empty) is ParticipantCrossingHistoryPresence.PRESENT_EMPTY
    assert participant_crossing_history_presence(governed) is ParticipantCrossingHistoryPresence.PRESENT


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_sdl_migration_fixture_preserves_legacy_scenario_without_inferred_inject() -> None:
    fixture_dir = REPO_ROOT / "contracts" / "fixtures" / "sdl" / "sdl-yaml-v1" / "valid" / "migration"
    before = fixture_dir / "participant-control-legacy-before.yaml"
    after = fixture_dir / "participant-control-opt-in-after.yaml"

    assert before.read_bytes() == after.read_bytes()
    scenario = parse_sdl_file(after)
    assert scenario.name == "participant-control-legacy"
    assert not scenario.injects


def test_runtime_snapshot_fixture_preserves_incumbent_history_without_claim_promotion(tmp_path: Path) -> None:
    fixture_dir = REPO_ROOT / "contracts" / "fixtures" / "snapshots" / "runtime-snapshot-v1" / "migration"
    before = _json(fixture_dir / "participant-control-legacy-before.json")
    after = _json(fixture_dir / "participant-control-opt-in-after.json")

    RuntimeSnapshotEnvelopeModel.model_validate(before)
    RuntimeSnapshotEnvelopeModel.model_validate(after)
    (tmp_path / "snapshot.json").write_text(json.dumps(before), encoding="utf-8")
    legacy_snapshot = LocalControlPlaneStore(tmp_path).load_snapshot()
    backups = list(tmp_path.glob("legacy-json-backup-*/snapshot.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == before
    assert json.loads((tmp_path / "snapshot.json").read_text(encoding="utf-8")) == before
    assert (tmp_path / "control-plane.sqlite3").is_file()
    assert participant_crossing_history_presence(before) is ParticipantCrossingHistoryPresence.ABSENT
    assert participant_crossing_history_presence(after) is ParticipantCrossingHistoryPresence.PRESENT_EMPTY
    assert legacy_snapshot.participant_crossing_history == {}
    assert legacy_snapshot.participant_behavior_history == before["participant_behavior_history"]
    assert after["participant_behavior_history"] == before["participant_behavior_history"]
    assert "policy-noninterference" not in json.dumps(after)


def test_backend_manifest_fixture_pair_uses_existing_feature_strength_adapter() -> None:
    fixture_dir = REPO_ROOT / "contracts" / "fixtures" / "backend-manifest" / "backend-manifest-v2" / "valid"
    legacy_model = BackendManifestV2Model.model_validate(_json(fixture_dir / "stub.json"))
    opt_in_model = BackendManifestV2Model.model_validate(_json(fixture_dir / "feature-support-bounded.json"))
    legacy = backend_manifest_from_v2_model(legacy_model)
    opt_in = backend_manifest_from_v2_model(opt_in_model)

    assert legacy.identity.name == opt_in.identity.name == "stub"
    assert (legacy.identity.version, opt_in.identity.version) == ("0.3.0", "0.2.0")
    assert "participant-crossing-occurrence-v1" in opt_in.supported_contract_versions
    declarations = {
        item.feature: item
        for item in opt_in.participant_runtime.feature_support  # type: ignore[union-attr]
    }
    assert declarations["participant_transformation"].support_level.value == "bounded"
    assert declarations["participant_transformation"].evidence_refs


def test_participant_manifest_fixture_pair_keeps_api_423_assurance_out_of_participant_view() -> None:
    fixture_dir = (
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "participant-implementation-manifest"
        / "participant-implementation-manifest-v1"
        / "valid"
    )
    legacy = ParticipantImplementationManifestModel.model_validate(
        _json(fixture_dir / "participant-control-legacy.json")
    )
    opt_in = ParticipantImplementationManifestModel.model_validate(_json(fixture_dir / "reference.json"))

    assert legacy.identity == opt_in.identity
    assert "participant-decision-surface-v2" not in legacy.supported_contract_versions
    assert "participant-decision-surface-v2" in opt_in.supported_contract_versions
    assert "participant-crossing-occurrence-v1" not in opt_in.supported_contract_versions


def test_backend_profile_fixture_pair_makes_required_crossing_contract_explicit() -> None:
    profile_dir = REPO_ROOT / "contracts" / "profiles" / "backend"
    legacy = BackendProfileModel.model_validate(_json(profile_dir / "provisioning-only.json"))
    required = BackendProfileModel.model_validate(_json(profile_dir / "full-remote-control-plane.json"))

    assert "participant-crossing-occurrence-v1" not in legacy.required_contracts
    assert {
        "participant-control-occurrence-v1",
        "participant-crossing-occurrence-v1",
    } <= set(required.required_contracts)

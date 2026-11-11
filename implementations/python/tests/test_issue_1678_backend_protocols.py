"""Backend protocol failures follow the exception and logging policy (issue #1678).

Absent governed objects raise a category. Diagnostics that a backend protocol
builds from a failed validation do not repeat the text of that validation, so
they cannot disclose rejected payload, stored-state or native-outcome values.
A defect inside a check is not reported as a domain refusal.
"""

from __future__ import annotations

import pytest
from raes_backend_protocols import service_materialization
from raes_backend_protocols.domain_topology import domain_topology_plan_diagnostics
from raes_backend_protocols.participant_execution_service import participant_execution_state
from raes_backend_stubs.manifest import create_stub_manifest
from raes_backend_stubs.stubs import StubParticipantRuntime
from raes_contracts.contracts import ParticipantActionResultModel
from raes_contracts.diagnostics import DiagnosticModel
from raes_contracts.errors import NotFoundError
from raes_contracts.participant_binding import ParticipantNativeActionExecution
from raes_contracts.participant_episode import (
    ParticipantEpisodeInitializeRequest,
    ParticipantEpisodeTerminateRequest,
)
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from tool_profile_support import ACTIVE, BLUE, BLUE_VIEW, admission_request

_SECRET = "backend-protocol-secret-sentinel-91c2"
_MESSAGE_LIMIT = DiagnosticModel.model_json_schema()["properties"]["message"]["maxLength"]


def test_missing_participant_execution_scope_is_not_found() -> None:
    snapshot = RuntimeSnapshot()
    with pytest.raises(NotFoundError, match="participant execution scope is not configured"):
        participant_execution_state("participant-execution.missing", snapshot)
    runtime = StubParticipantRuntime()
    snapshot = RuntimeSnapshot()
    with pytest.raises(NotFoundError):
        runtime.execution_state("participant-execution.missing", snapshot)


def _controller_operation(profile: object) -> ProvisionOp:
    return ProvisionOp(
        action=ChangeAction.CREATE,
        address="provision.node.dc-0",
        resource_type="node",
        payload={
            "domain_topology": {
                "domain_id": "corp",
                "profile": profile,
                "dns_name": "corp.example",
                "netbios_name": "CORP",
                "authority_account_address": "provision.account.admin",
                "role": "controller",
                "controller_addresses": ["provision.node.dc-0"],
            }
        },
    )


def test_invalid_domain_profile_binding_diagnostic_is_value_free() -> None:
    # Regression: the diagnostic once embedded the profile validation error, which repeats the input values.
    profile = {"binding_id": _SECRET, "value": {"password": _SECRET}}

    diagnostics = domain_topology_plan_diagnostics(ProvisioningPlan(operations=[_controller_operation(profile)]))

    invalid = [item for item in diagnostics if item.code == "provisioning.domain-topology.binding-invalid"]
    assert [item.message for item in invalid] == [
        "Domain topology binding is invalid: DomainTopologyBinding.profile must be a valid domain profile binding."
    ]
    assert all(_SECRET not in item.message and len(item.message) <= _MESSAGE_LIMIT for item in diagnostics)


def test_corrupt_participant_episode_state_diagnostic_is_value_free() -> None:
    # Regression: the rejection once embedded the enum error, which repeats the stored status value.
    runtime = StubParticipantRuntime()
    address = "participant.behavior.analyst"
    started = runtime.initialize(ParticipantEpisodeInitializeRequest(participant_address=address), RuntimeSnapshot())
    results = {key: dict(value) for key, value in started.snapshot.participant_episode_results.items()}
    results[address]["status"] = _SECRET
    corrupt = started.snapshot.with_entries(dict(started.snapshot.entries), participant_episode_results=results)

    result = runtime.terminate(ParticipantEpisodeTerminateRequest(participant_address=address), corrupt)

    assert not result.success
    assert [(item.code, item.message) for item in result.diagnostics] == [
        ("runtime.participant-runtime.rejected", "current state is invalid")
    ]


class _ContradictingRuntime(StubParticipantRuntime):
    """Publish a native outcome for a different action instance than the admitted binding."""

    @staticmethod
    def _model_action(request, snapshot, *, episode_id):
        outcome = ParticipantActionResultModel.model_validate(
            {
                "status": "succeeded",
                "participant_address": request.participant_address,
                "episode_id": episode_id,
                "action_instance_id": "scan-other",
                "action_contract_address": request.action_contract_address,
                "observation_point": "episode-step:scan-other:terminal-observation",
                "preconditions": [
                    {
                        "precondition_id": "authority-in-scope",
                        "precondition_class": "authority",
                        "status": "satisfied",
                        "participant_address": request.participant_address,
                        "episode_id": episode_id,
                        "action_contract_address": request.action_contract_address,
                        "observation_point": "episode-step:scan-other:attempt",
                    }
                ],
                "effects": [
                    {"effect_id": "no-effect", "effect_class": "no_effect", "description": "no environment effect"}
                ],
            }
        )
        return ParticipantNativeActionExecution(
            apply_result=ApplyResult(success=True, snapshot=snapshot), action_result=outcome
        )


def test_contradicting_native_outcome_diagnostic_omits_validation_text() -> None:
    runtime = _ContradictingRuntime()
    started = runtime.initialize(ParticipantEpisodeInitializeRequest(participant_address=BLUE), RuntimeSnapshot())

    result = runtime.admit_action(admission_request(BLUE, ACTIVE, BLUE_VIEW), started.snapshot)

    assert not result.success
    assert result.action_result is None
    assert [(item.code, item.message) for item in result.diagnostics] == [
        (
            "runtime.participant-autonomous-native-outcome-mismatch",
            "Native action outcome contradicts its autonomous binding.",
        )
    ]


def _content_placement(selection: object) -> ProvisioningPlan:
    operation = ProvisionOp(
        action=ChangeAction.CREATE,
        address="provision.content.site",
        resource_type="content-placement",
        payload={"spec": {"type": "file", "service_materialization": selection}},
    )
    return ProvisioningPlan(operations=[operation])


def test_malformed_private_service_binding_is_an_unsupported_profile() -> None:
    plan = _content_placement({"binding_id": _SECRET})

    diagnostics = service_materialization.service_materialization_plan_diagnostics(
        plan, create_stub_manifest().provisioner, None
    )

    assert [(item.code, item.message) for item in diagnostics] == [
        (
            "provisioner.unsupported-service-materialization-profile",
            "Provisioner does not support the selected service materialization profile.",
        )
    ]


def test_defect_in_private_service_binding_is_not_an_unsupported_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: a TypeError catch once reported any defect in this check as an unsupported profile.
    def defective(_value: object) -> None:
        raise TypeError("binding-reader-defect")

    monkeypatch.setattr(service_materialization, "profile_selection_binding", defective)

    placement = _content_placement({"binding_id": "binding"})
    provisioner = create_stub_manifest().provisioner
    with pytest.raises(TypeError, match="binding-reader-defect"):
        service_materialization.service_materialization_plan_diagnostics(placement, provisioner, None)


def test_concurrent_admission_records_every_failure_after_the_first(caplog: pytest.LogCaptureFixture) -> None:
    # Regression: a failure after the first one in a concurrent batch was dropped without a record.
    class FailingRuntime(StubParticipantRuntime):
        def admit_action(self, request, snapshot):
            raise RuntimeError(f"{request} failed with {_SECRET}")

    runtime = FailingRuntime()
    baseline = RuntimeSnapshot()
    with caplog.at_level("WARNING"), pytest.raises(RuntimeError, match="first"):
        runtime.admit_actions_concurrently(("first", "second"), baseline, 2)

    records = [record for record in caplog.records if record.name.startswith("raes_backend_protocols")]
    assert len(records) == 1
    assert records[0].levelname == "WARNING"
    assert _SECRET not in records[0].getMessage()
    assert _SECRET not in (records[0].exc_text or "")
    assert "ForeignCodeFailure" in (records[0].exc_text or "")

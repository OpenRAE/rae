"""Deterministic participant-proof fixtures for participant-crossing tests.

These fixtures build from ``raes_contracts`` plus small structural ``Protocol``
types that name the compiled-model shapes without importing the concrete
processor classes. They build the deterministic participant-implementation
manifest, selection, typed action result, and admission request from
compiled-model objects passed in by the caller (duck-typed).

The identities here are structural-proof placeholders (synthetic digests): no live
agent is installed and no live domain executes. ``WITHHELD_REFS`` are the
evaluator-only / internal surfaces the participant must never observe; they are the
source of the negative-boundary evidence these tests assert.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from raes_contracts.contracts import (
    ParticipantActionResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest


class ActionContract(Protocol):
    """Compiled action contract surface read by the proof builder."""

    spec: Mapping[str, Any]


class ParticipantBehavior(Protocol):
    """Compiled participant behavior surface read by the lifecycle/proof builders."""

    observation_boundary_addresses: Sequence[str]
    action_contract_addresses: Sequence[str]


class ObservationBoundary(Protocol):
    """Compiled observation boundary surface read by the boundary/admission builders."""

    spec: Mapping[str, Any] | None
    view_transitions: Sequence[Any]


AGENT_IDENTITY = {"name": "libvirt-deterministic-agent", "version": "1.0.0"}
MANIFEST_REF = "contracts/fixtures/participant-implementation-manifest/libvirt-deterministic.json"
MANIFEST_DIGEST = "sha256:" + "1" * 64
POLICY_ID = "libvirt-participant-agent-policy"
POLICY_VERSION = "1.0.0"
POLICY_DIGEST = "sha256:" + "3" * 64

# Refs the participant must never observe: evaluator internals, the internal DB,
# Wazuh, and the policy gate. The exposure policy withholds them.
WITHHELD_REFS = (
    "content.evaluator-notes",
    "nodes.customer-db.services.postgres",
    "nodes.wazuh-manager",
    "nodes.wazuh-indexer",
    "nodes.participant-policy-gate",
)

_PROOF_EPISODE_ID = "proof-ep-1"


def build_implementation_manifest() -> ParticipantImplementationManifestModel:
    """Return the deterministic participant-implementation manifest."""
    return ParticipantImplementationManifestModel.model_validate(
        {
            "schema_version": "participant-implementation-manifest/v1",
            "identity": AGENT_IDENTITY,
            "implementation_kind": "agent",
            "supported_contract_versions": [
                "participant-implementation-manifest-v1",
                "participant-implementation-provenance-v1",
                "participant-episode-state-envelope-v1",
                "participant-episode-history-event-stream-v1",
                "participant-behavior-history-event-stream-v1",
            ],
            "compatibility": {
                "participant_runtimes": ["libvirt-qemu"],
                "processors": ["raes-reference-processor"],
                "backends": ["libvirt-qemu"],
            },
            "concept_bindings": [
                {"scope": "implementation_kind", "family": "apparatus-declarations"},
                {"scope": "capabilities.supported_participant_contracts", "family": "apparatus-declarations"},
                {"scope": "capabilities.supported_decision_surface_modes", "family": "apparatus-declarations"},
                {"scope": "capabilities.tool_affordance_expectations", "family": "tools-and-artifacts"},
                {"scope": "capabilities.exposure_policy_kinds", "family": "provenance-and-evidence"},
            ],
            "constraints": {
                "max_parallel_episodes": "1",
                "simulation_disclosure": "deterministic-simulation: no live libvirt domain execution",
            },
            "capabilities": {
                "supported_participant_contracts": [
                    "participant-episode-state-envelope-v1",
                    "participant-episode-history-event-stream-v1",
                    "participant-behavior-history-event-stream-v1",
                ],
                "supported_decision_surface_modes": ["policy-directed"],
                "tool_affordance_expectations": ["http-api"],
                "exposure_policy_kinds": ["task-statement", "observation-stream"],
            },
        }
    )


def build_implementation_selection(
    participant_address: str,
    withheld_refs: tuple[str, ...] = WITHHELD_REFS,
) -> ParticipantImplementationSelectionModel:
    """Return the deterministic participant-implementation selection."""
    return ParticipantImplementationSelectionModel.model_validate(
        {
            "participant_address": participant_address,
            "implementation_identity": AGENT_IDENTITY,
            "manifest_ref": MANIFEST_REF,
            "manifest_digest": MANIFEST_DIGEST,
            "selected_decision_surface_mode": "policy-directed",
            "participant_contract_versions": [
                "participant-episode-state-envelope-v1",
                "participant-behavior-history-event-stream-v1",
            ],
            "exposure_policy": {
                "policy_id": POLICY_ID,
                "policy_version": POLICY_VERSION,
                "policy_digest": POLICY_DIGEST,
                "exposure_policy_kinds": ["task-statement", "observation-stream"],
                "disclosed_refs": [],
                "withheld_refs": list(withheld_refs),
                "tool_affordance_refs": [],
                "visibility_scope_refs": [],
            },
        }
    )


def build_action_result(
    *,
    participant_address: str,
    episode_id: str,
    action_instance_id: str,
    action_contract_address: str,
    contract_spec: Mapping[str, object],
) -> ParticipantActionResultModel:
    """Build a deterministic succeeded action_result for a compiled action contract.

    Reports every declared precondition (with empty support/evidence refs) to
    satisfy the SEM-211 completeness requirement, and only ``no_effect`` effects
    (which need no target/evidence refs), so the result never introduces a
    hidden-ref or boundary-evidence violation.
    """
    preconditions = []
    for pc in contract_spec.get("preconditions", ()):
        if not isinstance(pc, Mapping) or not pc.get("precondition_id") or not pc.get("precondition_class"):
            continue
        preconditions.append(
            {
                "precondition_id": str(pc["precondition_id"]),
                "precondition_class": str(pc["precondition_class"]),
                "status": "satisfied",
                "participant_address": participant_address,
                "episode_id": episode_id,
                "action_contract_address": action_contract_address,
                "observation_point": f"{action_instance_id}:pc-{pc['precondition_id']}",
                "support_refs": [],
                "evidence_refs": [],
            }
        )

    effects = []
    for eff in contract_spec.get("effects", ()):
        if not isinstance(eff, Mapping) or not eff.get("effect_id") or not eff.get("effect_class"):
            continue
        if str(eff["effect_class"]) == "no_effect":
            effects.append(
                {
                    "effect_id": str(eff["effect_id"]),
                    "effect_class": "no_effect",
                    "description": str(eff.get("description", "No domain effect in deterministic proof.")),
                }
            )

    return ParticipantActionResultModel.model_validate(
        {
            "status": "succeeded",
            "participant_address": participant_address,
            "episode_id": episode_id,
            "action_instance_id": action_instance_id,
            "action_contract_address": action_contract_address,
            "observation_point": f"{action_instance_id}:terminal-observation",
            "preconditions": preconditions,
            "effects": effects,
            "observations": [f"{action_instance_id}:terminal-observation"],
            "evidence_refs": [],
        }
    )


def contract_uses_sem211_action_results(contract: ActionContract) -> bool:
    """Return True when a compiled action contract declares SEM-211 typed classes.

    Duck-typed equivalent of the processor-internal gate, so callers outside the
    processor layer can decide whether to attach a typed ``action_result``.
    """
    return bool(
        getattr(contract, "precondition_classes", None)
        or getattr(contract, "effect_classes", None)
        or getattr(contract, "failure_classes", None)
    )


def iter_admission_pairs(
    behavior: ParticipantBehavior, observation_boundaries: Mapping[str, ObservationBoundary]
) -> list[tuple[str, str]]:
    """Return (action_address, action_instance_id) pairs to admit for one behavior.

    View-transition anchors pin specific action_instance_ids (the behavior-history
    validator checks each anchor resolves to a real OBSERVATION_EMITTED event);
    otherwise fall back to one generated id per declared action contract.
    """
    required: list[str] = []
    for ba in behavior.observation_boundary_addresses:
        boundary = observation_boundaries.get(ba)
        if boundary is None:
            continue
        for vt in boundary.view_transitions:
            aid = vt.get("action_instance_id") if isinstance(vt, dict) else getattr(vt, "action_instance_id", None)
            if aid and aid not in required:
                required.append(aid)
    first_action_address = next(iter(behavior.action_contract_addresses), None)
    if required and first_action_address is not None:
        return [(first_action_address, aid) for aid in required]
    return [(addr, f"proof-action-{i + 1:04d}") for i, addr in enumerate(behavior.action_contract_addresses)]


def build_participant_admission_request(
    *,
    behavior_address: str,
    action_address: str,
    action_instance_id: str,
    boundary_address: str,
    contract: ActionContract,
    episode_id: str = _PROOF_EPISODE_ID,
) -> ParticipantActionAdmissionRequest:
    """Build a deterministic participant action admission request for the proof.

    Attaches a typed ``action_result`` only when the contract declares SEM-211
    classes. ``visible_refs``/``disclosed_refs`` are empty: the admission surface
    exposes nothing of the internal or evaluator state.
    """
    action_result = None
    if contract_uses_sem211_action_results(contract):
        action_result = build_action_result(
            participant_address=behavior_address,
            episode_id=episode_id,
            action_instance_id=action_instance_id,
            action_contract_address=action_address,
            contract_spec=contract.spec,
        )
    return ParticipantActionAdmissionRequest(
        participant_address=behavior_address,
        action_contract_address=action_address,
        observation_boundary_address=boundary_address,
        action_instance_id=action_instance_id,
        implementation_manifest=build_implementation_manifest(),
        implementation_selection=build_implementation_selection(behavior_address),
        visible_refs=(),
        disclosed_refs=(),
        evidence_refs=(),
        observation_boundary_evidence_refs=(),
        action_result=action_result,
    )

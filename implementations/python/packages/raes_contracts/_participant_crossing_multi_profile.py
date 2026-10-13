"""Closed vocabulary for the separately governed two-operation profile."""

from typing import Literal, Self

from pydantic import Field, StrictInt, field_validator, model_validator

from ._participant_crossing_profile import HIDDEN
from ._participant_opacity_common import SafeRef
from .contracts.base import ContractModel, PrefixedDigestString

INPUTS = ("plain", "transform", "declassify", "unsupported", "forbidden", "unresolved")
OUTCOMES = ("permit", "deny", "unsupported", "transform", "declassify", "unresolved")
VISIBLE = tuple(
    sorted(
        ("policy.cut.advance", "runtime.restart")
        + tuple(f"crossing.request.{mode}.{key}" for mode in ("fresh", "retry") for key in "ab")
        + tuple(
            f"crossing.{event}.{key}"
            for event in (
                "decision.permit",
                "decision.deny",
                "decision.unsupported",
                "decision.unresolved",
                "transform",
                "declassify",
                "delivery",
                "replay.reject",
                "outcome.unknown",
                "status.completed",
                "status.failed",
            )
            for key in "ab"
        )
        + tuple(f"crossing.result.{outcome}.{key}" for outcome in OUTCOMES for key in "ab")
    )
)
DOMAINS = {
    "participant": ["participant-0"],
    "audience": ["audience-0"],
    "controller": ["controller-0"],
    "episode": ["episode-0"],
    "actor": ["actor-0"],
    "authority": ["authority-0"],
    "target": ["target-0"],
    "run": ["run-0"],
    "operation_kind": ["participant-crossing"],
    "idempotency_key": ["key-a", "key-b"],
    "operation_id": ["operation-a", "operation-b"],
    "receipt_id": ["receipt-a", "receipt-b"],
    "attempt_role": ["fresh-attempt", "retry-attempt"],
    "policy_cut": ["p0", "p1"],
    "input_class": list(INPUTS),
    "request_body": ["original", "changed"],
    "decision": ["none", *OUTCOMES],
    "replay": ["fresh", "retry"],
    "history_head": ["h0", "h1", "h2"],
    "effect_count": ["e0", "e1", "e2"],
    "knowledge": ["k0", "k1", "k2", "k3"],
    "gate": ["unresolved", "permit", "deny"],
    "capability": ["unresolved", "supported", "unsupported"],
    "abstract_phase": ["idle", "offered", "decided", "delivering", "responding"],
    "concrete_phase": [
        "idle",
        "validating",
        "resolving-cut",
        "resolving-capability",
        "gating",
        "preparing-record",
        "committing",
        "delivering",
        "responding",
    ],
}


def _domain(name):
    return Field(json_schema_extra={"const": DOMAINS[name]})


class MultiCrossingDomainsModel(ContractModel):
    participant: tuple[SafeRef, ...] = _domain("participant")
    audience: tuple[SafeRef, ...] = _domain("audience")
    controller: tuple[SafeRef, ...] = _domain("controller")
    episode: tuple[SafeRef, ...] = _domain("episode")
    actor: tuple[SafeRef, ...] = _domain("actor")
    authority: tuple[SafeRef, ...] = _domain("authority")
    target: tuple[SafeRef, ...] = _domain("target")
    run: tuple[SafeRef, ...] = _domain("run")
    operation_kind: tuple[SafeRef, ...] = _domain("operation_kind")
    idempotency_key: tuple[SafeRef, ...] = _domain("idempotency_key")
    operation_id: tuple[SafeRef, ...] = _domain("operation_id")
    receipt_id: tuple[SafeRef, ...] = _domain("receipt_id")
    attempt_role: tuple[SafeRef, ...] = _domain("attempt_role")
    policy_cut: tuple[SafeRef, ...] = _domain("policy_cut")
    input_class: tuple[SafeRef, ...] = _domain("input_class")
    request_body: tuple[SafeRef, ...] = _domain("request_body")
    decision: tuple[SafeRef, ...] = _domain("decision")
    replay: tuple[SafeRef, ...] = _domain("replay")
    history_head: tuple[SafeRef, ...] = _domain("history_head")
    effect_count: tuple[SafeRef, ...] = _domain("effect_count")
    knowledge: tuple[SafeRef, ...] = _domain("knowledge")
    gate: tuple[SafeRef, ...] = _domain("gate")
    capability: tuple[SafeRef, ...] = _domain("capability")
    abstract_phase: tuple[SafeRef, ...] = _domain("abstract_phase")
    concrete_phase: tuple[SafeRef, ...] = _domain("concrete_phase")

    @model_validator(mode="after")
    def _complete_domains(self) -> Self:
        if self.model_dump(mode="json") != DOMAINS:
            raise ValueError("multi-operation domains must be complete and exact")
        return self


class MultiAbstractCarrierModel(ContractModel):
    model_id: Literal["sem-230-participant-crossing-multi-abstract"]
    revision: Literal["rev1"]
    source_path: Literal["implementations/formal/participant_crossing/multi_abstract.py"]
    source_digest: PrefixedDigestString
    initial_state_ordinal: StrictInt = Field(ge=0, le=0)


class MultiConcreteCarrierModel(ContractModel):
    model_id: Literal["api-423-run-319-crossing-multi-kernel"]
    revision: Literal["rev1"]
    source_path: Literal["implementations/formal/participant_crossing/multi_concrete.py"]
    source_digest: PrefixedDigestString
    initial_state_ordinal: StrictInt = Field(ge=0, le=0)


class MultiParticipantCrossingParametersModel(ContractModel):
    kind: Literal["participant-crossing-multi-dpbb/v1"]
    domains: MultiCrossingDomainsModel
    left: MultiAbstractCarrierModel
    right: MultiConcreteCarrierModel
    visible_labels: tuple[SafeRef, ...] = Field(json_schema_extra={"const": list(VISIBLE)})
    hidden_labels: tuple[SafeRef, ...] = Field(json_schema_extra={"const": list(HIDDEN)})
    checker_tau: Literal["internal"]
    complete_carrier: Literal[True]
    depth_or_sample_bound: None
    fresh_operations: StrictInt = Field(ge=2, le=2)
    identity_reuse: Literal["conflict-only-no-recycling"]
    order: Literal["sequential-total-order"]
    time: Literal["untimed"]
    probability: Literal["excluded"]
    concurrency: Literal["excluded"]
    controller_handoff: Literal["excluded"]
    completion: Literal["cached-result-observation"]
    failure_scope: Literal["response-loss-after-durable-completion-and-clean-p1-restart"]
    history_scope: Literal["crossing-batch-heads-other-histories-fixed"]
    context_scope: Literal["synthetic-fixed-authority-with-exact-request-commitments"]

    @field_validator("complete_carrier", mode="before")
    @classmethod
    def _require_complete_carrier(cls, value: object) -> bool:
        if value is not True:
            raise ValueError("complete_carrier must be the JSON boolean true")
        return True

    @model_validator(mode="after")
    def _closed_labels_and_sources(self) -> Self:
        if self.visible_labels != VISIBLE or self.hidden_labels != HIDDEN:
            raise ValueError("multi-operation labels must match the exact projection")
        if self.left.source_digest == self.right.source_digest:
            raise ValueError("crossing transition authorities must have independent source identities")
        return self


MULTI_JOIN = {
    "profile_id": "participant-crossing-multi-operation-dpbb-finite-v1",
    "profile_revision": "rev1",
    "taxonomy_revision": "rev8",
    "relation_id": "divergence-preserving-branching-bisimulation",
    "left_carrier_ref": "sem-230-participant-crossing-multi-abstract",
    "observation_projection_ref": "participant-crossing-multi-operation-projection",
    "observation_projection_revision": "rev1",
    "finite_analysis_scope": "declared-complete-finite-carrier",
}


def validate_multi_crossing_profile_join(profile) -> None:
    if any(getattr(profile, key) != value for key, value in MULTI_JOIN.items()):
        raise ValueError("multi-operation profile coordinates do not match its parameters")


def multi_crossing_profile_schema_join() -> dict:
    return {
        "if": {
            "properties": {
                "parameters": {
                    "properties": {"kind": {"const": "participant-crossing-multi-dpbb/v1"}},
                    "required": ["kind"],
                }
            },
            "required": ["parameters"],
        },
        "then": {"properties": {key: {"const": value} for key, value in MULTI_JOIN.items()}},
    }

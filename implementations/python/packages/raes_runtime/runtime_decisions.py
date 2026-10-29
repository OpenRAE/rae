"""Closed provider-private decisions; never arbitrary snapshot metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from raes_contracts.augmentation_preparation import AugmentationPreparation
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.backend_operation import OperationGuarantee
from raes_contracts.errors import ConflictError
from raes_contracts.planning import RuntimeDomain

from .runtime_sequence_reference import RuntimeSequenceDecision
from .runtime_trial_decisions import (
    ExperimentCancellationDecision,
    ExperimentDecision,
    TrialArchiveDecision,
    TrialAttemptDecision,
    TrialInterruptionDecision,
    TrialObservationDecision,
    TrialReplacementDecision,
    TrialTerminalDecision,
)

DecisionIdentity = Annotated[str, Field(strict=True, min_length=1, max_length=256)]
DecisionDigest = Annotated[str, Field(strict=True, pattern=r"^sha256:[a-f0-9]{64}$")]


if TYPE_CHECKING:
    from .control_plane_store import ControlPlaneStore


class RunContextDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    schema_version: Literal["runtime-run-decision/v1"] = "runtime-run-decision/v1"
    run_scope: Annotated[str, Field(strict=True, pattern=r"^run:\S.{0,250}$")]
    store_digest: DecisionDigest
    status: Literal["opened", "retired"]

    @property
    def decision_id(self) -> str:
        return canonical_json_digest((self.schema_version, self.run_scope, self.status))


class RunOperationGuaranteesDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    schema_version: Literal["runtime-run-guarantees/v1"] = "runtime-run-guarantees/v1"
    run_scope: DecisionIdentity
    required_guarantees: tuple[OperationGuarantee, ...] = Field(max_length=5)

    @property
    def decision_id(self) -> str:
        return canonical_json_digest((self.schema_version, self.run_scope))


class RunProgramDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-run-program/v1"] = "runtime-run-program/v1"
    run_scope: DecisionIdentity
    execution_id: DecisionIdentity
    plan_digest: DecisionDigest
    actor_id: DecisionIdentity
    authorization_scope: tuple[DecisionIdentity, ...] = Field(min_length=1, max_length=64)

    @property
    def decision_id(self) -> str:
        return canonical_json_digest((self.schema_version, self.run_scope, self.execution_id))


class RunPhaseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-run-phase/v1"] = "runtime-run-phase/v1"
    run_scope: DecisionIdentity
    execution_id: DecisionIdentity
    phase: Annotated[int, Field(strict=True, ge=0, le=64)]
    state: Literal["started", "succeeded", "failed", "cancelled", "indeterminate"]
    operation_ids: tuple[DecisionIdentity, ...] = Field(default=(), max_length=64)

    @property
    def decision_id(self) -> str:
        return canonical_json_digest(
            (
                self.schema_version,
                self.run_scope,
                self.execution_id,
                self.phase,
                "start" if self.state == "started" else "terminal",
            )
        )


class RunPreparationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-run-preparation/v1"] = "runtime-run-preparation/v1"
    run_scope: DecisionIdentity
    execution_id: DecisionIdentity
    previews: dict[RuntimeDomain, AugmentationPreparation] = Field(default_factory=dict, max_length=3)
    admitted: bool

    @property
    def decision_id(self) -> str:
        return canonical_json_digest((self.schema_version, self.run_scope, self.execution_id))


RuntimeDecision = Annotated[
    RunContextDecision
    | RunOperationGuaranteesDecision
    | RunProgramDecision
    | RunPhaseDecision
    | RunPreparationDecision
    | ExperimentDecision
    | ExperimentCancellationDecision
    | TrialAttemptDecision
    | TrialObservationDecision
    | TrialTerminalDecision
    | TrialReplacementDecision
    | TrialArchiveDecision
    | RuntimeSequenceDecision
    | TrialInterruptionDecision,
    Field(discriminator="schema_version"),
]
_DECISION = TypeAdapter(RuntimeDecision)


def validate_runtime_decision(value: object) -> RuntimeDecision:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return _DECISION.validate_python(payload)


def require_identical_decision(existing: RuntimeDecision, candidate: RuntimeDecision) -> None:
    if existing.model_dump(mode="json") != candidate.model_dump(mode="json"):
        raise ConflictError("runtime decision identity conflicts with its committed value")


def bind_run_operation_guarantees(
    store: ControlPlaneStore, run_scope: str, required_guarantees: tuple[OperationGuarantee, ...]
) -> None:
    reader = getattr(store, "load_runtime_decisions", None)
    if reader is None:
        if required_guarantees:
            raise TypeError("run operation guarantees require a runtime decision store")
        return
    retained = any(isinstance(record, RunOperationGuaranteesDecision) for record in reader())
    if required_guarantees or retained:
        store.claim_runtime_decision(
            RunOperationGuaranteesDecision(run_scope=run_scope, required_guarantees=required_guarantees)
        )


def runtime_store_digest(store: object) -> str:
    from .runtime_resource_ownership import ledger_identity

    kind, identity = ledger_identity(store)
    if kind == "in-memory-ledger":
        identity = (id(identity[0]),)
    return canonical_json_digest((kind, identity))

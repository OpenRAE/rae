"""Reference-only delivery of admitted run and experiment progress."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from raes_contracts.canonical import canonical_json_digest

Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=256)]
Digest = Annotated[str, Field(strict=True, pattern=r"^sha256:[a-f0-9]{64}$")]


class RuntimeSequenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["raes-runtime-sequence/v1"] = "raes-runtime-sequence/v1"
    engine_id: Digest
    kind: Literal["run", "experiment"]
    execution_id: Identifier
    scope_id: Identifier
    request_digest: Digest
    worker_id: Identifier
    state_queue: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    activity_budget_ms: Annotated[int, Field(strict=True, ge=1, le=300_000)] = 60_000
    poll_interval_ms: Annotated[int, Field(strict=True, ge=100, le=60_000)] = 1000

    @property
    def workflow_id(self):
        return "raes-" + self.kind + "-" + canonical_json_digest(self.model_dump(mode="json")).removeprefix("sha256:")


class RuntimeSequenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-sequence-binding/v1"] = "runtime-sequence-binding/v1"
    reference: RuntimeSequenceReference
    actor_id: Identifier
    authorization_scope: tuple[Identifier, ...] = Field(min_length=1, max_length=64)

    @property
    def decision_id(self):
        # Rebinding the same execution to different artifacts, workers, or
        # delivery budgets conflicts before any workflow is submitted.
        return canonical_json_digest(
            (self.schema_version, self.reference.kind, self.reference.scope_id, self.reference.execution_id)
        )

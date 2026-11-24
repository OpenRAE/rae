"""Private retained ownership and checked outcome cuts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from raes_contracts.assigned_trial import TrialAssignmentModel, TrialOutcomeModel
from raes_contracts.canonical import canonical_json_digest


class TrialAssignmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-trial-assignment/v1"] = "runtime-trial-assignment/v1"
    assignment: TrialAssignmentModel

    @property
    def decision_id(self) -> str:
        return canonical_json_digest((self.schema_version, self.assignment.execution_attempt_id))


class TrialOutcomeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-trial-outcome/v1"] = "runtime-trial-outcome/v1"
    outcome: TrialOutcomeModel
    sequence: int = Field(ge=1)

    @property
    def decision_id(self) -> str:
        return canonical_json_digest((self.schema_version, self.outcome.assignment_digest, self.sequence))

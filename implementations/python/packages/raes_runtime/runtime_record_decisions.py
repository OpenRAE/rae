"""Private, versioned record publication and authored study bindings."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ExperimentRunModel, ExperimentStudyModel

Identity = Annotated[str, Field(strict=True, min_length=1, max_length=256)]


class ExperimentStudyDefinitionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-study-definition/v1"] = "runtime-study-definition/v1"
    experiment_id: Identity
    study: ExperimentStudyModel

    @property
    def decision_id(self):
        return canonical_json_digest((self.schema_version, self.experiment_id))


class ExperimentRecordPublicationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["runtime-record-publication/v1"] = "runtime-record-publication/v1"
    experiment_id: Identity
    state: Literal["candidate", "published"] = "candidate"
    run: ExperimentRunModel | None = None
    study: ExperimentStudyModel | None = None
    validation_status: Literal["passed", "failed", "not-performed"]
    failure_codes: tuple[Identity, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def _validate_record(self):
        if (self.run is None) == (self.study is None):
            raise ValueError("publication must identify exactly one run or study")
        return self

    @property
    def decision_id(self):
        # Version ownership is checked across both archive paths before persistence.
        identity = (
            ("run", self.run.run_id, self.run.run_version)
            if self.run is not None
            else ("study", self.study.study_id, self.study.study_version)
        )
        return canonical_json_digest(
            (self.schema_version, self.experiment_id, identity, self.validation_status, self.failure_codes, self.state)
        )

"""Resolve authored study policy before accepting inherited evidence scope."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypedDict

from ..canonical import canonical_json_digest

if TYPE_CHECKING:
    from .experiment_capture import ExperimentCaptureSpecModel
    from .experiment_study_contract import ExperimentStudyModel


class StudyRelationInputs(TypedDict, total=False):
    """Resolved artifacts used to validate inherited study evidence relations."""

    relation_scenarios: Mapping[str, Any] | None
    relation_capture_specs: Mapping[str, ExperimentCaptureSpecModel] | None


def validate_study_definition(study: ExperimentStudyModel, definition: ExperimentStudyModel | None) -> None:
    reference = study.definition_ref
    if reference is None:
        return
    if definition is None:
        raise ValueError("study snapshots require a resolved authored study definition")
    from .experiment_study_contract import ExperimentStudyModel

    definition = ExperimentStudyModel.model_validate(definition.model_dump(mode="json", warnings=False))
    if definition.definition_ref is not None:
        raise ValueError("resolved authored study definition must not be another snapshot")
    if (reference.ref_id, reference.ref_version, reference.ref_digest) != (
        definition.study_id,
        definition.study_version,
        canonical_json_digest(definition.model_dump(mode="json")),
    ):
        raise ValueError("resolved authored study definition does not match its pinned reference")
    excluded = {"membership", "study_version", "definition_ref"}
    if study.model_dump(mode="json", exclude=excluded) != definition.model_dump(mode="json", exclude=excluded):
        raise ValueError("study snapshot changed inherited authored policy or evidence relations")

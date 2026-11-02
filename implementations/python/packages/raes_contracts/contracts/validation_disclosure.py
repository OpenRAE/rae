"""ASR-515 validation-basis disclosure contracts.

Records the exact governed validation/admission profile used for one concrete
subject, the achieved strength, gate-result rows, and limitations. Joins the
ASR-511 catalog by ``(profile_id, profile_version, subject_kind)`` via
:func:`raes_contracts.validation_profiles.select_validation_profile` -- never a
second loader or a carrier-specific enum. Scenario/scenario-snapshot subjects
are referenced (``subject_ref``) using their existing stable identity/version/
digest semantics -- this module never modifies the SDL snapshot contract or
its canonical digest inputs. Experiment task/run/study carriers embed this
disclosure as an optional list, following the ``realized_form_disclosures`` /
``augmentation_disclosures`` idiom.

The gate-result/limitation row shapes and the ADR-072 strength-ordering gate
vocabulary live in :mod:`raes_contracts.contracts.validation_disclosure_gates`;
the subject/producer reference shapes live in
:mod:`raes_contracts.contracts.validation_subject_reference`. Both were split
out of this module (issue #259) to keep each file under the repo's 500-line
source-file cap -- this module re-imports what it needs from them, so the
public surface (including this module's own ``__all__``) is unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..timestamps import parse_rfc3339_datetime
from ..validation_profiles import select_validation_profile
from ..versions import VALIDATION_BASIS_DISCLOSURE_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, Rfc3339DateTimeString
from .experiment_manifest_references import ExperimentEvidenceRecordReferenceModel
from .schema_invariants import _CARRIER_DISCLOSURES_INSTANCE_PATH, add_raes_invariant
from .validation_disclosure_gates import (
    _EVIDENCE_REF_REQUIRED_STRENGTHS,
    _STRENGTH_RANK,
    _STRENGTH_REQUIRED_GATES,
    DiagnosticCodeRef,
    ValidationGateResultModel,
    ValidationLimitationModel,
)
from .validation_subject_reference import (
    ValidationProducerReferenceModel,
    ValidationSubjectReferenceModel,
)

if TYPE_CHECKING:
    # Deferred: raes_contracts.validation_profiles imports back from this
    # package (raes_contracts.contracts), so the runtime lookup happens
    # inside the model_validator method body, not at module import time.
    # PEP 563 (``from __future__ import annotations``) means these type-only
    # hints are never evaluated at runtime, so this import is safe here.
    from ..validation_profiles import ValidationProfileDefinitionModel

SubjectKind = Literal[
    "scenario",
    "scenario_snapshot",
    "experiment_task",
    "experiment_run",
    "experiment_study",
    "backend_conformance_claim",
    "participant_conformance_claim",
    "published_claim",
]

AchievedStrength = Literal[
    "structural",
    "semantic",
    "behavioral",
    "evidence_backed",
    "falsification_backed",
]

# The ONE explicit subject_kind -> ref_kind mapping (preflight/plan boundary).
# Do not introduce a second generic reference family or collapse this into a
# free-form or carrier-specific enum.
_SUBJECT_KIND_TO_REF_KIND: dict[str, str] = {
    "scenario": "scenario",
    "scenario_snapshot": "scenario-snapshot",
    "experiment_task": "task",
    "experiment_run": "run",
    "experiment_study": "study",
    "backend_conformance_claim": "backend",
    "participant_conformance_claim": "participant-implementation",
    "published_claim": "result",
}

_AUDIENCE_RESTRICTED_VALUES = frozenset({"public", "audience-restricted"})
_AUDIENCE_RESTRICTED_LIMITATION_CATEGORY = "audience_restricted"


def _validate_subject_kind_ref_kind_mapping(disclosure: ValidationBasisDisclosureModel) -> None:
    expected_ref_kind = _SUBJECT_KIND_TO_REF_KIND[disclosure.subject_kind]
    if disclosure.subject_ref.ref_kind != expected_ref_kind:
        raise ValueError(
            f"subject_kind {disclosure.subject_kind!r} requires subject_ref.ref_kind={expected_ref_kind!r}, "
            f"got {disclosure.subject_ref.ref_kind!r}"
        )


def _validate_gate_rows_against_profile(
    profile: ValidationProfileDefinitionModel, disclosure: ValidationBasisDisclosureModel
) -> None:
    gate_kinds = [gate.gate_kind for gate in disclosure.gate_results]
    if len(gate_kinds) != len(set(gate_kinds)):
        raise ValueError("gate_results gate_kind values must be unique")
    required_gate_kinds = set(profile.required_gate_kinds)
    allowed_gate_kinds = required_gate_kinds | set(profile.optional_gate_kinds)
    undeclared = sorted(set(gate_kinds) - allowed_gate_kinds)
    if undeclared:
        raise ValueError(
            f"gate_results gate_kind values are not declared by profile {profile.profile_id!r}: {undeclared}"
        )
    missing_required = sorted(required_gate_kinds - set(gate_kinds))
    if missing_required:
        raise ValueError(f"gate_results is missing required gate_kind values: {missing_required}")


def _validate_strength_ordering(disclosure: ValidationBasisDisclosureModel) -> None:
    gate_outcomes = {gate.gate_kind: gate.outcome for gate in disclosure.gate_results}
    required_gates = _STRENGTH_REQUIRED_GATES[disclosure.achieved_strength]
    not_passed = sorted(gate_kind for gate_kind in required_gates if gate_outcomes.get(gate_kind) != "passed")
    if not_passed:
        raise ValueError(
            f"achieved_strength {disclosure.achieved_strength!r} requires passed gate rows for: {not_passed}"
        )
    if disclosure.achieved_strength in _EVIDENCE_REF_REQUIRED_STRENGTHS and not disclosure.evidence_refs:
        raise ValueError(f"achieved_strength {disclosure.achieved_strength!r} requires at least one evidence_ref")


def _validate_required_gate_failures_capped(
    profile: ValidationProfileDefinitionModel, disclosure: ValidationBasisDisclosureModel
) -> None:
    gate_by_kind = {gate.gate_kind: gate for gate in disclosure.gate_results}
    unmet_required = sorted(
        gate_kind for gate_kind in profile.required_gate_kinds if gate_by_kind[gate_kind].outcome != "passed"
    )
    if unmet_required and not disclosure.limitations:
        raise ValueError(f"required gate rows that are not passed must carry an explicit limitation: {unmet_required}")


def _validate_not_applicable_gates_disclosed(disclosure: ValidationBasisDisclosureModel) -> None:
    if any(gate.outcome == "not_applicable" for gate in disclosure.gate_results) and not disclosure.limitations:
        raise ValueError("not_applicable gate outcomes must carry an explicit limitation")


def _validate_limitation_categories_declared(
    profile: ValidationProfileDefinitionModel, disclosure: ValidationBasisDisclosureModel
) -> None:
    declared = set(profile.limitation_categories)
    undeclared = sorted({limitation.limitation_category for limitation in disclosure.limitations} - declared)
    if undeclared:
        raise ValueError(
            f"limitations limitation_category values are not declared by profile {profile.profile_id!r}: {undeclared}"
        )


def _validate_minimum_strength_not_silently_below(
    profile: ValidationProfileDefinitionModel, disclosure: ValidationBasisDisclosureModel
) -> None:
    if (
        _STRENGTH_RANK[disclosure.achieved_strength] < _STRENGTH_RANK[profile.minimum_strength]
        and not disclosure.limitations
    ):
        raise ValueError(
            f"achieved_strength {disclosure.achieved_strength!r} below profile minimum_strength "
            f"{profile.minimum_strength!r} must carry an explicit limitation"
        )


def _validate_audience_restriction_disclosed(disclosure: ValidationBasisDisclosureModel) -> None:
    if disclosure.audience in _AUDIENCE_RESTRICTED_VALUES and not any(
        limitation.limitation_category == _AUDIENCE_RESTRICTED_LIMITATION_CATEGORY
        for limitation in disclosure.limitations
    ):
        raise ValueError(
            f"audience {disclosure.audience!r} disclosures must carry an "
            f"{_AUDIENCE_RESTRICTED_LIMITATION_CATEGORY} limitation rather than borrowing strength "
            "from a non-public view"
        )


_DISCLOSURE_INVARIANTS: tuple[tuple[str, str], ...] = (
    (
        "validation-basis-profile-join-resolves",
        "profile_id/profile_version/subject_kind must resolve one validation profile that declares the subject "
        "kind, and subject_ref.ref_kind must match the profile's ONE subject_kind mapping.",
    ),
    (
        "validation-basis-gate-rows-declared",
        "gate_results gate_kind values must be unique, drawn from the resolved profile's required/optional union, "
        "and every required gate_kind must be present.",
    ),
    (
        "validation-basis-strength-ordering-valid",
        "achieved_strength must be supported by ADR-072-ordered passed gate rows for its own rank (structural "
        "never implies semantic; semantic never implies behavioral); evidence_backed/falsification_backed "
        "additionally require at least one evidence_ref.",
    ),
    (
        "validation-basis-claim-capped-and-disclosed",
        "A required gate not passed, a not_applicable gate outcome, a below-minimum achieved_strength, and a "
        "public/audience-restricted audience each require an explicit, profile-declared limitation (the "
        "audience-restricted case specifically requires the audience_restricted category).",
    ),
)


class ValidationBasisDisclosureModel(ContractModel):
    """Governed disclosure of the validation/admission basis for one subject (ASR-515).

    Embeddable core for task/run/study carriers; scenario/scenario-snapshot
    subjects publish standalone via :class:`ValidationBasisDisclosureDocumentModel`.
    """

    profile_id: NonEmptyString
    profile_version: NonEmptyString
    subject_kind: SubjectKind
    subject_ref: ValidationSubjectReferenceModel
    achieved_strength: AchievedStrength
    gate_results: list[ValidationGateResultModel] = Field(min_length=1)
    limitations: list[ValidationLimitationModel] = Field(default_factory=list)
    evidence_refs: list[ExperimentEvidenceRecordReferenceModel] = Field(default_factory=list)
    producer_refs: list[ValidationProducerReferenceModel] = Field(default_factory=list)
    diagnostic_refs: list[DiagnosticCodeRef] = Field(default_factory=list)
    recorded_at: Rfc3339DateTimeString
    audience: Literal["internal", "public", "audience-restricted"] | None = None

    @model_validator(mode="after")
    def _validate_validation_basis_disclosure(self) -> ValidationBasisDisclosureModel:

        parse_rfc3339_datetime("recorded_at", self.recorded_at)
        _validate_subject_kind_ref_kind_mapping(self)
        profile = select_validation_profile(self.profile_id, self.profile_version, subject_kind=self.subject_kind)
        _validate_gate_rows_against_profile(profile, self)
        _validate_strength_ordering(self)
        _validate_required_gate_failures_capped(profile, self)
        _validate_not_applicable_gates_disclosed(self)
        _validate_limitation_categories_declared(profile, self)
        _validate_minimum_strength_not_silently_below(profile, self)
        _validate_audience_restriction_disclosed(self)
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        validator = (
            "raes_contracts.contracts.validation_disclosure.ValidationBasisDisclosureModel."
            "_validate_validation_basis_disclosure"
        )
        inputs = [
            {"contract_id": "validation-basis-disclosure-v1", "instance_path": "#"},
            {"contract_id": "experiment-task-v1", "instance_path": _CARRIER_DISCLOSURES_INSTANCE_PATH},
            {"contract_id": "experiment-run-v1", "instance_path": _CARRIER_DISCLOSURES_INSTANCE_PATH},
            {"contract_id": "experiment-study-v1", "instance_path": _CARRIER_DISCLOSURES_INSTANCE_PATH},
        ]
        for invariant_id, description in _DISCLOSURE_INVARIANTS:
            add_raes_invariant(json_schema, invariant_id, description, validator=validator, inputs=inputs)
        return json_schema


class ValidationBasisDisclosureDocumentModel(ContractModel):
    """Published wrapper adding ``schema_version`` around the embeddable disclosure core."""

    schema_version: Literal[VALIDATION_BASIS_DISCLOSURE_SCHEMA_VERSION] = VALIDATION_BASIS_DISCLOSURE_SCHEMA_VERSION
    disclosure: ValidationBasisDisclosureModel


def validate_carrier_validation_basis_disclosures(carrier: object, *, subject_kind: str) -> None:
    """Cross-check a carrier's embedded ``validation_basis_disclosures`` against its own identity.

    ``subject_kind`` (``experiment_task``/``experiment_run``/``experiment_study``) derives the
    carrier's ``{label}_id``/``{label}_version`` attribute names, so every carrier's
    model_validator can call this with one line.
    """
    carrier_label = subject_kind.removeprefix("experiment_")
    subject_id = getattr(carrier, f"{carrier_label}_id")
    subject_version = getattr(carrier, f"{carrier_label}_version")
    disclosures: Sequence[ValidationBasisDisclosureModel] = carrier.validation_basis_disclosures
    mismatched = sorted(
        f"{disclosure.subject_kind}:{disclosure.subject_ref.ref_id}"
        for disclosure in disclosures
        if (
            disclosure.subject_kind != subject_kind
            or disclosure.subject_ref.ref_id != subject_id
            or disclosure.subject_ref.ref_version != subject_version
        )
    )
    if mismatched:
        joined = ", ".join(mismatched)
        raise ValueError(
            f"{carrier_label} validation_basis_disclosures subject_kind and subject_ref must match the carrier "
            f"identity: {joined}"
        )


__all__ = [
    "AchievedStrength",
    "DiagnosticCodeRef",
    "SubjectKind",
    "ValidationBasisDisclosureDocumentModel",
    "ValidationBasisDisclosureModel",
    "ValidationGateResultModel",
    "ValidationLimitationModel",
    "ValidationProducerReferenceModel",
    "ValidationSubjectReferenceModel",
    "validate_carrier_validation_basis_disclosures",
]

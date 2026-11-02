"""Behavioral relation identifiers and the bounded claim binding to one relation definition.

The behavioral relation catalog owns relation meaning. A claim binding names a
relation revision and supplies the subject, carriers, quantifier and evidence
boundary, assurance state and limitations.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ._base import ContractModel, NonEmptyString

BehavioralRelationId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]*$")]


BehavioralTaxonomyRevision = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9.-]*$")]

_ASSURANCE_AXIS_RULES: dict[str, tuple[str, frozenset[str]]] = {
    "definition": ("defined", frozenset({"structural"})),
    "checker": ("implemented", frozenset({"structural", "finite"})),
    "bounded-test": ("tested", frozenset({"finite"})),
    "model-check": ("model-checked", frozenset({"model-check"})),
    "proof": ("proved", frozenset({"proof"})),
    "runtime-enforcement": ("enforced", frozenset({"structural", "finite"})),
    "backend-declaration": ("declared", frozenset({"structural"})),
    "backend-realization": ("realized", frozenset({"structural", "finite"})),
    "backend-conformance": ("conformant", frozenset({"finite", "statistical"})),
}


class BehavioralClaimBindingModel(ContractModel):
    """A bounded claim tied to one revisioned behavioral-relation definition.

    This is deliberately a claim *binding*, not another relation registry. The
    catalog owns relation meaning; consumers supply the subject, carriers,
    quantifier/evidence boundary, assurance state, and explicit limitations.
    """

    taxonomy_id: NonEmptyString
    taxonomy_revision: BehavioralTaxonomyRevision
    relation_id: BehavioralRelationId
    subject: NonEmptyString
    left_carrier_ref: NonEmptyString | None = None
    right_carrier_ref: NonEmptyString | None = None
    observation_projection_ref: NonEmptyString | None = None
    observation_projection_revision: NonEmptyString | None = None
    relation_parameter_profile_ref: NonEmptyString | None = None
    relation_parameter_profile_revision: NonEmptyString | None = None
    quantifier_scope: Literal[
        "single-artifact",
        "finite-cases",
        "sampled-population",
        "all-admitted-inputs",
        "all-traces",
        "all-strategies",
    ]
    evidence_scope: Literal["structural", "finite", "statistical", "model-check", "proof"]
    assurance_axis: (
        Literal[
            "definition",
            "checker",
            "bounded-test",
            "model-check",
            "proof",
            "runtime-enforcement",
            "backend-declaration",
            "backend-realization",
            "backend-conformance",
        ]
        | None
    ) = None
    evidence_boundary: NonEmptyString
    assurance_status: Literal[
        "defined",
        "implemented",
        "tested",
        "model-checked",
        "proved",
        "deliberately-unproved",
        "future",
        "enforced",
        "declared",
        "realized",
        "conformant",
    ]
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)
    limitations: list[NonEmptyString] = Field(min_length=1)
    explicit_non_claims: list[NonEmptyString] = Field(min_length=1)

    def _validate_quantifier_evidence(self) -> None:
        universal_scopes = {"all-admitted-inputs", "all-traces", "all-strategies"}
        if self.quantifier_scope in universal_scopes and self.evidence_scope not in {"model-check", "proof"}:
            raise ValueError("universal quantification requires model-check or proof evidence")

    def _validate_explicit_assurance_axis(self) -> None:
        if self.assurance_axis is None:
            return
        expected_status, allowed_evidence = _ASSURANCE_AXIS_RULES[self.assurance_axis]
        negative_axis_state = self.assurance_status == "future" or (
            self.assurance_axis == "proof" and self.assurance_status == "deliberately-unproved"
        )
        if negative_axis_state:
            if self.evidence_scope != "structural":
                raise ValueError(
                    f"assurance axis {self.assurance_axis!r} with status {self.assurance_status!r} "
                    "requires structural evidence"
                )
            return
        if self.assurance_status != expected_status or self.evidence_scope not in allowed_evidence:
            raise ValueError(
                f"assurance axis {self.assurance_axis!r} requires status {expected_status!r} "
                f"and evidence scope in {sorted(allowed_evidence)!r}"
            )

    def _validate_unscoped_assurance(self) -> None:
        if self.assurance_axis is not None:
            return
        if self.assurance_status in {"enforced", "declared", "realized", "conformant"}:
            raise ValueError(f"assurance status {self.assurance_status!r} requires an explicit assurance axis")
        if self.assurance_status == "proved" and self.evidence_scope != "proof":
            raise ValueError("proved assurance requires proof evidence")
        if self.assurance_status == "model-checked" and self.evidence_scope != "model-check":
            raise ValueError("model-checked assurance requires model-check evidence")

    @staticmethod
    def _validate_coordinate_pair(ref: str | None, revision: str | None, label: str) -> None:
        if (ref is None) != (revision is None):
            raise ValueError(f"{label} ref and revision must be supplied together")

    @model_validator(mode="after")
    def _validate_claim_strength(self) -> BehavioralClaimBindingModel:
        self._validate_quantifier_evidence()
        self._validate_explicit_assurance_axis()
        self._validate_unscoped_assurance()
        self._validate_coordinate_pair(
            self.observation_projection_ref,
            self.observation_projection_revision,
            "observation projection",
        )
        self._validate_coordinate_pair(
            self.relation_parameter_profile_ref,
            self.relation_parameter_profile_revision,
            "relation parameter profile",
        )
        return self


__all__ = ["BehavioralClaimBindingModel", "BehavioralRelationId", "BehavioralTaxonomyRevision"]

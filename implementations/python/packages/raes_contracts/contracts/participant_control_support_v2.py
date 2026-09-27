"""Admitted support requirements and exact-cut API-407 assessment bindings."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import ConfigDict, model_validator

from .base import ContractModel
from .participant_control_coordinates import Artifacts, ControlRef, Evidence, require_kind
from .participant_control_results import ControlEffectiveSupportModel


class ControlSupportAssessmentV2Model(ContractModel):
    """A recorded requirement-relative relation, subject to trusted resolution."""

    model_config = ConfigDict(frozen=True)
    obligation_id: ControlRef
    instance_id: ControlRef
    required_strength: Literal["exact", "bounded", "disclosed_weak"]
    required_constraints: Artifacts
    effective_support: ControlEffectiveSupportModel
    relation: Literal["exact", "bounded-compatible", "disclosed-weak-compatible", "insufficient", "unresolved"]
    evidence: Evidence

    @model_validator(mode="after")
    def _relation(self) -> Self:
        for item in self.required_constraints:
            require_kind(item, "constraint")
        if self.required_strength == "bounded" and not self.required_constraints:
            raise ValueError("bounded support requirement needs admitted constraints")
        observed = self.effective_support
        if observed.instance_id != self.instance_id:
            raise ValueError("support assessment has a different instance")
        if self.relation in {"exact", "bounded-compatible", "disclosed-weak-compatible"}:
            if observed.status != "resolved" or observed.installation is None:
                raise ValueError("positive support relation needs resolved installed support")
        if self.relation == "exact" and observed.effective_level != "exact":
            raise ValueError("exact support relation needs exact effective support")
        if self.relation == "bounded-compatible" and (
            self.required_strength == "exact" or observed.effective_level != "bounded"
        ):
            raise ValueError("bounded support does not satisfy exact or mismatched strength")
        if self.relation == "disclosed-weak-compatible" and (
            self.required_strength != "disclosed_weak" or observed.effective_level != "disclosed_weak"
        ):
            raise ValueError("disclosed weak support relation is incompatible")
        if self.required_strength == "exact" and self.relation not in {"exact", "insufficient", "unresolved"}:
            raise ValueError("exact requirement cannot accept weaker support")
        return self

    @property
    def satisfied(self) -> bool:
        return self.relation in {"exact", "bounded-compatible", "disclosed-weak-compatible"}

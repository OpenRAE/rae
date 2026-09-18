"""Admitted experiment trial-plan contract (SCE-002/SCE-006).

The immutable, schedule-independent handoff between experiment design/admission
and orchestration selected by issue #652, governed by ADR-084, and specified by
invariants SVR-018..SVR-030 in
``specs/formal/scenario-variation-trial-realization/README.md``. Architecture
guardrails are recorded in
``docs/decisions/issue-788-sce-002-admitted-trial-plan-contract-preflight.md``.

The plan reuses owning contracts (``TrialCoordinateModel``,
``ExperimentSelectionOutcomeModel``, ``ExperimentBindingDescriptorModel``,
``ExperimentStochasticControlModel``, ``RandomStreamDrawRecordModel``,
``TrialCleanupPlanModel``, ``ExecutionRetryPolicyModel``,
``SchedulerIsolationProofModel``, ``ExperimentManifestReferenceModel``,
``RealizationEnvelopeIdentityModel``, and the typed experiment references)
rather than duplicating their meaning, and pins exact refs/digests instead of
copying declarations. Every entry commits explicit resolved outcomes and
bindings: no unresolved sample, default, backend choice, fact, or secret lookup
survives admission. The leaf component contracts live in
:mod:`admitted_trial_plan_components`; this module composes them into the entry
and plan roots.

Integrity is a one-way, acyclic chain (per the preflight): ``logical
coordinate + pinned inputs + identity profiles -> plan_entry_id and run_id ->
cleanup-plan identity -> entry canonical digest -> complete-plan canonical
digest``. Digest fields are excluded from their own canonical projection and no
child references the enclosing plan digest, so a keyed-entry map plus RFC
8785/JCS canonicalization makes input reordering and worker count irrelevant to
identity while a tampered plan fails closed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .._canonical import canonical_json_digest
from ..versions import ADMITTED_TRIAL_PLAN_SCHEMA_VERSION
from .admitted_trial_plan_components import (
    AdmittedApparatusBindingModel,
    AdmittedBindingModel,
    AdmittedExecutionControlModel,
    AdmittedInstantiationProvenanceModel,
    AdmittedMixedCompositionBindingModel,
    AdmittedParticipantManifestReferenceModel,
    AdmittedSelectionRecordModel,
    AdmittedTrialPlanAdmissionModel,
    AdmittedTrialPlanInputRefsModel,
    AdmittedTrialPlanProfilesModel,
    AdmittedTrialSourceReferenceModel,
    BindingOrigin,
    ExperimentScenarioFamilyReferenceModel,
    SelectionPolicyKind,
)
from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .experiment_apparatus import ExperimentStochasticControlModel
from .random_stream import RandomStreamDrawRecordModel, TrialCoordinateModel
from .schema_invariants import _add_raes_invariant
from .trial_cleanup import SchedulerIsolationProofModel, TrialCleanupPlanModel

#: Canonical-shape placeholder used only while sealing; replaced by the real digest.
_PLACEHOLDER_DIGEST = "sha256:" + "0" * 64


def _canonical_content(model: ContractModel, digest_field: str) -> dict[str, object]:
    """Return the model's canonical JSON projection with its own digest field removed."""

    data = model.model_dump(mode="json")
    data.pop(digest_field, None)
    return data


def _verify_self_digest(model: ContractModel, digest_field: str) -> None:
    """Fail closed unless ``digest_field`` equals the JCS digest of the remaining content."""

    declared = getattr(model, digest_field)
    expected = canonical_json_digest(_canonical_content(model, digest_field))
    if declared != expected:
        raise ValueError(f"{digest_field} does not match the canonical digest of its content")


def _seal(model_cls: type, digest_field: str, fields: dict[str, object]) -> object:
    """Construct ``model_cls`` with ``digest_field`` set to its own content digest.

    Uses ``model_construct`` for the placeholder pass so the recomputed digest is
    byte-identical to what the closed model's ``model_dump`` produces, then runs
    full validation on the sealed instance.
    """

    provisional = model_cls.model_construct(**fields, **{digest_field: _PLACEHOLDER_DIGEST})
    digest = canonical_json_digest(_canonical_content(provisional, digest_field))
    return model_cls(**fields, **{digest_field: digest})


def _require_unique(field_name: str, values: list[str]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


def entry_owned_resource_refs(plan: AdmittedTrialPlanModel, plan_entry_id: str) -> set[str]:
    """Return the resource identities one entry owns via its referenced cleanup plan.

    Resource ownership is the union of the ``resource_refs`` declared by every
    boundary of the entry's referenced cleanup plan. Bounded parallelism must
    never authorize two entries that share any owned resource (one trial, or its
    cleanup, could otherwise read, mutate, or destroy another's state). This is
    the single owning definition reused by both the plan's embedded
    isolation check and the standalone plan-to-schedule join validator so the two
    surfaces cannot drift.
    """

    entry = plan.entries.get(plan_entry_id)
    if entry is None:
        raise ValueError(f"plan_entry_id {plan_entry_id!r} does not resolve inside the admitted plan")
    cleanup_plan = plan.cleanup_plans.get(entry.execution_controls.cleanup_plan_ref)
    refs: set[str] = set()
    if cleanup_plan is not None:
        for boundary in cleanup_plan.resource_boundaries.values():
            refs.update(boundary.resource_refs)
    return refs


def isolation_resource_overlaps(plan: AdmittedTrialPlanModel, plan_entry_ids: list[str]) -> list[str]:
    """Return the resource identities shared by any pair of the given entries."""

    owned = {entry_id: entry_owned_resource_refs(plan, entry_id) for entry_id in plan_entry_ids}
    covered = list(owned)
    shared: set[str] = set()
    for first_index in range(len(covered)):
        for second_index in range(first_index + 1, len(covered)):
            shared.update(owned[covered[first_index]] & owned[covered[second_index]])
    return sorted(shared)


class AdmittedTrialEntryModel(ContractModel):
    """One immutable admitted trial entry at a unique logical coordinate."""

    plan_entry_id: NonEmptyString
    coordinate: TrialCoordinateModel
    run_id: NonEmptyString
    selections: list[AdmittedSelectionRecordModel] = Field(default_factory=list)
    bindings: list[AdmittedBindingModel] = Field(default_factory=list)
    stochastic_draws: list[RandomStreamDrawRecordModel] = Field(default_factory=list)
    apparatus: AdmittedApparatusBindingModel | AdmittedMixedCompositionBindingModel
    execution_controls: AdmittedExecutionControlModel
    instantiation_provenance: AdmittedInstantiationProvenanceModel
    entry_digest: PrefixedDigestString

    @model_validator(mode="after")
    def _validate_entry(self) -> AdmittedTrialEntryModel:
        if self.run_id == self.plan_entry_id:
            raise ValueError("entry run_id must be distinct from plan_entry_id")
        _require_unique(
            "entry selection variation_point_id",
            [selection.variation_point_id for selection in self.selections],
        )
        for draw in self.stochastic_draws:
            if draw.rejection_exhausted:
                raise ValueError("admitted entry stochastic draws must record a resolved outcome, not exhaustion")
        provenance = self.instantiation_provenance
        if provenance.plan_entry_id != self.plan_entry_id or provenance.run_id != self.run_id:
            raise ValueError("entry instantiation_provenance must match the entry plan_entry_id and run_id")
        _verify_self_digest(self, "entry_digest")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        _add_raes_invariant(
            json_schema,
            "admitted-trial-entry-resolved-and-integrity-bound",
            "An admitted trial entry keeps run_id distinct from plan_entry_id, records unique resolved variation "
            "selections and non-exhausted stochastic draws, matches its instantiation provenance to the entry "
            "identity, and binds its content with a recomputed entry_digest.",
            validator="raes_contracts.contracts.admitted_trial_plan.AdmittedTrialEntryModel._validate_entry",
            inputs=[{"contract_id": "admitted-trial-plan-v1", "instance_path": "#/entries"}],
        )
        return json_schema


class AdmittedTrialPlanModel(ContractModel):
    """Immutable, schedule-independent admitted trial plan (SCE-002/SCE-006, ADR-084)."""

    schema_version: Literal[ADMITTED_TRIAL_PLAN_SCHEMA_VERSION] = ADMITTED_TRIAL_PLAN_SCHEMA_VERSION
    plan_id: NonEmptyString
    profiles: AdmittedTrialPlanProfilesModel
    input_refs: AdmittedTrialPlanInputRefsModel
    stochastic_controls: dict[NonEmptyString, ExperimentStochasticControlModel] = Field(default_factory=dict)
    cleanup_plans: dict[NonEmptyString, TrialCleanupPlanModel] = Field(min_length=1)
    isolation_proof: SchedulerIsolationProofModel | None = None
    entries: dict[NonEmptyString, AdmittedTrialEntryModel] = Field(min_length=1)
    admission: AdmittedTrialPlanAdmissionModel
    plan_digest: PrefixedDigestString

    @model_validator(mode="after")
    def _validate_plan(self) -> AdmittedTrialPlanModel:
        self._validate_map_keys()
        self._validate_identity_graph()
        self._validate_joins()
        self._validate_authority_agreement()
        self._validate_isolation()
        if self.admission.entry_count != len(self.entries):
            raise ValueError("admission entry_count must equal the number of admitted entries")
        _verify_self_digest(self, "plan_digest")
        return self

    def _validate_authority_agreement(self) -> None:
        # Values duplicated from incumbent authorities must agree, or a correctly
        # digested plan could still carry contradictory execution intent.
        profile = self.profiles.random_stream_profile
        for control in self.stochastic_controls.values():
            binding = control.executable_binding
            if binding is not None and binding.profile_ref.ref_id != profile:
                raise ValueError(
                    "stochastic control executable binding profile must equal the plan random_stream_profile"
                )
        family_id = self.input_refs.scenario_family_ref.ref_id
        for entry in self.entries.values():
            condition_id = entry.coordinate.condition_id
            for binding in entry.bindings:
                descriptor = binding.descriptor
                if condition_id is not None and descriptor.source_condition_id != condition_id:
                    raise ValueError(
                        "entry binding descriptor source_condition_id must equal the entry coordinate condition_id"
                    )
                target = descriptor.target
                if getattr(target, "plane", None) == "scenario" and target.scenario_family_id != family_id:
                    raise ValueError(
                        "scenario-plane binding descriptor scenario_family_id must equal the pinned scenario family"
                    )

    def _validate_map_keys(self) -> None:
        for key, control in self.stochastic_controls.items():
            if key != control.control_id:
                raise ValueError("stochastic_controls map key must equal the embedded control_id")
        for key, cleanup_plan in self.cleanup_plans.items():
            if key != cleanup_plan.plan_id:
                raise ValueError("cleanup_plans map key must equal the embedded cleanup plan_id")
        for key, entry in self.entries.items():
            if key != entry.plan_entry_id:
                raise ValueError("entries map key must equal the embedded plan_entry_id")

    def _validate_identity_graph(self) -> None:
        entry_ids = set(self.entries)
        run_ids = [entry.run_id for entry in self.entries.values()]
        _require_unique("entry run_id", run_ids)
        run_id_set = set(run_ids)
        if self.plan_id in run_id_set:
            raise ValueError("plan_id must be distinct from every entry run_id")
        collisions = run_id_set & entry_ids
        if collisions:
            raise ValueError("entry run_id must be distinct from every plan_entry_id")
        coordinates = [
            (entry.coordinate.condition_id, entry.coordinate.block_id, entry.coordinate.replicate_id)
            for entry in self.entries.values()
        ]
        if len(coordinates) != len(set(coordinates)):
            raise ValueError("admitted entries must have unique logical coordinates")
        family_id = self.input_refs.scenario_family_ref.ref_id
        for entry in self.entries.values():
            provenance = entry.instantiation_provenance
            if provenance.plan_id != self.plan_id:
                raise ValueError("entry instantiation_provenance plan_id must equal the admitted plan_id")
            if provenance.scenario_family_id != family_id:
                raise ValueError("entry instantiation_provenance scenario_family_id must equal the pinned family ref")

    def _validate_joins(self) -> None:
        mixed_entries = [
            entry
            for entry in self.entries.values()
            if isinstance(entry.apparatus, AdmittedMixedCompositionBindingModel)
        ]
        mixed_profile = self.profiles.compiler_profile == "trial-compiler-mixed-composition-v1"
        if bool(mixed_entries) != mixed_profile:
            raise ValueError("mixed composition entries require the matching compiler and identity profiles")
        if mixed_profile and (
            self.profiles.entry_identity_profile != "trial-entry-identity-mixed-composition-v1"
            or self.profiles.run_identity_profile != "archival-run-identity-mixed-composition-v1"
        ):
            raise ValueError("mixed composition compiler and identity profiles must move together")
        if not mixed_profile and (
            self.profiles.entry_identity_profile != "trial-entry-identity-v1"
            or self.profiles.run_identity_profile != "archival-run-identity-v1"
        ):
            raise ValueError("legacy compiler and identity profiles must move together")
        declared_profiles = {
            (reference.ref_id, reference.ref_version, reference.ref_digest)
            for reference in self.input_refs.mixed_composition_profile_refs
        }
        used_profiles = {
            (
                entry.apparatus.profile_ref.ref_id,
                entry.apparatus.profile_ref.ref_version,
                entry.apparatus.profile_ref.ref_digest,
            )
            for entry in mixed_entries
        }
        if declared_profiles != used_profiles:
            raise ValueError("mixed composition entry profile references must equal the plan's exact input set")
        if any(
            entry.apparatus.source_trial is not None and entry.apparatus.source_trial.plan_id == self.plan_id
            for entry in mixed_entries
        ):
            raise ValueError("mixed composition source trials must reference an external already-sealed plan")
        referenced_cleanup: set[str] = set()
        for entry in self.entries.values():
            cleanup_ref = entry.execution_controls.cleanup_plan_ref
            cleanup_plan = self.cleanup_plans.get(cleanup_ref)
            if cleanup_plan is None:
                raise ValueError(f"entry cleanup_plan_ref {cleanup_ref!r} does not resolve to a plan cleanup block")
            if cleanup_plan.plan_entry_id != entry.plan_entry_id or cleanup_plan.run_id != entry.run_id:
                raise ValueError("referenced cleanup plan must bind the same plan_entry_id and run_id as the entry")
            referenced_cleanup.add(cleanup_ref)
            self._validate_entry_draws(entry)
        orphan_cleanup = sorted(set(self.cleanup_plans) - referenced_cleanup)
        if orphan_cleanup:
            raise ValueError(f"cleanup plans must be referenced by an entry: {', '.join(orphan_cleanup)}")

    def _validate_entry_draws(self, entry: AdmittedTrialEntryModel) -> None:
        for draw in entry.stochastic_draws:
            control = self.stochastic_controls.get(draw.control_id)
            if control is None:
                raise ValueError(
                    f"entry stochastic draw control_id {draw.control_id!r} does not resolve to a plan control"
                )
            if control.executable_binding is None:
                raise ValueError("entry stochastic draw must reference a control that carries an executable binding")
            if draw.address.namespace != control.executable_binding.namespace:
                raise ValueError("entry stochastic draw address namespace must match its control binding namespace")
            if draw.address.trial_coordinate != entry.coordinate:
                raise ValueError(
                    "entry stochastic draw address trial_coordinate must equal the enclosing entry coordinate"
                )

    def _validate_isolation(self) -> None:
        if self.isolation_proof is None:
            return
        proof = self.isolation_proof
        unknown = sorted(set(proof.plan_entry_ids) - set(self.entries))
        if unknown:
            raise ValueError(f"isolation proof references unknown plan entries: {', '.join(unknown)}")
        if proof.requested_parallelism <= 1:
            return
        # Bounded parallelism must not authorize entries that own the same
        # resource: a proof cannot claim independence for trials whose cleanup
        # boundaries overlap, or one trial (or its cleanup) could read, mutate,
        # or destroy another's state.
        overlap = isolation_resource_overlaps(self, list(proof.plan_entry_ids))
        if overlap:
            raise ValueError("isolation proof authorizes parallel entries that share resources: " + ", ".join(overlap))

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        _add_raes_invariant(
            json_schema,
            "admitted-trial-plan-identity-joins-and-integrity",
            "An admitted trial plan keeps map keys equal to embedded ids, keeps plan/entry/run identities distinct, "
            "gives every entry a unique logical coordinate and archival run_id, resolves cleanup and "
            "stochastic-control joins (with each draw addressed to its entry coordinate), exact mixed-composition "
            "profile inputs, and isolation-proof entries within the sealed plan, requires values duplicated from "
            "incumbent authorities (random-stream profile, "
            "binding condition/family) to agree, forbids bounded-parallel entries from sharing resources, matches "
            "admission cardinality, and binds the complete plan with a recomputed plan_digest over the entry set.",
            validator="raes_contracts.contracts.admitted_trial_plan.AdmittedTrialPlanModel._validate_plan",
            inputs=[{"contract_id": "admitted-trial-plan-v1", "instance_path": "#"}],
        )
        return json_schema


def seal_admitted_trial_entry(**fields: object) -> AdmittedTrialEntryModel:
    """Return a validated entry whose ``entry_digest`` binds its own content.

    Accepts every :class:`AdmittedTrialEntryModel` field except ``entry_digest``
    (``plan_entry_id``, ``coordinate``, ``run_id``, ``apparatus``,
    ``execution_controls``, ``instantiation_provenance``, and the optional
    ``selections`` / ``bindings`` / ``stochastic_draws``). The closed model
    validates required, unknown, and mistyped fields on construction.
    """

    return _seal(AdmittedTrialEntryModel, "entry_digest", fields)  # type: ignore[return-value]


def seal_admitted_trial_plan(**fields: object) -> AdmittedTrialPlanModel:
    """Return a validated plan whose ``plan_digest`` binds the complete entry set.

    Accepts every :class:`AdmittedTrialPlanModel` field except ``plan_digest``.
    ``schema_version`` defaults to the contract version; the closed model
    validates required, unknown, and mistyped fields on construction.
    """

    return _seal(AdmittedTrialPlanModel, "plan_digest", fields)  # type: ignore[return-value]


__all__ = [
    "AdmittedApparatusBindingModel",
    "AdmittedBindingModel",
    "AdmittedExecutionControlModel",
    "AdmittedInstantiationProvenanceModel",
    "AdmittedMixedCompositionBindingModel",
    "AdmittedParticipantManifestReferenceModel",
    "AdmittedSelectionRecordModel",
    "AdmittedTrialEntryModel",
    "AdmittedTrialPlanAdmissionModel",
    "AdmittedTrialPlanInputRefsModel",
    "AdmittedTrialPlanModel",
    "AdmittedTrialPlanProfilesModel",
    "AdmittedTrialSourceReferenceModel",
    "BindingOrigin",
    "ExperimentScenarioFamilyReferenceModel",
    "SelectionPolicyKind",
    "entry_owned_resource_refs",
    "isolation_resource_overlaps",
    "seal_admitted_trial_entry",
    "seal_admitted_trial_plan",
]

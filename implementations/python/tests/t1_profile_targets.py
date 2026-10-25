"""Narrow profile-capable stub target for runtime profile-authority tests.

The double negotiates ``plan-realization-profiles-v1`` and
``backend-realization-preparation-v1`` over the stub manifest. Its provisioner
selects configured public choices during preparation and records the prepared
profile bindings on the snapshot entries it applies. It implements no profile
semantics and no native effects, so the runtime, registry and control plane own
every verdict these tests assert.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace

from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
from raes_contracts.domain_profiles import (
    DomainProfileBindingBasis,
    DomainProfileBindingModel,
    DomainProfileBindingProvenanceModel,
    DomainProfileResolutionContextModel,
)
from raes_contracts.planning import ChangeAction, ProvisioningPlan
from raes_contracts.realization_preparation import BACKEND_PREPARATION_CONTRACT, RealizationPreparation
from raes_contracts.realization_profiles import (
    PLAN_PROFILE_CONTRACT,
    profile_context_digest,
    profile_resource_address,
    profile_selection_violation,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_runtime.registry import RuntimeTarget


class ProfileStubProvisioner(StubProvisioner):
    """Select configured choices and carry prepared bindings to the snapshot."""

    def __init__(self, envelope, context: DomainProfileResolutionContextModel, choices: Mapping[str, object]):
        super().__init__(envelope)
        self.domain_profile_context = context
        self._choices = deepcopy(dict(choices))

    def validate_profiles(self, plan: ProvisioningPlan) -> list:
        del plan
        return []

    def prepare(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> RealizationPreparation:
        if plan.profile_authority is None:
            return RealizationPreparation.for_request(plan, snapshot, operations=tuple(plan.operations))
        existing = tuple(binding for op in plan.operations for binding in op.profile_bindings)
        if profile_selection_violation(plan.profile_authority, existing, self.domain_profile_context) is None:
            bindings = existing
        else:
            bindings = tuple(self._select(binding) for binding in plan.profile_authority.bindings)
        operations = tuple(
            replace(op, profile_bindings=tuple(b for b in bindings if profile_resource_address(b) == op.address))
            if op.action is not ChangeAction.DELETE
            else op
            for op in plan.operations
        )
        return RealizationPreparation.for_request(plan, snapshot, operations=operations)

    def _select(self, binding: DomainProfileBindingModel) -> DomainProfileBindingModel:
        return binding.model_copy(
            update={
                "value": deepcopy(self._choices.get(binding.coordinate.definition_digest, binding.value)),
                "provenance": DomainProfileBindingProvenanceModel(
                    basis=DomainProfileBindingBasis.BACKEND_SELECTED, source_ref="urn:example:profile-stub"
                ),
                "children": tuple(self._select(child) for child in binding.children),
            }
        )

    def apply(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        result = super().apply(plan, snapshot)
        if not result.success:
            return result
        entries = dict(result.snapshot.entries)
        for op in plan.operations:
            if op.action is not ChangeAction.DELETE and op.address in entries:
                entries[op.address] = replace(entries[op.address], profile_bindings=tuple(op.profile_bindings))
        return replace(result, snapshot=result.snapshot.with_entries(entries))


def profile_stub_target(
    context: DomainProfileResolutionContextModel,
    choices: Mapping[str, object] | None = None,
    *,
    mailbox: bool = False,
) -> RuntimeTarget:
    """Return a stub target whose manifest pins ``context`` for profile execution.

    ``mailbox`` additionally declares credential bindings and exact runtime mail
    services so account mailbox selections can be planned and prepared.
    """

    base = create_stub_target()
    manifest = replace(
        base.manifest,
        supported_contract_versions=base.manifest.supported_contract_versions
        | {PLAN_PROFILE_CONTRACT, BACKEND_PREPARATION_CONTRACT},
        domain_profile_context_digest=profile_context_digest(context),
    )
    if mailbox:
        provisioner = manifest.capabilities.provisioner
        support = manifest.realization_support[0]
        manifest = replace(
            manifest,
            capabilities=replace(
                manifest.capabilities,
                provisioner=replace(
                    provisioner,
                    supported_account_features=provisioner.supported_account_features | {"credential_bindings"},
                ),
            ),
            realization_support=(
                replace(
                    support,
                    supported_exact_requirement_kinds=support.supported_exact_requirement_kinds
                    | {"runtime-mail-services"},
                ),
                *manifest.realization_support[1:],
            ),
        )
    provisioner = ProfileStubProvisioner(manifest.realization_envelope, context, choices or {})
    return replace(base, manifest=manifest, provisioner=provisioner)

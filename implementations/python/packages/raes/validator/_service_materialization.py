"""Semantic validation for service-owned content materialization."""

from raes_contracts.domain_profiles import DomainProfileBindingModel

from ..deployment_tenancy import StateOwner
from ..propositions import AssertionRole, PropositionBasis
from ..relationships import RelationshipType


class _ServiceMaterializationMixin:
    def _verify_service_materialization(self, name: str, item: object) -> None:
        binding = item.service_materialization
        if isinstance(binding, DomainProfileBindingModel):
            # The selected semantic contract owns its parameters. The content
            # target and relationship authority are still validated by core.
            return
        label = f"Content '{name}' service_materialization"
        service_target = binding.target_service_ref
        target_owner = self._split_node_service_ref(service_target)
        if not self._is_unresolved_var(service_target) and target_owner is None:
            self._err(f"{label} target_service_ref '{service_target}' must resolve to a named compute service")
        elif target_owner is not None and target_owner[0] != item.target:
            self._err(f"{label} target_service_ref must belong to content target node '{item.target}'")
        self._verify_membership_refs(
            binding.ordering_content_refs,
            self._s.content,
            lambda ref: f"{label} ordering_content_ref '{ref}' not in content section",
        )
        if name in binding.ordering_content_refs:
            self._err(f"{label} cannot order content after itself")
        self._verify_materialization_readback(name, label, binding)
        self._verify_materialization_tenancy(label, service_target, binding)

    def _verify_materialization_readback(self, content_name: str, label: str, binding: object) -> None:
        self._verify_membership_refs(
            binding.evidence_requirement_refs,
            self._s.evidence_requirements,
            lambda ref: f"{label} evidence_requirement_ref '{ref}' not in evidence_requirements section",
        )
        for assertion_ref in binding.readback_assertion_refs:
            self._verify_materialization_assertion(content_name, label, binding, assertion_ref)
        self._verify_membership_refs(
            binding.observation_boundary_refs,
            self._s.observation_boundaries,
            lambda ref: f"{label} observation_boundary_ref '{ref}' not in observation_boundaries section",
        )
        for boundary_ref in binding.observation_boundary_refs:
            self._verify_materialization_boundary(content_name, label, boundary_ref)

    def _verify_materialization_assertion(
        self,
        content_name: str,
        label: str,
        binding: object,
        assertion_ref: str,
    ) -> None:
        if self._is_unresolved_var(assertion_ref):
            return
        assertion = self._s.assertions.get(assertion_ref)
        if assertion is None:
            self._err(f"{label} readback_assertion_ref '{assertion_ref}' not in assertions section")
            return
        if assertion.role is not AssertionRole.POSTCONDITION:
            self._err(f"{label} readback assertion '{assertion_ref}' must be a postcondition")
        proposition = self._s.propositions.get(assertion.proposition)
        if proposition is None:
            return
        self._verify_materialization_proposition(content_name, label, binding, assertion_ref, proposition)

    def _verify_materialization_proposition(
        self,
        content_name: str,
        label: str,
        binding: object,
        assertion_ref: str,
        proposition: object,
    ) -> None:
        if proposition.basis is not PropositionBasis.OBSERVED_STATE:
            self._err(f"{label} readback assertion '{assertion_ref}' must use an observed-state proposition")
        if not {content_name, f"content.{content_name}"}.intersection(proposition.subjects):
            self._err(f"{label} readback assertion '{assertion_ref}' must observe the exact content subject")
        if not set(binding.evidence_requirement_refs).issubset(proposition.evidence_requirements):
            self._err(f"{label} readback assertion '{assertion_ref}' must require the bound readback evidence")

    def _verify_materialization_boundary(self, content_name: str, label: str, boundary_ref: str) -> None:
        boundary = self._s.observation_boundaries.get(boundary_ref)
        if boundary is not None and not {content_name, f"content.{content_name}"}.intersection(
            boundary.observable_refs
        ):
            self._err(f"{label} observation boundary '{boundary_ref}' must expose the exact content subject")

    def _verify_materialization_tenancy(self, label: str, target: str, binding: object) -> None:
        relationship_ref = binding.shared_service_relationship_ref
        if not relationship_ref or self._is_unresolved_var(relationship_ref):
            return
        relationship = self._s.relationships.get(relationship_ref)
        if relationship is None:
            self._err(f"{label} shared_service_relationship_ref '{relationship_ref}' not in relationships section")
            return
        if relationship.type is not RelationshipType.USES_SHARED_SERVICE or relationship.shared_service is None:
            self._err(f"{label} relationship '{relationship_ref}' must be a typed uses_shared_service relationship")
            return
        if relationship.target != target:
            self._err(f"{label} relationship '{relationship_ref}' must target the same named service")
        detail = relationship.shared_service
        if detail.mutable_state_owner is StateOwner.NONE or detail.reset_generation_owner is StateOwner.NONE:
            self._err(f"{label} relationship '{relationship_ref}' must assign mutable-state and reset ownership")

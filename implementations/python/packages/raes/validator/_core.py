"""SemanticValidator _ValidatorCore (split from validator.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""

from .._base import is_variable_ref
from .._declarations import DeclarationIndex, build_declaration_index, operating_scope_aliases
from .._errors import SDLValidationError
from .._reference_targetability import PURPOSE_LABELS, ReferencePurpose
from .._runtime_service_families import (
    RuntimeFamilyReference,
    iter_runtime_family_references,
)
from ..entities import flatten_entities
from ..nodes import NodeType
from ..scenario import ScenarioContent

# Purposes that admit every referenceable declaration, so no target qualifier applies.
_UNQUALIFIED_PURPOSES = frozenset({ReferencePurpose.DECLARED, ReferencePurpose.AUTHORITY_ANCHOR})


class _ValidatorCore:
    def __init__(self, scenario: ScenarioContent) -> None:
        self._s = scenario
        self._errors: list[str] = []
        self._warnings: list[str] = []
        self._declaration_index: DeclarationIndex | None = None
        self._runtime_references: dict[str, RuntimeFamilyReference] | None = None

    def _err(self, msg: str) -> None:
        self._errors.append(msg)

    def _warn(self, msg: str) -> None:
        self._warnings.append(msg)

    @staticmethod
    def _is_unresolved_var(value: object) -> bool:
        return is_variable_ref(value)

    def _node_kind(self, node_name: str) -> NodeType | None:
        node = self._s.nodes.get(node_name)
        return node.type if node is not None else None

    def _is_switch_node(self, node_name: str) -> bool:
        return self._node_kind(node_name) == NodeType.SWITCH

    def _is_compute_node(self, node_name: str) -> bool:
        return self._node_kind(node_name) == NodeType.COMPUTE

    def _all_entity_names(self) -> set[str]:
        return set(flatten_entities(self._s.entities).keys())

    def _split_node_service_ref(self, ref: object) -> tuple[str, str] | None:
        """Resolve a qualified service ref without parsing rendered delimiters."""

        if not isinstance(ref, str):
            return None
        for node_name, node in self._s.nodes.items():
            for service in node.services:
                if service.name and ref == f"nodes.{node_name}.services.{service.name}":
                    return node_name, service.name
        return None

    def _workflow_step_refs(self) -> set[str]:
        refs: set[str] = set()
        for workflow_name, workflow in self._s.workflows.items():
            for step_name in workflow.steps:
                refs.add(f"{workflow_name}.{step_name}")
        return refs

    def _named_ref_index(self, purpose: ReferencePurpose = ReferencePurpose.DECLARED) -> dict[str, set[str]]:
        """Build the alias map of declarations the reference policy admits for *purpose*.

        Bare refs stay available for most top-level sections when they are
        unambiguous among eligible declarations. Qualified refs are always
        accepted for top-level sections, and are required for infrastructure
        entries because those keys intentionally mirror node names.
        """
        return self._require_declaration_index().reference_aliases(purpose)

    def _require_declaration_index(self) -> DeclarationIndex:
        if self._declaration_index is None:
            raise RuntimeError("declaration index must be built before reference validation")
        return self._declaration_index

    def _ineligible_detail(self, ref: str, purpose: ReferencePurpose) -> str:
        """Explain a reference that names declarations its purpose does not admit."""

        declared = sorted(self._named_ref_index().get(ref, ()))
        if not declared or purpose in _UNQUALIFIED_PURPOSES:
            return ""
        verb = "is" if len(declared) == 1 else "are"
        return f"; {', '.join(declared)} {verb} not eligible as {PURPOSE_LABELS[purpose]}"

    def _operating_scope_ref_index(self) -> dict[str, set[str]]:
        """Build the alias map for ACT-601 ``Agent.operating_scope``.

        ADR-020 §2 defines operating scope as the declarative boundary for
        where the participant may act or observe: compute hosts, switch-backed
        subnets, services, and content (and content items). The shared
        reference policy names those declaration kinds; see
        :func:`raes._declarations.operating_scope_aliases`. Non-spatial,
        non-resource elements (conditions, accounts, relationships,
        objectives, ...) are not scope boundaries.
        """
        return operating_scope_aliases(self._require_declaration_index(), self._s)

    def _validate_operating_scope_ref(self, ref: str, *, owner_label: str) -> None:
        """Validate ``operating_scope`` against the spatial/resource index."""
        index = self._operating_scope_ref_index()
        candidates = index.get(ref)
        if not candidates:
            self._err(f"{owner_label} operating_scope '{ref}' does not reference any defined targetable element")
            return
        if len(candidates) > 1:
            choices = ", ".join(sorted(candidates))
            self._err(f"{owner_label} operating_scope '{ref}' is ambiguous; use one of: {choices}")

    def _validate_named_ref(
        self,
        ref: str,
        *,
        owner_label: str,
        ref_label: str,
        purpose: ReferencePurpose = ReferencePurpose.DECLARED,
    ) -> None:
        """Validate a reference against the declarations eligible for *purpose*."""
        index = self._named_ref_index(purpose)
        candidates = index.get(ref)
        if not candidates:
            qualifier = "" if purpose in _UNQUALIFIED_PURPOSES else "targetable "
            self._err(
                f"{owner_label} {ref_label} '{ref}' does not reference any defined {qualifier}element"
                f"{self._ineligible_detail(ref, purpose)}"
            )
            return

        if len(candidates) > 1:
            choices = ", ".join(sorted(candidates))
            self._err(f"{owner_label} {ref_label} '{ref}' is ambiguous; use one of: {choices}")

    def validate(self) -> None:
        """Run all validation passes and raise on errors."""
        self._errors = []
        self._warnings = []
        self._declaration_index = build_declaration_index(self._s, raise_on_collision=False)
        self._errors.extend(self._declaration_index.collision_errors)

        # OCR passes
        self._verify_nodes()
        self._verify_infrastructure()
        self._verify_runtime_configuration()
        self._verify_features()
        self._verify_conditions()
        self._verify_entities()
        self._verify_injects()
        self._verify_events()
        self._verify_scripts()
        self._verify_stories()
        self._verify_roles()
        self._verify_stateful_resources()

        # New section passes
        self._verify_content()
        self._verify_accounts()
        self._verify_relationships()
        self._verify_domain_topology()
        self._verify_enterprise_identity()
        self._verify_deployment_tenancy()
        self._verify_relationship_database_access()
        self._verify_relationship_mail_access()
        self._verify_relationship_forwarding_edges()
        self._verify_relationship_service_integrations()
        self._verify_relationship_proxy_upstreams()
        self._verify_agents()
        self._verify_participant_behavior()
        self._verify_propositions_and_assertions()
        self._verify_objectives()
        self._verify_objective_success_assertions()
        self._verify_precondition_assertion_uses()
        self._verify_workflows()
        self._verify_participant_outcomes()
        self._verify_evidence_requirements()
        self._verify_augmentation_scope()
        self._verify_execution_policy()
        self._verify_time_model()
        self._verify_variables()
        self._verify_variation_points()
        self._verify_realization_designations()
        self._verify_explicitness()
        self._collect_advisories()

        if self._errors:
            raise SDLValidationError(self._errors)

    def validate_node_realization(self) -> None:
        """Validate a bounded portable node context, without creating author intent.

        The caller supplies the selected live nodes, infrastructure, stateful
        resources and accounts. This is not full scenario admission and cannot
        authorize features, participant roles, domain membership or capture.
        """

        self._errors = []
        self._warnings = []
        self._runtime_references = None
        for name, node in self._s.nodes.items():
            self._verify_node_operating_system(name, node)
            self._verify_node_architecture(name, node)
        self._verify_infrastructure()
        self._verify_runtime_configuration()
        self._verify_stateful_resources()
        self._verify_variables()
        if self._errors:
            raise SDLValidationError(self._errors)

    def _verify_runtime_configuration(self) -> None:
        """Shared native reference checks for authored and selected runtime values."""

        self._verify_runtime_network()
        self._verify_runtime_network_sensors()
        self._verify_runtime_network_detection_engines()
        self._verify_runtime_service_listeners()
        self._verify_runtime_application()
        self._verify_runtime_capability_overrides()
        self._verify_runtime_process_resource_limits()
        self._verify_runtime_database_services()
        self._verify_runtime_dns_services()
        self._verify_runtime_ssh_servers()
        self._verify_runtime_app_authorizations()
        self._verify_runtime_service_manager_units()
        self._verify_runtime_identity_authorities()
        self._verify_runtime_file_services()
        self._verify_runtime_security_monitoring_managers()
        self._verify_runtime_datastore_services()
        self._verify_runtime_platform_applications()
        self._verify_runtime_forwarding_agents()
        self._verify_runtime_orchestration_authorities()
        self._verify_runtime_mail_services()

    @property
    def warnings(self) -> list[str]:
        """Return non-fatal advisories collected during validation."""
        return list(self._warnings)

    def _collect_advisories(self) -> None:
        self._warn_missing_vm_resources()

    def _warn_missing_vm_resources(self) -> None:
        for name, node in self._s.nodes.items():
            if node.type != NodeType.COMPUTE:
                continue
            if node.resources is None:
                self._warn(
                    f"Node '{name}' is compute without 'resources'. This is "
                    "valid SDL, but may be undeployable unless the backend "
                    "supplies defaults."
                )

    def _runtime_reference(self, ref: object) -> RuntimeFamilyReference | None:
        """Resolve an exact registered runtime address without delimiter parsing."""

        if not isinstance(ref, str):
            return None
        if self._runtime_references is None:
            references: dict[str, RuntimeFamilyReference] = {}
            for reference in iter_runtime_family_references(self._s):
                references.setdefault(reference.address, reference)
            self._runtime_references = references
        return self._runtime_references.get(ref)

    def _resolve_database_service_ref(self, ref: object) -> object | None:
        """Resolve a qualified ``nodes.<node>.runtime.database_services.<id>`` ref.

        Accepts the database-service form and the ``.databases.<id>`` form; both
        resolve to the owning :class:`RuntimeDatabaseService` so a relationship's
        ``database_access`` can be checked against it.
        """
        reference = self._runtime_reference(ref)
        if reference is None or reference.family.collection_name != "database_services":
            return None
        if reference.collection_path not in {(), ("databases",)}:
            return None
        return reference.owning_item

    def _resolve_application_ref(self, ref: object) -> object | None:
        """Resolve a qualified ``nodes.<node>.runtime.applications.<id>`` ref.

        Returns the owning :class:`RuntimeApplicationSurface` so a relationship's
        ``database_access`` source endpoint can be confirmed to be a runtime
        application (ADR-029 §4).
        """
        reference = self._runtime_reference(ref)
        if (
            reference is None
            or reference.family.collection_name != "applications"
            or reference.item is not reference.owning_item
        ):
            return None
        return reference.item

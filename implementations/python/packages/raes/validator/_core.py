"""SemanticValidator _ValidatorCore (split from validator.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""

from collections import defaultdict

from .._base import is_variable_ref
from .._declarations import DeclarationIndex, build_declaration_index
from .._errors import SDLValidationError
from .._runtime_service_families import (
    RuntimeFamilyReference,
    iter_runtime_family_references,
)
from ..entities import flatten_entities
from ..nodes import NodeType
from ..scenario import ScenarioContent


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

    def _named_ref_index(self, *, targetable: bool = False) -> dict[str, set[str]]:
        """Build the alias map for generic relationship/objective refs.

        Bare refs stay available for most top-level sections when they are
        unambiguous. Qualified refs are always accepted for top-level sections,
        and are required for infrastructure entries because those keys
        intentionally mirror node names.
        """
        if self._declaration_index is None:
            raise RuntimeError("declaration index must be built before reference validation")
        return self._declaration_index.reference_aliases(targetable=targetable)

    def _operating_scope_ref_index(self) -> dict[str, set[str]]:
        """Build the alias map for ACT-601 ``Agent.operating_scope``.

        ADR-020 §2 defines operating scope as the declarative boundary for
        where the participant may act or observe — concretely subnets,
        hosts, services, and content (and content items). The split here
        mirrors the pre-existing scope-validation patterns:

        - hosts come from ``nodes.*`` but only compute nodes (matches
          ``initial_knowledge.hosts``).
        - subnets come from ``infrastructure.*`` but only switch-backed
          entries (matches ``allowed_subnets``).
        - services come from declared services on compute nodes.
        - content references stay open across content sections and items.

        Non-spatial, non-resource elements (conditions, accounts,
        relationships, objectives, …) are not scope boundaries even though
        they appear in the generic targetable index.
        """
        index: dict[str, set[str]] = defaultdict(set)

        # Hosts: compute nodes only. Both bare and qualified references
        # aliases are accepted. Switch nodes go through the subnets path,
        # never the host path.
        for node_name, node in self._s.nodes.items():
            if node.type != NodeType.COMPUTE:
                continue
            canonical = f"nodes.{node_name}"
            index[node_name].add(canonical)
            index[canonical].add(canonical)

        # Subnets: switch-backed infrastructure only. Both bare and
        # qualified aliases. Compute-backed infrastructure entries (which
        # mirror compute nodes' names) go through the host path's `nodes.*`
        # alias, not here.
        for infra_name, _infra in self._s.infrastructure.items():
            if not self._is_switch_node(infra_name):
                continue
            canonical = f"infrastructure.{infra_name}"
            index[infra_name].add(canonical)
            index[canonical].add(canonical)

        self._add_operating_scope_service_aliases(index)
        self._add_operating_scope_content_aliases(index)

        return {alias: set(candidates) for alias, candidates in index.items()}

    def _add_operating_scope_service_aliases(self, index: dict[str, set[str]]) -> None:
        # Services: qualified `nodes.<vm>.services.<svc>` refs plus bare
        # service names. The service-ref helper only emits names declared
        # on compute nodes (a service on a switch is meaningless), so no extra
        # filtering is needed here.
        for node_name, node in self._s.nodes.items():
            for service in node.services:
                if not service.name:
                    continue
                ref = f"nodes.{node_name}.services.{service.name}"
                index[ref].add(ref)
                index[service.name].add(ref)

    def _add_operating_scope_content_aliases(self, index: dict[str, set[str]]) -> None:
        # Content: sections and items keep the unrestricted aliasing from
        # the targetable index; ADR-020 does not split content by sub-type.
        for content_name in self._s.content:
            canonical = f"content.{content_name}"
            index[content_name].add(canonical)
            index[canonical].add(canonical)
        for content_name, content in self._s.content.items():
            for item in content.items:
                if not item.name:
                    continue
                canonical = f"content.{content_name}.items.{item.name}"
                index[item.name].add(canonical)
                index[canonical].add(canonical)

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
        targetable: bool = False,
    ) -> None:
        """Validate a generic reference against the named-element index."""
        index = self._named_ref_index(targetable=targetable)
        candidates = index.get(ref)
        if not candidates:
            qualifier = "targetable " if targetable else ""
            self._err(f"{owner_label} {ref_label} '{ref}' does not reference any defined {qualifier}element")
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

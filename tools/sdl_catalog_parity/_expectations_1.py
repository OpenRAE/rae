"""Reference-edge expectations, part 1 (split from one registry literal)."""

from __future__ import annotations

from tools.sdl_catalog_parity._paths import (
    _ARTIFACT_VOLUME_FIELDS,
    _DANGLING,
    _DANGLING_CYCLIC,
    _DANGLING_ROLE,
    _MAIL_SERVICE_SCOPE,
    _NODE_ROLES,
    _NON_PRECONDITION_ROLE,
    _SEMANTIC,
    _STRUCTURAL_MODEL,
    _SWITCH_BACKED,
)

_PARTICIPANT_PHASE = "semantic validation and instantiation"

EXPECTATIONS_PART_1: dict[str, tuple[(str, str, str)]] = {
    "nodes.*.features[]": ("features", _SEMANTIC, _DANGLING),
    "nodes.*.features.*": (_NODE_ROLES, _SEMANTIC, _DANGLING_ROLE),
    "nodes.*.conditions[]": ("conditions", _SEMANTIC, _DANGLING),
    "nodes.*.conditions.*": (_NODE_ROLES, _SEMANTIC, _DANGLING_ROLE),
    "conditions.*.proposition": (
        "propositions",
        _SEMANTIC,
        "fatal dangling or ambiguous when present",
    ),
    "propositions.*.subjects[]": ("eligible:observation_subject", _SEMANTIC, _DANGLING),
    "propositions.*.evidence_requirements[]": (
        "evidence_requirements",
        _SEMANTIC,
        _DANGLING,
    ),
    "assertions.*.proposition": ("propositions", _SEMANTIC, _DANGLING),
    "nodes.*.injects[]": ("injects", _SEMANTIC, _DANGLING),
    "nodes.*.injects.*": (_NODE_ROLES, _SEMANTIC, _DANGLING_ROLE),
    "nodes.*.roles.*.entities[]": ("entities", _SEMANTIC, _DANGLING),
    "infrastructure.*.$key": (
        "nodes",
        _SEMANTIC,
        "fatal when no same-named node exists",
    ),
    "infrastructure.*.links[]": ("infrastructure", _SEMANTIC, _DANGLING),
    "infrastructure.*.properties[].*": (
        "infrastructure",
        _SEMANTIC,
        "fatal unless the key names a linked switch-backed entry",
    ),
    "infrastructure.*.acls[].from_net": ("infrastructure", _SEMANTIC, _SWITCH_BACKED),
    "infrastructure.*.acls[].to_net": ("infrastructure", _SEMANTIC, _SWITCH_BACKED),
    "infrastructure.*.dependencies[]": ("infrastructure", _SEMANTIC, _DANGLING),
    "features.*.dependencies[]": ("features", _SEMANTIC, _DANGLING_CYCLIC),
    "entities.*.events[]": ("events", _SEMANTIC, _DANGLING),
    "injects.*.from_entity": ("entities", _SEMANTIC, _DANGLING),
    "injects.*.to_entities[]": ("entities", _SEMANTIC, _DANGLING),
    "events.*.assertions[]": ("assertions", _SEMANTIC, _NON_PRECONDITION_ROLE),
    "events.*.injects[]": ("injects", _SEMANTIC, _DANGLING),
    "scripts.*.events[]": ("events", _SEMANTIC, _DANGLING),
    "stories.*.scripts[]": ("scripts", _SEMANTIC, _DANGLING),
    "content.*.target": ("nodes", _SEMANTIC, "fatal unless target is a compute node"),
    "content.*.service_materialization.target_service_ref": (
        "derived:node_services",
        _SEMANTIC,
        "fatal unless the exact service exists on the content target compute node",
    ),
    "content.*.service_materialization.shared_service_relationship_ref": (
        "relationships",
        _SEMANTIC,
        "fatal unless a matching typed shared-service relationship owns cross-tenant mutable state/reset",
    ),
    "content.*.service_materialization.ordering_content_refs[]": (
        "content",
        "semantic validation and planner ordering",
        "fatal dangling, self, or cyclic dependency",
    ),
    "content.*.service_materialization.readback_assertion_refs[]": (
        "assertions",
        _SEMANTIC,
        "fatal unless each ref is an observed-state postcondition",
    ),
    "content.*.service_materialization.evidence_requirement_refs[]": (
        "evidence_requirements",
        _SEMANTIC,
        "fatal unless each ref exists and every readback proposition requires it",
    ),
    "content.*.service_materialization.observation_boundary_refs[]": (
        "observation_boundaries",
        _SEMANTIC,
        "fatal dangling ref",
    ),
    "generated_artifacts.*.consumers[].node": ("nodes", _STRUCTURAL_MODEL, _DANGLING),
    "generated_artifacts.*.ordering_dependencies[]": (
        _ARTIFACT_VOLUME_FIELDS,
        "structural model and planner graph validation",
        _DANGLING_CYCLIC,
    ),
    "generated_artifacts.*.refresh_dependencies[]": (
        _ARTIFACT_VOLUME_FIELDS,
        _STRUCTURAL_MODEL,
        _DANGLING,
    ),
    "persistent_volumes.*.consumers[].node": ("nodes", _STRUCTURAL_MODEL, _DANGLING),
    "persistent_volumes.*.ordering_dependencies[]": (
        _ARTIFACT_VOLUME_FIELDS,
        "structural model and planner graph validation",
        _DANGLING_CYCLIC,
    ),
    "persistent_volumes.*.refresh_dependencies[]": (
        _ARTIFACT_VOLUME_FIELDS,
        _STRUCTURAL_MODEL,
        _DANGLING,
    ),
    "accounts.*.domain_ref": (
        "identity_domains",
        _SEMANTIC,
        "fatal dangling, ambiguous, or inconsistent topology",
    ),
    "identity_domains.*.authority_account_ref": (
        "accounts",
        _SEMANTIC,
        "fatal dangling, ambiguous, or authority outside domain controllers",
    ),
    "identity_forests.*.root_domain_ref": (
        "identity_domains",
        _SEMANTIC,
        "fatal dangling or root outside declared membership",
    ),
    "identity_forests.*.domain_refs[]": (
        "identity_domains",
        _SEMANTIC,
        "fatal dangling, duplicate, or domain in multiple forests",
    ),
    "identity_facades.*.service_ref": (
        "targetable",
        _SEMANTIC,
        "fatal unless target is a named compute service",
    ),
    "deployment_cells.*.tenant_ref": ("deployment_tenants", _SEMANTIC, _DANGLING),
    "deployment_cells.*.node_refs[]": (
        "nodes",
        _SEMANTIC,
        "fatal dangling, duplicate, or node in multiple cells",
    ),
    "accounts.*.node": ("nodes", _SEMANTIC, "fatal unless target is a compute node"),
    "relationships.*.source": (
        "eligible:relationship_endpoint",
        _SEMANTIC,
        "fatal dangling or ambiguous; subtype may narrow domain",
    ),
    "relationships.*.target": (
        "eligible:relationship_endpoint",
        _SEMANTIC,
        "fatal dangling or ambiguous; subtype may narrow domain",
    ),
    "relationships.*.participant.source_action_refs[]": (
        "action_contracts",
        _PARTICIPANT_PHASE,
        "fatal dangling, duplicate alias, or action unavailable to source",
    ),
    "relationships.*.participant.target_action_refs[]": (
        "action_contracts",
        _PARTICIPANT_PHASE,
        "fatal dangling, duplicate alias, or action unavailable to target",
    ),
    "relationships.*.participant.objective_refs[]": (
        "objectives",
        _PARTICIPANT_PHASE,
        "fatal dangling, duplicate alias, or unrelated objective owner",
    ),
    "relationships.*.participant.behavior_specification_refs[]": (
        "behavior_specifications",
        _PARTICIPANT_PHASE,
        "fatal dangling, duplicate alias, or unrelated participant binding",
    ),
    "relationships.*.participant.authority_basis_refs[]": (
        "eligible:authority_anchor",
        _PARTICIPANT_PHASE,
        "fatal dangling, ambiguous, duplicate alias, or wider than source authority",
    ),
    "relationships.*.participant.scope_refs[]": (
        "derived:operating_scope",
        _PARTICIPANT_PHASE,
        "fatal duplicate alias or outside spatial/resource scope of either endpoint or selected control policy",
    ),
    "relationships.*.participant.observation_boundary_refs[]": (
        "observation_boundaries",
        _PARTICIPANT_PHASE,
        "fatal dangling, duplicate alias, or unavailable source observation",
    ),
    "relationships.*.participant.control_specification_ref": (
        "behavior_specifications",
        _PARTICIPANT_PHASE,
        "fatal missing mixed-control policy or contradictory controller direction/scope",
    ),
    "relationships.*.database_access.role_ref": (
        "derived:database_roles",
        _SEMANTIC,
        "fatal outside the target database service",
    ),
    "relationships.*.mail_access.listener_ref": (
        "derived:mail_listeners",
        _SEMANTIC,
        _MAIL_SERVICE_SCOPE,
    ),
    "relationships.*.mail_access.mailbox_ref": (
        "derived:mailboxes",
        _SEMANTIC,
        _MAIL_SERVICE_SCOPE,
    ),
    "relationships.*.mail_access.domain_ref": (
        "derived:mail_domains",
        _SEMANTIC,
        _MAIL_SERVICE_SCOPE,
    ),
    "relationships.*.forwarding_edge.forwarder_ref": (
        "runtime:forwarding_agents",
        _SEMANTIC,
        "fatal dangling or ambiguous across scenario and node scopes",
    ),
    "nodes.*.runtime.network_detection_engines[].rule_sources[].generated_by": (
        "runtime:forwarding_agents",
        _SEMANTIC,
        "fatal dangling or ambiguous across scenario and node scopes",
    ),
    "relationships.*.service_integration.consumer_ref": (
        "runtime:platform_applications",
        _SEMANTIC,
        _DANGLING,
    ),
    "relationships.*.service_integration.engine_ref": (
        "runtime:platform_applications",
        _SEMANTIC,
        _DANGLING,
    ),
    "relationships.*.service_integration.auth_principal_ref": (
        "derived:engine_authorization_principals",
        _SEMANTIC,
        "fatal outside the engine authorization scope",
    ),
    "relationships.*.proxy_upstream.route_ref": (
        "derived:source_application_routes",
        _SEMANTIC,
        "fatal outside the source application",
    ),
    "relationships.*.proxy_upstream.upstream_node_ref": ("nodes", _SEMANTIC, _DANGLING),
    "relationships.*.proxy_upstream.upstream_service_ref": (
        "derived:upstream_node_services",
        _SEMANTIC,
        "fatal without a resolvable upstream node and service",
    ),
    "relationships.*.domain_join.controller_refs[]": (
        "nodes",
        _SEMANTIC,
        "fatal dangling, ambiguous, or controller outside target domain",
    ),
    "relationships.*.shared_service.mutable_state_refs[]": (
        "persistent_volumes",
        _SEMANTIC,
        "fatal dangling or conflicting state ownership",
    ),
}

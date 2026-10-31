"""Runtime platform-application (RuntimePlatformApplication) SDL surface tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from raes._runtime_service_families import RUNTIME_SERVICE_FAMILIES
from raes.runtime_platform_application import (
    RelationshipServiceIntegration,
    RelationshipServiceIntegrationDirection,
    RelationshipServiceIntegrationKind,
    RuntimePlatformApplication,
    RuntimePlatformApplicationCapability,
    RuntimePlatformApplicationCapabilityKind,
    RuntimePlatformApplicationConnector,
    RuntimePlatformApplicationConnectorKind,
    RuntimePlatformApplicationContentObject,
    RuntimePlatformApplicationContentObjectKind,
    RuntimePlatformApplicationExecutionPolicy,
    RuntimePlatformApplicationKind,
    RuntimePlatformApplicationMarking,
    RuntimePlatformApplicationMarkingScheme,
    RuntimePlatformApplicationOrganization,
    RuntimePlatformApplicationSetting,
    RuntimePlatformApplicationSettingClassification,
    RuntimePlatformApplicationSettingProvenance,
    RuntimePlatformApplicationTenant,
    RuntimePlatformApplicationUpstreamBinding,
    RuntimePlatformApplicationUpstreamBindingRole,
)
from raes.scenario import Scenario
from raes.validator import SemanticValidator
from raes_schemas import schema_bundle

# --------------------------------------------------------------------------- #
# Legacy per-platform_kind fixtures retained as compatibility examples
# --------------------------------------------------------------------------- #


def _threat_intel(**overrides) -> dict:
    application = {
        "platform_application_id": "misp",
        "service": "misp-web",
        "platform_kind": "threat_intel",
        "product": "MISP",
        "version": "2.4",
        "organizations": [{"organization_id": "org-aptl", "name": "APTL"}],
        "content_objects": [
            {"content_object_id": "tax-tlp", "kind": "taxonomy", "name": "tlp", "attributes": {"namespace": "tlp"}},
            {
                "content_object_id": "gc-mitre",
                "kind": "galaxy_cluster",
                "name": "mitre-attack",
                "references": ["tax-tlp"],
            },
            {"content_object_id": "wl-cidr", "kind": "warninglist", "attributes": {"match_type": "cidr"}},
            {
                "content_object_id": "feed-ct",
                "kind": "feed",
                "attributes": {"provider": "circl", "source_format": "misp"},
            },
            {"content_object_id": "sg-trusted", "kind": "sharing_group", "name": "trusted"},
        ],
        "markings": [{"marking_id": "tlp-red", "scheme": "tlp", "level": "red"}],
        "authorization_ref": "misp-rbac",
    }
    application.update(overrides)
    return application


def _soar(**overrides) -> dict:
    application = {
        "platform_application_id": "shuffle",
        "platform_kind": "soar",
        "product": "Shuffle",
        "content_objects": [
            {"content_object_id": "wf-enrich", "kind": "workflow", "name": "enrich-ioc"},
            {"content_object_id": "app-virustotal", "kind": "app", "name": "virustotal"},
        ],
    }
    application.update(overrides)
    return application


def _analyzer_engine(**overrides) -> dict:
    application = {
        "platform_application_id": "cortex",
        "platform_kind": "analyzer_engine",
        "product": "Cortex",
        "content_objects": [
            {"content_object_id": "an-virustotal", "kind": "analyzer", "name": "VirusTotal_GetReport"},
            {"content_object_id": "re-block", "kind": "responder", "name": "Block_IP"},
        ],
        "execution_policy": {"policy_id": "default", "runner": "docker", "max_concurrent_jobs": 5},
    }
    application.update(overrides)
    return application


def _case_management(**overrides) -> dict:
    application = {
        "platform_application_id": "thehive",
        "platform_kind": "case_management",
        "product": "TheHive",
        "content_objects": [
            {"content_object_id": "ct-incident", "kind": "case_template", "name": "incident"},
            {"content_object_id": "cf-severity", "kind": "custom_field", "name": "business-severity"},
        ],
    }
    application.update(overrides)
    return application


def _analytics_dashboard(**overrides) -> dict:
    application = {
        "platform_application_id": "wazuh-dashboard",
        "platform_kind": "analytics_dashboard",
        "product": "wazuh-dashboard",
        "tenants": [{"tenant_id": "global", "name": "global_tenant"}],
        "content_objects": [
            {"content_object_id": "ip-alerts", "kind": "index_pattern", "name": "wazuh-alerts-*"},
            {
                "content_object_id": "viz-top-agents",
                "kind": "visualization",
                "name": "top-agents",
                "references": ["ip-alerts"],
            },
        ],
        "upstream_bindings": [
            {
                "binding_id": "indexer-backend",
                "role": "index_backend",
                "target_node_ref": "wazuh-indexer",
                "target_service_ref": "indexer-https",
            }
        ],
    }
    application.update(overrides)
    return application


def _opencti(**overrides) -> dict:
    application = {
        "platform_application_id": "opencti",
        "service": "opencti-api",
        "product": "OpenCTI",
        "capabilities": [
            {
                "capability_id": "intelligence",
                "kind": "threat_intelligence_management",
                "evidence_refs": ["/evidence/opencti-capabilities.json"],
            },
            {"capability_id": "exchange", "kind": "intelligence_exchange"},
            {"capability_id": "cases", "kind": "case_management"},
            {"capability_id": "analysis", "kind": "analysis_execution"},
            {"capability_id": "automation", "kind": "workflow_automation"},
            {"capability_id": "presentation", "kind": "analytics_presentation"},
        ],
    }
    application.update(overrides)
    return application


_ALL_FIXTURES = {
    "threat_intel": _threat_intel,
    "soar": _soar,
    "analyzer_engine": _analyzer_engine,
    "case_management": _case_management,
    "analytics_dashboard": _analytics_dashboard,
}


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_full_threat_intel_inventory_is_valid() -> None:
    application = RuntimePlatformApplication(**_threat_intel())
    assert application.platform_application_id == "misp"
    assert application.platform_kind == RuntimePlatformApplicationKind.THREAT_INTEL
    assert application.content_objects[0].kind == RuntimePlatformApplicationContentObjectKind.TAXONOMY
    assert application.content_objects[1].references == ["tax-tlp"]
    assert application.markings[0].scheme == RuntimePlatformApplicationMarkingScheme.TLP
    assert application.authorization_ref == "misp-rbac"


@pytest.mark.parametrize("kind", list(_ALL_FIXTURES))
def test_every_platform_kind_fixture_is_valid(kind: str) -> None:
    application = RuntimePlatformApplication(**_ALL_FIXTURES[kind]())
    assert application.platform_kind == RuntimePlatformApplicationKind(kind)


def test_analytics_dashboard_binding_and_references() -> None:
    application = RuntimePlatformApplication(**_analytics_dashboard())
    binding = application.upstream_bindings[0]
    assert binding.role == RuntimePlatformApplicationUpstreamBindingRole.INDEX_BACKEND
    assert application.tenants[0].tenant_id == "global"


def test_one_application_can_declare_multiple_provider_neutral_capabilities() -> None:
    application = RuntimePlatformApplication(**_opencti())

    assert [capability.kind for capability in application.capabilities] == [
        RuntimePlatformApplicationCapabilityKind.THREAT_INTELLIGENCE_MANAGEMENT,
        RuntimePlatformApplicationCapabilityKind.INTELLIGENCE_EXCHANGE,
        RuntimePlatformApplicationCapabilityKind.CASE_MANAGEMENT,
        RuntimePlatformApplicationCapabilityKind.ANALYSIS_EXECUTION,
        RuntimePlatformApplicationCapabilityKind.WORKFLOW_AUTOMATION,
        RuntimePlatformApplicationCapabilityKind.ANALYTICS_PRESENTATION,
    ]
    assert application.capabilities[0].evidence_refs == ["/evidence/opencti-capabilities.json"]


# --------------------------------------------------------------------------- #
# Stable-id rejection (empty / variable placeholder)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("bad_id", ["", "   ", "${app}"])
def test_platform_application_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="platform_application_id"):
        RuntimePlatformApplication(**_soar(platform_application_id=bad_id))


@pytest.mark.parametrize("bad_id", ["", "${org}"])
def test_organization_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="organization_id"):
        RuntimePlatformApplicationOrganization(organization_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "${tenant}"])
def test_tenant_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="tenant_id"):
        RuntimePlatformApplicationTenant(tenant_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "${obj}"])
def test_content_object_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="content_object_id"):
        RuntimePlatformApplicationContentObject(content_object_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "${capability}"])
def test_capability_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="capability_id"):
        RuntimePlatformApplicationCapability(capability_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "${marking}"])
def test_marking_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="marking_id"):
        RuntimePlatformApplicationMarking(marking_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "${binding}"])
def test_binding_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="binding_id"):
        RuntimePlatformApplicationUpstreamBinding(binding_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "${connector}"])
def test_connector_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="connector_id"):
        RuntimePlatformApplicationConnector(connector_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "${setting}"])
def test_setting_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="setting_id"):
        RuntimePlatformApplicationSetting(setting_id=bad_id)


# --------------------------------------------------------------------------- #
# Enum normalization + sentinels
# --------------------------------------------------------------------------- #


def test_enum_normalization_is_case_and_separator_insensitive() -> None:
    application = RuntimePlatformApplication(**_soar(platform_kind="SOAR"))
    assert application.platform_kind == RuntimePlatformApplicationKind.SOAR

    obj = RuntimePlatformApplicationContentObject(content_object_id="o", kind="GALAXY-CLUSTER")
    assert obj.kind == RuntimePlatformApplicationContentObjectKind.GALAXY_CLUSTER

    binding = RuntimePlatformApplicationUpstreamBinding(binding_id="b", role="INDEX-BACKEND")
    assert binding.role == RuntimePlatformApplicationUpstreamBindingRole.INDEX_BACKEND

    connector = RuntimePlatformApplicationConnector(connector_id="c", kind="ANALYZER-ENGINE")
    assert connector.kind == RuntimePlatformApplicationConnectorKind.ANALYZER_ENGINE

    setting = RuntimePlatformApplicationSetting(setting_id="s", provenance="CONFIG-FILE")
    assert setting.provenance == RuntimePlatformApplicationSettingProvenance.CONFIG_FILE

    capability = RuntimePlatformApplicationCapability(capability_id="intel", kind="THREAT-INTELLIGENCE-MANAGEMENT")
    assert capability.kind == RuntimePlatformApplicationCapabilityKind.THREAT_INTELLIGENCE_MANAGEMENT


def test_variable_placeholder_enums_pass_through() -> None:
    obj = RuntimePlatformApplicationContentObject(content_object_id="o", kind="${kind}")
    assert obj.kind == "${kind}"

    capability = RuntimePlatformApplicationCapability(capability_id="c", kind="${kind}")
    assert capability.kind == "${kind}"


def test_unknown_enum_member_is_rejected() -> None:
    with pytest.raises(ValidationError, match="platform_kind must be one of"):
        RuntimePlatformApplication(platform_application_id="p", platform_kind="bogus")

    with pytest.raises(ValidationError, match="kind must be one of"):
        RuntimePlatformApplicationCapability(capability_id="c", kind="bogus")


def test_open_taxonomies_carry_unknown_and_other() -> None:
    for enum_cls in (
        RuntimePlatformApplicationKind,
        RuntimePlatformApplicationCapabilityKind,
        RuntimePlatformApplicationContentObjectKind,
        RuntimePlatformApplicationUpstreamBindingRole,
        RuntimePlatformApplicationConnectorKind,
        RuntimePlatformApplicationSettingProvenance,
    ):
        members = {m.value for m in enum_cls}
        assert {"unknown", "other"} <= members, enum_cls.__name__


def test_closed_vocabularies_carry_no_sentinels() -> None:
    scheme = {m.value for m in RuntimePlatformApplicationMarkingScheme}
    assert scheme == {"tlp", "pap", "distribution"}
    classification = {m.value for m in RuntimePlatformApplicationSettingClassification}
    assert classification == {"plain", "redacted", "operator_secret"}


# --------------------------------------------------------------------------- #
# Duplicate-id rejection + list coercion
# --------------------------------------------------------------------------- #


def test_rejects_duplicate_local_stable_ids_across_child_kinds() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime platform application stable id 'shared-id'"):
        RuntimePlatformApplication(
            platform_application_id="p",
            organizations=[{"organization_id": "shared-id"}],
            tenants=[{"tenant_id": "shared-id"}],
        )


def test_capability_ids_share_the_application_local_stable_id_namespace() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime platform application stable id 'shared-id'"):
        RuntimePlatformApplication(
            platform_application_id="p",
            capabilities=[{"capability_id": "shared-id", "kind": "case_management"}],
            content_objects=[{"content_object_id": "shared-id"}],
        )


def test_rejects_duplicate_content_object_references() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime platform application references entry on 'o'"):
        RuntimePlatformApplicationContentObject(content_object_id="o", references=["a", "a"])


def test_rejects_duplicate_capability_evidence_references() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime platform application evidence_refs entry on 'c'"):
        RuntimePlatformApplicationCapability(capability_id="c", evidence_refs=["/evidence.json", "/evidence.json"])


def test_scalar_ref_lists_coerce_to_single_element_lists() -> None:
    obj = RuntimePlatformApplicationContentObject(
        content_object_id="o", references="ip-1", marking_refs="tlp-red", evidence_refs="/evidence.json"
    )
    assert obj.references == ["ip-1"]
    assert obj.marking_refs == ["tlp-red"]
    assert obj.evidence_refs == ["/evidence.json"]

    capability = RuntimePlatformApplicationCapability(capability_id="c", evidence_refs="/capability.json")
    assert capability.evidence_refs == ["/capability.json"]


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        RuntimePlatformApplicationOrganization(organization_id="o", bogus="x")


# --------------------------------------------------------------------------- #
# Content objects never carry raw bodies
# --------------------------------------------------------------------------- #


def test_content_object_has_no_raw_body_field() -> None:
    fields = set(RuntimePlatformApplicationContentObject.model_fields)
    assert not (fields & {"body", "raw", "raw_body", "content", "document", "payload"})
    assert {"attributes", "references", "marking_refs", "evidence_refs"} <= fields


# --------------------------------------------------------------------------- #
# Secret redaction (connectors + settings)
# --------------------------------------------------------------------------- #


def test_secret_named_connector_may_use_plain_scenario_classification() -> None:
    connector = RuntimePlatformApplicationConnector(
        connector_id="c",
        name="cortex-api-key",
        credential_classification="plain",
    )

    assert connector.credential_classification == RuntimePlatformApplicationSettingClassification.PLAIN


def test_secret_named_connector_with_redacted_classification_is_valid() -> None:
    connector = RuntimePlatformApplicationConnector(
        connector_id="c", name="cortex-api-key", credential_classification="operator_secret"
    )
    assert connector.credential_classification == RuntimePlatformApplicationSettingClassification.OPERATOR_SECRET


def test_secret_named_setting_may_carry_scenario_value() -> None:
    setting = RuntimePlatformApplicationSetting(setting_id="s", name="admin_password", value="hunter2")

    assert setting.value == "hunter2"


def test_secret_named_setting_redacted_is_valid() -> None:
    setting = RuntimePlatformApplicationSetting(setting_id="s", name="admin_password", classification="redacted")
    assert setting.classification == RuntimePlatformApplicationSettingClassification.REDACTED


def test_redacted_setting_must_not_carry_raw_value() -> None:
    with pytest.raises(ValidationError, match="must omit its raw value"):
        RuntimePlatformApplicationSetting(setting_id="s", name="log_level", value="debug", classification="redacted")


def test_plain_non_secret_setting_keeps_value() -> None:
    setting = RuntimePlatformApplicationSetting(setting_id="s", name="log_level", value="debug")
    assert setting.value == "debug"


# --------------------------------------------------------------------------- #
# Legacy platform categories do not imply configuration completeness
# --------------------------------------------------------------------------- #


def test_unknown_platform_kind_is_permissive() -> None:
    application = RuntimePlatformApplication(platform_application_id="p", platform_kind="unknown")
    assert application.platform_kind == RuntimePlatformApplicationKind.UNKNOWN


def test_other_platform_kind_is_permissive() -> None:
    application = RuntimePlatformApplication(platform_application_id="p", platform_kind="other")
    assert application.platform_kind == RuntimePlatformApplicationKind.OTHER


def test_default_platform_kind_is_unknown_and_permissive() -> None:
    application = RuntimePlatformApplication(platform_application_id="p")
    assert application.platform_kind == RuntimePlatformApplicationKind.UNKNOWN


def test_variable_placeholder_platform_kind_is_exempt() -> None:
    application = RuntimePlatformApplication(platform_application_id="p", platform_kind="${kind}")
    assert application.platform_kind == "${kind}"


@pytest.mark.parametrize(
    "platform_kind",
    ["threat_intel", "soar", "analyzer_engine", "case_management", "analytics_dashboard"],
)
def test_legacy_platform_kind_does_not_require_product_specific_content(platform_kind: str) -> None:
    application = RuntimePlatformApplication(platform_application_id="platform", platform_kind=platform_kind)

    assert application.platform_kind == RuntimePlatformApplicationKind(platform_kind)
    assert application.capabilities == []


def test_capabilities_are_registered_as_qualified_reference_children() -> None:
    family = next(family for family in RUNTIME_SERVICE_FAMILIES if family.collection_name == "platform_applications")

    assert ("capabilities", "capability_id") in {(child.collection_name, child.id_field) for child in family.child_refs}


def test_qualified_capability_reference_resolves_in_a_relationship() -> None:
    scenario = Scenario(
        name="platform-capability-reference",
        nodes={
            "tip": {
                "type": "compute",
                "runtime": {
                    "platform_applications": [
                        {
                            "platform_application_id": "opencti",
                            "capabilities": [
                                {
                                    "capability_id": "intelligence",
                                    "kind": "threat_intelligence_management",
                                }
                            ],
                        }
                    ]
                },
            }
        },
        relationships={
            "uses-intelligence": {
                "type": "depends_on",
                "source": "nodes.tip",
                "target": "nodes.tip.runtime.platform_applications.opencti.capabilities.intelligence",
            }
        },
    )

    SemanticValidator(scenario).validate()


def test_legacy_fields_are_marked_deprecated_in_the_model_schema() -> None:
    properties = RuntimePlatformApplication.model_json_schema()["properties"]

    assert properties["platform_kind"]["deprecated"] is True
    assert properties["content_objects"]["deprecated"] is True
    assert properties["capabilities"].get("deprecated") is not True


def test_published_scenario_contract_exposes_capabilities_and_legacy_deprecations() -> None:
    definitions = schema_bundle()["sdl-authoring-input-v1"]["$defs"]
    application_properties = definitions["RuntimePlatformApplication"]["properties"]

    assert application_properties["capabilities"]["items"] == {"$ref": "#/$defs/RuntimePlatformApplicationCapability"}
    assert application_properties["platform_kind"]["deprecated"] is True
    assert application_properties["content_objects"]["deprecated"] is True
    assert definitions["RuntimePlatformApplicationCapabilityKind"]["enum"] == [
        "threat_intelligence_management",
        "intelligence_exchange",
        "case_management",
        "analysis_execution",
        "workflow_automation",
        "analytics_presentation",
        "unknown",
        "other",
    ]


def test_execution_policy_parses_nested_fields() -> None:
    policy = RuntimePlatformApplicationExecutionPolicy(policy_id="p", runner="docker", max_concurrent_jobs="8")
    assert policy.max_concurrent_jobs == 8


# --------------------------------------------------------------------------- #
# RelationshipServiceIntegration
# --------------------------------------------------------------------------- #


def test_service_integration_full_edge_is_valid() -> None:
    integration = RelationshipServiceIntegration(
        consumer_ref="thehive",
        engine_ref="cortex",
        integration_kind="analyzer",
        auth_principal_ref="cortex-api-user",
        enabled=True,
        direction="outbound",
        description="TheHive calls Cortex analyzers",
    )
    assert integration.consumer_ref == "thehive"
    assert integration.engine_ref == "cortex"
    assert integration.integration_kind == RelationshipServiceIntegrationKind.ANALYZER
    assert integration.auth_principal_ref == "cortex-api-user"
    assert integration.enabled is True
    assert integration.direction == RelationshipServiceIntegrationDirection.OUTBOUND


def test_service_integration_defaults() -> None:
    integration = RelationshipServiceIntegration()
    assert integration.integration_kind == RelationshipServiceIntegrationKind.UNKNOWN
    assert integration.direction == RelationshipServiceIntegrationDirection.BIDIRECTIONAL
    assert integration.enabled is None


def test_service_integration_open_kind_normalizes() -> None:
    integration = RelationshipServiceIntegration(integration_kind="WEBHOOK")
    assert integration.integration_kind == RelationshipServiceIntegrationKind.WEBHOOK
    integration = RelationshipServiceIntegration(integration_kind="ENRICHMENT")
    assert integration.integration_kind == RelationshipServiceIntegrationKind.ENRICHMENT


def test_service_integration_open_kind_carries_unknown_and_other() -> None:
    members = {m.value for m in RelationshipServiceIntegrationKind}
    assert {"unknown", "other"} <= members


def test_service_integration_open_kind_accepts_unknown_member() -> None:
    integration = RelationshipServiceIntegration(integration_kind="unknown")
    assert integration.integration_kind == RelationshipServiceIntegrationKind.UNKNOWN


def test_service_integration_closed_direction_normalizes() -> None:
    integration = RelationshipServiceIntegration(direction="INBOUND")
    assert integration.direction == RelationshipServiceIntegrationDirection.INBOUND
    integration = RelationshipServiceIntegration(direction="bidirectional")
    assert integration.direction == RelationshipServiceIntegrationDirection.BIDIRECTIONAL


def test_service_integration_closed_direction_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError, match="direction must be one of"):
        RelationshipServiceIntegration(direction="sideways")


def test_service_integration_closed_direction_carries_no_sentinels() -> None:
    members = {m.value for m in RelationshipServiceIntegrationDirection}
    assert members == {"inbound", "outbound", "bidirectional"}


def test_service_integration_variable_placeholder_enums_pass_through() -> None:
    integration = RelationshipServiceIntegration(integration_kind="${kind}", direction="${dir}")
    assert integration.integration_kind == "${kind}"
    assert integration.direction == "${dir}"


def test_service_integration_enabled_parses_string_bool() -> None:
    integration = RelationshipServiceIntegration(enabled="false")
    assert integration.enabled is False
    integration = RelationshipServiceIntegration(enabled="${flag}")
    assert integration.enabled == "${flag}"

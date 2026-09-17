"""Runtime forwarding-agent (SCN-010 §5.5) SDL surface tests.

Covers the OPEN ``agent_kind`` discriminator spine, the typed source / transform
/ ship-target / buffer-policy / reload-channel / setting children, secret-bearing
setting + enrollment-identity redaction, duplicate-id rejection, partial
descriptions and composed pipelines. Selected completeness belongs to admission.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from raes._errors import SDLValidationError
from raes.runtime_forwarding_agent import (
    RelationshipForwardingEdge,
    RuntimeForwardingAgent,
    RuntimeForwardingAgentImplementation,
    RuntimeForwardingAgentKind,
    RuntimeForwardingBufferCrypto,
    RuntimeForwardingBufferPolicy,
    RuntimeForwardingEnrollmentClassification,
    RuntimeForwardingParseFormat,
    RuntimeForwardingProtocol,
    RuntimeForwardingReloadChannel,
    RuntimeForwardingReloadChannelKind,
    RuntimeForwardingSetting,
    RuntimeForwardingShipTarget,
    RuntimeForwardingSource,
    RuntimeForwardingSourceKind,
    RuntimeForwardingTransform,
    RuntimeForwardingTransformKind,
)
from raes.runtime_security_monitoring import RuntimeSecurityMonitoringListenerRole
from raes.scenario import Scenario
from raes.validator import SemanticValidator

# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


def _log_forwarder(**overrides) -> dict:
    agent = {
        "forwarding_agent_id": "wazuh-sidecar-suricata",
        "implementation": "wazuh_agent",
        "agent_kind": "log_forwarder",
        "version": "4.7.0",
        "name": "suricata-eve-shipper",
        "sources": [
            {
                "source_id": "eve",
                "kind": "tailed_path",
                "location": "/logs/eve.json",
                "parse_format": "json",
            }
        ],
        "transforms": [{"transform_id": "passthrough", "kind": "passthrough"}],
        "ship_targets": [
            {
                "target_id": "manager",
                "target_node_ref": "wazuh-manager",
                "ingestion_port": 1514,
                "enrollment_port": 1515,
                "protocol": "syslog",
                "enrollment_identity_classification": "redacted",
            }
        ],
        "buffer_policy": {
            "buffer_policy_id": "client-buffer",
            "queue_capacity": 5000,
            "eps": 500,
            "crypto": "aes",
            "reconnect_seconds": 60,
        },
        "settings": [
            {
                "setting_id": "node-name",
                "name": "node_name",
                "value": "suricata-sidecar",
                "provenance": "configuration_file",
            }
        ],
    }
    agent.update(overrides)
    return agent


def _content_sync(**overrides) -> dict:
    agent = {
        "forwarding_agent_id": "misp-suricata-sync",
        "implementation": "misp_suricata_sync",
        "agent_kind": "content_sync",
        "version": "1.0",
        "name": "misp-iocs-to-rules",
        "sources": [
            {
                "source_id": "misp-feed",
                "kind": "api_pull",
                "location": "https://misp/attributes/restSearch",
                "parse_format": "misp_json",
                "selector": "aptl:enforce",
            }
        ],
        "transforms": [
            {"transform_id": "ioc-rule", "kind": "ioc_to_rule", "sid_namespace": "99000000"},
        ],
        "ship_targets": [
            {
                "target_id": "rules-file",
                "target_service_ref": "suricata",
                "protocol": "tcp",
            }
        ],
        "reload_channels": [
            {
                "reload_channel_id": "suricata-reload",
                "target_ref": "suricata.control_channels.rule-reload",
                "kind": "unix_socket",
            }
        ],
    }
    agent.update(overrides)
    return agent


# --------------------------------------------------------------------------- #
# Construction / typed-child coercion                                         #
# --------------------------------------------------------------------------- #


def test_log_forwarder_typed_children() -> None:
    agent = RuntimeForwardingAgent(**_log_forwarder())

    assert agent.forwarding_agent_id == "wazuh-sidecar-suricata"
    assert agent.implementation is RuntimeForwardingAgentImplementation.WAZUH_AGENT
    assert agent.agent_kind is RuntimeForwardingAgentKind.LOG_FORWARDER
    assert isinstance(agent.sources[0], RuntimeForwardingSource)
    assert agent.sources[0].kind is RuntimeForwardingSourceKind.TAILED_PATH
    assert agent.sources[0].parse_format is RuntimeForwardingParseFormat.JSON
    assert isinstance(agent.transforms[0], RuntimeForwardingTransform)
    assert agent.transforms[0].kind is RuntimeForwardingTransformKind.PASSTHROUGH
    target = agent.ship_targets[0]
    assert isinstance(target, RuntimeForwardingShipTarget)
    assert target.ingestion_port == 1514
    assert target.enrollment_port == 1515
    assert target.protocol is RuntimeForwardingProtocol.SYSLOG
    assert target.enrollment_identity_classification is RuntimeForwardingEnrollmentClassification.REDACTED
    assert isinstance(agent.buffer_policy, RuntimeForwardingBufferPolicy)
    assert agent.buffer_policy.crypto is RuntimeForwardingBufferCrypto.AES
    assert agent.buffer_policy.queue_capacity == 5000


def test_content_sync_typed_children() -> None:
    agent = RuntimeForwardingAgent(**_content_sync())

    assert agent.agent_kind is RuntimeForwardingAgentKind.CONTENT_SYNC
    assert agent.sources[0].kind is RuntimeForwardingSourceKind.API_PULL
    assert agent.sources[0].selector == "aptl:enforce"
    assert agent.transforms[0].kind is RuntimeForwardingTransformKind.IOC_TO_RULE
    assert agent.transforms[0].sid_namespace == "99000000"
    assert isinstance(agent.reload_channels[0], RuntimeForwardingReloadChannel)
    assert agent.reload_channels[0].kind is RuntimeForwardingReloadChannelKind.UNIX_SOCKET
    assert agent.buffer_policy is None


def test_kebab_case_enum_inputs_normalize() -> None:
    agent = RuntimeForwardingAgent(
        **_log_forwarder(
            implementation="Wazuh-Agent",
            sources=[{"source_id": "s1", "kind": "tailed-path", "parse_format": "eve-json"}],
        )
    )
    assert agent.implementation is RuntimeForwardingAgentImplementation.WAZUH_AGENT
    assert agent.sources[0].kind is RuntimeForwardingSourceKind.TAILED_PATH
    assert agent.sources[0].parse_format is RuntimeForwardingParseFormat.EVE_JSON


def test_open_tail_kinds_impose_no_profile() -> None:
    # unknown / other are permissive — a near-empty instance validates.
    for kind in ("unknown", "other"):
        agent = RuntimeForwardingAgent(forwarding_agent_id=f"agent-{kind}", agent_kind=kind)
        assert agent.agent_kind.value == kind


def test_variable_ref_agent_kind_is_exempt_from_guard() -> None:
    agent = RuntimeForwardingAgent(forwarding_agent_id="agent-var", agent_kind="${agent_kind}")
    assert agent.agent_kind == "${agent_kind}"


def test_invalid_enum_value_rejected() -> None:
    with pytest.raises(ValidationError, match="agent_kind must be one of"):
        RuntimeForwardingAgent(forwarding_agent_id="bad", agent_kind="totally_invalid")


def test_id_fields_reject_variable_placeholders() -> None:
    with pytest.raises(ValidationError, match="forwarding_agent_id must be a qualified SDL identifier"):
        RuntimeForwardingAgent(forwarding_agent_id="${id}")


# --------------------------------------------------------------------------- #
# Duplicate-id and secret-redaction guards                                    #
# --------------------------------------------------------------------------- #


def test_rejects_duplicate_stable_ids_across_children() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime forwarding agent stable id 'dup'"):
        RuntimeForwardingAgent(
            **_log_forwarder(
                sources=[{"source_id": "dup", "kind": "tailed_path"}],
                transforms=[{"transform_id": "dup", "kind": "passthrough"}],
            )
        )


def test_buffer_policy_id_participates_in_uniqueness() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime forwarding agent stable id 'shared'"):
        RuntimeForwardingAgent(
            **_log_forwarder(
                sources=[{"source_id": "shared", "kind": "tailed_path"}],
                buffer_policy={
                    "buffer_policy_id": "shared",
                    "queue_capacity": 1,
                },
                ship_targets=[{"target_id": "t1", "ingestion_port": 1514}],
            )
        )


def test_secret_named_setting_may_carry_scenario_value() -> None:
    setting = RuntimeForwardingSetting(setting_id="enroll", name="enrollment_key", value="hunter2")

    assert setting.value == "hunter2"


def test_secret_named_setting_redacted_is_accepted() -> None:
    setting = RuntimeForwardingSetting(setting_id="enroll", name="authd.pass", classification="redacted")
    assert setting.classification.value == "redacted"


def test_classified_setting_must_omit_value_even_with_plain_name() -> None:
    with pytest.raises(ValidationError, match="must omit its raw value"):
        RuntimeForwardingSetting(setting_id="s", name="something", value="x", classification="operator_secret")


def test_ship_target_port_range_enforced() -> None:
    with pytest.raises(ValidationError, match="ingestion_port must be <= 65535"):
        RuntimeForwardingShipTarget(target_id="t", ingestion_port=70000)


# --------------------------------------------------------------------------- #
# require_profile_for_agent_kind — log_forwarder                              #
# --------------------------------------------------------------------------- #


def test_log_forwarder_positive_profile() -> None:
    # The full fixture already satisfies the profile.
    agent = RuntimeForwardingAgent(**_log_forwarder())

    assert agent.agent_kind is RuntimeForwardingAgentKind.LOG_FORWARDER
    assert agent.buffer_policy is not None
    assert any(target.has_ingestion_endpoint() for target in agent.ship_targets)


def test_log_forwarder_allows_no_buffer_policy() -> None:
    agent = RuntimeForwardingAgent(**_log_forwarder(buffer_policy=None))
    assert agent.buffer_policy is None


def test_log_forwarder_allows_partial_endpoint_knowledge() -> None:
    agent = RuntimeForwardingAgent(
        **_log_forwarder(ship_targets=[{"target_id": "manager", "enrollment_port": 1515, "protocol": "syslog"}])
    )
    assert agent.ship_targets[0].ingestion_port is None
    assert agent.ship_targets[0].enrollment_port == 1515


def test_log_forwarder_can_compose_ioc_transform() -> None:
    agent = RuntimeForwardingAgent(**_log_forwarder(transforms=[{"transform_id": "convert", "kind": "ioc_to_rule"}]))
    assert agent.transforms[0].kind is RuntimeForwardingTransformKind.IOC_TO_RULE


# --------------------------------------------------------------------------- #
# require_profile_for_agent_kind — content_sync                               #
# --------------------------------------------------------------------------- #


def test_content_sync_positive_profile() -> None:
    agent = RuntimeForwardingAgent(**_content_sync())

    assert agent.agent_kind is RuntimeForwardingAgentKind.CONTENT_SYNC
    assert any(source.kind is RuntimeForwardingSourceKind.API_PULL for source in agent.sources)
    assert any(transform.kind is RuntimeForwardingTransformKind.IOC_TO_RULE for transform in agent.transforms)
    assert agent.reload_channels


def test_content_sync_can_use_a_file_source() -> None:
    agent = RuntimeForwardingAgent(**_content_sync(sources=[{"source_id": "s", "kind": "tailed_path"}]))
    assert agent.sources[0].kind is RuntimeForwardingSourceKind.TAILED_PATH


def test_content_sync_can_use_a_non_ioc_transform() -> None:
    agent = RuntimeForwardingAgent(**_content_sync(transforms=[{"transform_id": "t", "kind": "parse"}]))
    assert agent.transforms[0].kind is RuntimeForwardingTransformKind.PARSE


def test_content_sync_can_have_no_reload_channel() -> None:
    agent = RuntimeForwardingAgent(**_content_sync(reload_channels=[]))
    assert agent.reload_channels == []


def test_content_sync_can_buffer_work() -> None:
    agent = RuntimeForwardingAgent(**_content_sync(buffer_policy={"buffer_policy_id": "b", "queue_capacity": 1}))
    assert agent.buffer_policy.queue_capacity == 1


def test_content_sync_can_declare_enrollment_endpoint() -> None:
    agent = RuntimeForwardingAgent(**_content_sync(ship_targets=[{"target_id": "rules", "enrollment_port": 1515}]))
    assert agent.ship_targets[0].enrollment_port == 1515


def test_content_sync_preserves_protected_enrollment_posture() -> None:
    agent = RuntimeForwardingAgent(
        **_content_sync(ship_targets=[{"target_id": "rules", "enrollment_identity_classification": "operator_secret"}])
    )
    assert (
        agent.ship_targets[0].enrollment_identity_classification
        is RuntimeForwardingEnrollmentClassification.OPERATOR_SECRET
    )


def test_content_sync_allows_ship_target_without_enrollment() -> None:
    # A ship_target with no enrollment endpoint and the default 'none' class is fine.
    agent = RuntimeForwardingAgent(
        **_content_sync(
            ship_targets=[{"target_id": "rules", "ingestion_port": 0}],
        )
    )
    assert agent.ship_targets[0].enrollment_identity_classification is RuntimeForwardingEnrollmentClassification.NONE


# --------------------------------------------------------------------------- #
# Scenario-level ship_target ref resolution (validator.py)                     #
# --------------------------------------------------------------------------- #


def _validate(scenario: Scenario) -> list[str]:
    validator = SemanticValidator(scenario)
    try:
        validator.validate()
        return []
    except SDLValidationError as exc:
        return exc.errors


def _manager_node() -> dict:
    return {
        "type": "compute",
        "resources": {"ram": "2 gib", "cpu": 2},
        "services": [{"port": 1514, "protocol": "tcp", "name": "wazuh-agent-events"}],
    }


def _sensor_node(agent: dict) -> dict:
    return {
        "type": "compute",
        "resources": {"ram": "1 gib", "cpu": 1},
        "services": [{"port": 80, "protocol": "tcp", "name": "suricata"}],
        "runtime": {"forwarding_agents": [agent]},
    }


def test_scenario_level_surface_reuses_runtime_forwarding_agent() -> None:
    scenario = Scenario(name="forwarding", forwarding_agents=[_log_forwarder()])

    assert "forwarding_agents" in Scenario.model_fields
    assert isinstance(scenario.forwarding_agents[0], RuntimeForwardingAgent)


def test_log_forwarder_target_node_ref_resolves_to_defined_node() -> None:
    # The _log_forwarder fixture ships to target_node_ref "wazuh-manager".
    scenario = Scenario(
        name="forwarding",
        nodes={"wazuh-manager": _manager_node(), "sensor": _sensor_node(_log_forwarder())},
    )
    assert _validate(scenario) == []


def test_ship_target_node_ref_must_resolve_to_defined_node() -> None:
    agent = _log_forwarder(
        ship_targets=[{"target_id": "manager", "target_node_ref": "ghost-node", "ingestion_port": 1514}],
    )
    scenario = Scenario(name="forwarding", nodes={"sensor": _sensor_node(agent)})
    errors = _validate(scenario)
    assert any("target_node_ref 'ghost-node'" in error for error in errors)


def test_ship_target_service_ref_must_resolve_on_target_node() -> None:
    agent = _log_forwarder(
        ship_targets=[
            {
                "target_id": "manager",
                "target_node_ref": "manager",
                "target_service_ref": "missing-svc",
                "ingestion_port": 1514,
            }
        ],
    )
    scenario = Scenario(
        name="forwarding",
        nodes={"manager": _manager_node(), "sensor": _sensor_node(agent)},
    )
    errors = _validate(scenario)
    assert any("target_service_ref 'missing-svc'" in error and "manager" in error for error in errors)


def test_content_sync_target_service_ref_resolves_on_owning_node() -> None:
    # No target_node_ref -> the service ref must resolve on the forwarder's own node.
    scenario = Scenario(name="forwarding", nodes={"sensor": _sensor_node(_content_sync())})
    assert _validate(scenario) == []


def test_scenario_level_ship_target_service_ref_requires_target_node_ref() -> None:
    agent = _log_forwarder(
        forwarding_agent_id="db-wazuh-agent",
        ship_targets=[
            {
                "target_id": "manager",
                "target_service_ref": "wazuh-agent-events",
                "ingestion_port": 1514,
                "protocol": "syslog",
            }
        ],
    )
    scenario = Scenario(
        name="forwarding",
        nodes={"wazuh-manager": _manager_node()},
        forwarding_agents=[agent],
    )

    errors = _validate(scenario)

    assert any("target_service_ref 'wazuh-agent-events' requires target_node_ref" in error for error in errors)


def test_forwarding_agent_ids_are_unique_across_scenario_and_nodes() -> None:
    scenario = Scenario(
        name="forwarding",
        nodes={"sensor": _sensor_node(_log_forwarder())},
        forwarding_agents=[_log_forwarder()],
    )

    errors = _validate(scenario)

    assert any("Duplicate forwarding_agent_id 'wazuh-sidecar-suricata'" in error for error in errors)


def test_forwarding_edge_resolves_scenario_level_forwarder() -> None:
    agent = _log_forwarder(
        forwarding_agent_id="db-wazuh-agent",
        ship_targets=[
            {
                "target_id": "manager",
                "target_node_ref": "wazuh-manager",
                "target_service_ref": "wazuh-agent-events",
                "ingestion_port": 1514,
                "protocol": "syslog",
                "enrollment_port": 1515,
                "enrollment_identity_classification": "redacted",
            }
        ],
    )
    scenario = Scenario(
        name="forwarding",
        nodes={
            "db": {
                "type": "compute",
                "resources": {"ram": "1 gib", "cpu": 1},
                "services": [{"port": 5432, "protocol": "tcp", "name": "postgres"}],
            },
            "wazuh-manager": _manager_node(),
        },
        forwarding_agents=[agent],
        relationships={
            "db-logs-forwarded-wazuh": {
                "type": "connects_to",
                "source": "db",
                "target": "wazuh-manager",
                "forwarding_edge": {
                    "forwarder_ref": "db-wazuh-agent",
                    "target_listener_role": "agent_event_ingestion",
                    "protocol": "syslog",
                },
            }
        },
    )

    assert _validate(scenario) == []


def test_forwarding_edge_missing_forwarder_reports_combined_resolution_scope() -> None:
    scenario = Scenario(
        name="forwarding",
        nodes={
            "db": {
                "type": "compute",
                "resources": {"ram": "1 gib", "cpu": 1},
                "services": [{"port": 5432, "protocol": "tcp", "name": "postgres"}],
            },
            "wazuh-manager": _manager_node(),
        },
        relationships={
            "db-logs-forwarded-wazuh": {
                "type": "connects_to",
                "source": "db",
                "target": "wazuh-manager",
                "forwarding_edge": {"forwarder_ref": "missing-agent"},
            }
        },
    )

    errors = _validate(scenario)

    assert any(
        "forwarder_ref 'missing-agent' does not resolve to a forwarding agent "
        "on any node or in scenario forwarding_agents" in error
        for error in errors
    )


# --------------------------------------------------------------------------- #
# RelationshipForwardingEdge (SCN-010 §5.7)                                    #
# --------------------------------------------------------------------------- #


def test_forwarding_edge_typed_fields() -> None:
    edge = RelationshipForwardingEdge(
        forwarder_ref="wazuh-sidecar-suricata",
        target_listener_role="agent_event_ingestion",
        protocol="tls",
        crypto_method="aes-256-gcm",
        parse_format="eve_json",
        description="agent ships eve.json to the manager",
    )
    assert edge.forwarder_ref == "wazuh-sidecar-suricata"
    assert edge.target_listener_role is RuntimeSecurityMonitoringListenerRole.AGENT_EVENT_INGESTION
    assert edge.parse_format is RuntimeForwardingParseFormat.EVE_JSON
    assert edge.enrollment_identity_classification is RuntimeForwardingEnrollmentClassification.NONE


def test_forwarding_edge_normalizes_kebab_case_enums() -> None:
    edge = RelationshipForwardingEdge(
        forwarder_ref="agent-1",
        target_listener_role="Agent-Enrollment",
        parse_format="MISP-JSON",
    )
    assert edge.target_listener_role is RuntimeSecurityMonitoringListenerRole.AGENT_ENROLLMENT
    assert edge.parse_format is RuntimeForwardingParseFormat.MISP_JSON


def test_forwarding_edge_reuses_listener_role_enum() -> None:
    # The target_listener_role REUSES the manager-side enum, not a fork.
    edge = RelationshipForwardingEdge(forwarder_ref="agent-1", target_listener_role="syslog_ingestion")
    assert isinstance(edge.target_listener_role, RuntimeSecurityMonitoringListenerRole)
    assert edge.target_listener_role is RuntimeSecurityMonitoringListenerRole.SYSLOG_INGESTION


def test_forwarding_edge_rejects_unknown_listener_role() -> None:
    with pytest.raises(ValidationError, match="target_listener_role must be one of"):
        RelationshipForwardingEdge(forwarder_ref="agent-1", target_listener_role="totally_invalid")


def test_forwarding_edge_rejects_invalid_parse_format() -> None:
    with pytest.raises(ValidationError, match="parse_format must be one of"):
        RelationshipForwardingEdge(forwarder_ref="agent-1", parse_format="totally_invalid")


def test_forwarding_edge_forwarder_ref_required() -> None:
    with pytest.raises(ValidationError, match="forwarder_ref must be a non-empty string"):
        RelationshipForwardingEdge(forwarder_ref="")


def test_forwarding_edge_forwarder_ref_allows_variable_placeholder() -> None:
    edge = RelationshipForwardingEdge(forwarder_ref="${forwarder}")
    assert edge.forwarder_ref == "${forwarder}"


def test_forwarding_edge_present_enrollment_identity_must_be_redacted() -> None:
    with pytest.raises(ValidationError, match="must be 'redacted' or 'operator_secret'"):
        RelationshipForwardingEdge(
            forwarder_ref="agent-1",
            enrollment_identity_ref="agent-key-001",
            enrollment_identity_classification="none",
        )


def test_forwarding_edge_redacted_enrollment_identity_accepted() -> None:
    edge = RelationshipForwardingEdge(
        forwarder_ref="agent-1",
        enrollment_identity_ref="agent-key-001",
        enrollment_identity_classification="redacted",
    )
    assert edge.enrollment_identity_classification is RuntimeForwardingEnrollmentClassification.REDACTED


def test_forwarding_edge_operator_secret_enrollment_identity_accepted() -> None:
    edge = RelationshipForwardingEdge(
        forwarder_ref="agent-1",
        enrollment_identity_ref="agent-key-001",
        enrollment_identity_classification="operator_secret",
    )
    assert edge.enrollment_identity_classification is RuntimeForwardingEnrollmentClassification.OPERATOR_SECRET


def test_forwarding_edge_no_enrollment_identity_defaults_clean() -> None:
    # Absent enrollment_identity_ref imposes no classification requirement.
    edge = RelationshipForwardingEdge(forwarder_ref="agent-1")
    assert edge.enrollment_identity_ref == ""
    assert edge.enrollment_identity_classification is RuntimeForwardingEnrollmentClassification.NONE


def test_forwarding_edge_variable_classification_defers_check() -> None:
    edge = RelationshipForwardingEdge(
        forwarder_ref="agent-1",
        enrollment_identity_ref="agent-key-001",
        enrollment_identity_classification="${class}",
    )
    assert edge.enrollment_identity_classification == "${class}"

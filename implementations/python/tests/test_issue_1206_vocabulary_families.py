"""Every disposed identity uses one governed parser, including nested families."""

import importlib

import pytest
from raes.runtime_values import parse_runtime_enum_or_var
from raes_contracts.controlled_vocabularies import (
    controlled_vocabulary_id_for_scope,
    load_controlled_vocabulary_catalog,
)

_IDENTITIES = (
    ("raes.runtime_app_authorization", "RuntimeAppAuthorizationResourceVocabulary"),
    ("raes.runtime_app_authorization", "RuntimeAppAuthorizationPrincipalKind"),
    ("raes.runtime_application", "RuntimeApplicationProtocol"),
    ("raes.runtime_application", "RuntimeApplicationParameterLocation"),
    ("raes.runtime_capabilities", "RuntimeProcessRole"),
    ("raes.runtime_database_vocab", "DatabaseEngine"),
    ("raes.runtime_database_vocab", "DatabaseProtocol"),
    ("raes.runtime_database_vocab", "DatabaseObjectOrigin"),
    ("raes.runtime_database_vocab", "DatabaseRoleType"),
    ("raes.runtime_database_vocab", "DatabaseSettingProvenance"),
    ("raes.runtime_database_vocab", "DatabaseAuthMethod"),
    ("raes.runtime_datastore_vocab", "RuntimeDatastoreEngine"),
    ("raes.runtime_datastore_vocab", "RuntimeDatastorePartitionKind"),
    ("raes.runtime_datastore_vocab", "RuntimeDatastoreNodeRole"),
    ("raes.runtime_datastore_vocab", "RuntimeDatastoreNodeEndpointRole"),
    ("raes.runtime_datastore_vocab", "RuntimeDatastoreEvictionPolicy"),
    ("raes.runtime_datastore_vocab", "RuntimeDatastoreReplicationStrategy"),
    ("raes.runtime_datastore_vocab", "RuntimeDatastoreSettingProvenance"),
    ("raes.runtime_directory_identity", "RuntimeIdentityAuthorityKind"),
    ("raes.runtime_directory_identity", "RuntimeIdentityAuthorityProtocol"),
    ("raes.runtime_directory_identity", "RuntimeIdentitySubjectKind"),
    ("raes.runtime_directory_identity", "RuntimeIdentityPolicyKind"),
    ("raes.runtime_directory_identity", "RuntimeIdentityRecordOrigin"),
    ("raes.runtime_dns_vocab", "DnsServerImplementation"),
    ("raes.runtime_dns_vocab", "DnsServiceRole"),
    ("raes.runtime_dns_vocab", "DnsZoneKind"),
    ("raes.runtime_dns_vocab", "DnsZonePurpose"),
    ("raes.runtime_dns_vocab", "DnsRecordProvenance"),
    ("raes.runtime_dns_vocab", "DnsForwarderTransport"),
    ("raes.runtime_dns_vocab", "DnsSettingProvenance"),
    ("raes.runtime_environment", "RuntimeEnvironmentVariableProvenance"),
    ("raes.runtime_file_service", "RuntimeFileServiceProtocol"),
    ("raes.runtime_file_service", "RuntimeFileShareKind"),
    ("raes.runtime_file_service", "RuntimeFileServicePrincipalKind"),
    ("raes.runtime_file_service", "RuntimeFileServicePrincipalOrigin"),
    ("raes.runtime_file_service", "RuntimeFileServiceAccessBasis"),
    ("raes.runtime_filesystem", "RuntimeFilesystemStability"),
    ("raes.runtime_forwarding_agent_vocab", "RuntimeForwardingAgentImplementation"),
    ("raes.runtime_forwarding_agent_vocab", "RuntimeForwardingSourceKind"),
    ("raes.runtime_forwarding_agent_vocab", "RuntimeForwardingParseFormat"),
    ("raes.runtime_forwarding_agent_vocab", "RuntimeForwardingProtocol"),
    ("raes.runtime_forwarding_agent_vocab", "RuntimeForwardingReloadChannelKind"),
    ("raes.runtime_forwarding_agent_vocab", "RuntimeForwardingSettingProvenance"),
    ("raes.runtime_identity", "RuntimeIdentityProvenance"),
    ("raes.runtime_listeners", "RuntimeListenerProtocol"),
    ("raes.runtime_listeners", "RuntimeListenerProvenance"),
    ("raes.runtime_mail_vocab", "RuntimeMailProtocol"),
    ("raes.runtime_mail_vocab", "RuntimeMailListenerRole"),
    ("raes.runtime_mail_vocab", "RuntimeMailAuthMechanism"),
    ("raes.runtime_mail_vocab", "RuntimeMailComponentKind"),
    ("raes.runtime_mail_vocab", "RuntimeMailDomainRole"),
    ("raes.runtime_mail_vocab", "RuntimeMailMailboxStoreKind"),
    ("raes.runtime_mail_vocab", "RuntimeMailMailboxRole"),
    ("raes.runtime_mail_vocab", "RuntimeMailQueueKind"),
    ("raes.runtime_mail_vocab", "RuntimeMailSettingProvenance"),
    ("raes.runtime_mounts", "RuntimeMountSourceKind"),
    ("raes.runtime_mounts", "RuntimeControlInterfaceKind"),
    ("raes.runtime_network", "RuntimeNetworkDriver"),
    ("raes.runtime_network_detection", "RuntimeNetworkDetectionEngineImplementation"),
    ("raes.runtime_network_detection", "RuntimeNetworkDetectionEngineKind"),
    ("raes.runtime_network_detection", "RuntimeNetworkDetectionAppProtocol"),
    ("raes.runtime_network_detection", "RuntimeNetworkDetectionRuleSourceKind"),
    ("raes.runtime_network_detection", "RuntimeNetworkDetectionRuleFormat"),
    ("raes.runtime_network_detection", "RuntimeNetworkDetectionNetworkSetKind"),
    ("raes.runtime_network_detection", "RuntimeNetworkDetectionOutputFormat"),
    ("raes.runtime_network_detection", "RuntimeNetworkDetectionEventType"),
    ("raes.runtime_network_detection", "RuntimeNetworkDetectionControlChannelKind"),
    ("raes.runtime_network_sensor", "RuntimeNetworkSensorImplementation"),
    ("raes.runtime_network_sensor", "RuntimeNetworkSensorKind"),
    ("raes.runtime_network_sensor", "RuntimeNetworkSensorCaptureMode"),
    ("raes.runtime_orchestration", "RuntimeOrchestrationEngine"),
    ("raes.runtime_platform_application_vocab", "RuntimePlatformApplicationKind"),
    ("raes.runtime_platform_application_vocab", "RuntimePlatformApplicationContentObjectKind"),
    ("raes.runtime_platform_application_vocab", "RuntimePlatformApplicationUpstreamBindingRole"),
    ("raes.runtime_platform_application_vocab", "RuntimePlatformApplicationSettingProvenance"),
    ("raes.runtime_security_monitoring._enums", "RuntimeSecurityMonitoringImplementation"),
    ("raes.runtime_security_monitoring._enums", "RuntimeSecurityMonitoringManagerKind"),
    ("raes.runtime_security_monitoring._enums", "RuntimeSecurityMonitoringListenerRole"),
    ("raes.runtime_security_monitoring._enums", "RuntimeSecurityMonitoringComponentKind"),
    ("raes.runtime_security_monitoring._enums", "RuntimeSecurityMonitoringContentKind"),
    ("raes.runtime_security_monitoring._enums", "RuntimeSecurityMonitoringContentFormat"),
    ("raes.runtime_security_monitoring._enums", "RuntimeSecurityMonitoringSettingProvenance"),
    ("raes.runtime_security_monitoring_definitions", "RuntimeSecurityMonitoringDetectionEngine"),
    ("raes.runtime_security_monitoring_definitions", "RuntimeSecurityMonitoringDetectionDefinitionKind"),
    ("raes.runtime_service_units", "ServiceManagerKind"),
    ("raes.runtime_software", "RuntimeSoftwareComponentType"),
    ("raes.runtime_software", "RuntimeSoftwareComponentProvenance"),
)


@pytest.mark.parametrize("module,name", _IDENTITIES)
def test_disposed_identity_accepts_distinct_private_tokens_exactly(module, name):
    enum_type = getattr(importlib.import_module(module), name)
    vocabulary_id = controlled_vocabulary_id_for_scope(f"sdl.definitions.{name}")
    vocabulary = load_controlled_vocabulary_catalog().vocabularies[vocabulary_id]
    assert set(vocabulary.terms) == {member.value for member in enum_type}
    for token in ("x-owner:private-a", "x-owner:private-b", "x-peer:private-a"):
        assert parse_runtime_enum_or_var(token, enum_type, field_name="identity") == token
    assert parse_runtime_enum_or_var("${selected}", enum_type, field_name="identity") == "${selected}"
    with pytest.raises(ValueError):
        parse_runtime_enum_or_var("unqualified-private-value", enum_type, field_name="identity")

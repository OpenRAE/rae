# Field classifications for the product-semantics audit

This is the field ledger for the [issue 959 audit](product-semantics-audit.md),
linked from the existing [scope inventory](scope-inventory.md). Reviewed baseline:
`2ed2d97cee641419912dfd2e4e2e4b0c9c61f35e`, 2026-09-16.

The scope is every model reachable from the 17 registered runtime families,
plus service-manager units: 115 model types and 899 fields, including inherited
fields. The runtime registry remains authoritative. This ledger neither
registers families nor changes model validation. Adjacent surfaces outside this
field graph have separate dispositions in the audit.

Each field has one primary semantic owner:

- P — portable domain concept, including local identity and descriptive labels.
- C — optional authored/configured state.
- K — capability or requirement.
- B — integration/binding, including typed references and endpoints.
- A — policy/authorization/marking, including protection decisions.
- N — product-native identity or extension, including bounded native format data.
- R — realization choice, such as a selected workload image or backing path.
- O — observation/evidence, including provenance and reported state.
- D — delivery machinery. No selected field has this owner; backend operations
  remain outside these inventory models.

These categories describe meaning, not whether the field is syntactically
required or proof that a value was observed. A declared expected observation
remains an authored constraint; actual observation needs its own provenance.
A C field is optional at its containing inventory boundary, but a present typed
record can still have structural requirements. B reference integrity and A
security constraints remain binding when supplied. Container fields name the
primary owner; their children's rows classify independent axes in that record.

Fields inherit the audit's bounded disposition for their family. Explicit
exceptions are `RuntimeApplicationRoute.methods`,
`RuntimeServiceListener` endpoint completeness and
`ServiceManagerUnit` manager/name/state coupling. Their confirmed defects are
recorded in #1298, #1299 and #1297 respectively. Retained native profiles and
documentation debt are explained in the audit rather than relabeled portable.
The #1206 [vocabulary dispositions](scope-inventory.md#issue-1206-implementation-dispositions-2026-09-12)
supply the term-level extension/finite-set decisions for enum-typed fields.
Free native strings are not vocabulary tokens or executable profile identities.

The coverage test compares this table with the live registry, recursively
reachable Pydantic fields and their owning source files. New, removed, duplicate
or unclassified fields require review. That test checks completeness of this
ledger, not correctness of these judgments, runtime validity, backend support,
or full lifecycle conformance. The audit's source/probe and review evidence
supply those separate arguments.

## Model fields

| Model | Owning source | Field classifications |
| --- | --- | --- |
| `Database` | [runtime_database.py](../../../implementations/python/packages/raes/runtime_database.py) | P: `database_id`, `name`, `description`; C: `schemas`; O: `origin` |
| `DatabaseGrant` | [runtime_database.py](../../../implementations/python/packages/raes/runtime_database.py) | P: `description`; B: `grantee_role_ref`, `object_ref`; A: `object_type`, `privileges`, `with_grant_option` |
| `DatabaseListener` | [runtime_database.py](../../../implementations/python/packages/raes/runtime_database.py) | P: `description`; B: `address`, `port` |
| `DatabaseRole` | [runtime_database.py](../../../implementations/python/packages/raes/runtime_database.py) | P: `role_id`, `name`, `description`; A: `role_type`, `can_login`; O: `origin` |
| `DatabaseSchema` | [runtime_database.py](../../../implementations/python/packages/raes/runtime_database.py) | P: `schema_id`, `name`, `description`; C: `tables`; O: `origin` |
| `DatabaseSetting` | [runtime_database.py](../../../implementations/python/packages/raes/runtime_database.py) | P: `name`, `description`; C: `value`; A: `value_classification`; O: `provenance` |
| `DatabaseTable` | [runtime_database.py](../../../implementations/python/packages/raes/runtime_database.py) | P: `table_id`, `name`, `description` |
| `DnsDynamicUpdatePolicy` | [runtime_dns.py](../../../implementations/python/packages/raes/runtime_dns.py) | P: `description`; A: `enabled`, `allowed_clients`, `key_names`, `policy` |
| `DnsForwarder` | [runtime_dns.py](../../../implementations/python/packages/raes/runtime_dns.py) | P: `description`; C: `transport`, `tls_server_name`; B: `address`, `port` |
| `DnsMxRdata` | [runtime_dns_records.py](../../../implementations/python/packages/raes/runtime_dns_records.py) | P: `preference`, `exchange` |
| `DnsResolverPolicy` | [runtime_dns.py](../../../implementations/python/packages/raes/runtime_dns.py) | P: `description`; A: `recursion_enabled`, `allow_recursion`, `forwarders`, `forwarding_policy`, `dnssec_validation`, `query_logging`, `default_logging` |
| `DnsResourceRecord` | [runtime_dns_records.py](../../../implementations/python/packages/raes/runtime_dns_records.py) | P: `rdata`, `target`, `text`, `soa`, `mx`, `srv`, `description`; B: `address` |
| `DnsResourceRecordSet` | [runtime_dns_records.py](../../../implementations/python/packages/raes/runtime_dns_records.py) | P: `rrset_id`, `record_type`, `zone_class`, `ttl`, `type_code`, `records`, `description`; N: `owner`; O: `provenance` |
| `DnsRuntimeSetting` | [runtime_dns.py](../../../implementations/python/packages/raes/runtime_dns.py) | P: `name`, `description`; C: `value`; A: `value_classification`; O: `provenance` |
| `DnsSoaRdata` | [runtime_dns_records.py](../../../implementations/python/packages/raes/runtime_dns_records.py) | P: `mname`, `rname`, `serial`, `refresh`, `retry`, `expire`, `minimum` |
| `DnsSrvRdata` | [runtime_dns_records.py](../../../implementations/python/packages/raes/runtime_dns_records.py) | P: `priority`, `weight`, `target`; B: `port` |
| `DnsZone` | [runtime_dns.py](../../../implementations/python/packages/raes/runtime_dns.py) | P: `zone_id`, `name`, `kind`, `purpose`, `zone_class`, `description`; C: `rrsets`; B: `zone_file_refs`; A: `transfer`; O: `provenance` |
| `DnsZoneTransferPolicy` | [runtime_dns.py](../../../implementations/python/packages/raes/runtime_dns.py) | P: `description`; A: `axfr_enabled`, `ixfr_enabled`, `allowed_clients`, `primary_servers`, `secondary_servers` |
| `RuntimeAppAuthorization` | [runtime_app_authorization.py](../../../implementations/python/packages/raes/runtime_app_authorization.py) | P: `app_authorization_id`, `name`, `description`; A: `auth_enabled`, `principals`, `roles`, `permission_grants`, `role_mappings`, `tenants`; N: `resource_vocabulary` |
| `RuntimeAppAuthorizationGrant` | [runtime_app_authorization.py](../../../implementations/python/packages/raes/runtime_app_authorization.py) | P: `grant_id`, `description`; B: `role_ref`; A: `actions`, `resource_patterns`, `effect`; N: `resource_kind` |
| `RuntimeAppAuthorizationPrincipal` | [runtime_app_authorization.py](../../../implementations/python/packages/raes/runtime_app_authorization.py) | P: `principal_id`, `kind`, `name`, `description`; A: `reserved`, `hidden`, `credential_classification`, `backend_roles` |
| `RuntimeAppAuthorizationRole` | [runtime_app_authorization.py](../../../implementations/python/packages/raes/runtime_app_authorization.py) | P: `role_id`, `name`, `description` |
| `RuntimeAppAuthorizationRoleMapping` | [runtime_app_authorization.py](../../../implementations/python/packages/raes/runtime_app_authorization.py) | P: `mapping_id`, `description`; B: `role_ref`; A: `backend_roles`, `users`, `hosts` |
| `RuntimeAppAuthorizationTenant` | [runtime_app_authorization.py](../../../implementations/python/packages/raes/runtime_app_authorization.py) | P: `tenant_id`, `name`, `description` |
| `RuntimeApplicationDisclosure` | [runtime_application.py](../../../implementations/python/packages/raes/runtime_application.py) | P: `description`; A: `sensitivity`; O: `trigger`, `status_code`, `disclosure` |
| `RuntimeApplicationExposedField` | [runtime_application_values.py](../../../implementations/python/packages/raes/runtime_application_values.py) | P: `name`, `description`; C: `value`; A: `sensitivity` |
| `RuntimeApplicationParameter` | [runtime_application.py](../../../implementations/python/packages/raes/runtime_application.py) | P: `name`, `location`, `data_type`, `description`; K: `required` |
| `RuntimeApplicationRedirect` | [runtime_application.py](../../../implementations/python/packages/raes/runtime_application.py) | P: `description`; C: `target`, `status_code`, `condition` |
| `RuntimeApplicationResponse` | [runtime_application.py](../../../implementations/python/packages/raes/runtime_application.py) | P: `description`; C: `status_code`, `content_type` |
| `RuntimeApplicationRoute` | [runtime_application.py](../../../implementations/python/packages/raes/runtime_application.py) | P: `route_id`, `path`, `methods`, `name`, `description`; C: `parameters`, `responses`, `templates`, `static_assets`, `redirects`, `disclosures`, `exposed_fields`; B: `upstream_target`; A: `auth_required`, `auth_scheme`, `session_required` |
| `RuntimeApplicationRouteUpstreamTarget` | [runtime_application.py](../../../implementations/python/packages/raes/runtime_application.py) | B: `target_node_ref`, `target_service`, `scheme`; A: `tls_terminated_here` |
| `RuntimeApplicationSurface` | [runtime_application.py](../../../implementations/python/packages/raes/runtime_application.py) | P: `application_id`, `name`, `description`; C: `base_path`, `routes`; B: `service`, `protocol`; N: `framework` |
| `RuntimeDatabaseService` | [runtime_database.py](../../../implementations/python/packages/raes/runtime_database.py) | P: `database_service_id`, `name`, `description`; C: `listeners`, `databases`, `settings`; B: `service`, `protocol`; A: `roles`, `grants`; N: `engine`, `version` |
| `RuntimeDatastoreCluster` | [runtime_datastore_partitions.py](../../../implementations/python/packages/raes/runtime_datastore_partitions.py) | P: `cluster_id`, `name`, `description`; N: `uuid`, `discovery_mode`, `partitioner`, `native_protocol_version`; O: `health`, `node_count`, `shard_total`, `shard_primaries`, `doc_count`, `store_size_bytes` |
| `RuntimeDatastoreEnginePlugin` | [runtime_datastore_nodes.py](../../../implementations/python/packages/raes/runtime_datastore_nodes.py) | P: `plugin_id`, `name`, `description`; N: `version` |
| `RuntimeDatastoreMapping` | [runtime_datastore_partitions.py](../../../implementations/python/packages/raes/runtime_datastore_partitions.py) | P: `mapping_id`, `name`, `description`; C: `dynamic_policy`, `date_detection`; B: `partition_ref`; N: `field_type_census`; O: `top_level_field_count`, `leaf_field_count`, `dynamic_template_count`, `schema_digest`, `evidence_refs` |
| `RuntimeDatastoreNode` | [runtime_datastore_nodes.py](../../../implementations/python/packages/raes/runtime_datastore_nodes.py) | P: `node_id`, `name`, `description`; C: `roles`, `is_coordinator`, `heap_init_bytes`, `heap_max_bytes`, `memory_locked`, `plugins`; B: `endpoints`; N: `engine_version`, `build_hash`, `build_type` |
| `RuntimeDatastoreNodeEndpoint` | [runtime_datastore_nodes.py](../../../implementations/python/packages/raes/runtime_datastore_nodes.py) | P: `endpoint_id`, `description`; C: `role`; B: `protocol`, `address`, `port` |
| `RuntimeDatastorePartition` | [runtime_datastore_partitions.py](../../../implementations/python/packages/raes/runtime_datastore_partitions.py) | P: `partition_id`, `kind`, `name`, `description`; C: `shard_count`, `replica_count`, `replication_factor`, `durable_writes`; N: `uuid`, `replication_strategy`, `per_dc_factor_map`, `datatype_census`; O: `doc_count`, `doc_count_deleted`, `store_size_bytes`, `creation_timestamp`, `open_closed_status`, `health` |
| `RuntimeDatastorePersistence` | [runtime_datastore_partitions.py](../../../implementations/python/packages/raes/runtime_datastore_partitions.py) | P: `persistence_id`, `description`; N: `rdb_save_points`, `aof`, `eviction`, `maxmemory` |
| `RuntimeDatastoreService` | [runtime_datastore.py](../../../implementations/python/packages/raes/runtime_datastore.py) | P: `datastore_service_id`, `data_model`, `name`, `description`; C: `cluster`, `nodes`, `partitions`, `templates`, `aliases`, `mappings`, `lifecycle_policies`, `ingest_pipelines`, `persistence`, `pubsub_channels`, `queues_streams`, `settings`; B: `service`, `protocol`, `authorization_ref`; A: `transport_security`; N: `engine`, `version`; R: `backup_targets` |
| `RuntimeDatastoreSetting` | [runtime_datastore_partitions.py](../../../implementations/python/packages/raes/runtime_datastore_partitions.py) | P: `setting_id`, `name`, `description`; C: `value`; A: `classification`; N: `scope`; O: `provenance` |
| `RuntimeDatastoreTemplate` | [runtime_datastore_partitions.py](../../../implementations/python/packages/raes/runtime_datastore_partitions.py) | P: `template_id`, `name`, `description`; B: `mapping_ref`; N: `index_patterns`, `settings_summary`; O: `template_digest`, `evidence_refs` |
| `RuntimeDatastoreTransportSecurity` | [runtime_datastore_partitions.py](../../../implementations/python/packages/raes/runtime_datastore_partitions.py) | P: `transport_security_id`, `description`; A: `mode`, `client_verification`, `node_verification` |
| `RuntimeDnsService` | [runtime_dns.py](../../../implementations/python/packages/raes/runtime_dns.py) | P: `dns_service_id`, `name`, `roles`, `description`; C: `zones`, `settings`; B: `service`, `configuration_file_refs`; A: `resolver_policy`, `dynamic_update`; N: `implementation`, `version`; O: `log_file_refs` |
| `RuntimeFileService` | [runtime_file_service.py](../../../implementations/python/packages/raes/runtime_file_service.py) | P: `file_service_id`, `description`; C: `shares`; B: `service`, `protocol`; A: `principals`, `access_rules`; N: `backend`; O: `access_observations` |
| `RuntimeFileServiceAccessObservation` | [runtime_file_service.py](../../../implementations/python/packages/raes/runtime_file_service.py) | P: `observation_id`, `description`; B: `subject_ref`, `resource_ref`; A: `sensitivity`; O: `action`, `outcome`, `basis` |
| `RuntimeFileServiceAccessRule` | [runtime_file_service.py](../../../implementations/python/packages/raes/runtime_file_service.py) | P: `rule_id`, `description`; B: `subject_ref`, `resource_ref`; A: `action`, `effect`, `basis` |
| `RuntimeFileServicePrincipal` | [runtime_file_service.py](../../../implementations/python/packages/raes/runtime_file_service.py) | P: `principal_id`, `kind`, `name`, `description`; B: `local_user_ref`, `directory_subject_ref`; A: `credential_classification`; N: `external_id`; O: `status`, `origin` |
| `RuntimeFileServiceShare` | [runtime_file_service.py](../../../implementations/python/packages/raes/runtime_file_service.py) | P: `share_id`, `name`, `kind`, `description`; C: `comment`; A: `read_only`, `browseable`, `guest_ok`, `valid_users`, `valid_groups`, `invalid_users`, `write_users`; R: `backing_path` |
| `RuntimeForwardingAgent` | [runtime_forwarding_agent.py](../../../implementations/python/packages/raes/runtime_forwarding_agent.py) | P: `forwarding_agent_id`, `agent_kind`, `ownership_role`, `name`, `description`; C: `sources`, `transforms`, `buffer_policy`, `settings`; B: `ship_targets`, `reload_channels`; N: `implementation`, `version` |
| `RuntimeForwardingBufferPolicy` | [runtime_forwarding_buffer.py](../../../implementations/python/packages/raes/runtime_forwarding_buffer.py) | P: `buffer_policy_id`, `description`; C: `queue_capacity`, `eps`, `reconnect_seconds`; A: `crypto` |
| `RuntimeForwardingReloadChannel` | [runtime_forwarding_agent.py](../../../implementations/python/packages/raes/runtime_forwarding_agent.py) | P: `reload_channel_id`, `kind`, `description`; B: `target_ref` |
| `RuntimeForwardingSetting` | [runtime_forwarding_agent.py](../../../implementations/python/packages/raes/runtime_forwarding_agent.py) | P: `setting_id`, `name`, `description`; C: `value`; A: `classification`; O: `provenance` |
| `RuntimeForwardingShipTarget` | [runtime_forwarding_agent.py](../../../implementations/python/packages/raes/runtime_forwarding_agent.py) | P: `target_id`, `description`; C: `ingestion_port`, `enrollment_port`; B: `target_node_ref`, `target_service_ref`, `protocol`; A: `enrollment_identity_classification` |
| `RuntimeForwardingSource` | [runtime_forwarding_agent.py](../../../implementations/python/packages/raes/runtime_forwarding_agent.py) | P: `source_id`, `kind`, `description`; C: `selector`; B: `location`; N: `parse_format` |
| `RuntimeForwardingTransform` | [runtime_forwarding_agent.py](../../../implementations/python/packages/raes/runtime_forwarding_agent.py) | P: `transform_id`, `kind`, `description`; N: `sid_namespace` |
| `RuntimeIdentityAttribute` | [runtime_directory_identity.py](../../../implementations/python/packages/raes/runtime_directory_identity.py) | P: `description`; A: `value_classification`; N: `name`, `values`; O: `origin`, `provenance` |
| `RuntimeIdentityAuthority` | [runtime_directory_identity.py](../../../implementations/python/packages/raes/runtime_directory_identity.py) | P: `identity_authority_id`, `kind`, `name`, `description`; C: `subjects`; B: `services`, `relationships`; A: `policies`; N: `namespace`, `domain_name`, `realm`, `issuer`, `tenant_id`, `base_dn` |
| `RuntimeIdentityAuthorityService` | [runtime_directory_identity.py](../../../implementations/python/packages/raes/runtime_directory_identity.py) | P: `service_id`, `description`; B: `service`, `protocol`, `address`, `port` |
| `RuntimeIdentityPolicy` | [runtime_directory_identity.py](../../../implementations/python/packages/raes/runtime_directory_identity.py) | P: `policy_id`, `name`, `description`; B: `applies_to_refs`; A: `policy_kind`, `settings` |
| `RuntimeIdentityRelationship` | [runtime_directory_identity.py](../../../implementations/python/packages/raes/runtime_directory_identity.py) | P: `relationship_id`, `relationship_type`, `description`; B: `source_ref`, `target_ref`, `external_target` |
| `RuntimeIdentitySubject` | [runtime_directory_identity.py](../../../implementations/python/packages/raes/runtime_directory_identity.py) | P: `subject_id`, `kind`, `name`, `description`; C: `display_name`, `attributes`; A: `enabled`; N: `principal_name`, `distinguished_name`, `domain`, `service_principal_names`; O: `origin` |
| `RuntimeListenerReadiness` | [runtime_listeners.py](../../../implementations/python/packages/raes/runtime_listeners.py) | P: `description`; O: `probe`, `criteria`, `evidence_refs` |
| `RuntimeMailAlias` | [runtime_mail_service/_elements.py](../../../implementations/python/packages/raes/runtime_mail_service/_elements.py) | P: `alias_id`, `description`; C: `external_targets`; B: `address`, `domain_ref`, `target_refs` |
| `RuntimeMailComponent` | [runtime_mail_service/_elements.py](../../../implementations/python/packages/raes/runtime_mail_service/_elements.py) | P: `component_id`, `kind`, `name`, `description`; N: `version` |
| `RuntimeMailDomain` | [runtime_mail_service/_elements.py](../../../implementations/python/packages/raes/runtime_mail_service/_elements.py) | P: `domain_id`, `name`, `description`; C: `role` |
| `RuntimeMailListener` | [runtime_mail_service/_elements.py](../../../implementations/python/packages/raes/runtime_mail_service/_elements.py) | P: `listener_id`, `description`; C: `role`; K: `capabilities`; B: `service`, `protocol`, `component_ref`; A: `auth_mechanisms`, `tls_mode`, `tls_versions`; N: `banner`, `advertised_identity` |
| `RuntimeMailMailbox` | [runtime_mail_service/_elements.py](../../../implementations/python/packages/raes/runtime_mail_service/_elements.py) | P: `mailbox_id`, `description`; C: `role`; B: `address`, `domain_ref`, `store_ref`, `account_ref`, `local_user_ref`; A: `auth_mechanisms`, `credential_classification`; N: `local_part`; O: `status` |
| `RuntimeMailMailboxStore` | [runtime_mail_service/_elements.py](../../../implementations/python/packages/raes/runtime_mail_service/_elements.py) | P: `store_id`, `kind`, `description`; C: `path` |
| `RuntimeMailQueue` | [runtime_mail_service/_elements.py](../../../implementations/python/packages/raes/runtime_mail_service/_elements.py) | P: `queue_id`, `kind`, `name`, `description`; O: `message_count`, `stability` |
| `RuntimeMailRoutingRule` | [runtime_mail_service/_elements.py](../../../implementations/python/packages/raes/runtime_mail_service/_elements.py) | P: `rule_id`, `kind`, `description`; B: `source_ref`, `target_ref`, `relay_host` |
| `RuntimeMailService` | [runtime_mail_service/_service.py](../../../implementations/python/packages/raes/runtime_mail_service/_service.py) | P: `mail_service_id`, `name`, `description`; C: `components`, `listeners`, `domains`, `mailbox_stores`, `mailboxes`, `aliases`, `queues`, `settings`; B: `service`; A: `routing_rules`; N: `engine`, `version` |
| `RuntimeMailSetting` | [runtime_mail_service/_elements.py](../../../implementations/python/packages/raes/runtime_mail_service/_elements.py) | P: `setting_id`, `name`, `description`; C: `value`; B: `component_ref`; A: `value_classification`; O: `provenance`, `source_path` |
| `RuntimeNetworkDetectionControlChannel` | [runtime_network_detection.py](../../../implementations/python/packages/raes/runtime_network_detection.py) | P: `channel_id`, `kind`, `description`; C: `path`; K: `capabilities`; B: `service`; A: `auth_required` |
| `RuntimeNetworkDetectionEngine` | [runtime_network_detection.py](../../../implementations/python/packages/raes/runtime_network_detection.py) | P: `network_detection_engine_id`, `engine_kind`, `name`, `description`; C: `rule_sources`, `network_sets`, `output_streams`; K: `app_layer_protocols`; B: `process_ref`, `sensor_ref`, `configuration_file_refs`, `control_channels`; N: `implementation`, `version`, `revision`; O: `log_file_refs`, `evidence_refs` |
| `RuntimeNetworkDetectionNetworkSet` | [runtime_network_detection.py](../../../implementations/python/packages/raes/runtime_network_detection.py) | P: `set_id`, `kind`, `name`, `description`; C: `selector_values`; B: `network_refs` |
| `RuntimeNetworkDetectionOutputStream` | [runtime_network_detection.py](../../../implementations/python/packages/raes/runtime_network_detection.py) | P: `stream_id`, `description`; C: `path`, `enabled`; N: `format`, `event_types` |
| `RuntimeNetworkDetectionRuleSource` | [runtime_network_detection.py](../../../implementations/python/packages/raes/runtime_network_detection.py) | P: `source_id`, `kind`, `name`, `description`; B: `file_refs`, `generated_by`; N: `format`; O: `rule_count`, `loaded` |
| `RuntimeNetworkSensor` | [runtime_network_sensor.py](../../../implementations/python/packages/raes/runtime_network_sensor.py) | P: `network_sensor_id`, `sensor_kind`, `name`, `description`; C: `monitoring_posture`, `capture_mode`, `capture_interfaces`; B: `monitored_network_refs`, `process_ref`, `configuration_file_refs`; N: `implementation`, `version`, `revision`; O: `log_file_refs`, `evidence_refs` |
| `RuntimeOrchestrationAuthority` | [runtime_orchestration.py](../../../implementations/python/packages/raes/runtime_orchestration.py) | P: `orchestration_authority_id`, `name`, `description`; B: `control_interface_ref`; A: `scope`, `lifecycle_policy`, `privilege_class`; N: `engine`, `engine_api_version`; R: `spawn_templates`; O: `realized_children` |
| `RuntimeOrchestrationLifecyclePolicy` | [runtime_orchestration.py](../../../implementations/python/packages/raes/runtime_orchestration.py) | P: `description`; A: `timeout`, `cleanup`, `execution_timeout` |
| `RuntimeOrchestrationRealizedChild` | [runtime_orchestration.py](../../../implementations/python/packages/raes/runtime_orchestration.py) | P: `workload_id`, `description`; O: `image_ref`, `count`, `evidence_ref` |
| `RuntimeOrchestrationScope` | [runtime_orchestration.py](../../../implementations/python/packages/raes/runtime_orchestration.py) | P: `description`; B: `organization_ref`; N: `environment_name` |
| `RuntimeOrchestrationSpawnTemplate` | [runtime_orchestration.py](../../../implementations/python/packages/raes/runtime_orchestration.py) | P: `template_id`, `description`; R: `image_ref`, `purpose` |
| `RuntimePlatformApplication` | [runtime_platform_application.py](../../../implementations/python/packages/raes/runtime_platform_application.py) | P: `platform_application_id`, `name`, `description`; C: `organizations`, `tenants`, `content_objects`, `settings`; K: `capabilities`; B: `service`, `upstream_bindings`, `connectors`, `authorization_ref`; A: `markings`, `execution_policy`; N: `platform_kind`, `product`, `version` |
| `RuntimePlatformApplicationCapability` | [runtime_platform_application_content.py](../../../implementations/python/packages/raes/runtime_platform_application_content.py) | P: `capability_id`, `description`; K: `kind`; O: `evidence_refs` |
| `RuntimePlatformApplicationConnector` | [runtime_platform_application_content.py](../../../implementations/python/packages/raes/runtime_platform_application_content.py) | P: `connector_id`, `name`, `description`; C: `enabled`; B: `kind`; A: `credential_classification` |
| `RuntimePlatformApplicationContentObject` | [runtime_platform_application_content.py](../../../implementations/python/packages/raes/runtime_platform_application_content.py) | P: `content_object_id`, `name`, `description`; B: `references`; A: `marking_refs`; N: `kind`, `attributes`; O: `evidence_refs` |
| `RuntimePlatformApplicationExecutionPolicy` | [runtime_platform_application_content.py](../../../implementations/python/packages/raes/runtime_platform_application_content.py) | P: `policy_id`, `description`; A: `max_concurrent_jobs`, `job_timeout`, `rate_limit`; N: `runner` |
| `RuntimePlatformApplicationMarking` | [runtime_platform_application_content.py](../../../implementations/python/packages/raes/runtime_platform_application_content.py) | P: `marking_id`, `description`; A: `level`, `value`; N: `scheme` |
| `RuntimePlatformApplicationOrganization` | [runtime_platform_application_content.py](../../../implementations/python/packages/raes/runtime_platform_application_content.py) | P: `organization_id`, `name`, `description` |
| `RuntimePlatformApplicationSetting` | [runtime_platform_application_content.py](../../../implementations/python/packages/raes/runtime_platform_application_content.py) | P: `setting_id`, `name`, `description`; C: `value`; A: `classification`, `redaction`; O: `provenance` |
| `RuntimePlatformApplicationTenant` | [runtime_platform_application_content.py](../../../implementations/python/packages/raes/runtime_platform_application_content.py) | P: `tenant_id`, `name`, `description` |
| `RuntimePlatformApplicationUpstreamBinding` | [runtime_platform_application_content.py](../../../implementations/python/packages/raes/runtime_platform_application_content.py) | P: `binding_id`, `description`; B: `role`, `target_node_ref`, `target_service_ref` |
| `RuntimePublishedPortRef` | [runtime_listeners.py](../../../implementations/python/packages/raes/runtime_listeners.py) | B: `container_port`, `protocol`, `host_ip`, `host_port` |
| `RuntimeScheduledJob` | [runtime_scheduled_job.py](../../../implementations/python/packages/raes/runtime_scheduled_job.py) | P: `scheduled_job_id`, `name`, `description`; C: `enabled`, `schedule`; B: `command_ref`; O: `run_state` |
| `RuntimeScheduledJobRunState` | [runtime_scheduled_job.py](../../../implementations/python/packages/raes/runtime_scheduled_job.py) | O: `last_run`, `next_run`, `last_result` |
| `RuntimeScheduledJobSchedule` | [runtime_scheduled_job.py](../../../implementations/python/packages/raes/runtime_scheduled_job.py) | P: `kind`; C: `spec`, `enabled` |
| `RuntimeSecurityMonitoringAgent` | [runtime_security_monitoring/_models.py](../../../implementations/python/packages/raes/runtime_security_monitoring/_models.py) | P: `agent_id`, `name`, `description`; B: `address`, `node_ref`, `group_refs`; N: `version`, `os`; O: `status` |
| `RuntimeSecurityMonitoringAgentGroup` | [runtime_security_monitoring/_models.py](../../../implementations/python/packages/raes/runtime_security_monitoring/_models.py) | P: `group_id`, `name`, `description`; B: `member_refs`, `configuration_file_refs` |
| `RuntimeSecurityMonitoringComponent` | [runtime_security_monitoring/_models.py](../../../implementations/python/packages/raes/runtime_security_monitoring/_models.py) | P: `component_id`, `kind`, `name`, `description`; C: `enabled`; B: `process_ref`; O: `status` |
| `RuntimeSecurityMonitoringContentSet` | [runtime_security_monitoring/_models.py](../../../implementations/python/packages/raes/runtime_security_monitoring/_models.py) | P: `content_id`, `kind`, `name`, `description`; B: `file_refs`; N: `format`; O: `file_count`, `loaded` |
| `RuntimeSecurityMonitoringDetectionDefinition` | [runtime_security_monitoring_definitions.py](../../../implementations/python/packages/raes/runtime_security_monitoring_definitions.py) | P: `definition_id`, `name`, `description`; C: `enabled`, `level`, `severity`, `match_strings`, `regex_patterns`, `field_predicates`, `frequency`, `timeframe_seconds`, `same_source_constraints`; B: `content_set_ref`, `parent_definition_refs`, `target_refs`; N: `engine`, `definition_kind`, `native_id`, `decoded_as`, `decoder_names`, `decoder_fields`, `if_sid_refs`, `if_matched_sid_refs`, `groups`, `mitre_attack_ids`, `compliance_tags`, `tactic_labels`, `technique_labels`, `tags`; O: `source_artifact_ref`, `source_file_ref`, `source_start_line`, `source_end_line`, `digest_algorithm`, `canonical_digest`, `loaded`, `parser_accepted`, `evidence_refs` |
| `RuntimeSecurityMonitoringFieldPredicate` | [runtime_security_monitoring_definitions.py](../../../implementations/python/packages/raes/runtime_security_monitoring_definitions.py) | P: `operator`, `description`; C: `value`; N: `field` |
| `RuntimeSecurityMonitoringListener` | [runtime_security_monitoring/_models.py](../../../implementations/python/packages/raes/runtime_security_monitoring/_models.py) | P: `listener_id`, `description`; B: `service`, `role`, `protocol`; A: `auth_required`, `tls_enabled` |
| `RuntimeSecurityMonitoringManager` | [runtime_security_monitoring/_models.py](../../../implementations/python/packages/raes/runtime_security_monitoring/_models.py) | P: `security_monitoring_manager_id`, `manager_kind`, `name`, `description`; C: `listeners`, `components`, `agents`, `agent_groups`, `content_sets`, `detection_definitions`, `settings`; B: `service`, `configuration_file_refs`; N: `implementation`, `version`, `revision`; O: `log_file_refs`, `evidence_refs` |
| `RuntimeSecurityMonitoringSetting` | [runtime_security_monitoring/_models.py](../../../implementations/python/packages/raes/runtime_security_monitoring/_models.py) | P: `setting_id`, `name`, `description`; C: `value`; B: `component_ref`; A: `value_classification`; O: `provenance`, `source_path` |
| `RuntimeServiceListener` | [runtime_listeners.py](../../../implementations/python/packages/raes/runtime_listeners.py) | P: `service_listener_id`, `description`; C: `scope`; B: `service`, `address`, `port`, `protocol`, `address_family`, `bind_interface`, `socket_path`, `process_ref`, `published_port_refs`; O: `process_name`, `readiness`, `provenance`, `evidence_refs` |
| `RuntimeSshServer` | [runtime_ssh_server.py](../../../implementations/python/packages/raes/runtime_ssh_server.py) | P: `description`, `ssh_server_id`; B: `service`; A: `forced_command`, `accept_env`, `allow_users`, `deny_users`, `allow_groups`, `deny_groups`, `authentication_methods`, `password_authentication`, `pubkey_authentication`, `permit_tty`, `chroot_directory`, `authorized_keys_file`, `match_rules` |
| `ServiceManagerUnit` | [runtime_service_units.py](../../../implementations/python/packages/raes/runtime_service_units.py) | P: `unit_id`, `description`; C: `exec_start`; B: `service`; N: `manager_kind`, `unit_name`, `unit_type`; O: `load_state`, `active_state`, `sub_state`, `enabled_state`, `result`, `exit_code`, `status_text`, `main_pid`, `unit_file_path` |
| `ServiceUnitExecStart` | [runtime_service_units.py](../../../implementations/python/packages/raes/runtime_service_units.py) | P: `description`; C: `command_kind`, `command`; A: `command_redacted` |
| `SshForcedCommand` | [runtime_ssh_server.py](../../../implementations/python/packages/raes/runtime_ssh_server.py) | P: `description`; A: `command_kind`, `command`, `command_redacted` |
| `SshMatchCriterion` | [runtime_ssh_server.py](../../../implementations/python/packages/raes/runtime_ssh_server.py) | P: `kind`; A: `pattern` |
| `SshMatchRule` | [runtime_ssh_server.py](../../../implementations/python/packages/raes/runtime_ssh_server.py) | P: `description`, `match_id`; A: `forced_command`, `accept_env`, `allow_users`, `deny_users`, `allow_groups`, `deny_groups`, `authentication_methods`, `password_authentication`, `pubkey_authentication`, `permit_tty`, `chroot_directory`, `authorized_keys_file`, `criteria` |

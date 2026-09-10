# SDL Sections Reference

A scenario is a YAML document with a required top-level `name`, optional
top-level metadata and composition fields, and the authoring sections catalogued
below. Aside from `name`, every top-level field is optional. The normative,
machine-checked enumeration is `specs/sdl/sections.md`.

Top-level composition fields are:

- `version` — scenario or module version
- `module` — optional publishable module descriptor (`id`, `version`, `parameters`, `exports`, `description`)
- `imports` — optional module imports using backward-compatible `path:` or canonical `source:`

Canonical `imports.source` classes are:

- `local:...` for repo-local files
- `oci:...` for remote OCI-packaged modules
- `locked:...` for lockfile-resolved concrete imports

## Section Overview

### OCR-derived core

The OCR scoring pipeline sections (`metrics`, `evaluations`, `tlos`, `goals`)
were removed from the SDL by
[ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md); graded
scoring, reward, and evaluation outputs now live in the experiment/evaluator
plane (ADR-055/064/069). Declarative `conditions` remain.

| Section | Type | Purpose |
|---------|------|---------|
| `nodes` | `dict[str, Node]` | Compute nodes and network switches — the compute/network topology |
| `infrastructure` | `dict[str, InfraNode]` | Deployment topology: counts, links, dependencies, IP/CIDR, ACLs |
| `features` | `dict[str, Feature]` | Software (Service/Configuration/Artifact) deployed to compute nodes |
| `conditions` | `dict[str, Condition]` | Declarative health/readiness checks (command+interval or library source) |
| `entities` | `dict[str, Entity]` | Teams, organizations, people (recursive, with exercise roles) |
| `injects` | `dict[str, Inject]` | Actions between entities during exercises |
| `events` | `dict[str, Event]` | Triggered actions combining conditions + injects |
| `scripts` | `dict[str, Script]` | Timed event sequences with human-readable durations |
| `stories` | `dict[str, Story]` | Top-level exercise orchestration grouping scripts |

### RAES extensions

| Section | Type | Purpose | Adapted From |
|---------|------|---------|--------------|
| `content` | `dict[str, Content]` | Data placed into systems (files, datasets, emails) | CyRIS `copy_content` |
| `accounts` | `dict[str, Account]` | Curated scenario/provisioning accounts on nodes, not full runtime identity inventory | CyRIS `add_account` |
| `identity_domains` | `dict[str, IdentityDomain]` | Authored domain identity and authority for controller/join realization | RAES ADR-082 |
| `relationships` | `dict[str, Relationship]` | Typed edges between elements (auth, trust, federation) | STIX Relationship SRO |
| `forwarding_agents` | `list[RuntimeForwardingAgent]` | Scenario-level forwarding and shipping agents with element-carried identity | RAES ADR-050 |
| `agents` | `dict[str, Agent]` | Autonomous participants (actions, knowledge, scope) | CybORG Agents, extended by RAES |
| `action_contracts` | `dict[str, ParticipantActionContract]` | Preconditions, effects, failures, interactions, and fidelity claims for participant actions | RAES participant model |
| `observation_boundaries` | `dict[str, ParticipantObservationBoundary]` | Participant-visible, hidden, discovered, and evidence-bearing information projections | RAES participant model |
| `outcome_interpretation_rules` | `dict[str, OutcomeInterpretationRule]` | Rules connecting action observations and evidence to scenario-local outcomes | RAES participant model |
| `behavior_specifications` | `dict[str, ParticipantBehaviorSpecification]` | Versioned aggregates over participant action, observation, outcome, authority, and mode surfaces | RAES ACT-606 |
| `evidence_requirements` | `dict[str, EvidenceRequirement]` | Portable authored capture obligations, distinct from captured evidence | RAES DSL-124, ADR-066 |
| `objectives` | `dict[str, Objective]` | Scenario-local objectives binding actors, targets, windows, and success (against observable `conditions`); not EXP task records | CACAO action/target/agent |
| `workflows` | `dict[str, Workflow]` | Branching and parallel control graphs over declared objectives | CACAO workflow graph patterns; semantics tightened using Step Functions / Argo / SCXML style control-flow rules |
| `variables` | `dict[str, Variable]` | Parameterization (types, defaults, substitution) | CACAO playbook_variables |
| `variation_points` | `dict[str, VariationPoint]` | Named bounded scenario-family domains and typed targets | RAES ADR-084 |

---

## Nodes

Nodes are the compute and network elements of the scenario.

Operating-system identity is split into three independent fields: `os` is the
family, `os_distribution` is the governed distribution or product line, and
`os_version` is only the release token. A version requires a distribution, and
a distribution requires a family. Backends admit distribution/version pairs as
coupled compatibility rows; they must not infer support by cross-pairing values
from different rows. Runtime proof for these fields is guest-observed evidence
bound to the executing operation and selected realization envelope—not an image
tag, boot success, or a copied plan/snapshot value.

```yaml
nodes:
  corp-switch:
    type: Switch
    description: Corporate LAN

  web-server:
    type: compute
    os: linux                           # windows, linux, macos, freebsd, other
    architecture: x86_64                 # target-node CPU architecture: x86_64, aarch64
    os_distribution: ubuntu
    os_version: "22.04"
    source: ubuntu-22.04                # provider-neutral image reference
    resources:
      ram: 4 GiB                        # human-readable: GiB, MiB, GB, MB
      cpu: 2
    features:                           # dict form: {feature: role} or list form: [feature]
      nginx: web-admin
    conditions:
      web-health: web-admin
    roles:
      web-admin: www-data               # shorthand: role: username
      operator:                         # longhand
        username: ops
        entities: [blue-team.alice]     # binds to entity
    services:                           # authored node-local transport bindings
      - port: 80
        protocol: tcp
        name: http
      - port: 443
        name: https
      - port: 389
        name: ldap
    runtime:                            # observed runtime configuration facts
      mounts:
        - target: /shuffle-database
          source: aptl_shuffle_data
          source_sensitivity: plain
          source_kind: volume
          filesystem_type: ext4
          read_only: false
          options: [rw, nosuid]
          options_sensitivity: plain
          propagation: rprivate
          stability: volume_backed
          backend_generated: true
      filesystem_inventory:
        - path: /app/app.py
          entry_type: file
          owner_user: root
          owner_group: root
          uid: 0
          gid: 0
          mode: "0644"                 # quote to preserve leading zeroes
          size: 4096
          content_digest: 4f8c2d
          digest_algorithm: sha256
          source_path: src/webapp/app.py
          provenance: python-package
          stability: stable
          sensitivity: plain
        - path: /var/log/gunicorn/access.log
          entry_type: file
          mode: "0600"
          stability: log
          sensitivity: operator_secret
      local_control_interfaces:
        - path: /run/docker.sock
          kind: unix_socket
          protocol: docker
          bind_source_sensitivity: operator_secret
          access: read_write
      processes:
        - name: shufflebackend
          command: ./shufflebackend
          user: root
          working_directory: /app
        - name: supervisord
          pid: 1
          command: supervisord -n
          role: supervisor
        - name: gunicorn
          parent_pid: 1
          command: [gunicorn, app:app]
          role: worker
      environment:
        - name: TECHVAULT_ADMIN_PASSWORD
          value_classification: redacted
          provenance: operator
        - name: SCENARIO_FIXTURE_TOKEN
          value: fixture-token
          value_classification: secret_fixture
          provenance: compose
      linux_capabilities:
        required: [CAP_NET_ADMIN]
        effective: CAP_NET_ADMIN
      operational_policy:
        restart: unless_stopped
        resource_limits:
          memory: 512 MiB
          cpu: 0.5
          pids: 128
          process_limits:
            - resource: open_file_descriptors
              soft: 4096
              hard: 8192
              subject:
                name: gunicorn
                role: worker
              scope: subtree
            - resource: locked_memory_bytes
              soft: 0
              hard: unlimited
              subject:
                name: shufflebackend
              scope: process
      container:
        entrypoint: [/entrypoint.sh]
        command: [gunicorn, app:app]
        log_driver: json-file
        log_options:
          max-size: 10m
          max-file: "3"
        namespaces:
          cgroup: private
          ipc: private
          pid: private
          userns: host
          uts: private
        privileged: false
        read_only_rootfs: false
        publish_all_ports: false
        autoremove: false
        shm_size: 64 MiB
        masked_paths: [/proc/acpi, /proc/kcore]
        read_only_paths: [/proc/sys]
        cgroup_parent: /docker
        runtime_name: runc
        devices:
          - host_path: /dev/null
            container_path: /dev/null
            permissions: rwm
        device_cgroup_rules: [c 1:3 rwm]
        seccomp_profile: unconfined
        security_opt: [seccomp:unconfined, no-new-privileges]
        extra_hosts:
          - hostname: wazuh-manager
            address: 172.20.0.10
        dns: [8.8.8.8]
        dns_options: [ndots:0]
        dns_search: [techvault.local]
        group_add: [adm, "101"]
      packages:
        - manager: apk
          name: musl
          version: 1.2.4-r2
      software_components:
        - component_id: shuffle-backend-app
          name: shuffle-backend
          version: 1.2.3
          component_type: application
          provenance: package-manager
          ecosystem: go
          purl: "pkg:golang/github.com/frikky/shuffle@1.2.3"
          cpe: "cpe:2.3:a:shuffle:shuffle:1.2.3:*:*:*:*:*:*:*"
          package_manager: apk
          package_name: shuffle-backend
          package_version: 1.2.3-r0
          manifest_path: /app/go.mod
          installed_paths: [/app/shufflebackend, /app/go.mod]
          hashes:
            - algorithm: sha256
              value: abc123
      dependency_manifests:
        - ecosystem: go
          path: /app/go.mod
          format: go-module
      local_identity:                   # observed /etc/passwd, /etc/group, sudo facts
        users:
          - username: www-data
            uid: 33
            primary_gid: 33
            primary_group: www-data
            home: /var/www
            shell: /usr/sbin/nologin
            no_login: true
            provenance: image
            stability: stable
        groups:
          - name: www-data
            gid: 33
            members: [www-data]
            provenance: image
        sudo_rules:
          - principal: wazuh
            principal_kind: user
            run_as_users: [root]
            commands: ["/usr/bin/systemctl restart wazuh-agent"]
            nopasswd: true
      network:                          # deliberately required runtime network state
        hostname: techvault-webapp
        domainname: techvault.local
        endpoints:
          - network: aptl-dmz           # references a switch-backed infrastructure entry
            ip_address: 172.20.0.20
            ip_prefix_length: 24
            gateway: 172.20.0.1
            mac_address: 02:42:ac:14:00:14
            aliases: [aptl-webapp, webapp]
            dns_names: [aptl-webapp, webapp]
            backend:
              driver: bridge
              ipam_driver: default
              driver_options: {com.docker.network.bridge.name: br-aptl-dmz}
        published_ports:
          - container_port: 8080
            protocol: tcp
            host_ip: 0.0.0.0
            host_port: 8080
      service_listeners:                 # observed in-node bind endpoints
        - listener_id: gunicorn-http-ipv4
          service: http                  # owning same-node Node.services[].name
          address: 0.0.0.0
          port: 80
          protocol: tcp
          address_family: ipv4
          scope: wildcard
          process_ref: gunicorn
          process_name: gunicorn
          published_port_refs:
            - container_port: 80
              protocol: tcp
              host_ip: 0.0.0.0
              host_port: 80
          readiness:
            probe: GET /
            criteria: HTTP 200
          provenance: osquery
        - listener_id: supervisord-loopback
          address: 127.0.0.1
          port: 9001
          protocol: tcp
          address_family: ipv4
          scope: loopback_only
          process_ref: supervisord
      applications:                     # observed HTTP route/API/UI surface
        - application_id: techvault-webapp
          service: techvault-http       # owning same-node Node.services[].name
          protocol: http
          framework: flask
          base_path: /
          routes:
            - route_id: login
              path: /login
              methods: [GET, POST]
              auth_required: false
              session_required: false
              auth_scheme: form_login
              parameters:
                - name: username
                  location: form
                  required: true
                - name: password
                  location: form
                  required: true
              responses:
                - status_code: 200
                  content_type: text/html
              templates: [/app/templates/login.html]
              static_assets: [/app/static/style.css]
              redirects:
                - target: /dashboard
                  status_code: 302
                  condition: valid credentials
            - route_id: upload
              path: /files/upload
              methods: [POST]
              auth_required: true
              session_required: true
              parameters:
                - name: document
                  location: uploaded_file
                  required: true
            - route_id: diagnostics
              path: /debug/info
              methods: [GET]
              exposed_fields:
                - name: build_token
                  sensitivity: secret_fixture
                  value: fixture-token-1234
              disclosures:
                - trigger: any request
                  status_code: 200
                  disclosure: internal package versions and host paths
                  sensitivity: plain
      database_services:                # observed database logical state
        - database_service_id: techvault-postgres
          service: techvault-pg         # owning same-node Node.services[].name
          engine: postgresql
          protocol: postgresql
          version: "16.13"
          listeners:
            - address: "*"
              port: 5432
          databases:
            - database_id: techvault-db
              name: techvault
              origin: scenario
              schemas:
                - schema_id: public-schema
                  name: public
                  tables:
                    - {table_id: users-tbl, name: users}
                    - {table_id: audit-tbl, name: audit_log}
            - database_id: template0-db
              name: template0
              origin: built_in           # engine built-in, not scenario-authored
          roles:
            - {role_id: app-role, name: techvault, role_type: application, can_login: true}
          grants:
            - grantee_role_ref: app-role
              object_type: table
              object_ref: users-tbl
              privileges: [SELECT, INSERT, UPDATE]
          settings:
            - {name: listen_addresses, value: "*", provenance: configuration_file}
            - name: password_encryption     # explicit redaction omits value
              value_classification: redacted
              provenance: operator_override
      dns_services:                     # observed DNS authoritative/resolver state
        - dns_service_id: techvault-bind
          service: dns                  # owning same-node Node.services[].name
          implementation: bind
          roles: [authoritative, recursive_resolver]
          configuration_file_refs: [/etc/bind/named.conf]
          resolver_policy:
            recursion_enabled: true
            allow_recursion: [10.0.0.0/24]
            dnssec_validation: auto
            forwarders:
              - {address: 8.8.8.8, port: 53, transport: udp}
          zones:
            - zone_id: techvault-local
              name: techvault.local.
              purpose: forward
              zone_file_refs: [/etc/bind/db.techvault.local]
              rrsets:
                - rrset_id: root-soa
                  owner: techvault.local.
                  record_type: soa
                  ttl: 3600
                  records:
                    - soa:
                        mname: ns1.techvault.local.
                        rname: hostmaster.techvault.local.
                        serial: 2026052801
                        refresh: 3600
                        retry: 600
                        expire: 604800
                        minimum: 300
                - rrset_id: web-a
                  owner: web.techvault.local.
                  record_type: a
                  ttl: 300
                  records:
                    - {address: 10.0.0.20}
          settings:
            - name: tsig_secret          # explicit redaction omits value
              value_classification: redacted
              provenance: operator_override
      network_detection_engines:        # observed IDS/NDR engine state
        - network_detection_engine_id: suricata-engine
          implementation: suricata
          engine_kind: ids
          version: "7.0.15"
          sensor_ref: suricata-sensor    # same-node runtime.network_sensors id
          app_layer_protocols: [http, tls, dns, ssh, smtp, ftp, smb]
          configuration_file_refs: [/etc/suricata/suricata.yaml]
          rule_sources:
            - source_id: local-rules
              kind: local
              format: suricata_rule
              rule_count: 46
              file_refs: [/etc/suricata/rules/local.rules]
          network_sets:
            - set_id: home-net
              kind: home_net
              name: HOME_NET
              network_refs: [dmz-net, internal-net]
          output_streams:
            - stream_id: eve-json
              format: eve_json
              path: /var/log/suricata/eve.json
              event_types: [alert, http, dns, tls, ssh, flow, netflow, stats]
          control_channels:
            - channel_id: command-socket
              kind: unix_socket
              path: /var/run/suricata-command.socket
              capabilities: [rule_reload]
      security_monitoring_managers:     # observed SIEM/security-monitoring manager state
        - security_monitoring_manager_id: techvault-wazuh
          service: wazuh-api            # owning same-node Node.services[].name
          implementation: wazuh
          manager_kind: siem
          version: "4.12.0"
          configuration_file_refs: [/var/ossec/etc/ossec.conf]
          log_file_refs: [/var/ossec/logs/ossec.log]
          listeners:
            - listener_id: manager-api
              service: wazuh-api
              role: api
              auth_required: true
              tls_enabled: true
            - listener_id: agent-events
              service: wazuh-agent-events
              role: agent_event_ingestion
          components:
            - component_id: analysisd
              kind: analysis_engine
              name: wazuh-analysisd
              status: running
          agents:
            - agent_id: "001"
              name: aptl-web-agent
              status: available
              group_refs: [default]
          agent_groups:
            - group_id: default
              member_refs: ["001"]
              configuration_file_refs: [/var/ossec/etc/shared/default/agent.conf]
          content_sets:
            - content_id: wazuh-ruleset
              kind: rule_corpus
              format: wazuh_rule_xml
              file_count: 173
              file_refs: [/var/ossec/ruleset/rules]
              loaded: true
          detection_definitions:
            - definition_id: rule-301010
              engine: wazuh
              definition_kind: correlation_rule
              native_id: "301010"
              content_set_ref: wazuh-ruleset
              source_file_ref: /var/ossec/etc/rules/ad_rules.xml
              source_start_line: 12
              source_end_line: 35
              digest_algorithm: sha256
              canonical_digest: 1111111111111111111111111111111111111111111111111111111111111111
              loaded: true
              parser_accepted: true
              level: 10
              severity: high
              field_predicates:
                - field: win.system.eventID
                  operator: equals
                  value: "4769"
              if_sid_refs: [rule-300000]
              frequency: 5
              timeframe_seconds: 60
              groups: [windows, kerberos]
              mitre_attack_ids: [T1558.003]
          settings:
            - setting_id: json-output
              name: jsonout_output
              value: "yes"
              provenance: configuration_file
              source_path: /var/ossec/etc/ossec.conf
            - setting_id: api-token       # explicit redaction omits value
              name: api_token
              value_classification: redacted
              provenance: operator_override
      datastore_services:               # observed non-relational datastore state
        - datastore_service_id: opensearch-store
          service: opensearch           # owning same-node Node.services[].name
          engine: opensearch
          data_model: search_index      # OPEN discriminator selects the profile
          version: "2.13"
          cluster:
            cluster_id: os-cluster
            uuid: native-cluster-uuid
            health: green
            discovery_mode: zen
            node_count: 3
            shard_total: 6
            shard_primaries: 3
            doc_count: 1053842
            store_size_bytes: 1391460626
          nodes:
            - node_id: os-node-1
              roles: [data, cluster_manager]
              engine_version: "2.13"      # product-neutral node engine provenance
              build_type: rpm
              build_hash: dae2bfc9389617
              heap_init_bytes: "1 GiB"    # human sizes normalize to bytes
              heap_max_bytes: "1 GiB"
              memory_locked: true         # observed mlockall posture
              endpoints:
                - endpoint_id: http       # participant-facing listener
                  role: client
                  protocol: https
                  address: 172.20.0.12
                  port: 9200
                - endpoint_id: transport  # inter-node listener
                  role: peer
                  protocol: transport
                  address: 172.20.0.12
                  port: 9300
              plugins:                    # per-plugin version retained
                - plugin_id: opensearch-security
                  name: opensearch-security
                  version: 2.13.0.0
          partitions:                   # search_index requires shard/replica geometry
            - partition_id: alerts-index
              uuid: native-index-uuid
              kind: index
              doc_count: 68993
              doc_count_deleted: 0
              store_size_bytes: 96888422
              creation_timestamp: "2026-05-28T00:00:05.253Z"
              open_closed_status: open
              shard_count: 3
              replica_count: 1
          mappings:                     # bounded schema manifest, not raw _mapping JSON
            - mapping_id: alerts-mapping
              partition_ref: alerts-index
              leaf_field_count: 670
              field_type_census: {keyword: 220, date: 9, ip: 12}
              dynamic_policy: "true"
              dynamic_template_count: 5
              schema_digest: sha256:alerts-mapping
          templates:                    # bounded template manifest, not raw _template JSON
            - template_id: wazuh-template
              index_patterns: [wazuh-alerts-4.x-*]
              settings_summary: {index.number_of_shards: "3"}
              mapping_ref: alerts-mapping
          transport_security:
            transport_security_id: os-transport
            mode: tls
            node_verification: true
          authorization_ref: opensearch-rbac   # same-node runtime.app_authorizations id
          settings:
            - setting_id: keystore-pw   # explicit redaction omits value
              name: bootstrap.password
              classification: redacted
      platform_applications:            # declared participant-visible application state
        - platform_application_id: misp-tip
          service: misp                 # owning same-node Node.services[].name
          product: MISP
          version: "2.4"
          capabilities:                 # functional roles, not completeness claims
            - capability_id: intelligence-management
              kind: threat_intelligence_management
            - capability_id: intelligence-exchange
              kind: intelligence_exchange
          organizations:
            - organization_id: home-org
              name: TechVault CTI
          markings:
            - marking_id: tlp-amber
              scheme: tlp
              level: amber
          authorization_ref: misp-rbac  # same-node runtime.app_authorizations id
      forwarding_agents:                # observed log-shipping / intel-sync state
        - forwarding_agent_id: wazuh-sidecar-suricata
          implementation: wazuh_agent
          agent_kind: log_forwarder     # OPEN discriminator selects the profile
          version: "4.7.0"
          sources:
            - source_id: eve
              kind: tailed_path
              location: /logs/eve.json
              parse_format: json
          transforms:
            - transform_id: passthrough
              kind: passthrough
          ship_targets:                 # log_forwarder requires an ingestion endpoint
            - target_id: manager
              target_node_ref: wazuh.manager   # cross-node target resolves to a node
              ingestion_port: 1514
              enrollment_port: 1515
              protocol: syslog
              enrollment_identity_classification: redacted  # identity never recorded
          buffer_policy:                # log_forwarder requires a buffer_policy
            buffer_policy_id: client-buffer
            queue_capacity: 5000
            eps: 500
            crypto: aes
          settings:
            - setting_id: authd-pass    # explicit redaction omits value
              name: authd.pass
              classification: redacted
      orchestration_authorities:        # observed container-spawn authority state
        - orchestration_authority_id: shuffle-orborus
          control_interface_ref: docker-sock   # same-node local_control_interfaces id
          engine: docker
          privilege_class: host_root_equivalent  # OPEN discriminator selects the profile
          scope:
            organization_ref: org-aptl
            environment_name: shuffle
          spawn_templates:
            - template_id: worker
              image_ref: ghcr.io/shuffle/shuffle-worker:1.4.0
              purpose: workflow
          lifecycle_policy:
            timeout: 300s
            cleanup: on_exit
          realized_children:
            - workload_id: worker-pool
              image_ref: shuffle-worker:1.4.0
              count: 12
      identity_authorities:             # observed directory/domain/IdP/IAM state
        - identity_authority_id: techvault-domain
          kind: domain
          namespace: techvault.local
          domain_name: TECHVAULT
          realm: TECHVAULT.LOCAL
          base_dn: DC=techvault,DC=local
    services:
            - service_id: ldap-endpoint
              service: ldap             # owning same-node Node.services[].name
              protocol: ldap
              address: dc.techvault.local
              port: 389
          subjects:
            - subject_id: alice
              kind: user
              name: alice
              principal_name: alice@TECHVAULT.LOCAL
              distinguished_name: CN=Alice,CN=Users,DC=techvault,DC=local
              enabled: true
            - subject_id: domain-admins
              kind: group
              name: Domain Admins
            - subject_id: app-svc
              kind: service_principal
              name: webapp
              service_principal_names: [HTTP/web.techvault.local]
          relationships:
            - relationship_id: alice-admin
              relationship_type: member_of
              source_ref: alice
              target_ref: domain-admins
          policies:
            - policy_id: default-domain-policy
              policy_kind: password
              applies_to_refs: [techvault-domain, ldap-endpoint, alice-admin]
              settings:
                - name: min_length
                  values: "14"
    asset_value:                        # CIA triad (from CybORG)
      confidentiality: high
      integrity: medium
      availability: critical
```

**Switch** nodes are pure connectivity objects. They may define `type` and an optional `description`, but `source`, `resources`, `os`, `architecture`, `os_version`, `features`, `conditions`, `injects`, `roles`, `services`, `asset_value`, and `runtime` are rejected.

**Compute** is a portable resource kind, not a synonym for virtual machine.
Without another declaration a backend may realize a compute node with any
admitted substrate. Authors constrain that choice at the scenario root:

```yaml
realization:
  constraints:
    - field_pointer: /nodes/web
      concern: compute-substrate
      posture: constrained
      domain:
        kind: enum
        values: [operating-system-container, virtual-machine]
```

Use `posture: exact` with an exact domain to require one mechanism. The
portable mechanisms are `virtual-machine`, `operating-system-container`, and
`physical-device`; governed extension terms remain available for modes such as
reference emulation. Planning preserves this constraint separately from the
node kind, and runtime evidence records the mechanism actually selected.
Historical `type: vm` is accepted only by explicit migration, where it becomes
`type: compute` plus an exact `virtual-machine` constraint.

For **compute** nodes, `resources` remain optional at the SDL layer to preserve abstract specifications, but a compute node without `resources` emits a non-fatal advisory because many deployment backends will need explicit sizing or well-defined defaults.

**Target-node architecture:** `architecture` is the CPU architecture the target node or guest requires. Canonical values are `x86_64` and `aarch64`; case-insensitive aliases (`amd64`, `x64`, `x86-64`, `arm64`) normalize to them, and a custom architecture uses the governed `x-<owner>:<term>` extension form. It is distinct from a runtime package's artifact architecture and from a backend host's architecture. Absence means the scenario imposes no target-node architecture requirement; it never implies the host, runner, or image architecture. When a node declares `architecture`, every architecture-constrained runtime package on that node must resolve to the same canonical value, and a node without `architecture` may not carry an architecture-constrained package.

**Feature list shorthand:** `features: [nginx, php]` expands to `{nginx: "", php: ""}` (no role binding required).

When `features`, `conditions`, or `injects` use the `{name: role}` form, the role must be declared in the node's `roles` map.

Concrete service bindings on a compute node must be unique by `protocol` + `port`. Reusing `53/tcp` and `53/udp` is valid; declaring `443/tcp` twice on the same node is rejected. If a service binding also has a `name`, that `name` must be unique within the node and can be targeted directly as `nodes.<node>.services.<service_name>`.

A `services` entry identifies an authored node-local transport binding. It does
not authorize any source to reach the port, prove a live listener, publish a
host port, or classify an `internal`/`external` audience. Traffic authorization
is declared separately through `infrastructure.*.acls`; observed bind state is
recorded in `runtime.service_listeners`, and host publication is recorded in
`runtime.network.published_ports`. Service entries are closed-world objects, so
an unmodeled field such as `role` is rejected rather than interpreted as policy
or silently dropped.

`runtime` is authored declarative contract state for compute nodes across VM and container realizations. Every
field present there requires exact state, constrains acceptable state, or marks
an explicitly open realization point. A value does not become an SDL
requirement merely because Docker, a scanner, or a participant-visible probe
reported it. Captured facts stay in a source evidence bundle and
`ExperimentEvidenceRecordModel`; an author must deliberately promote a fact to
the smallest semantically correct SDL field before it can affect compilation.
Model defaults are likewise not proof of author declaration: explicitness is
tracked through `model_fields_set` and SEM-218, not inferred from
`model_dump()` output.

Some historical runtime type and field names describe the observation that
motivated the surface. Their carrier semantics are nevertheless declarative:
presence in authored `Node.runtime` makes the value contract state. Mounts
describe required filesystem attachments, including filesystem type,
propagation, stability, whether a backend may generate the source, and
sensitivity classifications for the source and option strings. Mount sources
or options classified as
`redacted` or `operator_secret` must omit the raw value. This sensitivity
vocabulary is an RAES runtime contract, not an adopted taxonomy from Docker,
Compose, or the cited scenario-language precedents. `filesystem_inventory` records
runtime-observed filesystem entries with absolute path, entry type, ownership,
UID/GID, mode, size, digest algorithm/value pairs, source-package path,
provenance, stability, and sensitivity classification.
`local_control_interfaces` describe path-local control APIs such as Unix
sockets; host-side bind sources use `bind_source_sensitivity` and must omit
`bind_source` when classified as `redacted` or `operator_secret`; `processes`
records the supervised or load-bearing process set, including the primary
execution identity; `environment` records observed runtime environment
variables with provenance and value classification, where redacted and
operator-secret values omit raw data and `secret_fixture` is the explicit
exercise-fixture disclosure; `linux_capabilities` records container/Linux
capability policy; `operational_policy` records restart policy and required
resource policy. Its `memory`, `memory_swap`, `cpu`, and `pids` fields govern
node/container capacity. Its `process_limits` collection separately governs
portable soft/hard process limits: `open_file_descriptors` counts descriptors
and `locked_memory_bytes` counts bytes; each value is a non-negative integer,
`unlimited`, or a whole-field variable. Every record selects a declared
`runtime.processes` identity and states whether the limit applies only to that
process or to its subtree. All populated selector fields must match the same
declared process. A redacted command must be omitted and paired with another
stable selector such as name, role, user, or working directory; command content
cannot be authored and then discarded from identity. Native names such as
`nofile`/`memlock`, Docker
`ulimits`, systemd directives, and raw `/proc` data are backend dialect or
evidence, not SDL. An authored empty collection requires exact absence, while
omission creates no closed requirement unless a `realization` designation
explicitly opens or constrains the concern. `container` records observed
host/container configuration and
namespace/security facts, including `seccomp_profile` (the portable seccomp
posture — `default`, `unconfined`, a named profile, or a profile path) and
`security_opt` (the bounded list of backend-native engine security options
such as `seccomp:unconfined` or `no-new-privileges`); a seccomp posture is a
distinct security control from `privileged`, so it is recorded separately (see
[ADR-028](../../decisions/adrs/adr-028-container-seccomp-security-options-surface.md));
`packages` records package-manager rows. A package without `repository` is
obtained from the target's ordinary configured sources. The optional
`repository` child declares required final repository state through a closed,
versioned profile. Profile `apt` version `1` is the initial portable form:

```yaml
packages:
  - manager: apt
    name: wazuh-agent
    version: 4.12.0-1
    repository:
      repository_profile: apt
      profile_version: "1"
      uri: https://packages.wazuh.com/4.x/apt/
      suite: stable
      components: [main]
      signing_key:
        uri: https://packages.wazuh.com/key/GPG-KEY-WAZUH
        format: openpgp-ascii-armored
        digest: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```

Repository and signing-key URIs are credential-free HTTPS locations. The key
digest pins the exact public OpenPGP bytes, and `format` states whether those
bytes are `openpgp-ascii-armored` or `openpgp-binary`; a backend must not infer
the format from content. `suite` and the non-empty, duplicate-free
`components` collection are structured APT values, not fragments of a `deb`
line. The package manager must be exactly `apt`, matching the profile. Backend
implementations own dedicated keyring/source-list paths and safe fetching,
digest verification, rendering, locking, installation, and independent
readback. The SDL cannot supply a `signed-by` path, an options map, a command,
credentials, or private key material. `source` remains an opaque provenance
label and `purl` remains package identity metadata; neither is parsed as a
repository or executable value. Future package managers use their own closed
profile and version rather than adding manager-specific options to this one.

`software_components` records
node-local software identity at component granularity with stable RAES ids,
component type, version, purl/CPE/hash identifiers, package or manifest
lineage, and runtime paths when required; and `dependency_manifests` records
required manifest files. Software components are required final state, not
invocation surfaces, process snapshots, HTTP route inventory, or scanner
capture method (see
[ADR-056](../../decisions/adrs/adr-056-runtime-observed-values-and-credential-posture.md)
for the cross-surface observed-value and credential-posture inventory, and
[ADR-034](../../decisions/adrs/adr-034-runtime-software-component-inventory.md)).

Container health results are evidence, not `runtime` fields. Put the authored
healthcheck definition in `conditions`, bind it through `Node.conditions`, and
record status, failing streak, timestamps, exit codes, and output separately;
the valid portable fixture
[`runtime-health-observation.json`](../../../contracts/fixtures/experiment-core/experiment-evidence-record-v1/valid/runtime-health-observation.json)
shows that carrier. Scanner identity/version/database, scan time, raw findings,
and advisory snapshot state likewise belong in evidence. Derived severity
counts belong in `ExperimentDerivedMeasureModel`; they do not automatically
become native weakness facts. Authored classifications use standalone external concept bindings.

`runtime.service_manager_units` records observed service-manager unit
lifecycle state — what `systemctl` exposes from inside a realized range node.
Each entry carries a stable RAES `unit_id`, a `manager_kind` (initially
`systemd`, with `other` reserved), the native `unit_name` such as
`sshd.service`, a `unit_type` (`service`/`socket`/`target`/`timer`/`path`/
`mount`/`automount`/`swap`/`device`/`slice`/`scope`/`other`), and the
participant-observable state quadruple `load_state` (loaded/not_found/masked/
error/merged/stub/bad_setting/unknown), `active_state` (active/reloading/
inactive/failed/activating/deactivating/unknown), bounded free-form `sub_state`
(e.g. `running`/`exited`/`dead`), and `enabled_state` (enabled/enabled_runtime/
disabled/static/alias/masked/generated/indirect/transient/unknown). The last
run is classified via `result` (success/exit_code/signal/timeout/watchdog/
oom_kill/core_dump/start_limit_hit/resources/protocol/other/unknown) with
optional `exit_code` (only valid when `result` is `exit_code`) and a short
`status_text` for evidence like `226/NAMESPACE`. Optional fields capture the
`main_pid` when a live process exists, the `unit_file_path` (cross-checked
against `runtime.filesystem_inventory` when that inventory is non-empty), and
a redactable `exec_start` (`command_kind` `absolute_path` / `redacted`, with
`command_redacted` forcing an empty `command`). An optional `service` ref
pointing at the same-node `Node.services[].name` (bare or
`nodes.<node>.services.<name>`) ties a unit to the transport service it
launches. This surface is observed WHAT-IS lifecycle state: it is not
`Node.services` (transport bindings), not `conditions` (authored
monitoring/readiness intent), not `runtime.processes` (live processes — a
failed, disabled, static, or active/exited unit may have no live process),
not `runtime.container.init_process` (container PID-1/init configuration),
not `runtime.operational_policy.restart` (orchestrator restart policy), not
`runtime.ssh_servers` (sshd policy — `sshd.service` lifecycle is the unit,
sshd directives are the SSH surface), and not package/software/filesystem
inventory. Raw `systemctl`, `journalctl`, unit-file text, and backend
inspector payloads are not portable schema; secret-bearing `ExecStart` values
must be classified `redacted` and omit the raw command (see
[ADR-035](../../decisions/adrs/adr-035-service-manager-unit-state-runtime-surface.md)).

`runtime.local_identity` records the observed local identity database — the
node-scoped `/etc/passwd`, `/etc/group`, and sudo/sudoers facts. `users` carry
`username`, `uid`, `primary_gid`, `primary_group`, `gecos`, `home`, `shell`,
`supplemental_groups`, and the three distinct status facts `disabled`,
`locked`, and `no_login` (a no-login shell is not the same fact as a locked
password or a disabled account), plus `provenance` and `stability`. `groups`
carry `name`, `gid`, and `members`. `sudo_rules` model privilege grants as
structured `principal`/`principal_kind`, `run_as_users`/`run_as_groups`,
`host_scope`, and a portable `commands` scope, with `nopasswd` and a
`command_redacted` flag; an optional `raw_entry` may carry the original
sudoers line as descriptive evidence only. This is observed inventory: it is
distinct from the top-level `accounts` provisioning surface, and service
accounts recorded here are not implicitly compiled into account placements
(see [ADR-024](../../decisions/adrs/adr-024-local-identity-inventory-surface.md)).

`runtime.network` records deliberately required container network state,
distinct from the `infrastructure` topology declaration. `hostname`,
`domainname`, aliases/DNS names, addresses, prefix, gateway, MAC, backend
configuration, and published bindings are contract facts when authored.
Docker network IDs, endpoint IDs, generated DNS names, and incidental inspect
output are not accepted by the SDL schema; preserve them in evidence and the
inventory mapping ledger instead. The valid portable fixture
[`docker-network-endpoint-observation.json`](../../../contracts/fixtures/experiment-core/experiment-evidence-record-v1/valid/docker-network-endpoint-observation.json)
demonstrates the evidence side. `published_ports` keeps container port, host IP,
host port, and protocol distinct from the authored `services` declaration and image-default
`source.build.config.exposed_ports`
(see [ADR-025](../../decisions/adrs/adr-025-container-network-realization-surface.md)).

`runtime.network_sensors` records observed passive or inline NSM/IDS sensor
posture hosted by the node. Each entry has a stable `network_sensor_id`, bounded
implementation/kind/posture/capture-mode fields, capture interfaces such as
`any`, and `monitored_network_refs` naming the declared switch-backed networks
whose traffic the sensor observes. Monitoring scope is distinct from network
attachment: `runtime.network.endpoints` can show that a node is multi-homed,
while `runtime.network_sensors` states that the node observes those networks.
Configuration, log, and evidence refs are checked against
`runtime.filesystem_inventory` when that inventory is non-empty. Fully
qualified refs such as `nodes.suricata.runtime.network_sensors.suricata`
participate in relationships, generic reference validation, and module import
rewriting (see
[ADR-042](../../decisions/adrs/adr-042-network-sensor-runtime-monitoring.md)).

`runtime.service_listeners` records observed in-node listener bind state:
stable listener id, transport protocol, port or Unix socket path, bind address
or interface, address family, listener scope, optional same-node service ref,
optional process owner ref/name, readiness evidence, provenance, evidence refs,
and optional typed correlations to `runtime.network.published_ports`. It is
distinct from `Node.services` (authored service identity), from
`runtime.network.published_ports` (host publication), and from
protocol-specific runtime inventories such as HTTP applications, DNS, mail, and
database services. A wildcard address such as `0.0.0.0` or `::` is a wildcard
inside the node namespace; host exposure remains a published-port fact. Fully
qualified refs such as
`nodes.web.runtime.service_listeners.gunicorn-http-ipv4` participate in
relationships, generic reference validation, and module import rewriting (see
[ADR-043](../../decisions/adrs/adr-043-runtime-service-listener-surface.md)).

`runtime.network_detection_engines` records observed IDS/NDR detection-engine
state hosted by the node: engine identity, parser families, rule-source
inventories, network zoning/address-set variables, output streams,
reload/control channels, and evidence refs. It is distinct from passive sensor
posture (`runtime.network_sensors`), SIEM manager inventory
(`runtime.security_monitoring_managers`), software component identity, raw
filesystem evidence, HTTP applications, and transport services. Each engine
has a stable `network_detection_engine_id`; child collections use stable ids for rule sources,
network sets, output streams, and control channels. File/path refs are checked
against `runtime.filesystem_inventory` when that inventory is non-empty, and
network-set refs resolve to switch-backed infrastructure entries. Fully
qualified refs such as
`nodes.suricata.runtime.network_detection_engines.suricata-engine.output_streams.eve-json`
participate in relationships, generic reference validation, and module import
rewriting (see
[ADR-044](../../decisions/adrs/adr-044-network-detection-engine-runtime-inventory.md)).

`runtime.applications` records the participant-observable HTTP application
route/API/UI surface — what an adversary, defender, agent, scanner, or evaluator
can observe of the web application itself, distinct from the transport-level
`services` binding and from the host exposure in `runtime.network`. Each entry
is a `RuntimeApplicationSurface` with a stable `application_id`, an optional
`service` referencing the owning same-node `Node.services[].name` (bare name or
the qualified `nodes.<node>.services.<name>` form), a `protocol`/`framework`
classification, and an optional `base_path`. Each `routes` entry carries a
stable `route_id` (the route `path` is data, never a mapping key, and may carry
path variables and be shared across methods), normalized HTTP `methods`,
observable `auth_required`/`session_required`/`auth_scheme`, typed `parameters`
located by `path`/`query`/`header`/`cookie`/`form`/`json_body`/`uploaded_file`,
`responses` with status code and content type, `templates`/`static_assets`
associations resolving to the node's observed file inventory,
`redirects`, observable error/disclosure behavior in
`disclosures`, and `exposed_fields` for route-visible fixture secrets or
intentionally exposed diagnostic fields classified with the shared runtime
sensitivity vocabulary — `redacted` and `operator_secret` fields omit their raw
value, while `secret_fixture` fields may carry deliberate exercise fixture
values (see
[ADR-026](../../decisions/adrs/adr-026-application-http-surface-inventory.md)
and
[ADR-057](../../decisions/adrs/adr-057-runtime-secret-name-classifier-boundaries.md)).

`runtime.database_services` records the participant-observable database
logical state — what an adversary, defender, agent, scanner, or evaluator can
observe of a database itself, distinct from the transport-level `services`
binding, the host exposure in `runtime.network`, and the HTTP surface in
`runtime.applications`. Each entry is a `RuntimeDatabaseService` with a stable
`database_service_id`, an optional `service` referencing the owning same-node
`Node.services[].name`, and distinct `engine`/`protocol`/`version` facts — a
PostgreSQL service is never modelled as `protocol: other`. `listeners` record
what the database process listens on (the wildcard `*`, an IP, a hostname, or a
Unix socket path) and are not host publication, which remains
`runtime.network.published_ports`. `databases` carry typed `schemas` and
`tables`; `roles` are database-local authorization principals, not OS accounts
or top-level `accounts`; and every database, schema, table, and role has a
stable `*_id` symbol kept separate from its observed `name`, plus an `origin`
classification so engine built-ins (`template0`, `postgres`) are not mistaken
for scenario-authored objects. `grants` are typed privilege facts structured by
grantee role, target object, and privileges. `settings` carry a `provenance`
(introspection, configuration file, image default, operator override, runtime
default) and a value classification reusing the shared runtime sensitivity
vocabulary — `redacted`/`operator_secret` settings omit their raw value, so
PostgreSQL secret areas such as `primary_conninfo`, password attributes, and
TLS key material never enter the model. An application-to-database access edge
reuses the top-level `relationships` graph: the relationship endpoints resolve
to the runtime application and the database service or logical database, and a
typed `database_access` block keeps the access `role_ref` and `auth_method`
structurally validated (see
[ADR-029](../../decisions/adrs/adr-029-database-logical-state-runtime-surface.md)).

Three further typed relationship subtypes attach domain-specific access detail
to a top-level edge without re-typing the families they reference:
`forwarding_edge` (a forwarding agent's target listener role, redacted
enrollment identity, protocol, and parse format), `service_integration` (a
platform-to-engine integration's kind, direction, and API auth principal), and
`proxy_upstream` (a reverse-proxy route's upstream node/service and
TLS-termination posture, which must agree with the route's own
`upstream_target`). See
[ADR-052](../../decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md).

`runtime.dns_services` records observed DNS logical and protocol state hosted
by the node: authoritative zones, RRsets, typed common RDATA, resolver policy,
forwarders, DNSSEC validation posture, dynamic-update posture, logging posture,
bounded settings, and evidence refs. It is distinct from `Node.services`
(transport listeners such as UDP/TCP 53), `runtime.container` resolver client
options, `runtime.network` endpoint aliases/generated DNS names, HTTP
applications, filesystem evidence, and generic relationships. Each service has
a stable `dns_service_id` and optional same-node `service` ref. Zones use
stable `zone_id` values and observed DNS names. `rrsets` group records by
owner, class, type, and TTL; typed payloads exist for SOA, MX, SRV, TXT, A,
and AAAA, with target/rdata fields and an `other` + `type_code` path for
additional IANA RR types. `configuration_file_refs`, `log_file_refs`, and
`zone_file_refs` are checked against `runtime.filesystem_inventory` when that
inventory is non-empty. Fully qualified refs such as
`nodes.dns.runtime.dns_services.bind.zones.corp.rrsets.web-a` participate in
relationships, generic reference validation, and module import rewriting (see
[ADR-039](../../decisions/adrs/adr-039-dns-service-runtime-inventory.md)).

`runtime.security_monitoring_managers` records observed SIEM and
security-monitoring manager state hosted by the node: manager identity,
same-node transport ownership, listeners, manager modules/components, enrolled
agents, agent groups, detection or monitoring content sets, parsed detection
definitions, bounded settings, and evidence refs. It is distinct from
`Node.services` transport bindings, `runtime.processes` process snapshots,
`runtime.service_manager_units` lifecycle state, filesystem evidence, raw logs,
alert telemetry, and raw vendor rule/config payloads. Each manager has a stable
`security_monitoring_manager_id`; child collections use stable ids for listeners, components,
agents, groups, content sets, detection definitions, and settings.
`content_sets` is corpus/file inventory, while `detection_definitions` is the
typed manifest of loaded parsed definitions from that corpus. Detection
definitions preserve portable engine/kind, native id, source file/span,
canonical digest, loaded/parser-accepted state, level/severity, predicates,
decoder constraints, correlation refs, tags, MITRE/compliance mappings, and
optional target refs. Agent group member refs resolve to manager-local agents,
agent `group_refs` resolve to manager-local groups, setting `component_ref`
values resolve to manager-local components, detection `content_set_ref` values
resolve to manager-local content sets, and detection correlation refs resolve
to manager-local definitions. File refs and setting source paths are checked
against `runtime.filesystem_inventory` when that inventory is non-empty. Fully
qualified refs such as
`nodes.siem.runtime.security_monitoring_managers.wazuh.agents.001` participate
in relationships, generic reference validation, and module import rewriting
(see
[ADR-040](../../decisions/adrs/adr-040-security-monitoring-manager-runtime-inventory.md)
and
[ADR-045](../../decisions/adrs/adr-045-security-monitoring-detection-definition-semantics.md)).

`runtime.mail_services` records the participant-observable mail-server logical
state, distinct from transport-level `services`, host publication in
`runtime.network`, HTTP application routes, filesystem evidence, and top-level
scenario accounts. Each entry is a `RuntimeMailService` with a stable
`mail_service_id`, optional same-node `Node.services[].name` reference,
engine/version/name data, and typed child records for components, listeners,
domains, mailbox stores, mailboxes, aliases, routing rules, queues, and
settings. `listeners` bind SMTP/ESMTP, submission, IMAP/IMAPS, POP3, LMTP,
Sieve, or other mail protocols to same-node transport services and carry
advertised capabilities, banners, AUTH mechanisms, and TLS/STARTTLS posture.
`mailboxes` are service-local runtime records with address, domain/store refs,
role/status, authentication mechanisms, and credential-strength classification;
raw passwords and hashes are not representable on mailbox records. `settings`
carry provenance and source paths; explicit `redacted`/`operator_secret`
classifications omit raw values, while credential-shaped names remain scenario
content under ADR-057. Mail
client, DNS, logging/SIEM, relay, and similar edges stay in top-level
`relationships`; a typed `mail_access` block records mail protocol/auth/TLS and
mailbox/domain/listener refs when an edge needs mail-specific semantics (see
[ADR-038](../../decisions/adrs/adr-038-runtime-mail-service-logical-state.md)).

`runtime.identity_authorities` records observed directory, domain, realm,
identity-provider, cloud-IAM, authorization-system, and federation state. It is
not a provisioning command surface and it is not an Active Directory, LDAP,
SCIM, SAML, OIDC, or IAM schema clone. Each authority has a stable
`identity_authority_id`; optional namespace facts such as `domain_name`, `realm`,
`issuer`, `tenant_id`, and `base_dn`; protocol/API services that may reference
same-node `Node.services[].name` transport bindings; identity-bearing
subjects; policies; and typed relationships for membership, trust,
federation, delegation, ownership, synchronization, and association. Stable
RAES ids (`identity_authority_id`, `service_id`, `subject_id`, `policy_id`, and
`relationship_id`) are the portable reference surface and must be unique across
the owning authority's local namespace. Provider-stable object identifiers
remain observed data: use the specific field when one exists
(`distinguished_name`, `principal_name`, `service_principal_names`,
`issuer`, `tenant_id`, `base_dn`) or a bounded `attributes` entry for values
such as AD `objectGUID`/SID, LDAP `entryUUID`, SCIM `id`/`externalId`, SAML
NameID, or the OIDC `iss` + `sub` pair. Attribute and policy setting values use
the runtime sensitivity vocabulary: explicit `redacted`/`operator_secret`
classifications omit raw values, and credential-shaped names do not force
omission under ADR-057.
Local authority references resolve against all stable ids in the owning
authority; fully qualified references such as
`nodes.ad.runtime.identity_authorities.corp-domain.subjects.alice` participate
in top-level relationships, objectives, module import rewriting, and generic
reference validation (see
[ADR-032](../../decisions/adrs/adr-032-directory-domain-identity-runtime-surface.md)).

`runtime.app_authorizations` records observed application-internal
role-based access control stores — the in-app RBAC of a search cluster,
key-value store, dashboard, threat-intel platform, or case-management
application, distinct from the wire-protocol directory state in
`runtime.identity_authorities` and from database engine GRANTs in
`runtime.database_services`. Each entry is a `RuntimeAppAuthorization` with a
stable `app_authorization_id`, an open `resource_vocabulary` spine
discriminator (`index_pattern`, `cql_resource`, `redis_acl`, `app_resource`,
`unknown`, `other`) that names the resource space the store governs, and an
`auth_enabled` flag. Tier placement (storage RBAC for OpenSearch/Cassandra/Redis
versus presentation RBAC for dashboards, Cortex, Shuffle, and TheHive) is
derived from which spine references the authorization, never declared on the
model. `principals` are users, service accounts, API keys, or backend roles
with `reserved`/`hidden` flags; a principal never stores a raw bcrypt hash,
API key, or password — its credential posture is recorded purely via a
`credential_classification` (`none`, `redacted`, `operator_secret`), and a
secret-shaped principal name alone does not force a redaction classification.
`roles` are named local roles. The defining addition over a directory is the
resource-scoped `permission_grants` entry (role reference → `actions` →
`resource_patterns`) with an `allow`/`deny` effect and a `resource_kind`; the
grant's `resource_kind` is the single author-settable source of truth for the
resource vocabulary, while the authorization's `resource_vocabulary` is the
declared set validated against the grants. `role_mappings` bind backend roles,
users, or hosts onto a local role, and `tenants` model namespace scopes. An
authorization that declares a concrete (non-`unknown`) `resource_vocabulary`
must carry at least one permission grant with a matching `resource_kind`, and
`permission_grants`/`role_mappings` `role_ref` values resolve to roles declared
within the same authorization. Fully qualified refs such as
`nodes.indexer.runtime.app_authorizations.opensearch-security.roles.admin`
participate in relationships, generic reference validation, and module import
rewriting (see
[ADR-046](../../decisions/adrs/adr-046-app-authorization-runtime-inventory.md)).

`runtime.scheduled_jobs` records observed recurring scheduled jobs hosted by
the node as a cadence-plus-run-state primitive only, distinct from
`runtime.service_manager_units` (systemd-scoped lifecycle, including the
`timer` unit kind) and from the forwarding/sync inputs and outputs that belong
to the referencing forwarding agent. Each entry is a `RuntimeScheduledJob` with
a stable `scheduled_job_id`, an `enabled` flag, an optional `command_ref`, an
optional `schedule`, and an optional `run_state`. The `schedule` carries a
closed structural `kind` (`interval`, `cron`, `calendar`) and an opaque `spec`
string; the recurrence vocabulary is fixed (POSIX crontab / RFC 5545 RRULE /
fixed interval) and therefore carries neither `unknown` nor `other`. The
`run_state` records observed `last_run`/`next_run` timestamps and an open
`last_result` outcome (`success`, `failure`, `pending`, `unknown`, `other`).
Inputs, outputs, and trigger targets are intentionally absent — a bare-container
ENTRYPOINT cadence loop is encoded here, while what the loop ships is the
referencing forwarding agent's concern and an event trigger is a relationship,
not a recurrence. Fully qualified refs such as
`nodes.sync.runtime.scheduled_jobs.misp-pull` participate in relationships,
generic reference validation, and module import rewriting (see
[ADR-047](../../decisions/adrs/adr-047-scheduled-job-runtime-inventory.md)).

`runtime.datastore_services` records the participant-observable logical state of
a node's *non-relational* datastore — the OpenSearch/Elasticsearch search
cluster, the Cassandra wide-column store, and the Redis key-value store that the
irreducibly-relational `runtime.database_services` cannot shape. Each entry is a
`RuntimeDatastoreService` with a stable `datastore_service_id`, an optional
`service` referencing the owning same-node `Node.services[].name`, an open
`engine` fact, and an open `data_model` spine discriminator (`search_index`,
`wide_column`, `key_value`, `relational`, `unknown`, `other`). The discriminator
drives a required-profile guard so an under-populated instance fails validation:
a `search_index` requires at least one `partition` with `kind: index` carrying
shard/replica geometry; a search cluster may also record native UUID,
node/shard/document aggregate counts, and byte-normalized store size, while each
index partition may record native UUID, live and deleted document counts,
byte-normalized store size, creation timestamp, and open/closed status. A
`wide_column` store requires at least one `keyspace`
partition with a `replication_strategy` and `replication_factor`; and a
`key_value` store requires a `persistence` profile and rejects relational
object-tree (`keyspace`/`column_family`) partitions. `cluster`, `persistence`,
and `transport_security` are single nested postures, while `nodes`,
`partitions`, `templates`, `mappings`, and `settings` are id-bearing child
collections. `templates` and `mappings` are bounded manifests rather than raw
engine payloads: templates carry index patterns, selected settings, optional
mapping refs, digests, and evidence refs; mappings carry partition refs,
field-count/type census, dynamic policy, dynamic-template count, date-detection
posture, schema digests, and evidence refs. A concrete `search_index` service
must carry at least one structured mapping manifest. `aliases`,
`lifecycle_policies`, `ingest_pipelines`, `pubsub_channels`, `queues_streams`,
and `backup_targets` remain bare reference-name lists. Each `node` additionally
carries product-neutral engine
provenance and runtime posture (`engine_version`, `build_hash`, `build_type`,
initial/maximum `heap_init_bytes`/`heap_max_bytes` byte bounds, and
`memory_locked`), a typed per-node `plugins` inventory
(`RuntimeDatastoreEnginePlugin{plugin_id, name, version}` — retaining the
per-plugin version the former service-level `engine_plugins` list dropped), and a
typed `endpoints` inventory
(`RuntimeDatastoreNodeEndpoint{endpoint_id, role, protocol, address, port}`)
whose open `client`/`peer` role taxonomy distinguishes the participant-facing
listener from the inter-node one without naming any engine's protocol (replacing
the single ambiguous node `address`). Node plugin and endpoint ids share the
datastore service-wide stable-id namespace and are targetable as nested refs
(see
[ADR-058](../../decisions/adrs/adr-058-datastore-node-engine-provenance-and-endpoints.md)
amending ADR-048). `settings` reuse the shared runtime sensitivity
vocabulary: explicit `redacted`/`operator_secret` classifications omit raw
values, while credential-shaped setting names remain scenario content unless
the author marks the value withheld. `datatype_census` remains a key-value
datatype census and is not a search-index document count. Application-internal
RBAC is delegated to
`runtime.app_authorizations` via the string `authorization_ref` (resolved to a
same-node `app_authorization_id`), so the surface carries no embedded
principal/role/grant. Fully qualified refs such as
`nodes.indexer.runtime.datastore_services.opensearch-store.partitions.alerts-index`
and
`nodes.indexer.runtime.datastore_services.opensearch-store.mappings.alerts-mapping`
participate in relationships, generic reference validation, and module import
rewriting (see
[ADR-048](../../decisions/adrs/adr-048-datastore-service-runtime-inventory.md)).

`runtime.platform_applications` records the declared logical state of a node's
participant-visible platform application. Each entry has a stable
`platform_application_id`, an optional same-node `service` ref, product
metadata, and composable provider-neutral `capabilities`. Capability kinds are
`threat_intelligence_management`, `intelligence_exchange`, `case_management`,
`analysis_execution`, `workflow_automation`, `analytics_presentation`,
`unknown`, and `other`. One application may declare several capabilities. A
capability describes a functional role only; it does not imply a product,
configuration profile, loaded content, policy, transport binding, execution,
or completeness.

`platform_kind` and `content_objects` remain accepted as deprecated compatible
input. The former is classification only and the latter remains a bounded
manifest—typed `kind`, bounded `attributes`, typed `references`,
`marking_refs`, and `evidence_refs`, never a raw object body. Neither field
implies a capability. Within an application, all child stable ids share one
namespace; legacy content-object `references` resolve to sibling
`content_object_id` values and `marking_refs` to sibling `marking_id` values.
The string `authorization_ref` resolves to a same-node
`app_authorization_id`. Fully qualified refs such as
`nodes.tip.runtime.platform_applications.opencti.capabilities.exchange`
participate in relationships, generic reference validation, and module import
rewriting (see
[ADR-049](../../decisions/adrs/adr-049-platform-application-runtime-inventory.md)).

`runtime.forwarding_agents` records observed forwarding / intel-sync agent state
hosted by the node: the agent-side `(source, transform, ship-target, buffer)`
shipping spine that the SIEM/security-monitoring *manager* half
(`runtime.security_monitoring_managers`) and the detection-engine *consumer*
(`runtime.network_detection_engines`) cannot shape. Each entry is a
`RuntimeForwardingAgent` with a stable `forwarding_agent_id`, an open
`agent_kind` spine discriminator (`log_forwarder`, `content_sync`, `unknown`,
`other`), and typed children: `sources` (tailed path, API pull, or queue inputs),
`transforms` (`passthrough`/`parse`/`ioc_to_rule`), `ship_targets` (downstream
event-ingest and/or enrollment endpoints), an optional `buffer_policy`
(queue/back-pressure posture), `reload_channels` (downstream rule-reload sockets),
and bounded `settings`. The discriminator drives a required-profile guard:
`log_forwarder` requires a `buffer_policy` and at least one `ship_target` carrying
an ingestion endpoint and rejects any `ioc_to_rule` transform; `content_sync`
requires at least one `api_pull` source, one `ioc_to_rule` transform, and one
`reload_channel`, and rejects a `buffer_policy` and any `ship_target` enrollment
endpoint. A ship target's `target_node_ref`, when concrete, resolves to a defined
node, and a `target_service_ref` resolves to a service on the referenced node
(or, absent a node ref, on the owning node). Ship-target enrollment identities
use the closed `none`/`redacted`/`operator_secret` lattice and carry no raw value
field; forwarding settings use explicit redaction classifications to omit raw
values, not name-derived omission. Cadence composes a `runtime.scheduled_jobs` entry
and the inter-node trust edge composes a relationship forwarding edge — neither is
re-typed here. Fully qualified refs such as
`nodes.sensor.runtime.forwarding_agents.wazuh-sidecar.ship_targets.manager`
participate in relationships, generic reference validation, and module import
rewriting (see
[ADR-050](../../decisions/adrs/adr-050-forwarding-agent-runtime-inventory.md)).

Top-level `forwarding_agents` uses the same `RuntimeForwardingAgent` model for
off-node infrastructure forwarders that are not inventoried scenario nodes. A
relationship `forwarding_edge.forwarder_ref` may resolve to either registry, and
`forwarding_agent_id` values are unique across both. Because a scenario-level
agent has no owning node, any concrete `target_service_ref` on its ship target
must also name a concrete `target_node_ref`.

`runtime.orchestration_authorities` records observed container-spawn
orchestration-authority state hosted by the node: the authority to *spawn*
containers/workloads through a control interface — a SOAR orchestrator or an
analyzer engine holding `docker.sock` read-write. `RuntimeControlInterface`
(`runtime.local_control_interfaces`) types the docker.sock *shell* — a present
read-write Unix socket — but carries no field for what the holder is authorized to
*do*; this family carries the spawn contract. Each entry is a
`RuntimeOrchestrationAuthority` with a stable `orchestration_authority_id`, an open
`engine` taxonomy (`docker`/`containerd`/`podman`/`kubernetes`/`cri_o`), an optional
`scope`, typed `spawn_templates` (image + purpose), an optional `lifecycle_policy`,
typed `realized_children` (observed spawned workloads), and an open
`privilege_class` discriminator (`host_root_equivalent`, `namespaced`, `unknown`,
`other`). The `control_interface_ref` is the `control_interface_id` of a same-node
`RuntimeControlInterface` — referenced, never duplicated — and resolves at scenario
scope. The discriminator drives a required-profile guard: a `host_root_equivalent`
authority requires a concrete `control_interface_ref` (model-local), and at
scenario scope that interface must resolve to a read-write docker socket (a
read-write `unix_socket` whose path ends in `docker.sock`). Fully qualified refs
such as
`nodes.soar.runtime.orchestration_authorities.shuffle-orborus.spawn_templates.worker`
participate in relationships, generic reference validation, and module import
rewriting (see
[ADR-051](../../decisions/adrs/adr-051-orchestration-authority-runtime-inventory.md)).

`source` identifies the node's artifact by provider-neutral `name` and
`version`. When that artifact is a custom-built container image, the optional
`source.build` block records its observable build/provenance facts without
making any container engine the normative deployment model. `build` captures
the `base_image` and `base_image_digest`; the `dockerfile_path` and structured
`instructions` (typed `instruction` kind plus tokenized `arguments` — raw
recipe text is intentionally not stored, since `${...}` in shell/Dockerfile
syntax would collide with SDL variable substitution); the `layers` chain with
per-layer `digest`, `created_by`, `size`, and `empty` flag; `build_args` with a
`value_classification` so secret build arguments are redacted rather than
recorded, except for explicitly disclosed `secret_fixture` exercise values;
`copied_sources` mapping build-context `source_path` to in-image
`destination_path`; `config` recording image *defaults* (entrypoint, command,
working directory, exposed ports, native-keyed `labels`, and
`default_environment`); `source_inputs` mapping source-package inputs to
runtime destinations with optional checksums; and `attestation`, which records
attestation `status` (availability) separately from `verification` (result) so
that "no registry-visible attestation" is a distinct, falsifiable fact rather
than an inferred verification failure. Image-default `config` facts are kept
separate from runtime-effective facts under `runtime.container`; the same value
may appear in both with different meanings. See
[ADR-023](../../decisions/adrs/adr-023-container-image-build-provenance-surface.md).

---

## Infrastructure

Maps node names to deployment parameters.

```yaml
infrastructure:
  corp-switch:
    count: 1
    properties:
      cidr: 10.0.0.0/24
      gateway: 10.0.0.1
      internal: true                    # blocks internet egress
    acls:                               # network access controls (from CybORG NACLs)
      - name: allow-dmz-https
        direction: in
        from_net: dmz-switch
        protocol: tcp
        ports: [443]
        action: allow
      - name: deny-dmz-default
        direction: in
        from_net: dmz-switch
        action: deny

  web-server:
    count: 1                            # shorthand: web-server: 1
    links: [corp-switch]
    dependencies: [db-server]
    properties:                         # per-link IP assignments
      - corp-switch: 10.0.0.10
```

**Shorthand:** `web-server: 3` expands to `{count: 3}`.

`links` are switch/network connectivity references, not arbitrary infrastructure edges. If a node has attached `conditions`, its `count` must stay at `1` so the condition-to-node binding remains unambiguous. Per-link IP assignments must be valid IP addresses within the linked switch's CIDR.

ACL rule `name` is optional, but when present it must be unique within that infrastructure entry and can be targeted directly as `infrastructure.<infra>.acls.<acl_name>`.

---

## Features

Software deployed onto compute nodes. Three types: Service, Configuration, Artifact.

```yaml
features:
  nginx:
    type: Service
    source: nginx-1.24
  php-config:
    type: Configuration
    source: php-8.2-config
    dependencies: [nginx]               # deployed after nginx; cycles rejected
  log-agent:
    type: Artifact
    source: filebeat-8
    destination: /opt/filebeat
    environment: ["ELASTICSEARCH_HOST=10.0.0.5"]
```

Feature dependencies are hard same-node prerequisites at runtime. If a node
binds a feature whose declared dependency is not also bound on that same node,
runtime compilation emits a diagnostic and the plan is invalid rather than
silently ignoring the missing prerequisite.

---

## Conditions, Propositions, and Assertions

`conditions` describe executable probe implementations. They do not define
portable truth by themselves. A condition may bind to a proposition that says
what the probe observes.

```yaml
conditions:
  web-alive:
    proposition: web-alive
    command: "curl -sf http://localhost/ || exit 1"
    interval: 15
    timeout: 5
    retries: 3
    start_period: 30
  scanner:
    source: vuln-scanner-pkg            # alternative: library-based check
```

Must have either `command` + `interval` or `source`, not both.

`propositions` are backend-neutral statements about finite subjects and typed,
semantically grounded properties. Observed-state propositions name the authored
evidence requirements needed to decide them. `assertions` apply a role and
polarity to a proposition without redefining it.

```yaml
propositions:
  web-alive:
    description: The governed web service responds successfully.
    subjects: [nodes.web.services.https]
    basis: observed_state
    predicate:
      kind: boolean
      property: service-alive
      semantic_ref: urn:raes:observable:service-alive
      operator: equals
      expected: true
    evidence_requirements: [web-health-evidence]

assertions:
  web-alive-at-completion:
    proposition: web-alive
    role: postcondition
    polarity: positive
  web-alive-before-action:
    proposition: web-alive
    role: precondition
    polarity: positive
```

Portable truth outcomes are `true`, `false`, `unknown`, and `unsupported`.
`unsupported` reports an admitted capability limit; it is not a logical truth
value. Structural validity, evidence provenance, digest identity, and
behavioral equivalence remain separate claims.

---

## External classifications

Weakness and behavior classifications use standalone
[external concept bindings](../../../specs/concept-authority/external-concept-bindings.md),
not native SDL fields. See the
[migration guide](../../migration/external-classifications.md) for historical sources.
Route assertions use the exact route subject, never an implied node-level claim.

---

## Scoring: removed from the SDL

The OCR-inherited SDL scoring pipeline
(`conditions → metrics → evaluations → TLOs → goals`) and the CybORG
`agents.reward_calculator` label were removed from the authoring language by
[ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md). The
`metrics`, `evaluations`, `tlos` (Training Learning Objectives), and `goals`
sections are no longer SDL surfaces.

`conditions` remain first-class probe definitions, but backend-neutral truth is
expressed through `propositions` and role-constrained `assertions` (see
[Objectives](#objectives)). When a scenario genuinely needs a graded
score, cumulative reward, pass/fail evaluation, or a leaderboard value, that
concern lives in the experiment/evaluator plane — experiment-core contracts
(`experiment-task-v1` metric definitions, `experiment-study-v1` analysis plans;
[ADR-055](../../decisions/adrs/adr-055-experiment-core-contract-boundary.md)),
the evidence/measure contracts (`experiment-evidence-record-v1`,
`experiment-derived-measure-v1`;
[ADR-064](../../decisions/adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md)),
and the backend Evaluator
([ADR-069](../../decisions/adrs/adr-069-cage-2-replication-architecture.md)) —
never as authored SDL.

---

## Entities

Recursive team/organization hierarchy with exercise roles and OCR-style
fact maps.

```yaml
entities:
  blue-team:
    name: Blue Team
    role: Blue
    mission: Defend infrastructure
    facts:
      department: SOC
      primary-shift: nights
    entities:
      alice: {name: Alice}
      bob: {name: Bob}
  red-team:
    name: Red Team
    role: Red                           # White, Green, Red, Blue
```

Nested entities are referenced via dot-notation: `blue-team.alice`.

---

## Orchestration: Injects, Events, Scripts, Stories

```yaml
injects:
  phishing-email:
    source: phishing-pkg
    from-entity: red-team
    to-entities: [blue-team]

events:
  attack-wave:
    assertions: [scanner-ready]        # precondition assertion
    injects: [phishing-email]

scripts:
  main-timeline:
    start-time: 5 min                  # OCR units: y, mon, w, d, h, m/min, s/sec, ms, us, ns
    end-time: 2 hour
    speed: 1.0
    events:
      attack-wave: 30 min

stories:
  exercise:
    speed: 1
    scripts: [main-timeline]
```

Sub-second durations are rounded up to the nearest second, so `1 ms`,
`1 us`, and `1 ns` all parse as `1`.

---

## Content

Data placed into scenario systems. Adapted from CyRIS `copy_content`.

```yaml
content:
  phishing-emails:
    type: dataset
    target: exchange-server
    destination: /var/mail/
    format: eml
    sensitive: true
    items:
      - name: "Q3 Budget.eml"
        tags: [phishing, macro]
  flag-file:
    type: file
    target: victim
    path: /var/www/html/flag.txt
    text: "FLAG{found_it}"
  seed-data:
    type: dataset
    target: database
    source: customer-pii-seed          # large dataset via package reference
    format: sql
```

`target` is required for every content entry. Normally it references a compute node,
not a switch/network node. When ordinary node placement cannot establish
required service-owned state, `service_materialization` binds that content to a
named service on the same compute node:

```yaml
content:
  company-mail:
    type: dataset
    target: mail
    source: company-mail-corpus
    format: message-set-v1
    service_materialization:
      target_service_ref: nodes.mail.services.imap
      interface_profile: service-content
      profile_version: "1"
      requirements:
        operation: ensure-owned-items
        conflict_policy: reject-unowned-collision
        readback: canonical-content-digest
      readback_assertion_refs: [company-mail-visible]
      evidence_requirement_refs: [company-mail-readback]
      observation_boundary_refs: [participant-mail-view]
```

Search-index schema is a separate closed profile because field-schema
reconciliation has different desired state and readback from inserting owned
items:

```yaml
content:
  job-index-schema:
    type: dataset
    target: analysis
    service_materialization:
      target_service_ref: nodes.analysis.services.search
      interface_profile: service-search-index-schema
      profile_version: "1"
      requirements:
        operation: ensure-search-index-field-schema
        conflict_policy: reject-unowned-collision
        readback: canonical-portable-field-schema-digest
        field_semantics:
          key: exact-token
          status: exact-token
          relations: exact-token
      readback_assertion_refs: [job-index-schema-visible]
      evidence_requirement_refs: [job-index-schema-readback]
      observation_boundary_refs: [participant-search-view]
```

The portable semantic set also includes `full-text`, `integer`, `temporal`, and
`boolean`. Native mapping types, index names, endpoints, and queries remain in
backend-private configuration. A profile claim admits the operation; only fresh
native readback projected to the declared portable fields proves it.

The interface profile does not describe product APIs. It requires the backend
to reconcile the ordinary content through the named service, reject
unowned-item collisions, preserve declared tenant/reset ownership, and return
independent digest readback that can satisfy the observed-state postcondition
and participant projection. Backend profile support is separate from ordinary
`file`/`dataset`/`directory` support. The normative contract is
`specs/sdl/initial-service-state.md`.

`file` content requires `path`; ordinary `dataset` content requires either
`source` or non-empty `items`; the schema-only profile permits neither;
`directory` content requires `destination`.

---

## Accounts

Curated scenario/provisioning account resources within scenario nodes. Adapted
from CyRIS `add_account`.

```yaml
accounts:
  phished-user:
    username: jane
    node: workstation-01
    groups: [Users]
    password_strength: medium           # weak, medium, strong, none
    mail: jane@example.test
  app-service:
    username: appsvc
    node: web-server
    password_strength: weak
    auth_method: password               # password, key, certificate
    credential_bindings:
      - credential_id: primary-login
        purpose: primary_authentication
        auth_method: password
        material:
          classification: secret_fixture
          value: deliberately-weak-fixture
      - credential_id: operator-bootstrap
        purpose: administrative_authentication
        auth_method: certificate
        material:
          classification: operator_secret
          reference_id: operator-secret.web-bootstrap
```

`username` and `node` are required. `node` must reference a compute node, not a switch/network node.
Directory users, groups, service principals, devices, IAM roles, IdP
applications, and federation subjects belong in
`nodes.<node>.runtime.identity_authorities` when they are observed
identity-authority inventory. A top-level account may intentionally mirror one
of those subjects when the scenario needs a provisioned or participant starting
credential, but that is a second authored resource rather than the directory
model itself.

Credential bindings are nested under their owning account. Fixture literals
are deliberate authoritative scenario content; operator secrets are represented
only by safe logical references. Generic plans, snapshots, diagnostics, and
participant views are value-free unless an explicit governed participant view
authorizes disclosure of one exact fixture binding. See the normative
[account credential binding specification](../../../specs/sdl/account-credential-bindings.md).

---

## Identity Domains

Authored identity-domain realization intent. This is separate from observed
`nodes.*.runtime.identity_authorities` inventory.

```yaml
identity_domains:
  corp:
    profile: active_directory
    dns_name: corp.example
    netbios_name: CORP
    authority_account_ref: domain-admin

accounts:
  domain-admin:
    username: Administrator
    node: dc
  web-service:
    username: svc-web
    node: workstation
    spn: HTTP/workstation.corp.example
    domain_ref: corp

relationships:
  dc-role:
    type: domain_controller_for
    source: dc
    target: corp
    domain_controller: {}
  workstation-join:
    type: joins_domain
    source: workstation
    target: corp
    domain_join:
      controller_refs: [dc]
```

Every domain has a compute node controller, joins list explicit same-domain controller
candidates, the authority account lives on a controller, and domain-bound
accounts live on participating nodes. SPNs require `domain_ref`; the domain is
never inferred from the SPN or node operating system. See the
{download}`normative topology specification <../../../specs/sdl/authored-domain-topology.md>`.

---

## Relationships

Typed directed edges between any named scenario elements. Adapted from STIX Relationship SROs.

```yaml
relationships:
  exchange-auth:
    type: authenticates_with
    source: exchange-service
    target: ad-ds
  domain-trust:
    type: trusts
    source: child-domain
    target: parent-domain
    properties:
      trust_type: parent-child
      trust_direction: bidirectional
  sso:
    type: federates_with
    source: adfs
    target: azure-ad
    properties: {protocol: SAML}
  app-to-db:
    type: connects_to
    source: webapp
    target: postgres
    properties: {protocol: tcp, port: "5432"}
```

Types: `authenticates_with`, `trusts`, `federates_with`, `connects_to`,
`depends_on`, `manages`, `replicates_to`, `domain_controller_for`, and
`joins_domain`.

Relationship endpoints resolve against the scenario's named elements,
including top-level section keys, nested entity dot-paths, variables, other
relationships, content item `name` values, named service bindings
(`nodes.<node>.services.<service_name>`), runtime service listener refs
(`nodes.<node>.runtime.service_listeners.<listener_id>`), runtime
identity-authority refs
(`nodes.<node>.runtime.identity_authorities.<identity_authority_id>` and nested
`.services.<service_id>`, `.subjects.<subject_id>`, `.policies.<policy_id>`,
or `.relationships.<relationship_id>` refs), runtime DNS refs
(`nodes.<node>.runtime.dns_services.<dns_service_id>` and nested
`.zones.<zone_id>` or `.zones.<zone_id>.rrsets.<rrset_id>` refs), named
network sensor refs
(`nodes.<node>.runtime.network_sensors.<network_sensor_id>`), named
network detection-engine refs
(`nodes.<node>.runtime.network_detection_engines.<network_detection_engine_id>` and nested
`.rule_sources.<source_id>`, `.network_sets.<set_id>`,
`.output_streams.<stream_id>`, or `.control_channels.<channel_id>` refs), named
security-monitoring manager refs
(`nodes.<node>.runtime.security_monitoring_managers.<security_monitoring_manager_id>` and nested
`.listeners.<listener_id>`, `.components.<component_id>`,
`.agents.<agent_id>`, `.agent_groups.<group_id>`,
`.content_sets.<content_id>`, or `.settings.<setting_id>` refs), named datastore
service refs
(`nodes.<node>.runtime.datastore_services.<datastore_service_id>` and nested
`.nodes.<node_id>`, `.partitions.<partition_id>`, or `.settings.<setting_id>`
refs), named platform application refs
(`nodes.<node>.runtime.platform_applications.<platform_application_id>` and
nested `.capabilities.<capability_id>`, `.organizations.<organization_id>`,
`.tenants.<tenant_id>`,
`.content_objects.<content_object_id>`, `.markings.<marking_id>`,
`.upstream_bindings.<binding_id>`, `.connectors.<connector_id>`, or
`.settings.<setting_id>` refs), and named ACL
rules (`infrastructure.<infra>.acls.<acl_name>`).

Bare refs like `webapp` are valid when they are unambiguous. Any top-level section key may also be referenced explicitly as `<section>.<name>`, for example `nodes.webapp`, `features.postgres`, `accounts.db-admin`, or `infrastructure.dmz-net`. Content items may be referenced as `content.<content_name>.items.<item_name>` when a bare item `name` would collide with some other named element.

---

## Agents

Role-neutral scenario participants. Adapted from CybORG CAGE Challenge. This
section is also the SDL-authoring surface for declarative participant framing
(ACT-601, ADR-020) — it covers all five framing facets the language
guarantees: identity, role, starting conditions, authority anchors, and
operating scope.

```yaml
agents:
  red-agent:
    entity: red-team                    # identity + role (via entities.role)
    actions: [Scan, Exploit, Escalate]
    starting_accounts: [phished-user]   # references accounts section
    starting_assertions: [beacon-online-before-start]  # precondition assertion
    initial_knowledge:
      hosts: [user0]                    # known at scenario start
      subnets: [user-net]
      services: [ssh]                   # references nodes.*.services[].name
      accounts: [helpdesk-user]         # references accounts section
    authority_anchors:                  # declared bases for what the participant
      - red-team                        # may or is expected to do in scenario
      - red-controls-vm                 # meaning (entities, relationships, ...)
    allowed_subnets: [user-net, corp-net]
    operating_scope:                    # broader targetable scope beyond subnets
      - corp-net
      - user-net
    interactive_access:                 # explicit access-carrier availability
      primary-shell:                    # stable participant-local declaration id
        target_ref: user0               # compute-node ref; bare or nodes.user0
        channel: ssh                    # closed vocabulary: ssh or rdp
        account_ref: phished-user       # optional; same compute node + starting account
```

The CybORG-inherited `agents.reward_calculator` label was removed from the SDL by
[ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md): it was
an unbound free-text label that named a reward class running outside participant
perception. Reward now lives in the experiment/evaluator plane (ADR-055/064/069),
not as an authored SDL agent field.

`entity` is required and must resolve to the `entities` section; the
participant's authored identity and role both come from this binding (per
ADR-020). `initial_knowledge.hosts` references compute node names, `subnets`
references switch-backed infrastructure names, `services` references service
names declared in `nodes.*.services`, and `accounts` references entries in the
`accounts` section. `allowed_subnets` follows the same switch-backed
infrastructure rule.

`starting_assertions` lists precondition assertions, giving the authoring
surface a declarative hook for participant-relevant starting state without
equating a probe command with truth. `authority_anchors`
references any declared scenario element (entities, relationships, content,
nodes, …) that anchors what the participant is allowed or expected to do in
scenario meaning — these are SDL-level anchors, not control-plane
authentication or bearer-token identity. `operating_scope` references
targetable named scenario elements (subnets, hosts, services, content) that
define the boundary of where the participant may act or observe; it
generalises `allowed_subnets`, which remains restricted to switch-backed
infrastructure.

`interactive_access` is a keyed registry of authored access-carrier
availability. Each value is closed: `target_ref` resolves to a compute node, `channel` is
exactly `ssh` or `rdp` (or a whole-field variable before instantiation), and an
optional `account_ref` resolves to an account on that compute node that is already in the
participant's `starting_accounts`. The same concrete target/channel pair may
appear only once per participant after bare/qualified reference normalization;
different participants may declare it independently. Stable registry keys are
portable local identifiers and mapping order has no priority or fallback
meaning.

Absence means no authored interactive access. The SDL never infers this field
from OS, role, image, services, listeners, ACLs, ports, accounts, or
credentials. A declaration is not a hostname, URL, port, credential, caller
authentication rule, operating-scope grant, tool/action contract, runtime
session, or evidence that a backend realized access.

Each of `starting_assertions`, `authority_anchors`, and `operating_scope`
accepts `${var}` placeholders that resolve through the declared `variables`
section. Symbol-defining keys (agent names) remain stable identifiers and
must not be variables.

This section captures the authoring-layer guarantees of ACT-601. Broader
participant concerns — behavior semantics, visibility, trajectories,
budgets, verifier/reward — remain owned by separate ecosystem requirements
(ACT-602, ACT-606, SEM-208, ...) and are not fully represented by the `agents`
section.

Broader participant concerns are treated as first-class ecosystem surfaces,
even where the current SDL syntax does not expose their full shape. Those
concerns include:

- participant-visible tool and affordance surfaces
- participant control-context artifacts such as directives and policies
- decision-surface exposure policies describing what is visible or hidden to a
  participant
- trajectory, episode, benchmark, verifier, and reward assets
- concrete participant implementations, which remain distinct from authored
  participant intent and from backend realization

That distinction is important: the SDL describes participant intent and
scenario meaning, while processors, backends, and participant implementations
remain separate apparatus surfaces.

---

## Forwarding Agents

The top-level `forwarding_agents` list declares scenario-scoped logical
forwarders. Each element carries a stable `forwarding_agent_id`; relationship
subtypes may reference it from a `forwarding_edge`. This list is distinct from
`nodes.<node>.runtime.forwarding_agents`, which places the same logical family
on one node.

## Action Contracts

`action_contracts` describe participant-visible actions as declared behavior:
their applicability, intended and side effects, failure classes, interactions,
and fidelity basis. They do not embed runner commands or claim that a backend
can realize the action.

```yaml
action_contracts:
  inspect-portal:
    semantic_version: 1.0.0
    lifecycle_state: active
    behavioral_granularity: atomic
    procedure_basis: bounded inspection of the declared portal
    realization_profile: backend-declared
```

## Observation Boundaries

`observation_boundaries` define an information projection for a participant:
what begins observable or hidden, what may become discovered, and which evidence
supports the transition. They describe scenario meaning, not UI filtering or
control-plane authorization.

```yaml
observation_boundaries:
  red-view:
    projection_basis: participant-local view of the declared environment
    observable_refs: [content.task-brief]
    hidden_refs: [nodes.portal]
    evidence_refs: [content.terminal-output]
```

## Outcome Interpretation Rules

`outcome_interpretation_rules` state how participant action outcomes,
observations, objective results, and evidence claims are interpreted. They keep
the meaning of an observation separate from graded scoring or evaluator output.

```yaml
outcome_interpretation_rules:
  inspect-portal-outcome:
    semantic_version: 1.0.0
    participant_scope: participant_local
    observation_point_basis: inspect-portal terminal observation
    interpretation_basis: retained terminal evidence supports the local outcome
```

## Behavior Specifications

First-class participant behavior specifications name, version, and validate an
aggregate over existing participant behavior surfaces. They do not replace
`agents`, action contracts, observation boundaries, outcome interpretation
rules, authority refs, backend feature claims, or runtime evidence.

```yaml
behavior_specifications:
  red-scan-behavior:
    semantic_version: 1.0.0
    lifecycle_state: active
    participant_refs: [red-agent]
    participant_role_refs: [red]
    action_contract_refs: [scan]
    observation_boundary_refs: [red-view]
    outcome_interpretation_rule_refs: [red-outcome]
    authority_scope_refs:
      - nodes.web-server.services.https
    behavior_mode: policy-directed
    realization_profile_ref: participant-implementation-manifest:red-agent
    backend_feature_support_refs: [behavior_history]
    evidence_contract_refs: [participant-behavior-history-event-stream-v1]
    tool_affordances:
      scanner:
        tool_ref: scanner-package
        action_contract_refs: [scan]
        observation_boundary_refs: [red-view]
    extension_policy: governed-extension
    extensions:
      x-acme:review-note:
        owner: acme
        note: behavior spec reviewed for the exercise package
```

Refs fail closed: participants must resolve to declared `agents`, roles must
match roles of agent-bound entities, action contracts and observation
boundaries must resolve to their registries, outcome rules must resolve to
`outcome_interpretation_rules`, and `authority_scope_refs` must resolve to
targetable named scenario elements. `behavior_mode` is validated against the
governed `participant-decision-surface-modes` vocabulary.
External behavior classifications use standalone concept binding documents.
ATT&CK, ATLAS and NIST CSF remain optional pinned source catalogs, not governed
SDL scopes. A binding is an authored interpretation, not evidence of execution,
realization or conformance.

`tool_affordances` is a closed, participant-local mapping. Its keys identify
authored affordance bindings; each value may name one governed scenario
`content` identity and must name non-empty action-contract and observation-
boundary sets. The binding reference
`behavior_specifications.<spec>.tool_affordances.<id>` must be explicitly
classified by each referenced observation boundary. Presence means authored
availability only: visibility, apparatus support, eligibility, admission,
realization, effects, constraints, and evidence remain on their existing
contracts and do not follow from the binding.

Compiled behavior specifications use stable
`participant.behavior-specification.<name>` addresses and preserve dependency
links to the participant behavior, action contract, observation boundary, and
outcome-rule runtime addresses. Each nested affordance compiles independently
at `participant.behavior-specification.<name>.tool-affordance.<id>` with raw
refs and resolved content/action/observation addresses.

`participant_inject_deliveries` is a closed, keyed mapping for explicit
participant-directed delivery. Each binding has exactly one `participant_ref`
and preserves the original orchestration `inject_ref` plus its
`occurrence.event_ref`, `occurrence.script_ref`, and `occurrence.story_ref`.
It also names the governed source/result item, the participant's observation
boundary, a revisioned delivery policy with audience, exposure, visibility,
and disclosure bases, the fixed
`orchestration-occurrence-and-shared-time` order basis, temporal constraints,
evidence requirements, and the fail-closed `reject-no-delivery` disposition.
`external-direction` and `intervention` deliveries additionally bind a
compatible local `mixed_control` transition plus an explicit controller,
authority scope, effective order, validity interval, and control-evidence
basis; ordinary `disclosure` deliveries must not carry those fields. Admission
requires these coordinates to agree with the selected transition and target
controller state. The effective order must also fall inside the delivery's
bounded temporal constraints, and its control evidence must be covered by the
named evidence requirements.

The result item must be explicitly observable or disclosed by the named
boundary, and its visibility/disclosure bases must match the delivery policy.
The temporal and evidence declarations must bind the delivery declaration
itself. Environment-only injects remain orchestration input and do not create a
delivery implicitly. Compilation retains canonical participant, inject,
occurrence, item, boundary, time, evidence, controller, authority, order,
validity, and control-transition identities but never copies the inject body
or `environment` commands into participant metadata.
Runtime delivery, receipts, persistence, backend realization, and proof of
observation remain downstream contracts.

For `behavior_mode: mixed-control`, authors must also provide a closed
`mixed_control` declaration. It binds one controlled participant, explicit
controller states, fail-closed disposition rules, and ordered control facts.
Controller-state and transition mapping keys are portable local identifiers;
external participant, authority, scope, and evidence refs are rewritten by
module composition while local state/transition refs remain local.

```yaml
mixed_control:
  participant_ref: red-agent
  policy_revision: 1.0.0
  order_strategy: total-effective-order
  initial_state_ref: autonomous
  dispositions:
    duplicate: idempotent-if-equivalent
    stale: reject-no-state-change
    revoked: reject-no-state-change
    late: reject-no-state-change
    concurrent: order-then-revalidate
    conflict: reject-no-state-change
  controller_states:
    autonomous:
      controller_ref: self
      authority_basis_refs: [entities.red-team]
      scope_refs: [nodes.web]
      policy_revision: 1.0.0
      valid_from_order: 0
      valid_until_order: 10
      authority_status: active
      evidence_refs: [entities.red-team]
    pending:
      controller_ref: self
      authority_basis_refs: [entities.red-team]
      scope_refs: [nodes.web]
      policy_revision: 1.0.0
      valid_from_order: 10
      valid_until_order: 10
      authority_status: active
      evidence_refs: [entities.red-team]
  transitions:
    propose_supervision:
      transition_kind: proposal
      from_state_ref: autonomous
      to_state_ref: pending
      policy_revision: 1.0.0
      expected_state_revision: 0
      resulting_state_revision: 1
      effective_order: 10
      valid_from_order: 0
      valid_until_order: 10
      evidence_refs: [entities.red-team]
```

The full fixture at
`contracts/fixtures/sdl/mixed-control-v1/valid/mixed-control-participant.yaml`
shows proposal/approval flow across autonomous, pending, and supervised
states. Proposal, approval/denial, direction, intervention, handoff, override,
and cancellation remain distinct control facts. Admission, execution,
observation, wire contracts, and live histories belong to downstream runtime
surfaces.

---

## Evidence Requirements

`evidence_requirements` are portable capture obligations authored with the
scenario. They state sources, scope, trigger or boundary, channel, artifact
role, media types, handling, integrity, retention, and loss-disclosure intent.
They are not evidence records and do not prove that capture occurred.

```yaml
evidence_requirements:
  portal-trace:
    description: Retain the declared portal observation for the study.
    source_refs: [nodes.portal]
    scope_refs: [nodes.portal]
    trigger_ref: conditions.portal-online
    channel: application_log
    artifact_role: participant_observation
    media_types: [application/json]
    sensitivity: plain
    redaction: none
    integrity: checksum
    retention: study_lifetime
    loss_disclosure: required
```

Realized capture, checksums, provenance, loss reports, and derived analysis live
in processor/backend and experiment evidence contracts. They remain separate
from the authored requirement.

---

## Objectives

Declarative experiment semantics that bind actors, targets, timing, and success
criteria in the same SDL. Objective success composes invariant or postcondition
assertions over backend-neutral propositions
([ADR-079](../../decisions/adrs/adr-079-backend-neutral-proposition-and-truth-semantics.md)).

```yaml
objectives:
  red-initial-access:
    agent: red-agent                   # or: entity: red-team
    actions: [Scan, Exploit]           # should be declared on the agent
    targets:                           # any named scenario elements except variables/objectives/workflows
      - web-server
      - app-to-db
      - nodes.web-server.services.https
      - infrastructure.dmz-switch.acls.allow-dmz-https
    success:
      mode: all_of                     # all_of, any_of
      assertions: [beacon-online-achieved]
    window:
      stories: [exercise]
      scripts: [main-timeline]
      events: [attack-wave]
      workflows: [release-response]
      steps: [release-response.validate-release]

  blue-reporting:
    entity: blue-team
    success:
      assertions: [web-alive-at-completion]
    depends_on: [red-initial-access]
```

Every objective must declare exactly one actor: either `agent` or `entity`.
`success` is required and must reference at least one declared invariant or
postcondition assertion. `targets` are optional, but when present they must
resolve to named scenario elements. Bare target refs work when unambiguous;
otherwise use a qualified ref such as `nodes.web-server`, `features.app-to-db`,
or `content.mailbox.items.invoice.eml`. `window` is optional; when supplied,
referenced stories/scripts/events/workflows must exist and remain internally
consistent. Workflow steps use qualified refs of the form `<workflow>.<step>`.

`depends_on` is an ordering relation, not just commentary. It defines a partial order over objectives: downstream objectives are not considered ready until their predecessors have been satisfied. Objective dependency cycles are rejected.

This section is intentionally declarative. It says who is trying to do what, against what, during which window, and how success is interpreted. It does **not** embed backend-specific probes such as Wazuh queries or command-output checks. These objectives are scenario-local declarations; experiment-core task records live outside SDL and bind a scenario or scenario snapshot to an evaluation protocol, apparatus constraints, and study context.

---

## Workflows

Declarative control programs over SDL-defined objectives and portable workflow state. Workflows remain backend-agnostic: they express experiment control intent, retries, failure handling, and concurrency without embedding backend-native commands.

```yaml
workflows:
  release-response:
    start: validate-release
    steps:
      validate-release:
        type: objective
        objective: blue-validate-release
        on-success: branch-on-promotion
      branch-on-promotion:
        type: decision
        when:
          assertions: [rogue-release-promoted-before-branch]
        then: rollback-fanout
        else: finish
      rollback-fanout:
        type: parallel
        branches: [revoke-artifact, rollback-edge]
        join: rollback-joined
      revoke-artifact:
        type: objective
        objective: blue-revoke-artifact
        on-success: rollback-joined
      rollback-edge:
        type: objective
        objective: blue-preserve-service
        on-success: rollback-joined
      rollback-joined:
        type: join
        next: verify-rollback
      verify-rollback:
        type: decision
        when:
          steps:
            - step: revoke-artifact
              outcomes: [succeeded]
        then: finish
        else: revalidate-release
      revalidate-release:
        type: objective
        objective: blue-validate-release
        on-success: finish
      finish:
        type: end
```

Workflow step types are:

- `objective` — execute a declared objective; `on-success` is required and `on-failure` is optional. If `on-failure` is omitted, workflow execution fails terminally on objective failure.
- `decision` — branch on a declarative predicate using `then` / `else`
- `switch` — evaluate ordered `cases`, take the first matching case target, and fall back to `default` when no case predicate matches
- `retry` — re-run a declared objective until it succeeds or `max-attempts` is exhausted; `on-success` is required and `on-exhausted` is optional
- `call` — invoke another declared workflow as a reusable subflow; `workflow` and `on-success` are required, and `on-failure` is optional
- `parallel` — launch two or more branch entry steps concurrently and require all explicit branch paths to converge on a named `join` step; `on-failure` is optional
- `join` — an explicit barrier step, not a normal direct successor edge, that resumes linear control via `next` only after the owning `parallel` step has observed all branches converge
- `end` — terminal node

Compensation is step-attached and workflow-governed:

- compensable steps are `objective` and `call`
- those step kinds may declare `compensate-with: <workflow>`
- workflows may declare a `compensation:` policy with:
  - `mode: automatic | disabled`
  - `on: [failed, cancelled, timed_out]`
  - `failure_policy: fail_workflow | record_and_continue`
  - `order: reverse_completion` (the only supported ordering in v1)

Compensation targets are always declared workflows, never inline rollback step
graphs. Successful compensable steps register rollback intent, and automatic
compensation executes in reverse completion order when the primary workflow
terminates with a configured trigger.

Workflow predicates may observe:

- observable state via `conditions` and objective status via `objectives` (the OCR scoring surfaces `metrics`/`evaluations`/`tlos`/`goals` were removed by [ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md))
- prior step state via `steps`, where each entry names a prior executable step plus one or more expected outcomes (`succeeded`, `failed`, `exhausted`) and an optional `min-attempts`

Example predicate over prior step state:

```yaml
when:
  steps:
    - step: validate-release
      outcomes: [failed]
      min-attempts: 2
```

Workflow-visible step state is an immutable execution history. In v1, predicates may only inspect step outcomes and attempt counts; they may not inspect backend-specific failure classes. Step-state predicates must reference steps whose state is guaranteed to be known before the predicate executes.

After a `join`, downstream predicates may inspect executable branch steps from that fanout, but only when those steps are guaranteed on every path within their own branch before the join. Branch-local step state does not leak across sibling branches before the join, and a `parallel.on-failure` bypass does not expose abandoned branch state.

Workflow graphs remain acyclic. Every referenced step must exist, every step
must be reachable from `start`, joins must be referenced by exactly one
`parallel` step, every explicit branch path from a `parallel` step must
converge on its declared join, and workflow call graphs must also remain
acyclic. Workflow names may use canonical namespace-style dots, but workflow
step names may not because objective window refs use `<workflow>.<step>`
syntax and split on the final `.`.

Migration from the exploratory workflow syntax:

- replace `if` with `decision`
- replace `while` with `retry` when the repeated work is a single objective
- replace `next` on objective steps with required `on-success`
- replace `on-error` with `on-failure` (for `objective` / `parallel`) or `on-exhausted` (for `retry`)
- replace `parallel.next` with an explicit `join` step
- replace `step-outcomes: [step-name]` with `steps: [{step: step-name, outcomes: [...]}]`

---

## Variables

Scenario parameterization. Adapted from CACAO playbook_variables.

```yaml
variables:
  domain_name:
    type: string
    default: "corp.local"
    description: Active Directory domain name
  num_workstations:
    type: integer
    default: 5
  admin_strength:
    type: string
    default: weak
    allowed_values: [weak, medium, strong]
    required: false
```

Variables are referenced as `${var_name}` in other sections. They are **not resolved at parse time** — resolution happens at instantiation.

Full-value placeholders are currently supported in ordinary string fields,
common scalar fields (counts, booleans, scores, timings, RAM/CPU, ports), many
reference values, and selected leaf enum-backed property fields such as
`accounts.*.password_strength`, `entities.*.role`, `nodes.*.os`,
`nodes.*.asset_value.*`, `nodes.*.runtime.identity_authorities.*.kind`,
identity-authority subject/policy/relationship kinds, identity-authority ports
and enabled flags, `nodes.*.runtime.dns_services.*.implementation`, DNS
service roles, DNS zone kinds/purposes/classes, DNS record
classes/types/provenance, DNS resolver booleans and DNSSEC validation modes,
network detection-engine implementation/kind fields, parser, rule,
network-set, output, and control classifications, output booleans, rule counts, and control
capability fields,
security-monitoring manager implementation/kind fields, security-monitoring
listener/component/agent/content/setting classifications, security-monitoring
booleans and file counts, runtime service listener protocol, address-family,
scope, and provenance fields, `infrastructure.*.acls[*].action`, and
`objectives.*.success.mode`. The semantic validator checks that `${var_name}`
refers to a declared variable, and the repo-owned instantiation phase
substitutes concrete values before compilation/runtime planning. User-defined
mapping keys and discriminant/schema-shaping enum fields such as section
`type` tags still need concrete values, and placeholder keys are rejected at
parse time.

Think of variables as parameterizing **properties of declared objects**, not the object graph itself. For example, a node's hostname, a content file's text, or a subnet CIDR may be variable-backed, while top-level identifiers like `nodes.web`, `features.nginx`, or `accounts.domain-admin` must remain literal.

`default` and every entry in `allowed_values` must match the declared `type`. If `allowed_values` is provided, `default` must be one of those values.

---

## Objectives, Conditions, and Runtime Checks

The SDL carries:

- `conditions` — observable state (health checks and library-sourced checks)
- declarative objectives that bind actors, targets, windows, and success criteria expressed against observable `conditions`
- workflow graphs that branch or parallelize declared objectives without embedding runtime probe logic

The SDL carries **no** graded scoring pipeline: the OCR-inherited
`metrics`/`evaluations`/`tlos`/`goals` sections and the `agents.reward_calculator`
label were removed by
[ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md). Graded
scoring, reward, leaderboard values, and evaluation outputs live in the
experiment/evaluator plane (ADR-055/064/069).

Experiment-core task, run, apparatus-context, and study records are separate
contracts. They may reference SDL scenarios or scenario snapshots, but they are
not SDL sections.

Backend-specific auto-validation mechanics still live outside the SDL. The runtime may use Wazuh queries, command probes, file checks, or other adapters to determine whether an SDL-declared objective or observable condition has been satisfied, but those probe details are not the language itself.

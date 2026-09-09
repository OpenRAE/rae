"""Tests for SDL parsing, canonical fields, migration, and shorthands."""

from pathlib import Path

import pytest
from raes import SDLMigrationPolicy, instantiate_scenario
from raes._errors import SDLParseError, SDLValidationError
from raes.nodes import NodeType
from raes.parser import parse_sdl, parse_sdl_file


class TestKeyNormalization:
    def test_lowercase_keys(self):
        s = parse_sdl("name: test\nnodes:\n  sw:\n    type: switch")
        assert "sw" in s.nodes

    def test_uppercase_keys(self):
        """Explicit migration normalizes fields without rewriting identifiers."""
        s = parse_sdl(
            "Name: test\nNodes:\n  sw:\n    Type: Switch",
            migration_policy=SDLMigrationPolicy.ACCEPT,
        )
        assert "sw" in s.nodes
        assert s.nodes["sw"].type == NodeType.SWITCH
        assert [diagnostic.code for diagnostic in s.source_diagnostics] == [
            "sdl.noncanonical_field",
            "sdl.noncanonical_field",
            "sdl.noncanonical_field",
        ]

    def test_hyphenated_identifier_keys(self):
        sdl = """
name: test
nodes:
  vm-1:
    type: compute
    resources:
      ram: 1 gib
      cpu: 1
infrastructure:
  vm-1:
    count: 1
"""
        s = parse_sdl(sdl)
        assert "vm-1" in s.nodes

    def test_integer_keys_in_user_defined_mapping_are_rejected(self):
        # YAML lets authors write a bare ``1:`` as a key, which yaml.safe_load
        # parses as an integer. User-defined hashmap keys (node names, role
        # names, etc.) bypass the structural-field pass so the
        # integer survives until Pydantic. Closed-world ``SDLModel`` rejects
        # non-string keys; this test pins that contract so a future loosening
        # of the dict-key types (or a silent coerce-to-string) surfaces as a
        # test failure rather than a downstream cross-reference bug.
        sdl = """
name: test
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    roles:
      1: admin
"""
        with pytest.raises(SDLParseError) as excinfo:
            parse_sdl(sdl)
        assert "string" in str(excinfo.value).lower() or "type=string_type" in str(excinfo.value)

    def test_non_string_top_level_keys_are_rejected_cleanly(self):
        with pytest.raises(SDLParseError, match="top-level mapping keys must be strings"):
            parse_sdl("?")

    @pytest.mark.parametrize(
        ("sdl", "key_path"),
        [
            (
                """
name: test
variables:
  node_name:
    type: string
    default: sw
nodes:
  ${node_name}:
    type: switch
""",
                "nodes.${node_name}",
            ),
            (
                """
name: test
variables:
  node_suffix:
    type: string
    default: blue
nodes:
  web-${node_suffix}:
    type: switch
""",
                "nodes.web-${node_suffix}",
            ),
            (
                """
name: test
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    roles:
      ${role_name}: root
""",
                "nodes.vm.roles.${role_name}",
            ),
            (
                """
name: test
nodes:
  net:
    type: switch
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
infrastructure:
  net:
    count: 1
    properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}
  vm:
    count: 1
    links: [net]
    properties:
      - ${link_name}: 10.0.0.10
""",
                "infrastructure.vm.properties[0].${link_name}",
            ),
            (
                """
name: test
objectives:
  ${objective_name}:
    agent: red-agent
    success:
      assertions: [initial-access]
""",
                "objectives.${objective_name}",
            ),
        ],
    )
    def test_variable_placeholders_rejected_in_mapping_keys(self, sdl, key_path):
        with pytest.raises(SDLParseError) as caught:
            parse_sdl(sdl)
        if ".properties" in key_path:
            assert f"user-defined mapping keys: '{key_path}'" in str(caught.value)
        else:
            assert caught.value.diagnostics[0].code == "sdl.identifier.invalid"

    def test_variable_declaration_names_must_match_contract_grammar(self):
        sdl = """
name: test
variables:
  bad.name:
    type: string
    default: value
"""
        with pytest.raises(SDLParseError) as caught:
            parse_sdl(sdl)
        assert caught.value.diagnostics[0].code == "sdl.identifier.invalid"
        assert caught.value.diagnostics[0].pointer == "/variables/bad.name"


class TestShorthandExpansion:
    def test_objectives_section_parses(self):
        sdl = """
name: test
entities:
  red-team:
    role: Red
agents:
  red-agent:
    entity: red-team
    actions: [Scan, Exploit]
conditions:
  initial-access:
    command: /bin/check
    interval: 30
objectives:
  initial-access:
    agent: red-agent
    actions: [Scan]
    targets: [red-agent]
    success:
      assertions: [initial-access]
"""
        s = parse_sdl(sdl, skip_semantic_validation=True)
        assert s.objectives["initial-access"].agent == "red-agent"
        assert s.objectives["initial-access"].success.assertions == ["initial-access"]
        assert s.advisories == []

    def test_workflows_section_parses(self):
        sdl = """
name: test
entities:
  blue-team:
    role: Blue
conditions:
  release-ready:
    command: /bin/check
    interval: 30
propositions:
  release-ready:
    description: The governed release target has declared readiness state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: boolean, property: release-ready, semantic_ref: urn:raes:declared-property:release-ready, operator: equals, expected: true}
assertions:
  release-ready: {proposition: release-ready, role: postcondition, polarity: positive}
objectives:
  validate-release:
    entity: blue-team
    success:
      assertions: [release-ready]
workflows:
  release-response:
    start: validate
    steps:
      validate:
        type: objective
        objective: validate-release
        on_success: finish
      finish:
        type: end
"""
        s = parse_sdl(sdl, skip_semantic_validation=True)
        assert s.workflows["release-response"].start == "validate"
        assert "validate" in s.workflows["release-response"].steps

    def test_vm_without_resources_generates_advisory(self):
        sdl = """
name: test
nodes:
  vm:
    type: compute
"""
        s = parse_sdl(sdl)
        assert any("without 'resources'" in advisory for advisory in s.advisories)

    def test_runtime_configuration_parses_without_overloading_other_sections(self):
        sdl = """
name: shuffle-runtime-inventory
nodes:
  shuffle-backend:
    type: compute
    os: linux
    runtime:
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
          stability: volume-backed
          backend_generated: true
      filesystem_inventory:
        - path: /app/app.py
          entry_type: file
          owner_user: root
          owner_group: root
          uid: "0"
          gid: "0"
          mode: "0644"
          size: "4096"
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
          sensitivity: operator-secret
      local_control_interfaces:
        - control_interface_id: docker-sock
          path: /run/docker.sock
          kind: unix-socket
          protocol: docker
          bind_source_sensitivity: operator-secret
          access: read-write
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
          value_classification: secret-fixture
          provenance: compose
      linux_capabilities:
        required: [CAP_NET_ADMIN]
        effective: CAP_NET_ADMIN
        process_overrides:
          - subject:
              name: gunicorn
              parent_pid: 1
            scope: subtree
            drop: [cap-audit-control]
            description: interactive participant shell
      operational_policy:
        restart: unless-stopped
        resource_limits:
          memory: 512 MiB
          cpu: 0.5
          pids: 128
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
        read_only_paths: /proc/sys
        cgroup_parent: /docker
        runtime_name: runc
        init_process:
          enabled: true
          implementation: docker-init
          executable_path: /sbin/docker-init
          reaps_children: true
          argv: [/sbin/docker-init, "--", /entrypoint.sh]
        devices:
          - host_path: /dev/null
            container_path: /dev/null
            permissions: rwm
        device_cgroup_rules: c 1:3 rwm
        extra_hosts:
          - hostname: wazuh-manager
            address: 172.20.0.10
        dns: [8.8.8.8]
        dns_options: ndots:0
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
"""
        scenario = parse_sdl(sdl)
        node = scenario.nodes["shuffle-backend"]

        assert node.services == []
        assert node.runtime is not None
        assert node.runtime.mounts[0].target == "/shuffle-database"
        assert node.runtime.mounts[0].source_sensitivity == "plain"
        assert node.runtime.mounts[0].filesystem_type == "ext4"
        assert node.runtime.mounts[0].options_sensitivity == "plain"
        assert node.runtime.mounts[0].propagation == "rprivate"
        assert node.runtime.mounts[0].stability == "volume_backed"
        assert node.runtime.mounts[0].backend_generated is True
        assert node.runtime.filesystem_inventory[0].path == "/app/app.py"
        assert node.runtime.filesystem_inventory[0].entry_type == "file"
        assert node.runtime.filesystem_inventory[0].uid == 0
        assert node.runtime.filesystem_inventory[0].gid == 0
        assert node.runtime.filesystem_inventory[0].mode == "0644"
        assert node.runtime.filesystem_inventory[0].size == 4096
        assert node.runtime.filesystem_inventory[0].digest_algorithm == "sha256"
        assert node.runtime.filesystem_inventory[0].content_digest == "4f8c2d"
        assert node.runtime.filesystem_inventory[0].source_path == "src/webapp/app.py"
        assert node.runtime.filesystem_inventory[0].stability == "stable"
        assert node.runtime.filesystem_inventory[1].stability == "log"
        assert node.runtime.filesystem_inventory[1].sensitivity == "operator_secret"
        assert node.runtime.local_control_interfaces[0].path == "/run/docker.sock"
        assert node.runtime.local_control_interfaces[0].bind_source_sensitivity == "operator_secret"
        assert node.runtime.processes[0].command == ["./shufflebackend"]
        assert node.runtime.processes[1].name == "supervisord"
        assert node.runtime.processes[2].parent_pid == 1
        assert node.runtime.environment[0].name == "TECHVAULT_ADMIN_PASSWORD"
        assert node.runtime.environment[0].value_classification == "redacted"
        assert node.runtime.environment[1].value_classification == "secret_fixture"
        assert node.runtime.linux_capabilities.required == ["CAP_NET_ADMIN"]
        assert node.runtime.linux_capabilities.effective == ["CAP_NET_ADMIN"]
        overrides = node.runtime.linux_capabilities.process_overrides
        assert len(overrides) == 1
        assert overrides[0].subject.name == "gunicorn"
        assert overrides[0].subject.parent_pid == 1
        assert overrides[0].scope == "subtree"
        assert overrides[0].drop == ["CAP_AUDIT_CONTROL"]
        assert node.runtime.operational_policy.restart == "unless_stopped"
        assert node.runtime.operational_policy.resource_limits.memory == 512 * 1048576
        assert node.runtime.operational_policy.resource_limits.cpu == 0.5
        assert node.runtime.operational_policy.resource_limits.pids == 128
        assert node.runtime.container is not None
        assert node.runtime.container.entrypoint == ["/entrypoint.sh"]
        assert node.runtime.container.command == ["gunicorn", "app:app"]
        assert node.runtime.container.log_driver == "json-file"
        assert node.runtime.container.log_options == {"max-size": "10m", "max-file": "3"}
        assert node.runtime.container.namespaces.userns == "host"
        assert node.runtime.container.shm_size == 64 * 1048576
        assert node.runtime.container.masked_paths == ["/proc/acpi", "/proc/kcore"]
        assert node.runtime.container.read_only_paths == ["/proc/sys"]
        assert node.runtime.container.devices[0].container_path == "/dev/null"
        assert node.runtime.container.device_cgroup_rules == ["c 1:3 rwm"]
        assert node.runtime.container.extra_hosts[0].hostname == "wazuh-manager"
        assert node.runtime.container.dns_options == ["ndots:0"]
        assert node.runtime.container.group_add == ["adm", "101"]
        assert node.runtime.container.init_process is not None
        assert node.runtime.container.init_process.enabled is True
        assert node.runtime.container.init_process.implementation == "docker-init"
        assert node.runtime.container.init_process.executable_path == "/sbin/docker-init"
        assert node.runtime.container.init_process.reaps_children is True
        assert node.runtime.container.init_process.argv == ["/sbin/docker-init", "--", "/entrypoint.sh"]
        assert node.runtime.packages[0].manager == "apk"
        assert node.runtime.packages[0].name == "musl"
        assert node.runtime.packages[0].version == "1.2.4-r2"
        assert node.runtime.software_components[0].component_id == "shuffle-backend-app"
        assert node.runtime.software_components[0].name == "shuffle-backend"
        assert node.runtime.software_components[0].version == "1.2.3"
        assert node.runtime.software_components[0].component_type == "application"
        assert node.runtime.software_components[0].provenance == "package_manager"
        assert node.runtime.software_components[0].ecosystem == "go"
        assert node.runtime.software_components[0].purl == "pkg:golang/github.com/frikky/shuffle@1.2.3"
        assert node.runtime.software_components[0].package_manager == "apk"
        assert node.runtime.software_components[0].package_name == "shuffle-backend"
        assert node.runtime.software_components[0].package_version == "1.2.3-r0"
        assert node.runtime.software_components[0].manifest_path == "/app/go.mod"
        assert node.runtime.software_components[0].installed_paths == ["/app/shufflebackend", "/app/go.mod"]
        assert node.runtime.software_components[0].hashes[0].value == "abc123"
        assert node.runtime.dependency_manifests[0].ecosystem == "go"
        assert node.runtime.dependency_manifests[0].path == "/app/go.mod"
        assert node.runtime.dependency_manifests[0].format == "go-module"

    def test_runtime_local_identity_inventory_parses_with_canonical_keys(self):
        sdl = """
name: techvault-identity-inventory
nodes:
  techvault-webapp:
    type: compute
    os: linux
    runtime:
      local_identity:
        description: getent passwd/group capture
        users:
          - username: root
            uid: 0
            primary_gid: 0
            primary_group: root
            gecos: root
            home: /root
            shell: /bin/bash
            provenance: image
            stability: stable
          - username: www-data
            uid: 33
            primary_gid: 33
            primary_group: www-data
            home: /var/www
            shell: /usr/sbin/nologin
            supplemental_groups: [wazuh]
            no_login: true
            provenance: package
        groups:
          - name: root
            gid: 0
            members: [root]
          - name: wazuh
            gid: 101
            members: [www-data]
        sudo_rules:
          - principal: operator
            principal_kind: user
            run_as_users: [root]
            commands: ["/usr/bin/systemctl restart gunicorn"]
            nopasswd: true
"""
        scenario = parse_sdl(sdl)
        identity = scenario.nodes["techvault-webapp"].runtime.local_identity
        assert identity is not None
        assert identity.description == "getent passwd/group capture"
        assert identity.users[0].username == "root"
        assert identity.users[0].primary_gid == 0
        assert identity.users[0].provenance == "image"
        assert identity.users[1].username == "www-data"
        assert identity.users[1].no_login is True
        assert identity.users[1].supplemental_groups == ["wazuh"]
        assert identity.users[1].provenance == "package"
        assert identity.groups[1].name == "wazuh"
        assert identity.groups[1].gid == 101
        assert identity.sudo_rules[0].principal == "operator"
        assert identity.sudo_rules[0].run_as_users == ["root"]
        assert identity.sudo_rules[0].commands == ["/usr/bin/systemctl restart gunicorn"]
        assert identity.sudo_rules[0].nopasswd is True

    def test_runtime_local_identity_uid_variable_substitutes_on_instantiation(self):
        sdl = """
name: techvault-identity-variable
variables:
  svc_uid:
    type: integer
    required: true
nodes:
  techvault-webapp:
    type: compute
    os: linux
    runtime:
      local_identity:
        users:
          - username: wazuh
            uid: ${svc_uid}
            home: /var/ossec
            shell: /usr/sbin/nologin
            no_login: true
"""
        raw = parse_sdl(sdl)
        assert raw.nodes["techvault-webapp"].runtime.local_identity.users[0].uid == "${svc_uid}"
        instantiated = instantiate_scenario(raw, parameters={"svc_uid": 999})
        user = instantiated.nodes["techvault-webapp"].runtime.local_identity.users[0]
        assert user.uid == 999
        assert user.no_login is True

    def test_runtime_network_realization_parses_with_canonical_keys(self):
        sdl = """
name: techvault-network-realization
nodes:
  aptl-dmz:
    type: switch
  techvault-webapp:
    type: compute
    os: linux
    runtime:
      network:
        description: Docker network realization observed by harness inspection.
        hostname: techvault-webapp
        domainname: techvault.local
        endpoints:
          - network: aptl-dmz
            ip_address: 172.20.0.20
            ip_prefix_length: "24"
            gateway: 172.20.0.1
            mac_address: 02:42:ac:14:00:14
            aliases: [aptl-webapp, webapp]
            dns_names: [aptl-webapp, webapp]
            backend:
              driver: bridge
              ipam_driver: default
              driver_options:
                com.docker.network.bridge.name: br-dmz
              ipam_options:
                com.docker.network.driver.mtu: "1500"
        published_ports:
          - container_port: "8080"
            protocol: tcp
            host_ip: 127.0.0.1
            host_port: "8080"
infrastructure:
  aptl-dmz:
    properties:
      cidr: 172.20.0.0/24
      gateway: 172.20.0.1
"""
        scenario = parse_sdl(sdl)
        network = scenario.nodes["techvault-webapp"].runtime.network
        assert network is not None
        assert network.hostname == "techvault-webapp"
        assert network.domainname == "techvault.local"
        endpoint = network.endpoints[0]
        assert endpoint.network == "aptl-dmz"
        assert endpoint.ip_address == "172.20.0.20"
        assert endpoint.ip_prefix_length == 24
        assert endpoint.gateway == "172.20.0.1"
        assert endpoint.mac_address == "02:42:ac:14:00:14"
        assert endpoint.aliases == ["aptl-webapp", "webapp"]
        assert endpoint.dns_names == ["aptl-webapp", "webapp"]
        # Backend-native option keys are preserved verbatim as literal-map data.
        assert endpoint.backend.driver == "bridge"
        assert endpoint.backend.driver_options == {"com.docker.network.bridge.name": "br-dmz"}
        assert endpoint.backend.ipam_options == {"com.docker.network.driver.mtu": "1500"}
        binding = network.published_ports[0]
        assert binding.container_port == 8080
        assert binding.host_ip == "127.0.0.1"
        assert binding.host_port == 8080
        assert binding.protocol == "tcp"

    def test_runtime_network_ip_variable_substitutes_on_instantiation(self):
        sdl = """
name: techvault-network-variable
variables:
  webapp_ip:
    type: string
    required: true
nodes:
  aptl-dmz:
    type: switch
  techvault-webapp:
    type: compute
    os: linux
    runtime:
      network:
        endpoints:
          - network: aptl-dmz
            ip_address: ${webapp_ip}
infrastructure:
  aptl-dmz:
    properties:
      cidr: 172.20.0.0/24
      gateway: 172.20.0.1
"""
        raw = parse_sdl(sdl)
        assert raw.nodes["techvault-webapp"].runtime.network.endpoints[0].ip_address == "${webapp_ip}"
        instantiated = instantiate_scenario(raw, parameters={"webapp_ip": "172.20.0.20"})
        endpoint = instantiated.nodes["techvault-webapp"].runtime.network.endpoints[0]
        assert endpoint.ip_address == "172.20.0.20"

    def test_source_build_provenance_parses_with_canonical_keys(self):
        sdl = """
name: techvault-build-provenance
nodes:
  techvault-webapp:
    type: compute
    os: linux
    source:
      name: techvault-webapp
      version: local
      build:
        base_image: python:3.12-slim
        base_image_digest: sha256:deadbeef
        dockerfile_path: containers/webapp/Dockerfile
        instructions:
          - instruction: from
            arguments: [python:3.12-slim]
          - instruction: copy
            arguments: [webapp/app.py, /app/app.py]
        layers:
          - digest: sha256:layer1
            created_by: FROM python:3.12-slim
            size: "31000000"
          - created_by: ENV APP_HOME=/app
            empty: true
        build_args:
          - name: APP_VERSION
            value: 1.4.2
            value_classification: plain
          - name: PIP_INDEX_TOKEN
            value_classification: redacted
        copied_sources:
          - source_path: webapp/app.py
            destination_path: /app/app.py
        config:
          entrypoint: [/entrypoint.sh]
          command: [gunicorn, app:app]
          working_directory: /app
          exposed_ports: [8080/tcp]
          labels:
            org.opencontainers.image.source: https://example.test/techvault
            com.Example.Tier: webapp
          default_environment:
            - name: APP_HOME
              value: /app
        source_inputs:
          - identifier: webapp-app
            source_path: webapp/app.py
            destination_path: /app/app.py
            checksum: 4f8c2d
            checksum_algorithm: sha256
        attestation:
          status: absent
          verification: not-applicable
          attestation_type: in-toto
"""
        s = parse_sdl(sdl, skip_semantic_validation=True)
        build = s.nodes["techvault-webapp"].source.build

        assert build is not None
        assert build.base_image == "python:3.12-slim"
        assert build.dockerfile_path == "containers/webapp/Dockerfile"
        assert build.instructions[1].instruction.value == "copy"
        assert build.instructions[1].arguments == ["webapp/app.py", "/app/app.py"]
        assert build.layers[0].size == 31000000
        assert build.layers[1].empty is True
        assert build.build_args[1].value_classification.value == "redacted"
        assert build.copied_sources[0].destination_path == "/app/app.py"
        assert build.config.working_directory == "/app"
        assert build.config.exposed_ports == ["8080/tcp"]
        # Native, case-sensitive image label keys are preserved verbatim.
        assert build.config.labels == {
            "org.opencontainers.image.source": "https://example.test/techvault",
            "com.Example.Tier": "webapp",
        }
        assert build.config.default_environment[0].name == "APP_HOME"
        assert build.source_inputs[0].checksum_algorithm == "sha256"
        assert build.attestation.verification.value == "not_applicable"
        assert build.attestation.attestation_type.value == "in_toto"

    def test_source_shorthand(self):
        sdl = """
name: test
features:
  svc:
    type: service
    source: my-package
"""
        s = parse_sdl(sdl, skip_semantic_validation=True)
        assert s.features["svc"].source.name == "my-package"
        assert s.features["svc"].source.version == "*"

    def test_source_longhand(self):
        sdl = """
name: test
features:
  svc:
    type: service
    source:
      name: my-package
      version: 2.0.0
"""
        s = parse_sdl(sdl, skip_semantic_validation=True)
        assert s.features["svc"].source.version == "2.0.0"

    def test_infrastructure_count_shorthand(self):
        sdl = """
name: test
nodes:
  sw:
    type: switch
infrastructure:
  sw: 1
"""
        s = parse_sdl(sdl)
        assert s.infrastructure["sw"].count == 1

    def test_infrastructure_count_placeholder_shorthand(self):
        sdl = """
name: test
variables:
  switch_count:
    type: integer
    default: 1
nodes:
  sw:
    type: switch
infrastructure:
  sw: ${switch_count}
"""
        s = parse_sdl(sdl)
        assert s.infrastructure["sw"].count == "${switch_count}"

    def test_role_shorthand(self):
        sdl = """
name: test
nodes:
  vm:
    type: compute
    resources:
      ram: 1 gib
      cpu: 1
    roles:
      admin: "admin-user"
"""
        s = parse_sdl(sdl)
        assert s.nodes["vm"].roles["admin"].username == "admin-user"

    def test_entity_facts_keys_preserved(self):
        sdl = """
name: test
entities:
  blue-team:
    name: Blue Team
    facts:
      Department-Name: SOC
      Shift: nights
"""
        s = parse_sdl(sdl, skip_semantic_validation=True)
        assert s.entities["blue-team"].facts == {
            "Department-Name": "SOC",
            "Shift": "nights",
        }

    def test_feature_key_named_source_is_not_treated_as_source_field(self):
        sdl = """
name: test
nodes:
  web:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    roles: {admin: root}
    features:
      source: admin
features:
  source:
    type: service
    source: busybox
infrastructure:
  web: {count: 1}
"""
        s = parse_sdl(sdl, skip_semantic_validation=True)
        assert s.nodes["web"].features == {"source": "admin"}
        assert s.features["source"].source.name == "busybox"

    def test_entity_fact_key_named_source_is_not_treated_as_source_field(self):
        sdl = """
name: test
entities:
  blue-team:
    facts:
      source: internal-doc
"""
        s = parse_sdl(sdl, skip_semantic_validation=True)
        assert s.entities["blue-team"].facts == {"source": "internal-doc"}

    def test_ocr_duration_units_parse(self):
        sdl = """
name: test
events:
  phase-1: {}
scripts:
  main:
    start_time: 1 us
    end_time: 1 mon
    speed: 1
    events:
      phase-1: 1 ms
stories:
  exercise:
    scripts: [main]
"""
        s = parse_sdl(sdl)
        assert s.scripts["main"].start_time == 1
        assert s.scripts["main"].end_time == 2_592_000
        assert s.scripts["main"].events["phase-1"] == 1

    def test_leaf_enum_placeholders_parse(self):
        sdl = """
name: test
variables:
  account_strength:
    type: string
    default: strong
  host_os:
    type: string
    default: linux
  acl_action:
    type: string
    default: allow
  success_mode:
    type: string
    default: any_of
  team_role:
    type: string
    default: blue
nodes:
  net:
    type: switch
  vm:
    type: compute
    os: ${host_os}
    resources: {ram: 1 gib, cpu: 1}
infrastructure:
  net:
    count: 1
    properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}
    acls:
      - {name: allow-admin, direction: in, from_net: net, action: "${acl_action}"}
  vm:
    count: 1
    links: [net]
entities:
  blue-team:
    role: ${team_role}
accounts:
  admin:
    username: admin
    node: vm
    password_strength: ${account_strength}
conditions:
  release-ready:
    command: /bin/check
    interval: 30
propositions:
  release-ready:
    description: The governed release target has declared readiness state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: boolean, property: release-ready, semantic_ref: urn:raes:declared-property:release-ready, operator: equals, expected: true}
assertions:
  release-ready: {proposition: release-ready, role: postcondition, polarity: positive}
objectives:
  review:
    entity: blue-team
    success:
      mode: ${success_mode}
      assertions: [release-ready]
"""
        s = parse_sdl(sdl)
        assert s.nodes["vm"].os == "${host_os}"
        assert s.infrastructure["net"].acls[0].action == "${acl_action}"
        assert s.entities["blue-team"].role == "${team_role}"
        assert s.accounts["admin"].password_strength == "${account_strength}"
        assert s.objectives["review"].success.mode == "${success_mode}"

    def test_negative_numeric_duration_rejected(self):
        sdl = """
name: test
events:
  phase-1: {}
scripts:
  main:
    start_time: -5
    end_time: 10
    speed: 1
    events:
      phase-1: 1
stories:
  exercise:
    scripts: [main]
"""
        with pytest.raises(SDLParseError) as caught:
            parse_sdl(sdl)
        assert caught.value.diagnostics[0].code == "sdl.model.invalid"
        assert caught.value.diagnostics[0].pointer == "/scripts/main/start_time"


class TestFormat:
    def test_ocr_format(self):
        s = parse_sdl("name: test\nnodes:\n  sw:\n    type: switch")
        assert s.name == "test"

    def test_switch_rejects_vm_only_fields(self):
        sdl = """
name: test
nodes:
  sw:
    type: switch
    os: linux
    services:
      - port: 80
        name: http
"""
        with pytest.raises(SDLParseError) as caught:
            parse_sdl(sdl)
        assert caught.value.diagnostics[0].code == "sdl.model.invalid"
        assert caught.value.diagnostics[0].pointer == "/nodes/sw"

    @pytest.mark.parametrize(
        "field_name",
        [
            "nodes.vm.type",
            "features.svc.type",
            "content.seed.type",
            "relationships.r1.type",
            "variables.v1.type",
        ],
    )
    def test_discriminant_enums_reject_placeholders(self, field_name):
        sdl_by_field = {
            "nodes.vm.type": """
name: test
nodes:
  vm:
    type: ${node_kind}
""",
            "features.svc.type": """
name: test
features:
  svc:
    type: ${feature_type}
""",
            "content.seed.type": """
name: test
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
content:
  seed:
    type: ${content_type}
    target: vm
""",
            "relationships.r1.type": """
name: test
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
relationships:
  r1:
    type: ${relationship_type}
    source: vm
    target: vm
""",
            "variables.v1.type": """
name: test
variables:
  v1:
    type: ${variable_type}
    default: hello
""",
        }
        with pytest.raises(SDLParseError) as caught:
            parse_sdl(sdl_by_field[field_name], skip_semantic_validation=True)
        assert caught.value.diagnostics[0].code == "sdl.model.invalid"
        assert caught.value.diagnostics[0].pointer == "/" + field_name.replace(".", "/")

    @pytest.mark.parametrize(
        ("sdl", "message"),
        [
            (
                """
name: test
content:
  c1:
    type: file
""",
                "Content requires 'target'",
            ),
            (
                """
name: test
accounts:
  a1:
    username: admin
""",
                "Account requires 'node'",
            ),
            (
                """
name: test
agents:
  red-agent:
    actions: [Scan]
""",
                "Agent requires 'entity'",
            ),
        ],
    )
    def test_extension_sections_reject_missing_anchor_fields(self, sdl, message):
        with pytest.raises(SDLParseError) as caught:
            parse_sdl(sdl)
        assert caught.value.diagnostics[0].code == "sdl.model.invalid"
        assert caught.value.diagnostics[0].pointer.startswith(
            {"Content requires 'target'": "/content/c1", "Account requires 'node'": "/accounts/a1"}.get(
                message,
                "/agents/red-agent",
            )
        )


class TestErrorHandling:
    def test_empty_content(self):
        with pytest.raises(SDLParseError, match="empty"):
            parse_sdl("")

    def test_invalid_yaml(self):
        with pytest.raises(SDLParseError, match="YAML"):
            parse_sdl(":::invalid")

    def test_non_mapping(self):
        with pytest.raises(SDLParseError, match="mapping"):
            parse_sdl("- just\n- a\n- list")

    def test_no_identity(self):
        with pytest.raises(SDLParseError, match="name"):
            parse_sdl("description: no name or metadata")


class TestSkipSemanticValidation:
    def test_structural_only(self):
        """skip_semantic_validation=True skips cross-reference checks."""
        s = parse_sdl(
            "name: test\nentities:\n  blue:\n    role: blue\n"
            "objectives:\n  obj:\n    entity: blue\n    success:\n"
            "      assertions:\n        - missing-assertion",
            skip_semantic_validation=True,
        )
        assert "obj" in s.objectives


class TestModuleImports:
    def test_parse_sdl_rejects_imports_without_file_context(self):
        with pytest.raises(SDLParseError, match="parse_sdl_file"):
            parse_sdl(
                """
                name: root
                imports:
                  - path: common.yaml
                    namespace: common
                """
            )

    def test_parse_sdl_file_expands_namespaced_imports(self, tmp_path: Path):
        imported = tmp_path / "common.yaml"
        imported.write_text(
            """
name: common
version: 1.2.0
module:
  id: raes/common
  version: 1.2.0
  exports:
    nodes: [vm]
    conditions: [health]
    propositions: [health]
    assertions: [health]
    entities: [blue]
    objectives: [validate]
    workflows: [response]
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles:
      ops:
        username: operator
conditions:
  health:
    command: /bin/true
    interval: 15
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
entities:
  blue:
    role: blue
objectives:
  validate:
    entity: blue
    success:
      assertions: [health]
workflows:
  response:
    start: run
    steps:
      run:
        type: objective
        objective: validate
        on_success: finish
      finish:
        type: end
""",
            encoding="utf-8",
        )
        root = tmp_path / "root.yaml"
        root.write_text(
            """
name: root
imports:
  - path: common.yaml
    namespace: shared
    version: 1.2.0
""",
            encoding="utf-8",
        )

        scenario = parse_sdl_file(root)

        assert "shared.vm" in scenario.nodes
        assert "shared.health" in scenario.conditions
        assert "shared.validate" in scenario.objectives
        assert "shared.response" in scenario.workflows

    def test_parse_sdl_file_namespaces_named_qualified_refs(self, tmp_path: Path):
        # Composition must rewrite section-qualified named refs
        # (e.g. ``nodes.vm``, ``content.docs.items.playbook``) the same way
        # it rewrites bare names; the named-ref index added in #70 covers
        # both forms. The pre-existing relationship and objective rewrite
        # paths benefit from this fix too. Without it, importing a module
        # whose author uses a qualified ref leaves the ref pointing at a
        # nonexistent (or accidentally root-scoped) element after
        # namespacing.
        imported = tmp_path / "common.yaml"
        imported.write_text(
            """
name: common
version: 1.2.0
module:
  id: raes/common
  version: 1.2.0
  exports:
    nodes: [vm, net]
    infrastructure: [vm, net]
    entities: [blue]
    conditions: [health]
    propositions: [health]
    assertions: [health]
    content: [docs]
    relationships: [blue-controls-vm]
    agents: [blue-agent]
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    services:
      - name: ssh
        port: 22
    roles:
      ops:
        username: operator
  net:
    type: switch
infrastructure:
  net:
    count: 1
    properties:
      cidr: 10.0.0.0/24
      gateway: 10.0.0.1
  vm:
    count: 1
    links: [net]
entities:
  blue:
    role: blue
conditions:
  health:
    command: /bin/true
    interval: 15
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: precondition, polarity: positive}
content:
  docs:
    type: dataset
    target: vm
    items:
      - name: playbook
relationships:
  blue-controls-vm:
    type: manages
    source: entities.blue
    target: nodes.vm
agents:
  blue-agent:
    entity: blue
    starting_assertions: [health]
    authority_anchors: [entities.blue, content.docs.items.playbook]
    allowed_subnets: [net]
    operating_scope: [nodes.vm, infrastructure.net, nodes.vm.services.ssh]
""",
            encoding="utf-8",
        )
        root = tmp_path / "root.yaml"
        root.write_text(
            """
name: root
imports:
  - path: common.yaml
    namespace: shared
    version: 1.2.0
""",
            encoding="utf-8",
        )

        scenario = parse_sdl_file(root)

        agent = scenario.agents["shared.blue-agent"]
        assert agent.starting_assertions == ["shared.health"]
        assert agent.authority_anchors == ["entities.shared.blue", "content.shared.docs.items.playbook"]
        assert agent.operating_scope == [
            "nodes.shared.vm",
            "infrastructure.shared.net",
            "nodes.shared.vm.services.ssh",
        ]
        rel = scenario.relationships["shared.blue-controls-vm"]
        assert rel.source == "entities.shared.blue"
        assert rel.target == "nodes.shared.vm"

    def test_parse_sdl_file_namespaces_agent_participant_framing_fields(self, tmp_path: Path):
        # ACT-601 / ADR-020: Agent.starting_assertions, .authority_anchors, and
        # .operating_scope are semantic references and must be rewritten by the
        # module composition pass when their imported targets are namespaced;
        # otherwise an `agent.starting_assertions: [health]` from a root
        # scenario silently breaks (or, worse, accidentally binds to a same-
        # named root element) once the imported `conditions: health` becomes
        # `shared.health`.
        imported = tmp_path / "common.yaml"
        imported.write_text(
            """
name: common
version: 1.2.0
module:
  id: raes/common
  version: 1.2.0
  exports:
    nodes: [vm, net]
    infrastructure: [vm, net]
    entities: [blue]
    conditions: [health]
    propositions: [health]
    assertions: [health]
    relationships: [blue-controls-vm]
    agents: [blue-agent]
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    roles:
      ops:
        username: operator
  net:
    type: switch
infrastructure:
  net:
    count: 1
    properties:
      cidr: 10.0.0.0/24
      gateway: 10.0.0.1
  vm:
    count: 1
    links: [net]
entities:
  blue:
    role: blue
conditions:
  health:
    command: /bin/true
    interval: 15
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: precondition, polarity: positive}
relationships:
  blue-controls-vm:
    type: manages
    source: blue
    target: vm
agents:
  blue-agent:
    entity: blue
    starting_assertions: [health]
    authority_anchors: [blue, blue-controls-vm]
    allowed_subnets: [net]
    operating_scope: [vm, net]
""",
            encoding="utf-8",
        )
        root = tmp_path / "root.yaml"
        root.write_text(
            """
name: root
imports:
  - path: common.yaml
    namespace: shared
    version: 1.2.0
""",
            encoding="utf-8",
        )

        scenario = parse_sdl_file(root)

        agent = scenario.agents["shared.blue-agent"]
        assert agent.starting_assertions == ["shared.health"]
        assert agent.authority_anchors == ["shared.blue", "shared.blue-controls-vm"]
        assert agent.operating_scope == ["shared.vm", "shared.net"]
        # Semantic validation has already run as part of parse_sdl_file; if the
        # rewrite path were missing, validator would have raised on the
        # now-bare names that no longer exist after namespacing.

    def test_parse_sdl_file_rejects_version_mismatch(self, tmp_path: Path):
        imported = tmp_path / "common.yaml"
        imported.write_text(
            """
name: common
version: 2.0.0
module:
  id: raes/common
  version: 2.0.0
  exports:
    nodes: [sw]
nodes:
  sw:
    type: switch
""",
            encoding="utf-8",
        )
        root = tmp_path / "root.yaml"
        root.write_text(
            """
name: root
imports:
  - path: common.yaml
    namespace: common
    version: 1.0.0
""",
            encoding="utf-8",
        )

        with pytest.raises(SDLParseError, match="requested version"):
            parse_sdl_file(root)

    def test_parse_sdl_file_rejects_namespace_collisions(self, tmp_path: Path):
        first = tmp_path / "first.yaml"
        first.write_text(
            """
name: shared
version: 1.0.0
module:
  id: raes/first
  version: 1.0.0
  exports:
    nodes: [vm]
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
""",
            encoding="utf-8",
        )
        second = tmp_path / "second.yaml"
        second.write_text(
            """
name: shared
version: 1.0.0
module:
  id: raes/second
  version: 1.0.0
  exports:
    nodes: [vm]
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
""",
            encoding="utf-8",
        )
        root = tmp_path / "root.yaml"
        root.write_text(
            """
name: root
imports:
  - path: first.yaml
    namespace: shared
  - path: second.yaml
    namespace: shared
""",
            encoding="utf-8",
        )

        with pytest.raises(SDLParseError, match="collides"):
            parse_sdl_file(root)

    def test_parse_sdl_file_rewrites_database_and_application_relationship_refs(self, tmp_path: Path):
        # End-to-end composition: the relationship's source (a runtime
        # application ref) and target (a database service ref) must survive
        # module namespacing. Without `_nested_node_application_aliases` /
        # `_nested_node_database_aliases` being consumed by composition's
        # relationship rewrite, the refs would point at the un-namespaced
        # nodes and fail semantic validation on the composed scenario
        # (ADR-027 §2).
        imported = tmp_path / "shared-db.yaml"
        imported.write_text(
            """
name: shared-db
version: 1.0.0
module:
  id: raes/shared-db
  version: 1.0.0
  exports:
    nodes: [db, web]
    relationships: [webapp-to-db]
nodes:
  db:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    services:
      - {port: 5432, name: pg}
    runtime:
      database_services:
        - database_service_id: tv-pg
          service: pg
          engine: postgresql
          protocol: postgresql
          databases:
            - {database_id: tv, name: techvault}
          roles:
            - {role_id: app, name: techvault}
  web:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    services:
      - {port: 8080, name: http}
    runtime:
      applications:
        - {application_id: webapp, service: http}
relationships:
  webapp-to-db:
    type: connects_to
    source: nodes.web.runtime.applications.webapp
    target: nodes.db.runtime.database_services.tv-pg
    database_access: {role_ref: app, auth_method: scram_sha_256}
""",
            encoding="utf-8",
        )
        root = tmp_path / "root.yaml"
        root.write_text(
            """
name: root
imports:
  - path: shared-db.yaml
    namespace: shared
    version: 1.0.0
""",
            encoding="utf-8",
        )

        scenario = parse_sdl_file(root)

        rel = scenario.relationships["shared.webapp-to-db"]
        assert rel.source == "nodes.shared.web.runtime.applications.webapp"
        assert rel.target == "nodes.shared.db.runtime.database_services.tv-pg"
        # ``role_ref`` is service-local and intentionally not rewritten.
        assert rel.database_access.role_ref == "app"


class TestLoadRealScenarios:
    """RAES legacy scenario YAMLs use the metadata format which is no
    longer part of the SDL. These are expected to fail until the
    scenario YAMLs are migrated to SDL format."""

    @pytest.fixture
    def scenarios_dir(self):
        from pathlib import Path

        d = Path("scenarios")
        if not d.exists():
            pytest.skip("scenarios/ directory not found")
        return d

    @pytest.mark.xfail(reason="Legacy RAES scenario format not supported after SDL cleanup")
    def test_all_scenarios_parse(self, scenarios_dir):
        from raes.parser import parse_sdl_file

        for path in sorted(scenarios_dir.glob("*.yaml")):
            scenario = parse_sdl_file(path)
            assert scenario.name


class TestRuntimeApplicationParsing:
    def test_runtime_application_surface_parses_with_canonical_keys(self):
        sdl = """
name: techvault-application-surface
nodes:
  techvault-webapp:
    type: compute
    os: linux
    services:
      - port: 8080
        name: techvault-http
    runtime:
      applications:
        - application_id: techvault-webapp
          service: techvault-http
          protocol: http
          base_path: /
          framework: flask
          routes:
            - route_id: login
              path: /login
              methods: [get, post]
              auth_required: false
              session_required: false
              parameters:
                - name: username
                  location: form
                  required: true
              responses:
                - status_code: "200"
                  content_type: text/html
              redirects:
                - target: /dashboard
                  status_code: "302"
"""
        scenario = parse_sdl(sdl)
        applications = scenario.nodes["techvault-webapp"].runtime.applications
        assert len(applications) == 1
        surface = applications[0]
        assert surface.application_id == "techvault-webapp"
        assert surface.service == "techvault-http"
        assert surface.base_path == "/"
        route = surface.routes[0]
        assert route.route_id == "login"
        assert route.methods == ["GET", "POST"]
        assert route.auth_required is False
        assert route.parameters[0].name == "username"
        assert route.responses[0].status_code == 200
        assert route.redirects[0].status_code == 302

    def test_runtime_application_auth_variable_substitutes_on_instantiation(self):
        sdl = """
name: techvault-application-variable
variables:
  login_auth:
    type: boolean
    required: true
nodes:
  techvault-webapp:
    type: compute
    os: linux
    runtime:
      applications:
        - application_id: techvault-webapp
          routes:
            - route_id: login
              path: /login
              methods: [GET]
              auth_required: ${login_auth}
"""
        raw = parse_sdl(sdl)
        route = raw.nodes["techvault-webapp"].runtime.applications[0].routes[0]
        assert route.auth_required == "${login_auth}"
        instantiated = instantiate_scenario(raw, parameters={"login_auth": True})
        route = instantiated.nodes["techvault-webapp"].runtime.applications[0].routes[0]
        assert route.auth_required is True


class TestRuntimeSshServerParsing:
    def test_ssh_server_configuration_parses_with_canonical_keys(self):
        sdl = """
name: techvault-ssh-surface
nodes:
  techvault-kali:
    type: compute
    os: linux
    services:
      - port: 22
        name: ssh
    runtime:
      ssh_servers:
        - ssh_server_id: sshd-default
          service: ssh
          accept_env: [APTL_SESSION_ID, APTL_RUN_ID, APTL_TRACE_ID]
          password_authentication: false
          pubkey_authentication: true
          permit_tty: true
          allow_users: [kali]
          authentication_methods: [publickey]
          chroot_directory: /var/empty
          authorized_keys_file: /etc/ssh/authorized_keys.d/%u
          match_rules:
            - match_id: m-kali
              criteria:
                - kind: user
                  pattern: kali
              forced_command:
                command_kind: absolute_path
                command: /usr/local/bin/aptl-wrap-shell.sh
              permit_tty: true
"""
        scenario = parse_sdl(sdl)
        ssh_servers = scenario.nodes["techvault-kali"].runtime.ssh_servers
        assert len(ssh_servers) == 1
        server = ssh_servers[0]
        assert server.ssh_server_id == "sshd-default"
        assert server.service == "ssh"
        assert server.accept_env == ["APTL_SESSION_ID", "APTL_RUN_ID", "APTL_TRACE_ID"]
        assert server.password_authentication is False
        assert server.pubkey_authentication is True
        assert server.permit_tty is True
        assert server.allow_users == ["kali"]
        assert server.authentication_methods == ["publickey"]
        assert server.chroot_directory == "/var/empty"
        assert server.authorized_keys_file == "/etc/ssh/authorized_keys.d/%u"
        assert len(server.match_rules) == 1
        rule = server.match_rules[0]
        assert rule.match_id == "m-kali"
        assert rule.criteria[0].pattern == "kali"
        assert rule.forced_command is not None
        assert rule.forced_command.command == "/usr/local/bin/aptl-wrap-shell.sh"
        assert rule.permit_tty is True

    def test_ssh_server_accept_env_scalar_coerces_to_list(self):
        sdl = """
name: techvault-ssh-scalar
nodes:
  techvault-kali:
    type: compute
    os: linux
    services:
      - port: 22
        name: ssh
    runtime:
      ssh_servers:
        - ssh_server_id: sshd-default
          service: ssh
          accept_env: APTL_SESSION_ID
"""
        scenario = parse_sdl(sdl)
        server = scenario.nodes["techvault-kali"].runtime.ssh_servers[0]
        assert server.accept_env == ["APTL_SESSION_ID"]

    def test_ssh_server_chroot_directory_variable_substitutes_on_instantiation(self):
        sdl = """
name: techvault-ssh-variable
variables:
  chroot_path:
    type: string
    required: true
nodes:
  techvault-kali:
    type: compute
    os: linux
    services:
      - port: 22
        name: ssh
    runtime:
      ssh_servers:
        - ssh_server_id: sshd-default
          service: ssh
          chroot_directory: ${chroot_path}
"""
        raw = parse_sdl(sdl)
        server = raw.nodes["techvault-kali"].runtime.ssh_servers[0]
        assert server.chroot_directory == "${chroot_path}"
        instantiated = instantiate_scenario(raw, parameters={"chroot_path": "/var/empty"})
        server = instantiated.nodes["techvault-kali"].runtime.ssh_servers[0]
        assert server.chroot_directory == "/var/empty"

    def test_ssh_server_variable_ref_server_id_rejected_on_instantiation(self):
        from raes._errors import SDLInstantiationError

        sdl = """
name: techvault-ssh-bad-id
variables:
  server_id:
    type: string
    required: true
nodes:
  techvault-kali:
    type: compute
    os: linux
    services:
      - port: 22
        name: ssh
    runtime:
      ssh_servers:
        - ssh_server_id: ${server_id}
          service: ssh
"""
        # The parse step itself should reject a variable-ref symbol-defining identifier
        # because RuntimeSshServer.ssh_server_id rejects variable refs at model validation time.
        with pytest.raises((SDLParseError, SDLInstantiationError)):
            parse_sdl(sdl)


class TestRuntimeIdentityAuthorityParsing:
    def test_identity_authority_surface_parses_with_canonical_keys(self):
        sdl = """
name: techvault-directory-identity
nodes:
  ad:
    type: compute
    os: windows
    services:
      - {port: 389, name: ldap}
      - {port: 88, name: kerberos}
    runtime:
      identity_authorities:
        - identity_authority_id: techvault-domain
          kind: domain
          name: TechVault Domain
          namespace: techvault.local
          domain_name: TECHVAULT
          realm: TECHVAULT.LOCAL
          base_dn: DC=techvault,DC=local
          services:
            - service_id: ldap-endpoint
              service: ldap
              protocol: LDAP
              address: dc.techvault.local
              port: "389"
          subjects:
            - subject_id: alice
              kind: user
              name: alice
              principal_name: alice@TECHVAULT.LOCAL
              distinguished_name: CN=Alice,CN=Users,DC=techvault,DC=local
              enabled: true
              attributes:
                - name: department
                  values: security
            - subject_id: domain-admins
              kind: group
              name: Domain Admins
            - subject_id: ldap-svc
              kind: service-principal
              name: ldap
              service_principal_names: [LDAP/dc.techvault.local]
          relationships:
            - relationship_id: alice-admin
              relationship_type: member-of
              source_ref: alice
              target_ref: domain-admins
          policies:
            - policy_id: default-password-policy
              policy_kind: password
              name: Default Domain Policy
              applies_to_refs: [techvault-domain]
              settings:
                - name: min_length
                  values: "14"
"""
        scenario = parse_sdl(sdl)
        authority = scenario.nodes["ad"].runtime.identity_authorities[0]
        assert authority.identity_authority_id == "techvault-domain"
        assert authority.domain_name == "TECHVAULT"
        assert authority.services[0].service_id == "ldap-endpoint"
        assert authority.services[0].port == 389
        assert authority.subjects[0].principal_name == "alice@TECHVAULT.LOCAL"
        assert authority.subjects[0].attributes[0].values == ["security"]
        assert authority.subjects[2].service_principal_names == ["LDAP/dc.techvault.local"]
        assert authority.relationships[0].target_ref == "domain-admins"
        assert authority.policies[0].settings[0].values == ["14"]

    def test_identity_authority_value_fields_substitute_on_instantiation(self):
        sdl = """
name: techvault-directory-variable
variables:
  tenant_id:
    type: string
    required: true
nodes:
  idp:
    type: compute
    os: linux
    runtime:
      identity_authorities:
        - identity_authority_id: techvault-idp
          kind: identity-provider
          namespace: https://idp.techvault.local
          tenant_id: ${tenant_id}
"""
        raw = parse_sdl(sdl)
        authority = raw.nodes["idp"].runtime.identity_authorities[0]
        assert authority.tenant_id == "${tenant_id}"
        instantiated = instantiate_scenario(raw, parameters={"tenant_id": "tenant-123"})
        authority = instantiated.nodes["idp"].runtime.identity_authorities[0]
        assert authority.tenant_id == "tenant-123"

    def test_identity_authority_service_ref_must_resolve_to_same_node_service(self):
        sdl = """
name: bad-directory-service-ref
nodes:
  ad:
    type: compute
    os: windows
    services:
      - {port: 389, name: ldap}
    runtime:
      identity_authorities:
        - identity_authority_id: techvault-domain
          services:
            - service_id: ldap-endpoint
              service: missing-ldap
              protocol: ldap
"""
        with pytest.raises(SDLValidationError, match="references undefined service 'missing-ldap'"):
            parse_sdl(sdl)

    def test_identity_authority_relationship_refs_must_resolve_inside_authority(self):
        sdl = """
name: bad-directory-relationship-ref
nodes:
  ad:
    type: compute
    os: windows
    runtime:
      identity_authorities:
        - identity_authority_id: techvault-domain
          subjects:
            - {subject_id: domain-admins, kind: group, name: Domain Admins}
          relationships:
            - relationship_id: alice-admin
              relationship_type: member-of
              source_ref: alice
              target_ref: domain-admins
"""
        with pytest.raises(SDLValidationError, match="source_ref 'alice' does not resolve"):
            parse_sdl(sdl)

    def test_identity_authority_policy_applies_to_ref_must_resolve_inside_authority(self):
        sdl = """
name: bad-policy-ref
nodes:
  ad:
    type: compute
    os: windows
    runtime:
      identity_authorities:
        - identity_authority_id: techvault-domain
          policies:
            - policy_id: default-policy
              applies_to_refs: [missing-subject]
"""
        with pytest.raises(SDLValidationError, match="applies_to_ref 'missing-subject' does not resolve"):
            parse_sdl(sdl)

    def test_identity_authority_local_refs_include_stable_service_and_relationship_ids(self):
        sdl = """
name: directory-local-refs
nodes:
  ad:
    type: compute
    os: windows
    services:
      - {port: 389, name: ldap}
    runtime:
      identity_authorities:
        - identity_authority_id: techvault-domain
          services:
            - service_id: ldap-endpoint
              service: ldap
              protocol: ldap
          subjects:
            - {subject_id: alice, kind: user, name: alice}
            - {subject_id: domain-admins, kind: group, name: Domain Admins}
          relationships:
            - relationship_id: alice-admin
              relationship_type: member-of
              source_ref: alice
              target_ref: domain-admins
            - relationship_id: ldap-documents-membership
              relationship_type: associated
              source_ref: ldap-endpoint
              target_ref: alice-admin
          policies:
            - policy_id: ldap-audit-policy
              policy_kind: other
              applies_to_refs: [ldap-endpoint, alice-admin]
"""
        authority = parse_sdl(sdl).nodes["ad"].runtime.identity_authorities[0]

        assert authority.relationships[1].source_ref == "ldap-endpoint"
        assert authority.relationships[1].target_ref == "alice-admin"
        assert authority.policies[0].applies_to_refs == ["ldap-endpoint", "alice-admin"]

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("authority", "service"),
            ("authority", "subject"),
            ("authority", "policy"),
            ("authority", "relationship"),
            ("service", "subject"),
            ("service", "policy"),
            ("service", "relationship"),
            ("subject", "policy"),
            ("subject", "relationship"),
            ("policy", "relationship"),
        ],
    )
    def test_identity_authority_local_ref_ids_must_be_unique_across_id_families(self, left, right):
        authority_id = "shared" if "authority" in (left, right) else "techvault-domain"
        service_id = "shared" if "service" in (left, right) else "ldap-endpoint"
        subject_id = "shared" if "subject" in (left, right) else "alice"
        policy_id = "shared" if "policy" in (left, right) else "default-policy"
        relationship_id = "shared" if "relationship" in (left, right) else "alice-external"
        sdl = f"""
name: ambiguous-directory-local-ref
nodes:
  ad:
    type: compute
    os: windows
    runtime:
      identity_authorities:
        - identity_authority_id: {authority_id}
          services:
            - service_id: {service_id}
              protocol: ldap
          subjects:
            - subject_id: {subject_id}
              kind: user
              name: alice
          relationships:
            - relationship_id: {relationship_id}
              relationship_type: associated
              source_ref: {subject_id}
              external_target: external.example
          policies:
            - policy_id: {policy_id}
              applies_to_refs: [{subject_id}]
"""
        with pytest.raises(SDLParseError) as caught:
            parse_sdl(sdl)
        assert caught.value.diagnostics[0].code == "sdl.model.invalid"
        assert caught.value.diagnostics[0].pointer == "/nodes/ad/runtime/identity_authorities/0"

    def test_imported_identity_authority_refs_survive_module_namespacing(self, tmp_path):
        imported = tmp_path / "shared-directory.yaml"
        imported.write_text(
            """
name: shared-directory
version: 1.0.0
module:
  id: raes/shared-directory
  version: 1.0.0
  exports:
    nodes: [ad]
    relationships: [alice-admin, ldap-policy, membership-policy]
nodes:
  ad:
    type: compute
    os: windows
    runtime:
      identity_authorities:
        - identity_authority_id: techvault-domain
          services:
            - {service_id: ldap-endpoint, protocol: ldap}
          subjects:
            - {subject_id: alice, kind: user, name: alice}
            - {subject_id: domain-admins, kind: group, name: Domain Admins}
          policies:
            - policy_id: default-policy
              applies_to_refs: [techvault-domain]
          relationships:
            - relationship_id: alice-admin
              relationship_type: member-of
              source_ref: alice
              target_ref: domain-admins
relationships:
  alice-admin:
    type: trusts
    source: nodes.ad.runtime.identity_authorities.techvault-domain.subjects.alice
    target: nodes.ad.runtime.identity_authorities.techvault-domain.subjects.domain-admins
  ldap-policy:
    type: depends_on
    source: nodes.ad.runtime.identity_authorities.techvault-domain.services.ldap-endpoint
    target: nodes.ad.runtime.identity_authorities.techvault-domain.policies.default-policy
  membership-policy:
    type: depends_on
    source: nodes.ad.runtime.identity_authorities.techvault-domain.relationships.alice-admin
    target: nodes.ad.runtime.identity_authorities.techvault-domain.policies.default-policy
""",
            encoding="utf-8",
        )
        root = tmp_path / "root.yaml"
        root.write_text(
            """
name: root
imports:
  - path: shared-directory.yaml
    namespace: shared
    version: 1.0.0
""",
            encoding="utf-8",
        )

        scenario = parse_sdl_file(root)

        rel = scenario.relationships["shared.alice-admin"]
        assert rel.source == "nodes.shared.ad.runtime.identity_authorities.techvault-domain.subjects.alice"
        assert rel.target == "nodes.shared.ad.runtime.identity_authorities.techvault-domain.subjects.domain-admins"
        rel = scenario.relationships["shared.ldap-policy"]
        assert rel.source == "nodes.shared.ad.runtime.identity_authorities.techvault-domain.services.ldap-endpoint"
        assert rel.target == "nodes.shared.ad.runtime.identity_authorities.techvault-domain.policies.default-policy"
        rel = scenario.relationships["shared.membership-policy"]
        assert rel.source == "nodes.shared.ad.runtime.identity_authorities.techvault-domain.relationships.alice-admin"
        assert rel.target == "nodes.shared.ad.runtime.identity_authorities.techvault-domain.policies.default-policy"


class TestRuntimeDnsParsing:
    def test_dns_service_canonical_field_keys_preserve_names(self):
        sdl = """
name: techvault-dns
nodes:
  dns-host:
    type: compute
    os: linux
    services:
      - {port: 53, protocol: udp, name: dns}
    runtime:
      dns_services:
        - dns_service_id: tv-dns
          service: dns
          implementation: BIND
          roles: [authoritative, recursive-resolver]
          resolver_policy:
            recursion_enabled: true
            dnssec_validation: auto
            forwarders:
              - {address: 8.8.8.8, port: 53}
          zones:
            - zone_id: techvault-local
              name: TechVault.Local.
              zone_class: IN
              purpose: forward
              rrsets:
                - rrset_id: web-a
                  owner: Web.TechVault.Local.
                  record_type: A
                  ttl: 300
                  records:
                    - {address: 172.20.10.20}
"""
        raw = parse_sdl(sdl)
        dns = raw.nodes["dns-host"].runtime.dns_services[0]
        assert dns.dns_service_id == "tv-dns"
        assert dns.implementation.value == "bind"
        assert dns.roles[1].value == "recursive_resolver"
        assert dns.resolver_policy.dnssec_validation.value == "auto"
        zone = dns.zones[0]
        # Observed names are DNS data and are not case-folded.
        assert zone.name == "TechVault.Local."
        assert zone.rrsets[0].owner == "Web.TechVault.Local."
        assert zone.rrsets[0].record_type.value == "a"

    def test_dns_runtime_refs_rewrite_on_module_import(self, tmp_path):
        shared = tmp_path / "shared-dns.yaml"
        shared.write_text(
            """
name: shared-dns
version: 1.0.0
module:
  id: raes/shared-dns
  version: 1.0.0
  exports:
    nodes: [dns]
    relationships: [dns-record]
nodes:
  dns:
    type: compute
    os: linux
    services:
      - {port: 53, protocol: udp, name: dns}
    runtime:
      dns_services:
        - dns_service_id: tv-dns
          service: dns
          zones:
            - zone_id: techvault-local
              name: techvault.local.
              rrsets:
                - rrset_id: web-a
                  owner: web.techvault.local.
                  record_type: a
                  ttl: 300
                  records:
                    - {address: 172.20.10.20}
relationships:
  dns-record:
    type: connects_to
    source: nodes.dns.runtime.dns_services.tv-dns
    target: nodes.dns.runtime.dns_services.tv-dns.zones.techvault-local.rrsets.web-a
""",
            encoding="utf-8",
        )
        root = tmp_path / "root.yaml"
        root.write_text(
            """
name: root
imports:
  - path: shared-dns.yaml
    namespace: shared
    version: 1.0.0
""",
            encoding="utf-8",
        )

        scenario = parse_sdl_file(root)

        rel = scenario.relationships["shared.dns-record"]
        assert rel.source == "nodes.shared.dns.runtime.dns_services.tv-dns"
        assert rel.target == "nodes.shared.dns.runtime.dns_services.tv-dns.zones.techvault-local.rrsets.web-a"


class TestRuntimeDatabaseParsing:
    def test_database_service_canonical_field_keys_preserve_names(self):
        # Structural fields are canonical; observed object names are data and
        # survive verbatim, including mixed case and underscores.
        sdl = """
name: techvault-db
nodes:
  db-host:
    type: compute
    os: linux
    services:
      - {port: 5432, name: pg}
    runtime:
      database_services:
        - database_service_id: tv-pg
          service: pg
          engine: PostgreSQL
          protocol: postgresql
          databases:
            - database_id: tv-db
              name: TechVault_Prod
              schemas:
                - schema_id: pub
                  name: public
                  tables:
                    - {table_id: audit, name: Audit_Log}
          settings:
            - {name: log_statement, value: all, provenance: configuration-file}
"""
        raw = parse_sdl(sdl)
        dbsvc = raw.nodes["db-host"].runtime.database_services[0]
        assert dbsvc.database_service_id == "tv-pg"
        # Engine string normalizes for enum matching.
        assert str(dbsvc.engine.value) == "postgresql"
        # Observed names are preserved exactly, not case-folded.
        assert dbsvc.databases[0].name == "TechVault_Prod"
        assert dbsvc.databases[0].schemas[0].tables[0].name == "Audit_Log"
        assert dbsvc.settings[0].provenance.value == "configuration_file"

    def test_database_service_variable_substitutes_on_instantiation(self):
        sdl = """
name: techvault-db-variable
variables:
  pg_version:
    type: string
    required: true
nodes:
  db-host:
    type: compute
    os: linux
    services:
      - {port: 5432, name: pg}
    runtime:
      database_services:
        - database_service_id: tv-pg
          service: pg
          engine: postgresql
          protocol: postgresql
          version: ${pg_version}
"""
        raw = parse_sdl(sdl)
        assert raw.nodes["db-host"].runtime.database_services[0].version == "${pg_version}"
        instantiated = instantiate_scenario(raw, parameters={"pg_version": "16.13"})
        assert instantiated.nodes["db-host"].runtime.database_services[0].version == "16.13"


class TestADR073ScoringRemoval:
    """Negative-conformance coverage for the OCR scoring removal (ADR-073, SEM-206)."""

    @pytest.mark.parametrize(
        "section",
        ["metrics", "evaluations", "tlos", "goals"],
    )
    def test_removed_top_level_scoring_sections_rejected(self, section):
        sdl = f"name: test\n{section}:\n  x1: {{}}\n"
        with pytest.raises(SDLParseError, match="were removed from the language by ADR-073"):
            parse_sdl(sdl)

    def test_migration_message_points_to_success_assertions(self):
        with pytest.raises(SDLParseError, match="objectives.\\*.success.assertions"):
            parse_sdl("name: test\ngoals:\n  g1:\n    tlos: [t1]\n")

    def test_agent_reward_calculator_rejected(self):
        sdl = """
name: test
entities:
  red-team:
    role: red
agents:
  red-agent:
    entity: red-team
    reward_calculator: some-calc
"""
        with pytest.raises(SDLParseError):
            parse_sdl(sdl)

    def test_entity_tlos_rejected(self):
        sdl = """
name: test
entities:
  blue-team:
    role: blue
    tlos: [t1]
"""
        with pytest.raises(SDLParseError):
            parse_sdl(sdl)

    @pytest.mark.parametrize("field", ["metrics", "evaluations", "tlos", "goals"])
    def test_objective_success_removed_fields_rejected(self, field):
        sdl = f"""
name: test
entities:
  blue-team:
    role: blue
objectives:
  obj:
    entity: blue-team
    success:
      {field}: [x1]
"""
        with pytest.raises(SDLParseError):
            parse_sdl(sdl)

    def test_objective_success_accepts_assertions_only(self):
        sdl = """
name: test
entities:
  blue-team:
    role: blue
conditions:
  release-ready:
    command: /bin/check
    interval: 30
propositions:
  release-ready:
    description: The governed team has declared release readiness.
    subjects: [entities.blue-team]
    basis: declared_state
    predicate: {kind: boolean, property: release-ready, semantic_ref: urn:raes:declared-property:release-ready, operator: equals, expected: true}
assertions:
  release-ready: {proposition: release-ready, role: postcondition, polarity: positive}
objectives:
  obj:
    entity: blue-team
    success:
      assertions: [release-ready]
"""
        s = parse_sdl(sdl)
        assert s.objectives["obj"].success.assertions == ["release-ready"]

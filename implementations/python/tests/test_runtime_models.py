"""Compiler and runtime model tests."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from raes import SDLInstantiationError, parse_sdl, parse_sdl_file
from raes_backend_protocols.capabilities import (
    WorkflowFeature,
    WorkflowStatePredicateFeature,
)
from raes_processor.compiler import compile_runtime_model


def _scenario(yaml_str: str):
    return parse_sdl(textwrap.dedent(yaml_str))


class TestRuntimeModelCompilation:
    def test_feature_template_binds_to_multiple_nodes(self):
        model = compile_runtime_model(
            _scenario("""
name: bindings
nodes:
  vm1:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    features: {nginx: web}
    roles: {web: appuser}
  vm2:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    features: {nginx: web}
    roles: {web: appuser}
features:
  nginx: {type: service, source: nginx}
""")
        )

        assert set(model.feature_templates) == {"nginx"}
        assert set(model.feature_bindings) == {
            "provision.feature.vm1.nginx",
            "provision.feature.vm2.nginx",
        }
        assert model.feature_bindings["provision.feature.vm1.nginx"].node_name == "vm1"
        assert model.feature_bindings["provision.feature.vm2.nginx"].node_name == "vm2"
        assert not model.diagnostics

    def test_node_runtime_preserves_runtime_configuration_metadata(self):
        model = compile_runtime_model(
            _scenario("""
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
        devices:
          - host_path: /dev/null
            container_path: /dev/null
            permissions: rwm
        device_cgroup_rules: c 1:3 rwm
        seccomp_profile: unconfined
        security_opt: [seccomp:unconfined, no-new-privileges]
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
""")
        )

        runtime = model.node_deployments["provision.node.shuffle-backend"].spec["node"]["runtime"]
        assert runtime["mounts"][0]["target"] == "/shuffle-database"
        assert runtime["mounts"][0]["source_sensitivity"] == "plain"
        assert runtime["mounts"][0]["filesystem_type"] == "ext4"
        assert runtime["mounts"][0]["options_sensitivity"] == "plain"
        assert runtime["mounts"][0]["propagation"] == "rprivate"
        assert runtime["mounts"][0]["stability"] == "volume_backed"
        assert runtime["mounts"][0]["backend_generated"] is True
        assert runtime["filesystem_inventory"][0]["path"] == "/app/app.py"
        assert runtime["filesystem_inventory"][0]["entry_type"] == "file"
        assert runtime["filesystem_inventory"][0]["uid"] == 0
        assert runtime["filesystem_inventory"][0]["gid"] == 0
        assert runtime["filesystem_inventory"][0]["mode"] == "0644"
        assert runtime["filesystem_inventory"][0]["size"] == 4096
        assert runtime["filesystem_inventory"][0]["digest_algorithm"] == "sha256"
        assert runtime["filesystem_inventory"][0]["content_digest"] == "4f8c2d"
        assert runtime["filesystem_inventory"][0]["source_path"] == "src/webapp/app.py"
        assert runtime["filesystem_inventory"][1]["stability"] == "log"
        assert runtime["filesystem_inventory"][1]["sensitivity"] == "operator_secret"
        assert runtime["local_control_interfaces"][0]["path"] == "/run/docker.sock"
        assert runtime["local_control_interfaces"][0]["bind_source_sensitivity"] == "operator_secret"
        assert runtime["processes"][0]["command"] == ["./shufflebackend"]
        assert runtime["processes"][1]["name"] == "supervisord"
        assert runtime["processes"][2]["parent_pid"] == 1
        assert runtime["environment"][0]["name"] == "TECHVAULT_ADMIN_PASSWORD"
        assert runtime["environment"][0]["value_classification"] == "redacted"
        assert runtime["environment"][1]["value_classification"] == "secret_fixture"
        assert runtime["linux_capabilities"]["required"] == ["CAP_NET_ADMIN"]
        assert runtime["linux_capabilities"]["effective"] == ["CAP_NET_ADMIN"]
        assert runtime["operational_policy"]["restart"] == "unless_stopped"
        assert runtime["operational_policy"]["resource_limits"]["memory"] == 512 * 1048576
        assert runtime["operational_policy"]["resource_limits"]["cpu"] == 0.5
        assert runtime["operational_policy"]["resource_limits"]["pids"] == 128
        assert runtime["container"]["entrypoint"] == ["/entrypoint.sh"]
        assert runtime["container"]["command"] == ["gunicorn", "app:app"]
        assert runtime["container"]["log_driver"] == "json-file"
        assert runtime["container"]["log_options"] == {"max-size": "10m", "max-file": "3"}
        assert runtime["container"]["namespaces"]["userns"] == "host"
        assert runtime["container"]["shm_size"] == 64 * 1048576
        assert runtime["container"]["masked_paths"] == ["/proc/acpi", "/proc/kcore"]
        assert runtime["container"]["read_only_paths"] == ["/proc/sys"]
        assert runtime["container"]["devices"][0]["container_path"] == "/dev/null"
        assert runtime["container"]["device_cgroup_rules"] == ["c 1:3 rwm"]
        assert runtime["container"]["seccomp_profile"] == "unconfined"
        assert runtime["container"]["security_opt"] == ["seccomp:unconfined", "no-new-privileges"]
        assert runtime["container"]["extra_hosts"][0]["hostname"] == "wazuh-manager"
        assert runtime["container"]["dns_options"] == ["ndots:0"]
        assert runtime["container"]["group_add"] == ["adm", "101"]
        assert runtime["packages"][0]["manager"] == "apk"
        assert runtime["packages"][0]["name"] == "musl"
        assert runtime["packages"][0]["version"] == "1.2.4-r2"
        assert runtime["software_components"][0]["component_id"] == "shuffle-backend-app"
        assert runtime["software_components"][0]["name"] == "shuffle-backend"
        assert runtime["software_components"][0]["component_type"] == "application"
        assert runtime["software_components"][0]["provenance"] == "package_manager"
        assert runtime["software_components"][0]["package_manager"] == "apk"
        assert runtime["software_components"][0]["manifest_path"] == "/app/go.mod"
        assert runtime["software_components"][0]["installed_paths"] == ["/app/shufflebackend", "/app/go.mod"]
        assert runtime["software_components"][0]["hashes"][0]["algorithm"] == "sha256"
        assert runtime["dependency_manifests"][0]["ecosystem"] == "go"
        assert runtime["dependency_manifests"][0]["path"] == "/app/go.mod"
        assert runtime["dependency_manifests"][0]["format"] == "go-module"
        assert not model.diagnostics

    def test_node_runtime_preserves_identity_authority_inventory(self):
        model = compile_runtime_model(
            _scenario("""
name: directory-identity-runtime
nodes:
  ad:
    type: compute
    os: windows
    resources: {ram: 2 gib, cpu: 2}
    services:
      - {port: 389, name: ldap}
      - {port: 88, name: kerberos}
    runtime:
      identity_authorities:
        - identity_authority_id: techvault-domain
          kind: domain
          namespace: techvault.local
          domain_name: TECHVAULT
          realm: TECHVAULT.LOCAL
          services:
            - {service_id: ldap-endpoint, service: ldap, protocol: ldap, port: 389}
          subjects:
            - {subject_id: alice, kind: user, name: alice}
            - {subject_id: domain-admins, kind: group, name: Domain Admins}
          relationships:
            - relationship_id: alice-admin
              relationship_type: member-of
              source_ref: alice
              target_ref: domain-admins
""")
        )

        runtime = model.node_deployments["provision.node.ad"].spec["node"]["runtime"]
        authority = runtime["identity_authorities"][0]
        assert authority["identity_authority_id"] == "techvault-domain"
        assert authority["kind"] == "domain"
        assert authority["services"][0]["protocol"] == "ldap"
        assert authority["subjects"][1]["kind"] == "group"
        assert authority["relationships"][0]["relationship_type"] == "member_of"
        assert not model.diagnostics

    def test_node_runtime_preserves_file_service_inventory(self):
        model = compile_runtime_model(
            _scenario("""
name: fileshare-runtime
nodes:
  fileshare:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    services:
      - {port: 445, name: smb}
    runtime:
      local_identity:
        users:
          - {username: svc-fileshare, uid: 1100, primary_gid: 1100, primary_group: svc-fileshare}
      file_services:
        - file_service_id: fileshare-smb
          service: smb
          protocol: smb
          backend: samba-4.x
          shares:
            - share_id: public
              name: public
              kind: disk
              backing_path: /srv/samba/public
              read_only: true
              browseable: true
              guest_ok: true
            - share_id: deploy-keys
              name: deploy_keys
              kind: disk
              backing_path: /srv/samba/deploy_keys
              read_only: false
              browseable: false
              guest_ok: false
              valid_users: [svc-fileshare]
              write_users: [svc-fileshare]
          principals:
            - principal_id: nobody
              kind: guest
              name: nobody
              external_id: S-1-5-21-0-501
              status: enabled
              credential_classification: no_credential
              origin: built_in
            - principal_id: svc-fileshare
              kind: service_account
              name: svc-fileshare
              status: enabled
              credential_classification: redacted
              origin: provisioned
              local_user_ref: svc-fileshare
          access_rules:
            - rule_id: public-read
              subject_ref: nobody
              resource_ref: public
              action: read
              effect: allow
              basis: share_config
          access_observations:
            - observation_id: anon-mount-allowed
              subject_ref: anonymous
              resource_ref: public
              action: browse
              outcome: allowed
              basis: observed_probe
      filesystem_inventory:
        - path: /srv/samba/public
          entry_type: directory
          presence: present
        - path: /srv/samba/deploy_keys/id_ed25519
          entry_type: file
          presence: expected_absent
          description: Expected deploy-key attempted by setup, absent at capture.
""")
        )

        runtime = model.node_deployments["provision.node.fileshare"].spec["node"]["runtime"]
        file_service = runtime["file_services"][0]
        assert file_service["file_service_id"] == "fileshare-smb"
        assert file_service["protocol"] == "smb"
        assert file_service["shares"][0]["kind"] == "disk"
        assert file_service["shares"][0]["guest_ok"] is True
        assert file_service["principals"][0]["kind"] == "guest"
        assert file_service["principals"][1]["credential_classification"] == "redacted"
        assert file_service["access_rules"][0]["effect"] == "allow"
        assert file_service["access_observations"][0]["outcome"] == "allowed"
        assert runtime["filesystem_inventory"][1]["presence"] == "expected_absent"
        assert runtime["filesystem_inventory"][1]["entry_type"] == "file"
        assert not model.diagnostics

    def test_feature_binding_tracks_same_node_dependencies(self):
        model = compile_runtime_model(
            _scenario("""
name: feature-deps
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    features: {nginx: web, php-config: web}
    roles: {web: appuser}
features:
  nginx: {type: service, source: nginx}
  php-config: {type: configuration, source: php-config, dependencies: [nginx]}
""")
        )

        binding = model.feature_bindings["provision.feature.vm.php-config"]

        assert binding.ordering_dependencies == (
            "provision.node.vm",
            "provision.feature.vm.nginx",
        )
        assert binding.refresh_dependencies == (
            "provision.node.vm",
            "provision.feature.vm.nginx",
        )
        assert not model.diagnostics

    def test_missing_same_node_feature_dependency_emits_diagnostic(self):
        model = compile_runtime_model(
            _scenario("""
name: feature-deps
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    features: {php-config: web}
    roles: {web: appuser}
features:
  nginx: {type: service, source: nginx}
  php-config: {type: configuration, source: php-config, dependencies: [nginx]}
""")
        )

        binding = model.feature_bindings["provision.feature.vm.php-config"]
        diagnostics = {(diag.code, diag.address) for diag in model.diagnostics}

        assert (
            "provisioning.feature-dependency-binding-missing",
            "provision.feature.vm.php-config",
        ) in diagnostics
        assert binding.ordering_dependencies == ("provision.node.vm",)
        assert binding.refresh_dependencies == ("provision.node.vm",)

    def test_condition_and_inject_resources_preserve_context(self):
        model = compile_runtime_model(
            _scenario("""
name: bindings
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    injects: {phish: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 10}
injects:
  phish: {source: phishing-bundle}
""")
        )

        condition = model.condition_bindings["evaluation.condition.vm.health"]
        inject = model.injects["orchestration.inject.phish"]
        inject_binding = model.inject_bindings["orchestration.inject-binding.vm.phish"]

        assert condition.node_name == "vm"
        assert condition.role_name == "ops"
        assert condition.template_address == "template.condition.health"
        assert inject.name == "phish"
        assert inject.spec["source"]["name"] == "phishing-bundle"
        assert inject_binding.node_name == "vm"
        assert inject_binding.role_name == "ops"
        assert inject_binding.template_address == "template.inject.phish"
        assert inject_binding.ordering_dependencies == ("orchestration.inject.phish",)
        assert inject_binding.refresh_dependencies == (
            "provision.node.vm",
            "orchestration.inject.phish",
        )
        assert condition.result_contract.resource_type == "condition-binding"
        assert condition.result_contract.supports_passed is True
        assert condition.execution_contract.requires_start_event is True
        assert not model.diagnostics

    def test_objective_windows_and_workflows_resolve_refresh_dependencies(self):
        model = compile_runtime_model(
            _scenario("""
name: orchestration
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
objectives:
  initial:
    owner: blue
    success: {assertions: [health]}
    window:
      stories: [main]
      scripts: [timeline]
      events: [kickoff]
      workflows: [flow]
      steps: [flow.branch]
entities:
  blue: {role: blue}
events:
  kickoff: {assertions: [pre-health]}
scripts:
  timeline: {start_time: 0, end_time: 60, speed: 1, events: {kickoff: 10}}
stories:
  main: {scripts: [timeline]}
workflows:
  flow:
    start: start
    steps:
      start: {type: objective, objective: initial, on_success: branch}
      branch:
        type: decision
        when: {assertions: [pre-health]}
        then: end
        else: end
      end: {type: end}
""")
        )

        objective = model.objectives["evaluation.objective.initial"]
        workflow = model.workflows["orchestration.workflow.flow"]

        assert "evaluation.assertion.health" in objective.success_addresses
        assert objective.window_story_addresses == ("orchestration.story.main",)
        assert objective.window_script_addresses == ("orchestration.script.timeline",)
        assert objective.window_event_addresses == ("orchestration.event.kickoff",)
        assert objective.window_workflow_addresses == ("orchestration.workflow.flow",)
        assert objective.window_step_refs == ("flow.branch",)
        assert objective.window_step_workflow_addresses == ("orchestration.workflow.flow",)
        assert [ref.reference_kind for ref in objective.window_references] == [
            "story",
            "script",
            "event",
            "workflow",
            "workflow_step",
        ]
        assert objective.window_references[-1].workflow_name == "flow"
        assert objective.window_references[-1].step_name == "branch"
        assert "evaluation.assertion.health" in objective.ordering_dependencies
        assert "orchestration.workflow.flow" in objective.refresh_dependencies
        assert workflow.referenced_objective_addresses == ("evaluation.objective.initial",)
        assert workflow.start_step == "start"
        assert workflow.control_steps["start"].on_success == "branch"
        assert workflow.result_contract.observable_steps["start"].observable_outcomes == (
            "succeeded",
            "failed",
        )
        assert workflow.control_steps["start"].state_contract.observable_outcomes == (
            "succeeded",
            "failed",
        )
        assert workflow.control_steps["branch"].step_type == "decision"
        assert not workflow.control_steps["branch"].state_contract.state_observable
        assert workflow.control_edges["start"] == ("branch",)
        assert workflow.control_edges["branch"] == ("end",)
        assert workflow.step_assertion_addresses["branch"] == ("evaluation.assertion.pre-health",)
        assert "evaluation.assertion.pre-health" in workflow.step_predicate_addresses["branch"]
        assert workflow.ordering_dependencies == ()
        assert "evaluation.objective.initial" in workflow.refresh_dependencies
        assert model.objectives["evaluation.objective.initial"].result_contract.supports_passed is True
        assert not model.diagnostics

    def test_objective_window_step_outside_window_workflows_fails_admission(self):
        scenario = parse_sdl(
            textwrap.dedent("""
name: broken-window
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  initial:
    owner: blue
    success: {assertions: [health]}
    window:
      workflows: [flow]
      steps: [other.finish]
workflows:
  flow:
    start: finish
    steps:
      finish: {type: end}
  other:
    start: finish
    steps:
      finish: {type: end}
"""),
            skip_semantic_validation=True,
        )

        with pytest.raises(SDLInstantiationError) as exc_info:
            compile_runtime_model(scenario)
        assert any(
            "Objective 'initial' window step 'other.finish' is not part of the referenced workflows" in error
            for error in exc_info.value.errors
        )

    def test_missing_node_bindings_fail_compiler_admission(self):
        scenario = parse_sdl(
            textwrap.dedent("""
name: broken-bindings
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    features: {nginx: web}
    conditions: {health: web}
    injects: {phish: web}
    roles: {web: appuser}
"""),
            skip_semantic_validation=True,
        )

        with pytest.raises(SDLInstantiationError) as exc_info:
            compile_runtime_model(scenario)
        assert exc_info.value.errors == [
            "Node 'vm' references undefined feature 'nginx'",
            "Node 'vm' references undefined condition 'health'",
            "Node 'vm' references undefined inject 'phish'",
        ]

    def test_missing_runtime_graph_refs_fail_compiler_admission(self):
        scenario = parse_sdl(
            textwrap.dedent("""
name: broken-graph
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
objectives:
  initial:
    owner: blue
    success:
      assertions: [missing-assertion]
    window:
      workflows: [missing-workflow]
      steps: [missing-workflow.branch, badstep]
entities:
  blue: {role: blue}
scripts:
  timeline: {start_time: 0, end_time: 60, speed: 1, events: {missing-event: 10}}
stories:
  main: {scripts: [missing-script]}
workflows:
  flow:
    start: branch
    steps:
      branch:
        type: decision
        when: {assertions: [missing-assertion], objectives: [missing-objective]}
        then: finish
        else: finish
      finish: {type: end}
"""),
            skip_semantic_validation=True,
        )

        with pytest.raises(SDLInstantiationError) as exc_info:
            compile_runtime_model(scenario)
        errors = exc_info.value.errors
        assert any("Script 'timeline' references undefined event 'missing-event'" in error for error in errors)
        assert any("Story 'main' references undefined script 'missing-script'" in error for error in errors)
        assert any(
            "Objective 'initial' references undefined assertion 'missing-assertion'" in error for error in errors
        )
        assert any("Objective 'initial' references undefined workflow 'missing-workflow'" in error for error in errors)
        assert any("window step 'missing-workflow.branch' references undefined workflow" in error for error in errors)
        assert any("window step 'badstep' must use '<workflow>.<step>' syntax" in error for error in errors)
        assert any(
            "Workflow 'flow' step 'branch' references undefined objective 'missing-objective'" in error
            for error in errors
        )

    def test_workflow_with_retry_and_step_state_compiles(self):
        model = compile_runtime_model(
            _scenario("""
name: retry-test
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  attempt:
    owner: blue
    success: {assertions: [health]}
  recover:
    owner: blue
    success: {assertions: [health]}
workflows:
  retry:
    start: attempt-loop
    steps:
      attempt-loop:
        type: retry
        objective: attempt
        on_success: branch
        max_attempts: 3
        on_exhausted: handle-error
      branch:
        type: decision
        when:
          assertions: [pre-health]
          steps:
            - step: attempt-loop
              outcomes: [succeeded]
        then: done
        else: handle-error
      handle-error:
        type: objective
        objective: recover
        on_success: done
      done: {type: end}
""")
        )

        workflow = model.workflows["orchestration.workflow.retry"]
        assert workflow.control_steps["attempt-loop"].step_type == "retry"
        assert workflow.control_steps["attempt-loop"].objective_address == ("evaluation.objective.attempt")
        assert workflow.control_steps["attempt-loop"].max_attempts == 3
        predicate = workflow.control_steps["branch"].predicate
        assert predicate is not None
        assert predicate.step_state_predicates[0].step_name == "attempt-loop"
        assert set(workflow.required_features) == {
            WorkflowFeature.DECISION,
            WorkflowFeature.RETRY,
            WorkflowFeature.FAILURE_TRANSITIONS,
        }
        assert set(workflow.required_state_predicate_features) == {
            WorkflowStatePredicateFeature.OUTCOME_MATCHING,
        }
        assert workflow.referenced_objective_addresses == (
            "evaluation.objective.attempt",
            "evaluation.objective.recover",
        )
        assert "evaluation.assertion.pre-health" in workflow.step_predicate_addresses["branch"]
        assert not model.diagnostics

    def test_parallel_join_compiles_as_barrier_with_typed_predicate(self):
        model = compile_runtime_model(
            _scenario("""
name: parallel-join
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  left:
    owner: blue
    success: {assertions: [health]}
  right:
    owner: blue
    success: {assertions: [health]}
  recover:
    owner: blue
    success: {assertions: [health]}
workflows:
  flow:
    start: fanout
    steps:
      fanout:
        type: parallel
        branches: [left-branch, right-branch]
        join: joined
        on_failure: recover-step
      left-branch:
        type: objective
        objective: left
        on_success: joined
      right-branch:
        type: objective
        objective: right
        on_success: joined
      joined:
        type: join
        next: branch
      branch:
        type: decision
        when:
          steps:
            - step: left-branch
              outcomes: [succeeded]
              min_attempts: 2
        then: finish
        else: recover-step
      recover-step:
        type: objective
        objective: recover
        on_success: finish
      finish: {type: end}
""")
        )

        workflow = model.workflows["orchestration.workflow.flow"]
        assert workflow.control_edges["fanout"] == ("left-branch", "right-branch", "recover-step")
        assert workflow.join_owners == {"joined": "fanout"}
        assert workflow.control_steps["joined"].owning_parallel_step == "fanout"
        assert set(workflow.result_contract.observable_steps) == {
            "fanout",
            "left-branch",
            "right-branch",
            "recover-step",
        }
        assert workflow.control_steps["fanout"].state_contract.observable_outcomes == (
            "succeeded",
            "failed",
        )
        assert workflow.control_steps["fanout"].state_contract.fixed_attempts == 1
        assert not workflow.control_steps["joined"].state_contract.state_observable
        predicate = workflow.control_steps["branch"].predicate
        assert predicate is not None
        assert predicate.step_state_predicates == (predicate.step_state_predicates[0],)
        assert predicate.step_state_predicates[0].step_name == "left-branch"
        assert predicate.step_state_predicates[0].min_attempts == 2
        assert set(workflow.required_features) == {
            WorkflowFeature.DECISION,
            WorkflowFeature.PARALLEL_BARRIER,
            WorkflowFeature.FAILURE_TRANSITIONS,
        }
        assert set(workflow.required_state_predicate_features) == {
            WorkflowStatePredicateFeature.OUTCOME_MATCHING,
            WorkflowStatePredicateFeature.ATTEMPT_COUNTS,
        }
        assert not model.diagnostics

    def test_module_expansion_compiles_namespaced_runtime_addresses(self, tmp_path: Path):
        imported = tmp_path / "shared.yaml"
        imported.write_text(
            """
name: shared
version: 1.0.0
module:
  id: raes/shared
  version: 1.0.0
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
    roles: {ops: operator}
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
    owner: blue
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
  - path: shared.yaml
    namespace: shared
    version: 1.0.0
""",
            encoding="utf-8",
        )
        expanded_model = compile_runtime_model(parse_sdl_file(root))

        assert not expanded_model.diagnostics
        assert set(expanded_model.workflows) == {"orchestration.workflow.shared.response"}
        assert set(expanded_model.objectives) == {"evaluation.objective.shared.validate"}
        workflow = expanded_model.workflows["orchestration.workflow.shared.response"]
        assert workflow.referenced_objective_addresses == ("evaluation.objective.shared.validate",)
        assert workflow.control_steps["run"].objective_address == "evaluation.objective.shared.validate"

    def test_workflow_switch_call_and_timeout_compile_to_explicit_contracts(self):
        model = compile_runtime_model(
            parse_sdl(
                textwrap.dedent(
                    """
                    name: advanced-workflow
                    nodes:
                      vm:
                        type: compute
                        os: linux
                        resources: {ram: 1 gib, cpu: 1}
                        conditions: {health: ops}
                        roles: {ops: operator}
                    conditions:
                      health: {command: /bin/true, interval: 15}
                    propositions:
                      health:
                        description: The governed VM has declared runtime state.
                        subjects: [nodes.vm]
                        basis: declared_state
                        predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
                    assertions:
                      health: {proposition: health, role: postcondition, polarity: positive}
                      pre-health: {proposition: health, role: precondition, polarity: positive}
                    entities:
                      blue: {role: blue}
                    objectives:
                      validate:
                        owner: blue
                        success: {assertions: [health]}
                    workflows:
                      child:
                        start: run
                        steps:
                          run:
                            type: objective
                            objective: validate
                            on_success: finish
                          finish: {type: end}
                      parent:
                        start: route
                        timeout: 300
                        steps:
                          route:
                            type: switch
                            cases:
                              - when: {assertions: [pre-health]}
                                next: delegate
                            default: finish
                          delegate:
                            type: call
                            workflow: child
                            on_success: finish
                          finish: {type: end}
                    """
                )
            )
        )

        workflow = model.workflows["orchestration.workflow.parent"]

        assert workflow.execution_contract.timeout_seconds == 300
        assert workflow.execution_contract.step_types["route"] == "switch"
        assert workflow.execution_contract.step_types["delegate"] == "call"
        assert workflow.execution_contract.call_steps["delegate"] == "orchestration.workflow.child"
        assert workflow.control_steps["route"].default_step == "finish"
        assert workflow.control_steps["route"].switch_cases[0].next_step == "delegate"
        assert workflow.control_steps["delegate"].called_workflow_address == "orchestration.workflow.child"
        assert workflow.result_contract.observable_steps["delegate"].observable_outcomes == (
            "succeeded",
            "failed",
        )
        assert not model.diagnostics

    def test_workflow_compensation_compiles_to_explicit_contracts(self):
        model = compile_runtime_model(
            parse_sdl(
                textwrap.dedent(
                    """
                    name: compensation
                    nodes:
                      vm:
                        type: compute
                        os: linux
                        resources: {ram: 1 gib, cpu: 1}
                        conditions: {health: ops}
                        roles: {ops: operator}
                    conditions:
                      health: {command: /bin/true, interval: 15}
                    propositions:
                      health:
                        description: The governed VM has declared runtime state.
                        subjects: [nodes.vm]
                        basis: declared_state
                        predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
                    assertions:
                      health: {proposition: health, role: postcondition, polarity: positive}
                    entities:
                      blue: {role: blue}
                    objectives:
                      validate:
                        owner: blue
                        success: {assertions: [health]}
                    workflows:
                      rollback:
                        start: finish
                        steps:
                          finish: {type: end}
                      response:
                        start: run
                        compensation:
                          mode: automatic
                          on: [failed, cancelled, timed_out]
                          failure_policy: record_and_continue
                        steps:
                          run:
                            type: objective
                            objective: validate
                            compensate_with: rollback
                            on_success: finish
                            on_failure: finish
                          finish: {type: end}
                    """
                )
            )
        )

        workflow = model.workflows["orchestration.workflow.response"]

        assert WorkflowFeature.COMPENSATION in workflow.required_features
        assert workflow.control_steps["run"].compensation_workflow_address == "orchestration.workflow.rollback"
        assert workflow.execution_contract.compensation_mode == "automatic"
        assert set(workflow.execution_contract.compensation_triggers) == {
            "failed",
            "cancelled",
            "timed_out",
        }
        assert workflow.execution_contract.compensation_targets == {"run": "orchestration.workflow.rollback"}
        assert workflow.execution_contract.compensation_ordering == "reverse_completion"
        assert workflow.execution_contract.compensation_failure_policy == "record_and_continue"
        assert not model.diagnostics

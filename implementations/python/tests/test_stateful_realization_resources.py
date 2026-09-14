"""Typed desired-state resources for stateful service prerequisites."""

from __future__ import annotations

import textwrap
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from raes import SDLParseError, SDLValidationError, parse_sdl, parse_sdl_file
from raes_backend_stubs.stubs import create_stub_manifest
from raes_contracts.contracts import schema_bundle
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan


def _scenario(extra: str = ""):
    return parse_sdl(
        textwrap.dedent(
            f"""
            name: stateful-service
            nodes:
              indexer: {{type: compute, os: linux}}
              manager: {{type: compute, os: linux}}
            generated_artifacts:
              indexer-certs:
                generator: certificate_bundle
                lifecycle: regenerate_on_change
                provenance: config/certs.yml
                outputs:
                  - {{name: root-ca, path: root-ca.pem, sensitivity: public}}
                  - {{name: indexer-key, path: wazuh.indexer-key.pem, sensitivity: secret}}
                  - {{name: indexer-cert, path: wazuh.indexer.pem, sensitivity: public}}
                consumers:
                  - node: indexer
                    mount_destination: /usr/share/wazuh-indexer/certs
                    access_mode: read_only
              manager-config:
                generator: rendered_config
                lifecycle: regenerate_on_change
                provenance: config/wazuh_cluster/wazuh_manager.conf
                outputs:
                  - {{name: ossec-conf, path: ossec.conf, sensitivity: restricted}}
                consumers:
                  - node: manager
                    mount_destination: /wazuh-config-mount/etc/ossec.conf
                    access_mode: read_only
                ordering_dependencies: [generated_artifacts.indexer-certs]
            persistent_volumes:
              indexer-data:
                lifecycle: retain
                access_mode: read_write_once
                consumers:
                  - node: indexer
                    mount_destination: /var/lib/wazuh-indexer
                    access_mode: read_write
                ordering_dependencies: [generated_artifacts.indexer-certs]
            {extra}
            """
        )
    )


def _ssh_scenario(*, outputs: str, consumers: str):
    output_block = textwrap.indent(textwrap.dedent(outputs).strip(), "      ")
    consumer_block = textwrap.indent(textwrap.dedent(consumers).strip(), "      ")
    return parse_sdl(
        "name: ssh-access\n"
        "nodes:\n"
        "  producer: {type: compute, os: linux}\n"
        "  client: {type: compute, os: linux}\n"
        "generated_artifacts:\n"
        "  access:\n"
        "    generator: ssh_key_bundle\n"
        "    lifecycle: regenerate_on_change\n"
        "    provenance: access/ssh.yml\n"
        "    outputs:\n"
        f"{output_block}\n"
        "    consumers:\n"
        f"{consumer_block}\n"
    )


def test_stateful_resources_parse_compile_and_plan_in_dependency_order():
    manifest = create_stub_manifest()
    assert manifest.provisioner.supports_generated_artifacts
    assert manifest.provisioner.supports_persistent_volumes
    model = compile_runtime_model(_scenario())

    assert tuple(model.generated_artifacts) == (
        "provision.generated-artifact.indexer-certs",
        "provision.generated-artifact.manager-config",
    )
    assert tuple(model.persistent_volumes) == ("provision.persistent-volume.indexer-data",)

    execution = plan(model, manifest)
    operations = execution.provisioning.operations
    addresses = [operation.address for operation in operations]
    assert addresses.index("provision.generated-artifact.indexer-certs") < addresses.index(
        "provision.generated-artifact.manager-config"
    )
    assert addresses.index("provision.generated-artifact.indexer-certs") < addresses.index(
        "provision.persistent-volume.indexer-data"
    )
    artifact = execution.provisioning.resources["provision.generated-artifact.indexer-certs"]
    assert artifact.resource_type == "generated-artifact"
    assert artifact.payload["spec"]["outputs"][1]["sensitivity"] == "secret"
    assert artifact.payload["spec"]["consumers"][0]["target_address"] == "provision.node.indexer"
    requirements = {
        requirement.address: requirement
        for requirement in model.realization_requirements
        if requirement.requirement_kind in {"generated-artifact", "persistent-volume"}
    }
    assert requirements["provision.generated-artifact.indexer-certs"].field_path == (
        "generated_artifacts.indexer-certs"
    )
    assert requirements["provision.persistent-volume.indexer-data"].explicitness.value == "exact"
    authority = {
        entry.address: entry
        for entry in execution.provisioning.realization_authority
        if entry.requirement_kind in {"generated-artifact", "persistent-volume"}
    }
    assert authority.keys() == requirements.keys()
    assert all(entry.mode.value == "exact" and entry.payload_pointer == "/spec" for entry in authority.values())


def test_ssh_artifact_output_selection_survives_compile_and_plan():
    scenario = _ssh_scenario(
        outputs="""
        - {name: private-key, path: id_ed25519, sensitivity: secret, disposition: producer_private}
        - {name: public-key, path: id_ed25519.pub, sensitivity: public, disposition: consumer_selected}
        - {name: authorized-keys, path: authorized_keys, sensitivity: restricted, disposition: consumer_selected}
        """,
        consumers="""
        - node: producer
          mount_destination: /run/raes/ssh
          access_mode: read_only
          selected_outputs: [public-key]
        - node: client
          mount_destination: /home/operator/.ssh
          access_mode: read_only
          selected_outputs: [authorized-keys]
        """,
    )

    artifact = scenario.generated_artifacts["access"]
    assert artifact.generator.value == "ssh_key_bundle"
    assert artifact.outputs[0].disposition.value == "producer_private"
    assert artifact.consumers[1].selected_outputs == ["authorized-keys"]

    execution = plan(compile_runtime_model(scenario), create_stub_manifest())
    payload = execution.provisioning.resources["provision.generated-artifact.access"].payload["spec"]
    assert payload["outputs"][0]["disposition"] == "producer_private"
    assert payload["consumers"][0]["selected_outputs"] == ["public-key"]
    assert payload["consumers"][1]["selected_outputs"] == ["authorized-keys"]


@pytest.mark.parametrize(
    ("outputs", "consumers", "message"),
    [
        (
            "- {name: public-key, path: id.pub, sensitivity: public, disposition: consumer_selected}",
            """
            - node: client
              mount_destination: /home/operator/.ssh
              access_mode: read_only
            """,
            "SSH generated artifact consumers must select at least one output",
        ),
        (
            "- {name: public-key, path: id.pub, sensitivity: public, disposition: consumer_selected}",
            """
            - node: client
              mount_destination: /home/operator/.ssh
              access_mode: read_only
              selected_outputs: []
            """,
            "at least 1 item",
        ),
        (
            "- {name: public-key, path: id.pub, sensitivity: public, disposition: consumer_selected}",
            """
            - node: client
              mount_destination: /home/operator/.ssh
              access_mode: read_only
              selected_outputs: [public-key, public-key]
            """,
            "selected_outputs must be unique",
        ),
        (
            "- {name: public-key, path: id.pub, sensitivity: public, disposition: consumer_selected}",
            """
            - node: client
              mount_destination: /home/operator/.ssh
              access_mode: read_only
              selected_outputs: [missing]
            """,
            "unknown generated artifact output",
        ),
        (
            "- {name: private-key, path: id, sensitivity: secret, disposition: producer_private}",
            """
            - node: client
              mount_destination: /home/operator/.ssh
              access_mode: read_only
              selected_outputs: [private-key]
            """,
            "producer-private generated artifact output",
        ),
        (
            """
            - {name: public-key, path: id.pub, sensitivity: public, disposition: consumer_selected}
            - {name: authorized-keys, path: authorized_keys, sensitivity: restricted, disposition: consumer_selected}
            """,
            """
            - node: client
              mount_destination: /home/operator/.ssh
              access_mode: read_only
              selected_outputs: [public-key]
            """,
            "each consumer-selected SSH output must be selected",
        ),
    ],
)
def test_ssh_artifact_rejects_invalid_output_selection(
    outputs: str,
    consumers: str,
    message: str,
):
    with pytest.raises(SDLParseError, match=message):
        _ssh_scenario(outputs=outputs, consumers=consumers)


def test_legacy_generated_artifacts_keep_implicit_all_non_private_outputs():
    scenario = _scenario()
    artifact = scenario.generated_artifacts["indexer-certs"]

    assert artifact.consumers[0].selected_outputs == []
    execution = plan(compile_runtime_model(scenario), create_stub_manifest())
    payload = execution.provisioning.resources["provision.generated-artifact.indexer-certs"].payload["spec"]
    assert "selected_outputs" not in payload["consumers"][0]


def test_planner_rejects_ssh_artifact_when_backend_does_not_claim_kind_support():
    scenario = _ssh_scenario(
        outputs="- {name: public-key, path: id.pub, sensitivity: public, disposition: consumer_selected}",
        consumers="""
        - node: client
          mount_destination: /home/operator/.ssh
          access_mode: read_only
          selected_outputs: [public-key]
        """,
    )
    manifest = create_stub_manifest()
    limited = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            provisioner=replace(
                manifest.provisioner,
                supported_generated_artifact_kinds=frozenset({"certificate_bundle", "rendered_config"}),
                supported_regeneration_scopes=frozenset(),
            ),
        ),
    )

    execution = plan(compile_runtime_model(scenario), limited)

    assert "provisioner.unsupported-generated-artifact-kind" in {
        diagnostic.code for diagnostic in execution.diagnostics
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            "generated_artifacts:\n  manager-config:\n    ordering_dependencies: [generated_artifacts.missing]",
            "missing",
        ),
        (
            "persistent_volumes:\n  indexer-data:\n    consumers:\n      - node: missing\n        mount_destination: /data\n        access_mode: read_write",
            "missing",
        ),
    ],
)
def test_stateful_resources_reject_unknown_references(mutation: str, message: str):
    if mutation.startswith("generated_artifacts"):
        mutation = mutation.replace(
            "    ordering_dependencies:",
            "    generator: rendered_config\n"
            "    lifecycle: regenerate_on_change\n"
            "    provenance: template.yml\n"
            "    outputs: [{name: config, path: config.yml, sensitivity: restricted}]\n"
            "    consumers: [{node: indexer, mount_destination: /etc/config.yml, access_mode: read_only}]\n"
            "    ordering_dependencies:",
        )
    else:
        mutation = mutation.replace(
            "    consumers:",
            "    lifecycle: retain\n    access_mode: read_write_once\n    consumers:",
        )
    invalid_sdl = textwrap.dedent(f"name: invalid\nnodes:\n  indexer: {{type: compute, os: linux}}\n{mutation}\n")
    with pytest.raises(SDLValidationError, match=message):
        parse_sdl(invalid_sdl)


def test_stateful_resource_dependency_cycle_fails_before_backend_dispatch():
    scenario = parse_sdl(
        textwrap.dedent(
            """
            name: cycle
            nodes:
              indexer: {type: compute, os: linux}
            persistent_volumes:
              a:
                lifecycle: retain
                access_mode: read_write_once
                consumers:
                  - {node: indexer, mount_destination: /a, access_mode: read_write}
                ordering_dependencies: [persistent_volumes.b]
              b:
                lifecycle: retain
                access_mode: read_write_once
                consumers:
                  - {node: indexer, mount_destination: /b, access_mode: read_write}
                ordering_dependencies: [persistent_volumes.a]
            """
        )
    )

    execution = plan(compile_runtime_model(scenario), create_stub_manifest())
    assert not execution.is_valid
    assert any(diagnostic.code == "provisioning.ordering-cycle" for diagnostic in execution.diagnostics)


def test_stateful_resources_reject_ambiguous_bare_dependency_during_semantic_admission():
    invalid_sdl = textwrap.dedent(
        """
        name: ambiguous-stateful-dependency
        nodes:
          vm: {type: compute, os: linux}
        generated_artifacts:
          shared:
            generator: rendered_config
            lifecycle: regenerate_on_change
            provenance: config.yml
            outputs: [{name: config, path: config.yml, sensitivity: restricted}]
            consumers: [{node: vm, mount_destination: /etc/config.yml, access_mode: read_only}]
          consumer:
            generator: rendered_config
            lifecycle: regenerate_on_change
            provenance: consumer.yml
            outputs: [{name: consumer, path: consumer.yml, sensitivity: restricted}]
            consumers: [{node: vm, mount_destination: /etc/consumer.yml, access_mode: read_only}]
            ordering_dependencies: [shared]
        persistent_volumes:
          shared:
            lifecycle: retain
            access_mode: read_write_once
            consumers: [{node: vm, mount_destination: /var/lib/shared, access_mode: read_write}]
        """
    )

    with pytest.raises(SDLValidationError, match="ambiguous.*generated_artifacts.shared.*persistent_volumes.shared"):
        parse_sdl(invalid_sdl)


def test_composed_stateful_resources_reject_ambiguous_bare_dependency(tmp_path: Path):
    module = tmp_path / "stateful-module.yaml"
    module.write_text(
        textwrap.dedent(
            """
            name: stateful-module
            version: 1.0.0
            module:
              id: acme/stateful-module
              version: 1.0.0
              exports:
                nodes: [vm]
                generated_artifacts: [shared, consumer]
                persistent_volumes: [shared]
            nodes:
              vm: {type: compute, os: linux}
            generated_artifacts:
              shared:
                generator: rendered_config
                lifecycle: regenerate_on_change
                provenance: shared.yml
                outputs: [{name: shared, path: shared.yml, sensitivity: restricted}]
                consumers: [{node: vm, mount_destination: /etc/shared.yml, access_mode: read_only}]
              consumer:
                generator: rendered_config
                lifecycle: regenerate_on_change
                provenance: consumer.yml
                outputs: [{name: consumer, path: consumer.yml, sensitivity: restricted}]
                consumers: [{node: vm, mount_destination: /etc/consumer.yml, access_mode: read_only}]
                ordering_dependencies: [shared]
            persistent_volumes:
              shared:
                lifecycle: retain
                access_mode: read_write_once
                consumers: [{node: vm, mount_destination: /var/lib/shared, access_mode: read_write}]
            """
        ),
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: root
            imports:
              - source: local:stateful-module.yaml
                namespace: imported
                version: 1.0.0
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(SDLValidationError, match="ambiguous.*generated_artifacts.shared.*persistent_volumes.shared"):
        parse_sdl_file(root)


@pytest.mark.parametrize(
    ("resources", "message", "error_type"),
    [
        (
            """
            generated_artifacts:
              config:
                generator: rendered_config
                lifecycle: regenerate_on_change
                provenance: config.yml
                outputs: [{name: config, path: config.yml, sensitivity: restricted}]
                consumers: [{node: first, mount_destination: /srv/shared, access_mode: read_only}]
            persistent_volumes:
              data:
                lifecycle: retain
                access_mode: read_write_once
                consumers: [{node: first, mount_destination: /srv/shared, access_mode: read_write}]
            """,
            "mount_destination.*already consumed",
            SDLValidationError,
        ),
        (
            """
            generated_artifacts:
              config:
                generator: rendered_config
                lifecycle: regenerate_on_change
                provenance: config.yml
                outputs: [{name: config, path: config.yml, sensitivity: restricted}]
                consumers: [{node: first, mount_destination: /etc/config.yml, access_mode: read_write}]
            """,
            "generated artifact consumers must be read_only",
            SDLParseError,
        ),
        (
            """
            persistent_volumes:
              data:
                lifecycle: retain
                access_mode: read_write_once
                consumers:
                  - {node: first, mount_destination: /srv/first, access_mode: read_write}
                  - {node: second, mount_destination: /srv/second, access_mode: read_write}
            """,
            "read_write_once.*at most one writer node",
            SDLParseError,
        ),
        (
            """
            persistent_volumes:
              data:
                lifecycle: retain
                access_mode: read_write_once
                consumers: [{node: windows, mount_destination: /srv/data, access_mode: read_write}]
            """,
            "POSIX.*Windows",
            SDLValidationError,
        ),
        (
            """
            persistent_volumes:
              data:
                lifecycle: retain
                access_mode: read_write_once
                consumers: [{node: first, mount_destination: //srv/data, access_mode: read_write}]
            """,
            "canonical contained POSIX",
            SDLParseError,
        ),
    ],
)
def test_stateful_resources_reject_cross_resource_access_conflicts(
    resources: str,
    message: str,
    error_type: type[Exception],
):
    invalid_sdl = textwrap.dedent(
        """
        name: invalid-stateful-access
        nodes:
          first: {type: compute, os: linux}
          second: {type: compute, os: linux}
          windows: {type: compute, os: windows}
        """
    ) + textwrap.dedent(resources)

    with pytest.raises(error_type, match=message):
        parse_sdl(invalid_sdl)


@pytest.mark.parametrize(
    "invalid_path",
    [
        ".",
        "config//app.yml",
        "config/./app.yml",
        "config\\app.yml",
    ],
)
def test_generated_artifact_output_paths_must_be_canonical_posix(invalid_path: str):
    invalid_sdl = textwrap.dedent(
        f"""
        name: invalid-output-path
        nodes:
          vm: {{type: compute, os: linux}}
        generated_artifacts:
          config:
            generator: rendered_config
            lifecycle: regenerate_on_change
            provenance: config.yml
            outputs: [{{name: config, path: {invalid_path!r}, sensitivity: restricted}}]
            consumers: [{{node: vm, mount_destination: /etc/config.yml, access_mode: read_only}}]
        """
    )

    with pytest.raises(SDLParseError, match="canonical contained POSIX"):
        parse_sdl(invalid_sdl)


def test_stateful_collection_schema_rejects_exact_duplicates():
    payload = {
        "name": "duplicate-stateful-members",
        "nodes": {"vm": {"type": "compute", "os": "linux"}},
        "generated_artifacts": {
            "config": {
                "generator": "rendered_config",
                "lifecycle": "regenerate_on_change",
                "provenance": "config.yml",
                "outputs": [
                    {"name": "config", "path": "config.yml", "sensitivity": "restricted"},
                    {"name": "config", "path": "config.yml", "sensitivity": "restricted"},
                ],
                "consumers": [{"node": "vm", "mount_destination": "/etc/config.yml", "access_mode": "read_only"}],
            }
        },
    }

    schema = schema_bundle()["sdl-authoring-input-v1"]
    assert not Draft202012Validator(schema).is_valid(payload)


def test_stateful_schema_discloses_model_only_semantic_invariants():
    schema = schema_bundle()["sdl-authoring-input-v1"]
    invariant_ids = {entry["id"] for entry in schema["x-raes-invariants"]}

    assert {
        "stateful-generated-artifact-semantics",
        "stateful-persistent-volume-semantics",
        "stateful-cross-resource-semantics",
    } <= invariant_ids
    assert schema["x-raes-semantic-profile"]["required"] is True

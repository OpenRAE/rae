"""Tests for SDL structural models (Pydantic validation)."""

import pytest
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError
from raes._source import Source
from raes.conditions import Condition
from raes.entities import Entity, ExerciseRole, flatten_entities
from raes.features import Feature, FeatureType
from raes.infrastructure import ACLAction, ACLRule, InfraNode, SimpleProperties
from raes.nodes import (
    ContainerImageBuildProvenance,
    DatabaseAuthMethod,
    DatabaseEngine,
    DatabaseGrant,
    DatabaseListener,
    DatabaseObjectOrigin,
    DatabaseProtocol,
    DatabaseRoleType,
    DatabaseSchema,
    DatabaseSetting,
    DatabaseSettingProvenance,
    DatabaseTable,
    DnsRecordClass,
    DnsRecordType,
    DnsResourceRecordSet,
    DnsRuntimeSetting,
    DnssecValidationMode,
    DnsServerImplementation,
    DnsServiceRole,
    DockerfileInstruction,
    DockerfileInstructionKind,
    ImageAttestation,
    ImageAttestationStatus,
    ImageAttestationType,
    ImageBuildArg,
    ImageConfig,
    ImageCopiedSource,
    ImageEnvironmentDefault,
    ImageLayer,
    ImageSourceInput,
    ImageVerificationStatus,
    Node,
    NodeType,
    RelationshipProxyUpstream,
    Resources,
    Role,
    RuntimeApplicationDisclosure,
    RuntimeApplicationExposedField,
    RuntimeApplicationParameter,
    RuntimeApplicationParameterLocation,
    RuntimeApplicationProtocol,
    RuntimeApplicationRedirect,
    RuntimeApplicationResponse,
    RuntimeApplicationRoute,
    RuntimeApplicationRouteUpstreamScheme,
    RuntimeApplicationRouteUpstreamTarget,
    RuntimeApplicationSurface,
    RuntimeCapabilityOverrideScope,
    RuntimeCapabilityPolicy,
    RuntimeContainerConfiguration,
    RuntimeControlInterface,
    RuntimeControlInterfaceAccess,
    RuntimeControlInterfaceKind,
    RuntimeDatabaseService,
    RuntimeEnvironmentValueClassification,
    RuntimeEnvironmentVariableProvenance,
    RuntimeFileService,
    RuntimeFileServiceAccessEffect,
    RuntimeFileServiceAccessOutcome,
    RuntimeFileServiceAccessRule,
    RuntimeFileServiceCredentialClassification,
    RuntimeFileServicePrincipal,
    RuntimeFileServicePrincipalKind,
    RuntimeFileServiceProtocol,
    RuntimeFileServiceShare,
    RuntimeFileShareKind,
    RuntimeFilesystemEntryType,
    RuntimeFilesystemPresence,
    RuntimeFilesystemStability,
    RuntimeIdentityAttribute,
    RuntimeIdentityAuthorityKind,
    RuntimeIdentityAuthorityProtocol,
    RuntimeIdentityProvenance,
    RuntimeIdentityRecordOrigin,
    RuntimeIdentityRelationshipKind,
    RuntimeIdentitySubjectKind,
    RuntimeLocalGroup,
    RuntimeLocalIdentityInventory,
    RuntimeLocalUser,
    RuntimeMount,
    RuntimeMountPropagation,
    RuntimeMountSourceKind,
    RuntimeNetworkBackendDetail,
    RuntimeNetworkDriver,
    RuntimeNetworkEndpoint,
    RuntimeNetworkRealization,
    RuntimeProcessCapabilityOverride,
    RuntimeProcessRole,
    RuntimePublishedPort,
    RuntimeRestartPolicy,
    RuntimeSensitivityClassification,
    RuntimeSoftwareComponentProvenance,
    RuntimeSoftwareComponentType,
    RuntimeSudoPrincipalKind,
    RuntimeSudoRule,
    parse_ram,
)
from raes.objectives import Objective, ObjectiveSuccess, ObjectiveWindow
from raes.orchestration import (
    Inject,
    Script,
    Story,
    Workflow,
    WorkflowPredicate,
    WorkflowStep,
    WorkflowStepOutcome,
    WorkflowStepType,
    parse_duration,
)
from raes.vulnerabilities import Vulnerability

# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


class TestSource:
    def test_basic(self):
        s = Source(name="pkg", version="1.0")
        assert s.name == "pkg"
        assert s.version == "1.0"

    def test_default_version(self):
        s = Source(name="pkg")
        assert s.version == "*"

    def test_build_defaults_to_none(self):
        s = Source(name="pkg")
        assert s.build is None


class TestContainerImageBuildProvenance:
    """Tests for the SDL container image build/provenance surface (issue #364)."""

    def _full_build(self) -> dict:
        return {
            "base_image": "python:3.12-slim",
            "base_image_digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
            "dockerfile_path": "containers/webapp/Dockerfile",
            "instructions": [
                {"instruction": "from", "arguments": ["python:3.12-slim"]},
                {"instruction": "arg", "arguments": ["APP_VERSION"]},
                {"instruction": "copy", "arguments": ["webapp/app.py", "/app/app.py"]},
                {"instruction": "entrypoint", "arguments": ["/entrypoint.sh"]},
            ],
            "layers": [
                {
                    "digest": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
                    "created_by": "FROM python:3.12-slim",
                    "size": "31000000",
                },
                {"created_by": "ENV APP_HOME=/app", "empty": "true"},
            ],
            "build_args": [
                {"name": "APP_VERSION", "value": "1.4.2", "value_classification": "plain"},
                {"name": "PIP_INDEX_TOKEN", "value_classification": "redacted"},
            ],
            "copied_sources": [
                {"source_path": "webapp/app.py", "destination_path": "/app/app.py"},
                {
                    "source_path": "containers/webapp/entrypoint.sh",
                    "destination_path": "/entrypoint.sh",
                    "from_stage": "builder",
                },
            ],
            "config": {
                "entrypoint": "/entrypoint.sh",
                "command": ["gunicorn", "app:app"],
                "working_directory": "/app",
                "exposed_ports": ["8080/tcp"],
                "labels": {"org.opencontainers.image.source": "https://example.test/techvault"},
                "default_environment": [
                    {"name": "APP_HOME", "value": "/app", "value_classification": "plain"},
                ],
            },
            "source_inputs": [
                {
                    "identifier": "webapp-app",
                    "source_path": "webapp/app.py",
                    "destination_path": "/app/app.py",
                    "checksum": "4f8c2d",
                    "checksum_algorithm": "sha256",
                },
            ],
            "attestation": {
                "status": "absent",
                "verification": "unverified",
                "attestation_type": "none",
            },
        }

    def test_source_carries_full_build_provenance(self):
        s = Source(name="techvault-webapp", version="local", build=self._full_build())

        assert s.build is not None
        build = s.build
        assert build.base_image == "python:3.12-slim"
        assert build.dockerfile_path == "containers/webapp/Dockerfile"
        assert build.instructions[0].instruction == DockerfileInstructionKind.FROM
        assert build.instructions[2].arguments == ["webapp/app.py", "/app/app.py"]
        assert build.layers[0].size == 31000000
        assert build.layers[1].empty is True
        assert build.layers[1].digest == ""
        assert build.build_args[0].value == "1.4.2"
        assert build.copied_sources[1].from_stage == "builder"
        assert build.config is not None
        assert build.config.entrypoint == ["/entrypoint.sh"]
        assert build.config.working_directory == "/app"
        assert build.config.labels["org.opencontainers.image.source"] == "https://example.test/techvault"
        assert build.source_inputs[0].checksum_algorithm == "sha256"
        assert build.attestation is not None
        assert build.attestation.status == ImageAttestationStatus.ABSENT
        assert build.attestation.verification == ImageVerificationStatus.UNVERIFIED
        assert build.attestation.attestation_type == ImageAttestationType.NONE

    def test_instruction_kind_normalizes_case_and_hyphen(self):
        instruction = DockerfileInstruction(instruction="HEALTHCHECK", arguments="curl localhost")
        assert instruction.instruction == DockerfileInstructionKind.HEALTHCHECK
        assert instruction.arguments == ["curl localhost"]

    def test_instruction_rejects_unknown_kind(self):
        with pytest.raises(ValidationError, match="instruction must be one of"):
            DockerfileInstruction(instruction="not-a-real-instruction")

    def test_build_arg_redacted_value_must_be_omitted(self):
        with pytest.raises(ValidationError, match="redacted build arguments must omit value"):
            ImageBuildArg(name="SECRET", value="leaked", value_classification="redacted")

    def test_build_arg_rejects_name_with_equals(self):
        with pytest.raises(ValidationError, match="must not contain '='"):
            ImageBuildArg(name="A=B")

    def test_image_environment_default_redacted_value_must_be_omitted(self):
        with pytest.raises(ValidationError, match="redacted image environment variables must omit value"):
            ImageEnvironmentDefault(name="TOKEN", value="leaked", value_classification="redacted")

    def test_copied_source_destination_must_be_absolute(self):
        with pytest.raises(ValidationError, match="destination_path must be an absolute path"):
            ImageCopiedSource(source_path="webapp/app.py", destination_path="app/app.py")

    def test_copied_source_rejects_empty_source_path(self):
        with pytest.raises(ValidationError, match="source_path must be a non-empty string"):
            ImageCopiedSource(source_path="  ", destination_path="/app/app.py")

    def test_image_config_working_directory_must_be_absolute(self):
        with pytest.raises(ValidationError, match="working_directory must be an absolute path"):
            ImageConfig(working_directory="app")

    def test_image_config_rejects_duplicate_default_environment(self):
        with pytest.raises(ValidationError, match="Duplicate image environment variable 'APP_HOME'"):
            ImageConfig(
                default_environment=[
                    {"name": "APP_HOME", "value": "/app"},
                    {"name": "APP_HOME", "value": "/srv"},
                ],
            )

    def test_source_input_checksum_requires_algorithm(self):
        with pytest.raises(ValidationError, match="checksum requires checksum_algorithm"):
            ImageSourceInput(identifier="webapp-app", checksum="4f8c2d")

    def test_source_input_algorithm_requires_checksum(self):
        with pytest.raises(ValidationError, match="checksum_algorithm requires checksum"):
            ImageSourceInput(identifier="webapp-app", checksum_algorithm="sha256")

    def test_source_input_destination_must_be_absolute(self):
        with pytest.raises(ValidationError, match="destination_path must be an absolute path"):
            ImageSourceInput(identifier="webapp-app", destination_path="app/app.py")

    def test_attestation_absent_cannot_be_verified(self):
        with pytest.raises(ValidationError, match="absent attestation cannot have a verified"):
            ImageAttestation(status="absent", verification="verified")

    def test_attestation_absent_unverified_is_distinct_from_failed(self):
        absent = ImageAttestation(status="absent", verification="unverified")
        failed = ImageAttestation(status="present", verification="failed")
        assert absent.status == ImageAttestationStatus.ABSENT
        assert absent.verification == ImageVerificationStatus.UNVERIFIED
        assert failed.verification == ImageVerificationStatus.FAILED

    def test_build_rejects_duplicate_build_arg(self):
        with pytest.raises(ValidationError, match="Duplicate build argument 'APP_VERSION'"):
            ContainerImageBuildProvenance(
                build_args=[{"name": "APP_VERSION"}, {"name": "APP_VERSION"}],
            )

    def test_build_rejects_duplicate_source_input_identifier(self):
        with pytest.raises(ValidationError, match="Duplicate source input identifier 'webapp-app'"):
            ContainerImageBuildProvenance(
                source_inputs=[{"identifier": "webapp-app"}, {"identifier": "webapp-app"}],
            )

    def test_build_rejects_unknown_field(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            ContainerImageBuildProvenance(not_a_field="x")

    def test_layer_supports_variable_placeholders(self):
        layer = ImageLayer(digest="${layer_digest}", size="${layer_size}")
        assert layer.digest == "${layer_digest}"
        assert layer.size == "${layer_size}"


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


class TestParseRam:
    def test_integer(self):
        assert parse_ram(4096) == 4096

    def test_gib_string(self):
        assert parse_ram("4 GiB") == 4 * 1073741824

    def test_mib_string(self):
        assert parse_ram("512 MiB") == 512 * 1048576

    def test_bare_digits(self):
        assert parse_ram("1024") == 1024

    def test_invalid_string(self):
        with pytest.raises(ValueError, match="Invalid RAM"):
            parse_ram("four gigabytes")

    @pytest.mark.parametrize("value", [0, -1, True])
    def test_rejects_non_positive_or_bool_values(self, value):
        with pytest.raises(ValueError, match="RAM"):
            parse_ram(value)


class TestResources:
    def test_human_readable_ram(self):
        r = Resources(ram="2 gib", cpu=2)
        assert r.ram == 2 * 1073741824

    def test_integer_ram(self):
        r = Resources(ram=1024, cpu=1)
        assert r.ram == 1024

    def test_variable_placeholders(self):
        r = Resources(ram="${ram_bytes}", cpu="${cpu_cores}")
        assert r.ram == "${ram_bytes}"
        assert r.cpu == "${cpu_cores}"

    def test_rejects_non_positive_ram(self):
        with pytest.raises(ValidationError, match="RAM"):
            Resources(ram=0, cpu=1)


class TestNode:
    def test_vm_node(self):
        n = Node(
            type="compute",
            source={"name": "ubuntu", "version": "22.04"},
            resources={"ram": "4 gib", "cpu": 2},
        )
        assert n.type == NodeType.COMPUTE

    def test_switch_node(self):
        n = Node(type="switch")
        assert n.type == NodeType.SWITCH

    def test_switch_rejects_source(self):
        with pytest.raises(ValidationError, match="Switch.*source"):
            Node(type="switch", source={"name": "pkg"})

    def test_switch_rejects_resources(self):
        with pytest.raises(ValidationError, match="Switch.*resources"):
            Node(type="switch", resources={"ram": "1 gib", "cpu": 1})

    @pytest.mark.parametrize(
        ("field_name", "value"),
        [
            ("os", "linux"),
            ("architecture", "x86_64"),
            ("os_version", "22.04"),
            ("features", {"nginx": ""}),
            ("conditions", {"health-check": ""}),
            ("injects", {"email": ""}),
            ("roles", {"admin": {"username": "root"}}),
            ("services", [{"port": 80, "name": "http"}]),
            ("asset_value", {"confidentiality": "high"}),
            ("runtime", {"processes": [{"pid": 1, "command": "./shufflebackend"}]}),
        ],
    )
    def test_switch_rejects_other_vm_only_fields(self, field_name, value):
        with pytest.raises(ValidationError, match="Switch") as excinfo:
            Node(type="switch", **{field_name: value})
        assert field_name in excinfo.value.errors(include_input=False)[0]["msg"]

    def test_vm_runtime_configuration_surfaces(self):
        n = Node(
            type="compute",
            runtime={
                "mounts": [
                    {
                        "target": "/shuffle-database",
                        "source": "aptl_shuffle_data",
                        "source_sensitivity": "plain",
                        "source_kind": "volume",
                    }
                ],
                "local_control_interfaces": [
                    {
                        "control_interface_id": "docker-sock",
                        "path": "/run/docker.sock",
                        "kind": "unix_socket",
                        "protocol": "docker",
                        "bind_source_sensitivity": "operator_secret",
                        "access": "read_write",
                    }
                ],
                "processes": [
                    {
                        "pid": 1,
                        "command": "./shufflebackend",
                        "user": "root",
                        "working_directory": "/app",
                    }
                ],
                "packages": [
                    {
                        "manager": "apk",
                        "name": "musl",
                        "version": "1.2.4-r2",
                    }
                ],
                "software_components": [
                    {
                        "component_id": "shuffle-backend-app",
                        "name": "shuffle-backend",
                        "version": "1.2.3",
                        "component_type": "application",
                        "provenance": "package_manager",
                        "ecosystem": "go",
                        "purl": "pkg:golang/github.com/frikky/shuffle@1.2.3",
                        "cpe": "cpe:2.3:a:shuffle:shuffle:1.2.3:*:*:*:*:*:*:*",
                        "package_manager": "apk",
                        "package_name": "shuffle-backend",
                        "package_version": "1.2.3-r0",
                        "manifest_path": "/app/go.mod",
                        "installed_paths": ["/app/shufflebackend", "/app/go.mod"],
                        "hashes": [{"algorithm": "sha256", "value": "abc123"}],
                    }
                ],
                "dependency_manifests": [
                    {
                        "ecosystem": "go",
                        "path": "/app/go.mod",
                        "format": "go-module",
                    }
                ],
            },
        )

        runtime = n.runtime
        assert runtime is not None
        assert runtime.mounts[0].target == "/shuffle-database"
        assert runtime.mounts[0].source_sensitivity == RuntimeSensitivityClassification.PLAIN
        assert runtime.mounts[0].source_kind == RuntimeMountSourceKind.VOLUME
        assert runtime.local_control_interfaces[0].kind == RuntimeControlInterfaceKind.UNIX_SOCKET
        assert runtime.local_control_interfaces[0].bind_source == ""
        assert (
            runtime.local_control_interfaces[0].bind_source_sensitivity
            == RuntimeSensitivityClassification.OPERATOR_SECRET
        )
        assert runtime.local_control_interfaces[0].access == RuntimeControlInterfaceAccess.READ_WRITE
        assert len(runtime.processes) == 1
        assert runtime.processes[0].pid == 1
        assert runtime.processes[0].command == ["./shufflebackend"]
        assert runtime.processes[0].user == "root"
        assert runtime.processes[0].working_directory == "/app"
        assert runtime.packages[0].manager == "apk"
        assert runtime.packages[0].name == "musl"
        assert runtime.packages[0].version == "1.2.4-r2"
        assert runtime.software_components[0].component_id == "shuffle-backend-app"
        assert runtime.software_components[0].name == "shuffle-backend"
        assert runtime.software_components[0].version == "1.2.3"
        assert runtime.software_components[0].component_type == RuntimeSoftwareComponentType.APPLICATION
        assert runtime.software_components[0].provenance == RuntimeSoftwareComponentProvenance.PACKAGE_MANAGER
        assert runtime.software_components[0].ecosystem == "go"
        assert runtime.software_components[0].purl == "pkg:golang/github.com/frikky/shuffle@1.2.3"
        assert runtime.software_components[0].cpe == "cpe:2.3:a:shuffle:shuffle:1.2.3:*:*:*:*:*:*:*"
        assert runtime.software_components[0].package_manager == "apk"
        assert runtime.software_components[0].package_name == "shuffle-backend"
        assert runtime.software_components[0].package_version == "1.2.3-r0"
        assert runtime.software_components[0].manifest_path == "/app/go.mod"
        assert runtime.software_components[0].installed_paths == ["/app/shufflebackend", "/app/go.mod"]
        assert runtime.software_components[0].hashes[0].algorithm == "sha256"
        assert runtime.dependency_manifests[0].ecosystem == "go"
        assert runtime.dependency_manifests[0].path == "/app/go.mod"
        assert runtime.dependency_manifests[0].format == "go-module"

    @pytest.mark.parametrize(
        "runtime",
        [
            {"health": {"status": "healthy"}},
            {
                "package_vulnerabilities": [
                    {
                        "id": "CVE-2026-12345",
                        "package_name": "musl",
                        "installed_version": "1.2.4-r2",
                        "scanner": "trivy",
                        "image_digest": "sha256:abc123",
                        "scan_time": "2026-05-20T12:00:00Z",
                    }
                ]
            },
            {
                "network": {
                    "endpoints": [
                        {"network": "aptl-dmz", "network_id": "docker-network-id"},
                    ]
                }
            },
            {
                "network": {
                    "endpoints": [
                        {"network": "aptl-dmz", "network_id_stability": "ephemeral"},
                    ]
                }
            },
            {
                "network": {
                    "endpoints": [
                        {"network": "aptl-dmz", "endpoint_id": "docker-endpoint-id"},
                    ]
                }
            },
            {
                "network": {
                    "endpoints": [
                        {"network": "aptl-dmz", "endpoint_id_stability": "ephemeral"},
                    ]
                }
            },
            {
                "network": {
                    "endpoints": [
                        {"network": "aptl-dmz", "backend_generated": True},
                    ]
                }
            },
            {
                "network": {
                    "endpoints": [
                        {"network": "aptl-dmz", "generated_dns_names": ["generated-id"]},
                    ]
                }
            },
            {
                "software_components": [
                    {
                        "component_id": "shuffle-backend-app",
                        "name": "shuffle-backend",
                        "provenance": "scanner",
                    }
                ]
            },
            {
                "software_components": [
                    {
                        "component_id": "shuffle-backend-app",
                        "name": "shuffle-backend",
                        "provenance": "sbom",
                    }
                ]
            },
            {
                "software_components": [
                    {
                        "component_id": "shuffle-backend-app",
                        "name": "shuffle-backend",
                        "provenance": "filesystem",
                    }
                ]
            },
            {
                "software_components": [
                    {
                        "component_id": "shuffle-backend-app",
                        "name": "shuffle-backend",
                        "provenance": "process_inspection",
                    }
                ]
            },
        ],
    )
    def test_vm_runtime_rejects_observation_only_capture_facts(self, runtime):
        with pytest.raises(ValidationError):
            Node(type="compute", runtime=runtime)

    def test_vm_runtime_rejects_duplicate_software_component_id(self):
        with pytest.raises(ValidationError, match="Duplicate runtime software component 'webapp'"):
            Node(
                type="compute",
                runtime={
                    "software_components": [
                        {"component_id": "webapp", "name": "web application"},
                        {"component_id": "webapp", "name": "bundled library"},
                    ],
                },
            )

    def test_vm_runtime_software_component_paths_must_be_absolute(self):
        with pytest.raises(ValidationError, match="manifest_path must be an absolute path"):
            Node(
                type="compute",
                runtime={
                    "software_components": [
                        {
                            "component_id": "webapp",
                            "name": "web application",
                            "manifest_path": "app/package-lock.json",
                        }
                    ],
                },
            )

    def test_vm_runtime_operational_surfaces(self):
        n = Node(
            type="compute",
            runtime={
                "processes": [
                    {
                        "name": "supervisord",
                        "pid": 1,
                        "command": "supervisord -n",
                        "role": "supervisor",
                    },
                    {
                        "name": "gunicorn",
                        "pid": 42,
                        "parent_pid": 1,
                        "command": ["gunicorn", "app:app"],
                        "role": "worker",
                    },
                    {
                        "name": "wazuh-agentd",
                        "parent_pid": 1,
                        "command_redacted": True,
                        "role": "agent",
                    },
                ],
                "environment": [
                    {
                        "name": "DJANGO_SETTINGS_MODULE",
                        "value": "techvault.settings",
                        "value_classification": "plain",
                        "provenance": "compose",
                    },
                    {
                        "name": "TECHVAULT_ADMIN_PASSWORD",
                        "value_classification": "redacted",
                        "provenance": "operator",
                    },
                    {
                        "name": "SCENARIO_FIXTURE_TOKEN",
                        "value": "fixture-token",
                        "value_classification": "secret_fixture",
                        "provenance": "compose",
                    },
                ],
                "linux_capabilities": {
                    "required": ["CAP_NET_ADMIN"],
                    "effective": "CAP_NET_ADMIN",
                },
                "operational_policy": {
                    "restart": "unless-stopped",
                    "resource_limits": {
                        "memory": "512 MiB",
                        "cpu": "0.5",
                        "pids": "128",
                    },
                },
            },
        )

        runtime = n.runtime
        assert runtime is not None
        assert runtime.processes[0].role == RuntimeProcessRole.SUPERVISOR
        assert runtime.processes[1].parent_pid == 1
        assert runtime.processes[1].command == ["gunicorn", "app:app"]
        assert runtime.processes[2].command_redacted is True
        assert runtime.environment[1].value == ""
        assert runtime.environment[1].value_classification == RuntimeEnvironmentValueClassification.REDACTED
        assert runtime.environment[1].provenance == RuntimeEnvironmentVariableProvenance.OPERATOR
        assert runtime.environment[2].value_classification == RuntimeEnvironmentValueClassification.SECRET_FIXTURE
        assert runtime.linux_capabilities is not None
        assert runtime.linux_capabilities.required == ["CAP_NET_ADMIN"]
        assert runtime.linux_capabilities.effective == ["CAP_NET_ADMIN"]
        assert runtime.operational_policy is not None
        assert runtime.operational_policy.restart == RuntimeRestartPolicy.UNLESS_STOPPED
        assert runtime.operational_policy.resource_limits is not None
        assert runtime.operational_policy.resource_limits.memory == 512 * 1048576
        assert runtime.operational_policy.resource_limits.cpu == 0.5
        assert runtime.operational_policy.resource_limits.pids == 128

    def test_vm_runtime_filesystem_inventory_surfaces(self):
        n = Node(
            type="compute",
            runtime={
                "filesystem_inventory": [
                    {
                        "path": "/app/app.py",
                        "entry_type": "file",
                        "owner_user": "root",
                        "owner_group": "root",
                        "uid": "0",
                        "gid": 0,
                        "mode": 0o644,
                        "size": "4096",
                        "content_digest": "4f8c2d",
                        "digest_algorithm": "sha256",
                        "source_path": "src/webapp/app.py",
                        "provenance": "python-package",
                        "stability": "stable",
                        "sensitivity": "plain",
                    },
                    {
                        "path": "/var/log/gunicorn/access.log",
                        "entry_type": "file",
                        "mode": "0600",
                        "stability": "log",
                        "sensitivity": "operator-secret",
                    },
                    {
                        "path": "/run/secrets/fixture-token",
                        "entry_type": "file",
                        "stability": "runtime-created",
                        "sensitivity": "secret-fixture",
                    },
                ],
            },
        )

        runtime = n.runtime
        assert runtime is not None
        assert runtime.filesystem_inventory[0].path == "/app/app.py"
        assert runtime.filesystem_inventory[0].entry_type == RuntimeFilesystemEntryType.FILE
        assert runtime.filesystem_inventory[0].uid == 0
        assert runtime.filesystem_inventory[0].gid == 0
        assert runtime.filesystem_inventory[0].mode == "0644"
        assert runtime.filesystem_inventory[0].size == 4096
        assert runtime.filesystem_inventory[0].digest_algorithm == "sha256"
        assert runtime.filesystem_inventory[0].content_digest == "4f8c2d"
        assert runtime.filesystem_inventory[0].source_path == "src/webapp/app.py"
        assert runtime.filesystem_inventory[0].stability == RuntimeFilesystemStability.STABLE
        assert runtime.filesystem_inventory[0].sensitivity == RuntimeSensitivityClassification.PLAIN
        assert runtime.filesystem_inventory[1].stability == RuntimeFilesystemStability.LOG
        assert runtime.filesystem_inventory[1].sensitivity == RuntimeSensitivityClassification.OPERATOR_SECRET
        assert runtime.filesystem_inventory[2].stability == RuntimeFilesystemStability.RUNTIME_CREATED
        assert runtime.filesystem_inventory[2].sensitivity == RuntimeSensitivityClassification.SECRET_FIXTURE

    def test_vm_runtime_filesystem_entry_presence_defaults_to_present(self):
        n = Node(
            type="compute",
            runtime={
                "filesystem_inventory": [
                    {"path": "/etc/hosts", "entry_type": "file"},
                ],
            },
        )

        entry = n.runtime.filesystem_inventory[0]
        assert entry.presence == RuntimeFilesystemPresence.PRESENT

    def test_vm_runtime_filesystem_entry_expected_absent_preserves_entry_type(self):
        n = Node(
            type="compute",
            runtime={
                "filesystem_inventory": [
                    {
                        "path": "/root/.ssh/authorized_keys",
                        "entry_type": "file",
                        "presence": "expected_absent",
                        "description": "Deploy-key path attempted by setup but not present at capture.",
                    },
                ],
            },
        )

        entry = n.runtime.filesystem_inventory[0]
        assert entry.presence == RuntimeFilesystemPresence.EXPECTED_ABSENT
        assert entry.entry_type == RuntimeFilesystemEntryType.FILE

    def test_vm_runtime_file_service_surface(self):
        n = Node(
            type="compute",
            runtime={
                "file_services": [
                    {
                        "file_service_id": "fileshare-smb",
                        "service": "smb",
                        "protocol": "smb",
                        "backend": "samba-4.x",
                        "description": "TechVault fileshare published over SMB.",
                        "shares": [
                            {
                                "share_id": "public",
                                "name": "public",
                                "kind": "disk",
                                "backing_path": "/srv/samba/public",
                                "comment": "Anonymous-readable public share.",
                                "read_only": True,
                                "browseable": True,
                                "guest_ok": True,
                                "valid_users": ["guest"],
                            },
                            {
                                "share_id": "deploy-keys",
                                "name": "deploy_keys",
                                "kind": "disk",
                                "backing_path": "/srv/samba/deploy_keys",
                                "read_only": False,
                                "browseable": False,
                                "guest_ok": False,
                                "valid_users": ["svc-fileshare"],
                                "write_users": ["svc-fileshare"],
                            },
                        ],
                        "principals": [
                            {
                                "principal_id": "nobody",
                                "kind": "guest",
                                "name": "nobody",
                                "external_id": "S-1-5-21-0-501",
                                "status": "enabled",
                                "credential_classification": "no_credential",
                                "origin": "built_in",
                            },
                            {
                                "principal_id": "svc-fileshare",
                                "kind": "service_account",
                                "name": "svc-fileshare",
                                "status": "enabled",
                                "credential_classification": "redacted",
                                "origin": "provisioned",
                            },
                        ],
                        "access_rules": [
                            {
                                "rule_id": "public-read",
                                "subject_ref": "nobody",
                                "resource_ref": "public",
                                "action": "read",
                                "effect": "allow",
                                "basis": "share_config",
                            },
                        ],
                        "access_observations": [
                            {
                                "observation_id": "anon-mount-allowed",
                                "subject_ref": "anonymous",
                                "resource_ref": "public",
                                "action": "browse",
                                "outcome": "allowed",
                                "basis": "observed_probe",
                            },
                        ],
                    },
                ],
            },
        )

        service = n.runtime.file_services[0]
        assert service.file_service_id == "fileshare-smb"
        assert service.protocol == RuntimeFileServiceProtocol.SMB
        assert service.shares[0].kind == RuntimeFileShareKind.DISK
        assert service.shares[1].read_only is False
        assert service.principals[0].kind == RuntimeFileServicePrincipalKind.GUEST
        assert service.principals[1].credential_classification == RuntimeFileServiceCredentialClassification.REDACTED
        assert service.access_rules[0].effect == RuntimeFileServiceAccessEffect.ALLOW
        assert service.access_observations[0].outcome == RuntimeFileServiceAccessOutcome.ALLOWED

    def test_vm_runtime_file_service_rejects_duplicate_share_id(self):
        with pytest.raises(ValidationError):
            RuntimeFileService(
                file_service_id="svc",
                service="smb",
                protocol="smb",
                shares=[
                    RuntimeFileServiceShare(share_id="dup", name="a"),
                    RuntimeFileServiceShare(share_id="dup", name="b"),
                ],
            )

    def test_vm_runtime_file_service_rejects_id_collision_across_scopes(self):
        with pytest.raises(ValidationError):
            RuntimeFileService(
                file_service_id="svc",
                service="smb",
                protocol="smb",
                shares=[RuntimeFileServiceShare(share_id="alpha", name="alpha")],
                principals=[
                    RuntimeFileServicePrincipal(
                        principal_id="alpha",
                        kind="user",
                        name="alpha",
                    )
                ],
            )

    def test_vm_runtime_file_service_principal_credential_value_field_is_unrepresentable(self):
        # Raw credential material must not be expressible on the principal
        # record at all (ADR-036 §4, secret-handling gate). The field is
        # absent from the model; SDLModel's ``extra='forbid'`` config rejects
        # any attempt to set it, regardless of credential_classification.
        for field_name in ("credential_value", "credential_hash"):
            for classification in ("strong", "redacted", "no_credential", "${secret_class}"):
                with pytest.raises(ValidationError, match=field_name):
                    RuntimeFileServicePrincipal(
                        principal_id="bad",
                        kind="user",
                        name="bad",
                        credential_classification=classification,
                        **{field_name: "hunter2"},
                    )

    def test_vm_runtime_file_service_rejects_unknown_action_enum(self):
        with pytest.raises(ValidationError):
            RuntimeFileServiceAccessRule(
                rule_id="r",
                subject_ref="s",
                resource_ref="r",
                action="not-an-action",
                effect="allow",
                basis="share_config",
            )

    def test_vm_runtime_filesystem_entry_expected_absent_rejects_present_only_fields(self):
        for field_name, value in (
            ("size", 4096),
            ("content_digest", "deadbeef"),
            ("uid", 0),
            ("gid", 0),
            ("mode", "0644"),
            ("owner_user", "root"),
            ("owner_group", "root"),
            ("digest_algorithm", "sha256"),
        ):
            with pytest.raises(ValidationError, match=field_name):
                Node(
                    type="compute",
                    runtime={
                        "filesystem_inventory": [
                            {
                                "path": "/var/expected/missing",
                                "entry_type": "file",
                                "presence": "expected_absent",
                                field_name: value,
                            },
                        ],
                    },
                )

    def test_vm_runtime_container_host_config_surfaces(self):
        n = Node(
            type="compute",
            runtime={
                "mounts": [
                    {
                        "target": "/var/log/gunicorn",
                        "source": "techvault_gunicorn_logs",
                        "source_kind": "volume",
                        "filesystem_type": "ext4",
                        "read_only": False,
                        "options": ["rw", "nosuid"],
                        "propagation": "rprivate",
                        "stability": "volume-backed",
                        "backend_generated": True,
                    }
                ],
                "container": {
                    "entrypoint": ["/entrypoint.sh"],
                    "command": ["gunicorn", "app:app"],
                    "log_driver": "json-file",
                    "log_options": {"max-size": "10m", "max-file": "3"},
                    "namespaces": {
                        "cgroup": "private",
                        "ipc": "private",
                        "pid": "private",
                        "userns": "host",
                        "uts": "private",
                    },
                    "privileged": False,
                    "read_only_rootfs": False,
                    "publish_all_ports": False,
                    "autoremove": False,
                    "shm_size": "64 MiB",
                    "masked_paths": ["/proc/acpi", "/proc/kcore"],
                    "read_only_paths": "/proc/sys",
                    "cgroup_parent": "/docker",
                    "runtime_name": "runc",
                    "init_process": {
                        "enabled": True,
                        "implementation": "docker-init",
                        "executable_path": "/sbin/docker-init",
                        "reaps_children": True,
                        "argv": ["/sbin/docker-init", "--", "/entrypoint.sh"],
                    },
                    "devices": [
                        {
                            "host_path": "/dev/null",
                            "container_path": "/dev/null",
                            "permissions": "rwm",
                        }
                    ],
                    "device_cgroup_rules": "c 1:3 rwm",
                    "extra_hosts": [{"hostname": "wazuh-manager", "address": "172.20.0.10"}],
                    "dns": ["8.8.8.8"],
                    "dns_options": "ndots:0",
                    "dns_search": ["techvault.local"],
                    "group_add": ["adm", "101"],
                },
            },
        )

        runtime = n.runtime
        assert runtime is not None
        assert runtime.mounts[0].filesystem_type == "ext4"
        assert runtime.mounts[0].propagation == RuntimeMountPropagation.RPRIVATE
        assert runtime.mounts[0].stability == RuntimeFilesystemStability.VOLUME_BACKED
        assert runtime.mounts[0].backend_generated is True
        assert runtime.container is not None
        assert runtime.container.entrypoint == ["/entrypoint.sh"]
        assert runtime.container.command == ["gunicorn", "app:app"]
        assert runtime.container.log_driver == "json-file"
        assert runtime.container.namespaces is not None
        assert runtime.container.namespaces.userns == "host"
        assert runtime.container.privileged is False
        assert runtime.container.shm_size == 64 * 1048576
        assert runtime.container.read_only_paths == ["/proc/sys"]
        assert runtime.container.devices[0].host_path == "/dev/null"
        assert runtime.container.device_cgroup_rules == ["c 1:3 rwm"]
        assert runtime.container.extra_hosts[0].hostname == "wazuh-manager"
        assert runtime.container.dns_options == ["ndots:0"]
        assert runtime.container.group_add == ["adm", "101"]
        assert runtime.container.init_process is not None
        assert runtime.container.init_process.enabled is True
        assert runtime.container.init_process.implementation == "docker-init"
        assert runtime.container.init_process.executable_path == "/sbin/docker-init"
        assert runtime.container.init_process.reaps_children is True
        assert runtime.container.init_process.argv == ["/sbin/docker-init", "--", "/entrypoint.sh"]
        assert runtime.container.init_process.argv_redacted is False

    @pytest.mark.parametrize(
        ("runtime", "message"),
        [
            ({"mounts": [{"target": "shuffle-database", "source": "data"}]}, "target"),
            ({"mounts": [{"target": "/data", "backend_generated": "sometimes"}]}, "backend_generated"),
            ({"mounts": [{"target": "/data"}, {"target": "/data"}]}, "Duplicate runtime mount target"),
            ({"filesystem_inventory": [{"path": "app/app.py"}]}, "path"),
            (
                {"filesystem_inventory": [{"path": "/app/app.py", "content_digest": "abc"}]},
                "content_digest requires digest_algorithm",
            ),
            (
                {"filesystem_inventory": [{"path": "/app/app.py", "digest_algorithm": "sha256"}]},
                "digest_algorithm requires content_digest",
            ),
            ({"filesystem_inventory": [{"path": "/app/app.py", "mode": "888"}]}, "mode"),
            (
                {"filesystem_inventory": [{"path": "/app/app.py"}, {"path": "/app/app.py"}]},
                "Duplicate runtime filesystem path",
            ),
            (
                {"local_control_interfaces": [{"control_interface_id": "docker-sock", "path": "run/docker.sock"}]},
                "path",
            ),
            ({"processes": [{"pid": 0, "command": "./shufflebackend"}]}, "pid"),
            ({"processes": [{"working_directory": "app"}]}, "working_directory"),
            ({"dependency_manifests": [{"ecosystem": "go", "path": "go.mod"}]}, "path"),
            ({"container": {"masked_paths": ["proc/acpi"]}}, "masked_paths"),
            ({"container": {"devices": [{"host_path": "dev/null", "container_path": "/dev/null"}]}}, "host_path"),
            (
                {
                    "container": {
                        "devices": [
                            {"host_path": "/dev/null", "container_path": "/dev/null"},
                            {"host_path": "/dev/null", "container_path": "/dev/null"},
                        ]
                    }
                },
                "Duplicate runtime device mapping",
            ),
            (
                {
                    "container": {
                        "extra_hosts": [
                            {"hostname": "wazuh-manager", "address": "172.20.0.10"},
                            {"hostname": "wazuh-manager", "address": "172.20.0.11"},
                        ]
                    }
                },
                "Duplicate runtime extra host",
            ),
            ({"container": {"security_opt": ["seccomp:unconfined", ""]}}, "security_opt"),
            (
                {"container": {"security_opt": ["seccomp:unconfined", "seccomp:unconfined"]}},
                "Duplicate runtime security option",
            ),
            (
                {"container": {"seccomp_profile": "default", "security_opt": ["seccomp:unconfined"]}},
                "seccomp_profile",
            ),
            (
                {
                    "environment": [
                        {"name": "TECHVAULT_ADMIN_PASSWORD", "value_classification": "redacted"},
                        {"name": "TECHVAULT_ADMIN_PASSWORD", "value_classification": "redacted"},
                    ]
                },
                "Duplicate runtime environment variable",
            ),
            ({"environment": [{"name": "BAD=NAME"}]}, "environment variable name"),
            (
                {"processes": [{"name": "gunicorn"}, {"name": "gunicorn"}]},
                "Duplicate runtime process name",
            ),
            ({"linux_capabilities": {"required": [""]}}, "capability"),
            (
                {
                    "linux_capabilities": {
                        "process_overrides": [
                            {"subject": {"name": "sshd"}, "scope": "subtree", "drop": ["CAP_AUDIT_CONTROL"]},
                            {"subject": {"name": "sshd"}, "scope": "subtree", "drop": ["CAP_NET_ADMIN"]},
                        ]
                    }
                },
                "Duplicate runtime capability override",
            ),
            (
                {
                    "linux_capabilities": {
                        "process_overrides": [{"subject": {}, "scope": "process", "drop": ["CAP_AUDIT_CONTROL"]}]
                    }
                },
                "subject",
            ),
            (
                {"linux_capabilities": {"process_overrides": [{"subject": {"name": "sshd"}, "scope": "process"}]}},
                "capability",
            ),
            (
                {
                    "linux_capabilities": {
                        "process_overrides": [
                            {
                                "subject": {"name": "sshd"},
                                "scope": "totally-not-a-scope",
                                "drop": ["CAP_AUDIT_CONTROL"],
                            }
                        ]
                    }
                },
                "scope",
            ),
            ({"operational_policy": {"resource_limits": {"pids": 0}}}, "pids"),
            (
                {"local_identity": {"users": [{"username": "root"}, {"username": "root"}]}},
                "Duplicate runtime local user",
            ),
            (
                {"local_identity": {"groups": [{"name": "wheel"}, {"name": "wheel"}]}},
                "Duplicate runtime local group",
            ),
            (
                {"local_identity": {"groups": [{"name": "a", "gid": 10}, {"name": "b", "gid": 10}]}},
                "Duplicate runtime local group gid",
            ),
            (
                {
                    "local_identity": {
                        "sudo_rules": [
                            {"principal": "ops", "commands": ["/usr/bin/systemctl"]},
                            {"principal": "ops", "commands": ["/usr/bin/systemctl"]},
                        ]
                    }
                },
                "Duplicate runtime sudo rule",
            ),
            ({"local_identity": {"users": [{"username": "  "}]}}, "username"),
            ({"local_identity": {"users": [{"username": "svc", "home": "var/svc"}]}}, "home"),
            ({"local_identity": {"users": [{"username": "svc", "uid": -1}]}}, "uid"),
            ({"local_identity": {"groups": [{"name": ""}]}}, "group name"),
            (
                {
                    "local_identity": {
                        "sudo_rules": [{"principal": "ops", "command_redacted": True, "commands": ["/bin/sh"]}]
                    }
                },
                "redacted sudo rules must omit commands",
            ),
            (
                {
                    "identity_authorities": [
                        {"identity_authority_id": "techvault-domain"},
                        {"identity_authority_id": "techvault-domain"},
                    ]
                },
                "Duplicate runtime identity authority",
            ),
            (
                {
                    "identity_authorities": [
                        {
                            "identity_authority_id": "techvault-domain",
                            "subjects": [
                                {"subject_id": "alice", "kind": "user", "name": "alice"},
                                {"subject_id": "alice", "kind": "user", "name": "alice"},
                            ],
                        }
                    ]
                },
                "Duplicate runtime identity subject_id",
            ),
            (
                {
                    "identity_authorities": [
                        {
                            "identity_authority_id": "techvault-domain",
                            "relationships": [
                                {
                                    "relationship_id": "alice-admin",
                                    "relationship_type": "member_of",
                                    "source_ref": "alice",
                                    "target_ref": "domain-admins",
                                },
                                {
                                    "relationship_id": "alice-admin",
                                    "relationship_type": "member_of",
                                    "source_ref": "alice",
                                    "target_ref": "domain-admins",
                                },
                            ],
                        }
                    ]
                },
                "Duplicate runtime identity relationship_id",
            ),
            (
                {"container": {"init_process": {"executable_path": "sbin/docker-init"}}},
                "executable_path",
            ),
            (
                {"container": {"init_process": {"enabled": "maybe"}}},
                "enabled",
            ),
            (
                {"container": {"init_process": {"argv_redacted": True, "argv": ["/sbin/docker-init"]}}},
                "redacted init process argv must omit argv",
            ),
        ],
    )
    def test_runtime_configuration_rejects_invalid_runtime_anchors(self, runtime, message):
        with pytest.raises(ValidationError, match=message):
            Node(type="compute", runtime=runtime)

    def test_runtime_init_process_accepts_variable_refs_and_redaction(self):
        n = Node(
            type="compute",
            runtime={
                "container": {
                    "init_process": {
                        "enabled": "${init_enabled}",
                        "reaps_children": "${reaps}",
                        "executable_path": "${init_path}",
                        "argv_redacted": True,
                        "description": "backend-injected reaper",
                    }
                }
            },
        )

        container = n.runtime.container
        assert container is not None
        init = container.init_process
        assert init is not None
        assert init.enabled == "${init_enabled}"
        assert init.reaps_children == "${reaps}"
        assert init.executable_path == "${init_path}"
        assert init.argv_redacted is True
        assert init.argv == []
        assert init.description == "backend-injected reaper"

    def test_runtime_container_records_seccomp_and_security_opt(self):
        container = RuntimeContainerConfiguration(
            seccomp_profile="unconfined",
            security_opt=["seccomp:unconfined", "apparmor=unconfined", "no-new-privileges"],
        )

        assert container.seccomp_profile == "unconfined"
        assert container.security_opt == ["seccomp:unconfined", "apparmor=unconfined", "no-new-privileges"]

    def test_runtime_container_security_opt_coerces_scalar_string(self):
        container = RuntimeContainerConfiguration(security_opt="seccomp:unconfined")

        assert container.security_opt == ["seccomp:unconfined"]

    def test_runtime_container_seccomp_consistency_accepts_agreeing_values(self):
        container = RuntimeContainerConfiguration(
            seccomp_profile="unconfined",
            security_opt=["label=disable", "seccomp=unconfined"],
        )

        assert container.seccomp_profile == "unconfined"

    def test_runtime_container_seccomp_consistency_allows_variable_placeholder(self):
        container = RuntimeContainerConfiguration(
            seccomp_profile="${seccomp}",
            security_opt=["seccomp:unconfined"],
        )

        assert container.seccomp_profile == "${seccomp}"

    def test_runtime_container_seccomp_rejects_disagreeing_security_opt_entries(self):
        with pytest.raises(ValidationError, match="seccomp_profile"):
            RuntimeContainerConfiguration(security_opt=["seccomp:unconfined", "seccomp=default"])

    def test_vm_runtime_process_capability_overrides_surfaces(self):
        n = Node(
            type="compute",
            runtime={
                "processes": [
                    {"name": "entrypoint", "pid": 1, "role": "supervisor"},
                    {"name": "sshd", "parent_pid": 1, "role": "supervisor"},
                ],
                "linux_capabilities": {
                    "required": ["CAP_AUDIT_CONTROL"],
                    "effective": ["CAP_AUDIT_CONTROL"],
                    "process_overrides": [
                        {
                            "subject": {"name": "sshd", "parent_pid": 1},
                            "scope": "subtree",
                            "drop": ["cap-audit-control"],
                            "description": "interactive participant shell cannot disable auditing",
                        }
                    ],
                },
            },
        )

        runtime = n.runtime
        assert runtime is not None
        assert runtime.linux_capabilities is not None
        overrides = runtime.linux_capabilities.process_overrides
        assert len(overrides) == 1
        ov = overrides[0]
        assert ov.subject.name == "sshd"
        assert ov.subject.parent_pid == 1
        assert ov.scope == RuntimeCapabilityOverrideScope.SUBTREE
        # capability list passed through the same normalization pipeline as the
        # container-wide lists (hyphen-to-underscore, uppercase, CAP_* form).
        assert ov.drop == ["CAP_AUDIT_CONTROL"]
        assert ov.effective == []
        assert ov.add == []

    def test_runtime_process_capability_override_accepts_variable_refs(self):
        override = RuntimeProcessCapabilityOverride(
            subject={"name": "${shell_name}", "pid": "${shell_pid}"},
            scope="${shell_scope}",
            drop=["${dropped_cap}"],
        )

        assert override.subject.name == "${shell_name}"
        assert override.subject.pid == "${shell_pid}"
        assert override.scope == "${shell_scope}"
        assert override.drop == ["${dropped_cap}"]

    def test_runtime_process_capability_override_requires_a_subject_selector(self):
        with pytest.raises(ValidationError, match="subject"):
            RuntimeProcessCapabilityOverride(
                subject={},
                scope="process",
                drop=["CAP_AUDIT_CONTROL"],
            )

    def test_runtime_process_capability_override_requires_a_capability_assertion(self):
        with pytest.raises(ValidationError, match="capability"):
            RuntimeProcessCapabilityOverride(
                subject={"name": "sshd"},
                scope="process",
            )

    def test_runtime_process_capability_override_rejects_duplicates_within_list(self):
        with pytest.raises(ValidationError, match="Duplicate"):
            RuntimeProcessCapabilityOverride(
                subject={"name": "sshd"},
                scope="process",
                drop=["CAP_AUDIT_CONTROL", "cap_audit_control"],
            )

    def test_runtime_process_capability_override_rejects_non_cap_capability_name(self):
        with pytest.raises(ValidationError, match="CAP_"):
            RuntimeProcessCapabilityOverride(
                subject={"name": "sshd"},
                scope="process",
                drop=["AUDIT_CONTROL"],
            )

    def test_runtime_capability_policy_rejects_conflicting_overrides_for_same_subject(self):
        with pytest.raises(ValidationError, match="Duplicate runtime capability override"):
            RuntimeCapabilityPolicy(
                process_overrides=[
                    {
                        "subject": {"name": "sshd"},
                        "scope": "subtree",
                        "drop": ["CAP_AUDIT_CONTROL"],
                    },
                    {
                        "subject": {"name": "sshd"},
                        "scope": "subtree",
                        "drop": ["CAP_NET_ADMIN"],
                    },
                ]
            )

    def test_runtime_capability_policy_allows_same_name_different_scope(self):
        policy = RuntimeCapabilityPolicy(
            process_overrides=[
                {
                    "subject": {"name": "sshd"},
                    "scope": "process",
                    "drop": ["CAP_AUDIT_CONTROL"],
                },
                {
                    "subject": {"name": "sshd"},
                    "scope": "subtree",
                    "drop": ["CAP_NET_ADMIN"],
                },
            ]
        )
        assert len(policy.process_overrides) == 2

    def test_runtime_control_interface_accepts_windows_named_pipe_path(self):
        interface = RuntimeControlInterface(
            control_interface_id="docker-engine-pipe",
            path=r"\\.\pipe\docker_engine",
            kind="named-pipe",
            bind_source=r"\\.\pipe\docker_engine",
        )

        assert interface.path == r"\\.\pipe\docker_engine"
        assert interface.kind == RuntimeControlInterfaceKind.NAMED_PIPE
        assert interface.bind_source == r"\\.\pipe\docker_engine"

    def test_runtime_control_interface_named_pipe_path_requires_named_pipe_kind(self):
        with pytest.raises(ValidationError, match="named_pipe"):
            RuntimeControlInterface(
                control_interface_id="docker-engine-pipe",
                path=r"\\.\pipe\docker_engine",
                kind="unix-socket",
            )

    def test_runtime_mount_redacted_source_must_be_omitted(self):
        with pytest.raises(ValidationError, match="redacted runtime mount source"):
            RuntimeMount(
                target="/host-keys",
                source="/home/operator/.ssh",
                source_sensitivity="operator-secret",
            )

        mount = RuntimeMount(
            target="/host-keys",
            source_kind="bind",
            source_sensitivity="operator-secret",
            description="Host bind source withheld from the SDL artifact.",
        )

        assert mount.source == ""
        assert mount.source_sensitivity == RuntimeSensitivityClassification.OPERATOR_SECRET

    def test_runtime_mount_redacted_options_must_be_omitted(self):
        with pytest.raises(ValidationError, match="redacted runtime mount options"):
            RuntimeMount(
                target="/",
                options=["lowerdir=/var/lib/containerd/snapshots/1/fs"],
                options_sensitivity="redacted",
            )

        mount = RuntimeMount(
            target="/",
            options_sensitivity="redacted",
            description="Backend-local overlay options withheld.",
        )

        assert mount.options == []
        assert mount.options_sensitivity == RuntimeSensitivityClassification.REDACTED

    def test_runtime_control_interface_redacted_bind_source_must_be_omitted(self):
        with pytest.raises(ValidationError, match="redacted runtime control interface bind_source"):
            RuntimeControlInterface(
                control_interface_id="docker-sock",
                path="/run/docker.sock",
                bind_source="/var/run/docker.sock",
                bind_source_sensitivity="operator-secret",
            )

        interface = RuntimeControlInterface(
            control_interface_id="docker-sock",
            path="/run/docker.sock",
            protocol="docker",
            bind_source_sensitivity="operator-secret",
            access="read-write",
        )

        assert interface.bind_source == ""
        assert interface.bind_source_sensitivity == RuntimeSensitivityClassification.OPERATOR_SECRET

    def test_runtime_mount_json_schema_rejects_redacted_raw_details(self):
        validator = Draft202012Validator(RuntimeMount.model_json_schema())

        validator.validate(
            {
                "target": "/host-keys",
                "source_kind": "bind",
                "source_sensitivity": "operator_secret",
            }
        )
        with pytest.raises(JsonSchemaValidationError):
            validator.validate(
                {
                    "target": "/host-keys",
                    "source": "/home/operator/.ssh",
                    "source_sensitivity": "OPERATOR-SECRET",
                }
            )
        with pytest.raises(JsonSchemaValidationError):
            validator.validate(
                {
                    "target": "/",
                    "options": ["lowerdir=/var/lib/containerd/snapshots/1/fs"],
                    "options_sensitivity": "redacted",
                }
            )

    def test_runtime_control_interface_json_schema_rejects_redacted_bind_source(self):
        validator = Draft202012Validator(RuntimeControlInterface.model_json_schema())

        validator.validate(
            {
                "control_interface_id": "docker-sock",
                "path": "/run/docker.sock",
                "protocol": "docker",
                "bind_source_sensitivity": "operator_secret",
            }
        )
        with pytest.raises(JsonSchemaValidationError):
            validator.validate(
                {
                    "control_interface_id": "docker-sock",
                    "path": "/run/docker.sock",
                    "bind_source": "/var/run/docker.sock",
                    "bind_source_sensitivity": "OPERATOR_SECRET",
                }
            )

    def test_vm_runtime_local_identity_inventory_surfaces(self):
        n = Node(
            type="compute",
            runtime={
                "local_identity": {
                    "description": "getent passwd/group capture",
                    "users": [
                        {
                            "username": "root",
                            "uid": 0,
                            "primary_gid": 0,
                            "primary_group": "root",
                            "gecos": "root",
                            "home": "/root",
                            "shell": "/bin/bash",
                            "provenance": "image",
                            "stability": "stable",
                        },
                        {
                            "username": "www-data",
                            "uid": "33",
                            "primary_gid": 33,
                            "primary_group": "www-data",
                            "home": "/var/www",
                            "shell": "/usr/sbin/nologin",
                            "supplemental_groups": ["wazuh"],
                            "no_login": True,
                            "provenance": "package",
                        },
                        {
                            "username": "operator",
                            "uid": 1000,
                            "home": "/home/operator",
                            "shell": "/bin/bash",
                            "disabled": True,
                            "locked": True,
                            "provenance": "runtime-created",
                            "stability": "runtime_created",
                        },
                    ],
                    "groups": [
                        {"name": "root", "gid": 0, "members": ["root"], "provenance": "image"},
                        {"name": "www-data", "gid": 33, "members": ["www-data"]},
                        {"name": "wazuh", "gid": "101", "members": ["www-data", "operator"]},
                    ],
                    "sudo_rules": [
                        {
                            "principal": "operator",
                            "principal_kind": "user",
                            "run_as_users": ["root"],
                            "commands": ["/usr/bin/systemctl restart gunicorn"],
                            "nopasswd": True,
                        },
                        {
                            "principal": "wheel",
                            "principal_kind": "group",
                            "host_scope": "ALL",
                            "commands": ["ALL"],
                        },
                    ],
                },
            },
        )

        identity = n.runtime.local_identity
        assert identity is not None
        assert identity.description == "getent passwd/group capture"
        assert identity.users[0].username == "root"
        assert identity.users[0].uid == 0
        assert identity.users[0].primary_gid == 0
        assert identity.users[0].primary_group == "root"
        assert identity.users[0].gecos == "root"
        assert identity.users[0].home == "/root"
        assert identity.users[0].shell == "/bin/bash"
        assert identity.users[0].provenance == RuntimeIdentityProvenance.IMAGE
        assert identity.users[0].stability == RuntimeFilesystemStability.STABLE
        assert identity.users[1].uid == 33
        assert identity.users[1].supplemental_groups == ["wazuh"]
        assert identity.users[1].no_login is True
        assert identity.users[1].disabled is False
        assert identity.users[1].locked is False
        assert identity.users[1].provenance == RuntimeIdentityProvenance.PACKAGE
        assert identity.users[2].disabled is True
        assert identity.users[2].locked is True
        assert identity.users[2].no_login is False
        assert identity.users[2].provenance == RuntimeIdentityProvenance.RUNTIME_CREATED
        assert identity.groups[0].name == "root"
        assert identity.groups[0].gid == 0
        assert identity.groups[0].members == ["root"]
        assert identity.groups[2].gid == 101
        assert identity.groups[2].members == ["www-data", "operator"]
        assert identity.sudo_rules[0].principal == "operator"
        assert identity.sudo_rules[0].principal_kind == RuntimeSudoPrincipalKind.USER
        assert identity.sudo_rules[0].run_as_users == ["root"]
        assert identity.sudo_rules[0].commands == ["/usr/bin/systemctl restart gunicorn"]
        assert identity.sudo_rules[0].nopasswd is True
        assert identity.sudo_rules[1].principal_kind == RuntimeSudoPrincipalKind.GROUP
        assert identity.sudo_rules[1].host_scope == "ALL"

    def test_runtime_local_user_status_flags_are_independent(self):
        user = RuntimeLocalUser.model_validate({"username": "svc", "shell": "/usr/sbin/nologin", "no_login": True})
        assert user.no_login is True
        assert user.locked is False
        assert user.disabled is False

    def test_runtime_local_group_defaults(self):
        group = RuntimeLocalGroup(name="messagebus")
        assert group.gid is None
        assert group.members == []
        assert group.provenance == RuntimeIdentityProvenance.UNKNOWN

    def test_runtime_local_identity_inventory_is_optional(self):
        assert RuntimeLocalIdentityInventory().users == []
        assert Node(type="compute", runtime={}).runtime.local_identity is None

    def test_runtime_sudo_rule_redacted_commands_must_be_omitted(self):
        with pytest.raises(ValidationError, match="redacted sudo rules must omit commands"):
            RuntimeSudoRule(principal="ops", command_redacted=True, commands=["/bin/sh -c secret"])

    def test_runtime_sudo_rule_redacted_without_commands_is_valid(self):
        rule = RuntimeSudoRule(principal="ops", command_redacted=True)
        assert rule.command_redacted is True
        assert rule.commands == []


class TestRuntimeIdentityAuthorities:
    def test_vm_runtime_identity_authority_inventory_surfaces(self):
        n = Node(
            type="compute",
            services=[
                {"port": 389, "name": "ldap"},
                {"port": 88, "name": "kerberos"},
            ],
            runtime={
                "identity_authorities": [
                    {
                        "identity_authority_id": "techvault-domain",
                        "kind": "domain",
                        "name": "TechVault Domain",
                        "namespace": "techvault.local",
                        "domain_name": "TECHVAULT",
                        "realm": "TECHVAULT.LOCAL",
                        "base_dn": "DC=techvault,DC=local",
                        "services": [
                            {
                                "service_id": "ldap-endpoint",
                                "service": "ldap",
                                "protocol": "LDAP",
                                "address": "dc.techvault.local",
                                "port": "389",
                            }
                        ],
                        "subjects": [
                            {
                                "subject_id": "alice",
                                "kind": "user",
                                "name": "alice",
                                "principal_name": "alice@TECHVAULT.LOCAL",
                                "distinguished_name": "CN=Alice,CN=Users,DC=techvault,DC=local",
                                "enabled": True,
                                "attributes": [{"name": "department", "values": "security"}],
                            },
                            {
                                "subject_id": "domain-admins",
                                "kind": "group",
                                "name": "Domain Admins",
                                "distinguished_name": "CN=Domain Admins,CN=Users,DC=techvault,DC=local",
                            },
                            {
                                "subject_id": "ldap-svc",
                                "kind": "service_principal",
                                "name": "ldap",
                                "service_principal_names": ["LDAP/dc.techvault.local"],
                            },
                        ],
                        "relationships": [
                            {
                                "relationship_id": "alice-admin",
                                "relationship_type": "member-of",
                                "source_ref": "alice",
                                "target_ref": "domain-admins",
                            },
                            {
                                "relationship_id": "trust-parent",
                                "relationship_type": "trusts",
                                "source_ref": "techvault-domain",
                                "external_target": "corp.example",
                            },
                        ],
                        "policies": [
                            {
                                "policy_id": "default-password-policy",
                                "policy_kind": "password",
                                "name": "Default Domain Policy",
                                "applies_to_refs": ["techvault-domain"],
                                "settings": [{"name": "min_length", "values": "14"}],
                            }
                        ],
                    }
                ]
            },
        )

        authority = n.runtime.identity_authorities[0]
        assert authority.identity_authority_id == "techvault-domain"
        assert authority.kind == RuntimeIdentityAuthorityKind.DOMAIN
        assert authority.namespace == "techvault.local"
        assert authority.domain_name == "TECHVAULT"
        assert authority.realm == "TECHVAULT.LOCAL"
        assert authority.base_dn == "DC=techvault,DC=local"
        assert authority.services[0].protocol == RuntimeIdentityAuthorityProtocol.LDAP
        assert authority.services[0].port == 389
        assert authority.subjects[0].kind == RuntimeIdentitySubjectKind.USER
        assert authority.subjects[0].enabled is True
        assert authority.subjects[0].attributes[0].values == ["security"]
        assert authority.subjects[2].service_principal_names == ["LDAP/dc.techvault.local"]
        assert authority.relationships[0].relationship_type == RuntimeIdentityRelationshipKind.MEMBER_OF
        assert authority.relationships[1].external_target == "corp.example"
        assert authority.policies[0].applies_to_refs == ["techvault-domain"]
        assert authority.policies[0].settings[0].values == ["14"]

    def test_runtime_identity_secret_named_attribute_accepts_scenario_values(self):
        attribute = RuntimeIdentityAttribute(
            name="unicodePwd",
            values=["not-for-fixtures"],
            value_classification="plain",
        )

        assert attribute.values == ["not-for-fixtures"]

    def test_runtime_identity_attribute_accepts_observation_provenance(self):
        attr = RuntimeIdentityAttribute(name="misp_role", values=["admin"], provenance="runtime_created")

        assert attr.origin == RuntimeIdentityRecordOrigin.RUNTIME_CREATED
        assert attr.provenance == RuntimeIdentityRecordOrigin.RUNTIME_CREATED

    def test_runtime_identity_attribute_rejects_conflicting_origin_and_provenance(self):
        with pytest.raises(ValidationError, match="origin and provenance"):
            RuntimeIdentityAttribute(name="misp_role", origin="provisioned", provenance="runtime_created")

    def test_runtime_identity_authority_inventory_is_optional(self):
        assert Node(type="compute", runtime={}).runtime.identity_authorities == []


# ---------------------------------------------------------------------------
# Runtime network realization (ADR-025)
# ---------------------------------------------------------------------------


class TestRuntimeNetworkRealization:
    def test_vm_runtime_network_surface(self):
        n = Node(
            type="compute",
            runtime={
                "network": {
                    "description": "Docker network realization observed by harness inspection.",
                    "hostname": "techvault-webapp",
                    "domainname": "techvault.local",
                    "endpoints": [
                        {
                            "network": "aptl-dmz",
                            "ip_address": "172.20.0.20",
                            "ip_prefix_length": 24,
                            "gateway": "172.20.0.1",
                            "mac_address": "02:42:ac:14:00:14",
                            "aliases": ["aptl-webapp", "webapp"],
                            "dns_names": ["aptl-webapp", "webapp"],
                            "backend": {
                                "driver": "bridge",
                                "ipam_driver": "default",
                                "driver_options": {"com.docker.network.bridge.name": "br-dmz"},
                                "ipam_options": {"foo": "bar"},
                            },
                        },
                        {
                            "network": "aptl-internal",
                            "ip_address": "172.21.0.20",
                        },
                    ],
                    "published_ports": [
                        {
                            "container_port": 8080,
                            "protocol": "tcp",
                            "host_ip": "127.0.0.1",
                            "host_port": 8080,
                        }
                    ],
                },
            },
        )

        net = n.runtime.network
        assert net is not None
        assert net.hostname == "techvault-webapp"
        assert net.domainname == "techvault.local"
        ep = net.endpoints[0]
        assert ep.network == "aptl-dmz"
        assert ep.ip_address == "172.20.0.20"
        assert ep.ip_prefix_length == 24
        assert ep.gateway == "172.20.0.1"
        assert ep.mac_address == "02:42:ac:14:00:14"
        assert ep.aliases == ["aptl-webapp", "webapp"]
        assert ep.dns_names == ["aptl-webapp", "webapp"]
        assert ep.backend.driver == RuntimeNetworkDriver.BRIDGE
        assert ep.backend.ipam_driver == "default"
        assert ep.backend.driver_options == {"com.docker.network.bridge.name": "br-dmz"}
        assert ep.backend.ipam_options == {"foo": "bar"}
        # Defaults on a sparsely-specified endpoint.
        assert net.endpoints[1].backend is None
        binding = net.published_ports[0]
        assert binding.container_port == 8080
        assert binding.host_ip == "127.0.0.1"
        assert binding.host_port == 8080
        assert binding.protocol == "tcp"

    def test_runtime_network_is_optional(self):
        assert RuntimeNetworkRealization().endpoints == []
        assert Node(type="compute", runtime={}).runtime.network is None

    def test_endpoint_accepts_variable_placeholders(self):
        ep = RuntimeNetworkEndpoint(
            network="aptl-dmz",
            ip_address="${webapp_ip}",
            gateway="${dmz_gateway}",
            mac_address="${webapp_mac}",
            ip_prefix_length="${prefix}",
        )
        assert ep.ip_address == "${webapp_ip}"
        assert ep.mac_address == "${webapp_mac}"
        assert ep.ip_prefix_length == "${prefix}"

    def test_published_port_protocol_normalized_and_required(self):
        binding = RuntimePublishedPort(container_port="443", protocol="TCP")
        assert binding.container_port == 443
        assert binding.protocol == "tcp"
        assert binding.host_port is None

    def test_published_port_rejects_out_of_range_ports(self):
        with pytest.raises(ValidationError, match="container_port must be <= 65535"):
            RuntimePublishedPort(container_port=70000)
        with pytest.raises(ValidationError, match="host_port must be >= 1"):
            RuntimePublishedPort(container_port=8080, host_port=0)

    def test_published_port_rejects_empty_protocol(self):
        with pytest.raises(ValidationError, match="protocol must be a non-empty string"):
            RuntimePublishedPort(container_port=8080, protocol="  ")

    def test_published_port_rejects_invalid_host_ip(self):
        with pytest.raises(ValidationError, match="host_ip must be a valid IP address"):
            RuntimePublishedPort(container_port=8080, host_ip="not-an-ip")

    def test_endpoint_rejects_invalid_ip_and_gateway(self):
        with pytest.raises(ValidationError, match="ip_address must be a valid IP address"):
            RuntimeNetworkEndpoint(network="aptl-dmz", ip_address="999.0.0.1")
        with pytest.raises(ValidationError, match="gateway must be a valid IP address"):
            RuntimeNetworkEndpoint(network="aptl-dmz", gateway="bad-gateway")

    def test_endpoint_rejects_invalid_mac_address(self):
        with pytest.raises(ValidationError, match="mac_address must be a colon-separated MAC address"):
            RuntimeNetworkEndpoint(network="aptl-dmz", mac_address="02-42-ac-14-00-14")

    def test_endpoint_rejects_out_of_range_prefix_length(self):
        with pytest.raises(ValidationError, match="ip_prefix_length must be <= 128"):
            RuntimeNetworkEndpoint(network="aptl-dmz", ip_prefix_length=129)

    def test_endpoint_rejects_empty_network(self):
        with pytest.raises(ValidationError, match="network must be a non-empty string"):
            RuntimeNetworkEndpoint(network="  ")

    def test_endpoint_rejects_duplicate_aliases(self):
        with pytest.raises(ValidationError, match="Duplicate runtime network aliases"):
            RuntimeNetworkEndpoint(network="aptl-dmz", aliases=["webapp", "webapp"])

    def test_endpoint_rejects_duplicate_dns_names(self):
        with pytest.raises(ValidationError, match="Duplicate runtime network dns_names"):
            RuntimeNetworkEndpoint(network="aptl-dmz", dns_names=["webapp", "webapp"])

    def test_realization_rejects_duplicate_endpoint_networks(self):
        with pytest.raises(ValidationError, match="Duplicate runtime network endpoint for network 'aptl-dmz'"):
            RuntimeNetworkRealization(
                endpoints=[{"network": "aptl-dmz"}, {"network": "aptl-dmz"}],
            )

    def test_realization_rejects_conflicting_host_bindings(self):
        with pytest.raises(ValidationError, match="Duplicate host-published binding"):
            RuntimeNetworkRealization(
                published_ports=[
                    {"container_port": 8080, "host_ip": "127.0.0.1", "host_port": 8080, "protocol": "tcp"},
                    {"container_port": 9090, "host_ip": "127.0.0.1", "host_port": 8080, "protocol": "tcp"},
                ],
            )

    def test_realization_allows_same_host_port_on_distinct_protocols(self):
        realization = RuntimeNetworkRealization(
            published_ports=[
                {"container_port": 53, "host_ip": "127.0.0.1", "host_port": 53, "protocol": "tcp"},
                {"container_port": 53, "host_ip": "127.0.0.1", "host_port": 53, "protocol": "udp"},
            ],
        )
        assert len(realization.published_ports) == 2

    def test_backend_detail_normalizes_driver_enum(self):
        detail = RuntimeNetworkBackendDetail(driver="OVERLAY")
        assert detail.driver == RuntimeNetworkDriver.OVERLAY

    def test_backend_detail_rejects_unknown_driver(self):
        with pytest.raises(ValidationError, match="driver must be one of"):
            RuntimeNetworkBackendDetail(driver="quantum-mesh")


class TestRole:
    def test_basic_role(self):
        r = Role(username="admin")
        assert r.entities == []

    def test_role_with_entities(self):
        r = Role(username="user", entities=["blue-team.bob"])
        assert len(r.entities) == 1


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------


class TestInfraNode:
    def test_defaults(self):
        n = InfraNode()
        assert n.count == 1
        assert n.links == []

    def test_with_count(self):
        n = InfraNode(count=3)
        assert n.count == 3

    def test_rejects_zero_count(self):
        with pytest.raises(ValidationError, match="count must be >= 1"):
            InfraNode(count=0)

    def test_duplicate_links_rejected(self):
        with pytest.raises(ValidationError, match="unique"):
            InfraNode(links=["a", "a"])

    def test_count_placeholder(self):
        n = InfraNode(count="${replicas}")
        assert n.count == "${replicas}"

    def test_duplicate_acl_names_rejected(self):
        with pytest.raises(ValidationError, match="ACL names must be unique"):
            InfraNode(
                acls=[
                    {"name": "allow-admin", "direction": "in", "from_net": "wan"},
                    {"name": "allow-admin", "direction": "out", "to_net": "wan"},
                ]
            )


class TestSimpleProperties:
    def test_valid(self):
        p = SimpleProperties(cidr="10.0.0.0/24", gateway="10.0.0.1")
        assert p.cidr == "10.0.0.0/24"

    def test_gateway_outside_cidr(self):
        with pytest.raises(ValidationError, match="not within CIDR"):
            SimpleProperties(cidr="10.0.0.0/24", gateway="192.168.1.1")

    def test_invalid_cidr(self):
        # Pinned to the field-level ``validate_cidr`` validator (the ipaddress
        # stdlib message), not the model-level ``gateway_within_cidr`` check,
        # which would also reject this CIDR. Keeps the test honest about which
        # validator is under exercise.
        with pytest.raises(ValidationError, match="does not appear to be an IPv4 or IPv6"):
            SimpleProperties(cidr="not-a-cidr", gateway="10.0.0.1")

    def test_variable_placeholders_skip_network_validation(self):
        p = SimpleProperties(
            cidr="${network_cidr}",
            gateway="${network_gateway}",
            internal="${is_internal}",
        )
        assert p.cidr == "${network_cidr}"
        assert p.gateway == "${network_gateway}"
        assert p.internal == "${is_internal}"


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


class TestFeature:
    def test_service(self):
        f = Feature(type="service", source={"name": "apache"})
        assert f.type == FeatureType.SERVICE

    def test_with_dependencies(self):
        f = Feature(type="configuration", dependencies=["svc-a"])
        assert f.dependencies == ["svc-a"]


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------


class TestCondition:
    def test_command_based(self):
        c = Condition(command="/usr/bin/check.sh", interval=30)
        assert c.command == "/usr/bin/check.sh"

    def test_source_based(self):
        c = Condition(source={"name": "checker-pkg"})
        assert c.source.name == "checker-pkg"

    def test_rejects_both(self):
        with pytest.raises(ValidationError, match="both"):
            Condition(command="/bin/check", interval=10, source={"name": "pkg"})

    def test_rejects_neither(self):
        with pytest.raises(ValidationError, match="must have"):
            Condition()

    def test_command_without_interval(self):
        with pytest.raises(ValidationError, match="interval"):
            Condition(command="/bin/check")

    def test_scalar_placeholders(self):
        c = Condition(
            command="/usr/bin/check.sh",
            interval="${check_interval}",
            timeout="${check_timeout}",
            retries="${check_retries}",
            start_period="${check_start_period}",
        )
        assert c.interval == "${check_interval}"
        assert c.timeout == "${check_timeout}"
        assert c.retries == "${check_retries}"
        assert c.start_period == "${check_start_period}"


# ---------------------------------------------------------------------------
# Vulnerabilities
# ---------------------------------------------------------------------------


class TestVulnerability:
    def test_valid(self):
        v = Vulnerability(name="SQLi", description="SQL injection", **{"class": "CWE-89"})
        assert v.vuln_class == "CWE-89"

    def test_invalid_cwe(self):
        with pytest.raises(ValidationError, match="CWE"):
            Vulnerability(name="Test", description="Desc", **{"class": "INVALID"})


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class TestEntity:
    def test_basic(self):
        e = Entity(name="Team", role="blue")
        assert e.role == ExerciseRole.BLUE

    def test_role_placeholder(self):
        e = Entity(name="Team", role="${exercise_role}")
        assert e.role == "${exercise_role}"

    def test_facts_supported(self):
        e = Entity(name="Team", facts={"department": "SOC"})
        assert e.facts == {"department": "SOC"}

    def test_nested_entities(self):
        e = Entity(
            name="Team",
            entities={"bob": Entity(name="Bob")},
        )
        assert "bob" in e.entities

    def test_flatten(self):
        entities = {
            "blue": Entity(
                name="Blue",
                entities={"bob": Entity(name="Bob")},
            ),
        }
        flat = flatten_entities(entities)
        assert "blue" in flat
        assert "blue.bob" in flat


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


class TestParseDuration:
    def test_integer(self):
        assert parse_duration(60) == 60

    def test_simple_string(self):
        assert parse_duration("10 min") == 600

    def test_compound(self):
        assert parse_duration("1h 30min") == 5400

    def test_supports_months_and_years(self):
        assert parse_duration("1 mon") == 2_592_000
        assert parse_duration("1 y") == 31_536_000

    def test_supports_micro_and_nanoseconds(self):
        assert parse_duration("1 us") == 1
        assert parse_duration("1 ns") == 1

    def test_subsecond_values_round_up(self):
        assert parse_duration("1 ms") == 1
        assert parse_duration("1001 ms") == 2

    def test_supports_plus_syntax(self):
        assert parse_duration("1m+30") == 90

    def test_zero(self):
        assert parse_duration("0") == 0

    @pytest.mark.parametrize("value", [-1, -0.5, True, ""])
    def test_negative_or_blank_values_rejected(self, value):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration(value)

    def test_invalid(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("not a duration")

    def test_rejects_garbage_suffix(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("1h-nope")


class TestInject:
    def test_valid_pairing(self):
        i = Inject(from_entity="red", to_entities=["blue"])
        assert i.from_entity == "red"

    def test_rejects_partial_pairing(self):
        with pytest.raises(ValidationError, match="both"):
            Inject(from_entity="red")


class TestScript:
    def test_valid(self):
        s = Script(
            start_time="10 min",
            end_time="2 hour",
            speed=1.0,
            events={"evt-1": "30 min"},
        )
        assert s.start_time == 600
        assert s.end_time == 7200

    def test_end_before_start_rejected(self):
        with pytest.raises(ValidationError, match="end_time"):
            Script(
                start_time="2 hour",
                end_time="10 min",
                speed=1.0,
                events={"evt-1": "30 min"},
            )

    def test_event_outside_bounds_rejected(self):
        with pytest.raises(ValidationError, match="outside"):
            Script(
                start_time="10 min",
                end_time="20 min",
                speed=1.0,
                events={"evt-1": "30 min"},
            )

    def test_variable_placeholders(self):
        s = Script(
            start_time="${script_start}",
            end_time="${script_end}",
            speed="${script_speed}",
            events={"evt-1": "${event_time}"},
        )
        assert s.start_time == "${script_start}"
        assert s.end_time == "${script_end}"
        assert s.speed == "${script_speed}"
        assert s.events["evt-1"] == "${event_time}"


class TestStory:
    def test_valid(self):
        s = Story(scripts=["script-1"])
        assert s.speed == 1.0

    def test_speed_below_1_rejected(self):
        with pytest.raises(ValidationError, match="speed must be >= 1.0"):
            Story(scripts=["script-1"], speed=0.5)


# ---------------------------------------------------------------------------
# Objectives (RAES extensions)
# ---------------------------------------------------------------------------


class TestObjectiveSuccess:
    def test_requires_at_least_one_reference(self):
        with pytest.raises(ValidationError, match="at least one assertion"):
            ObjectiveSuccess()

    def test_accepts_assertion_reference(self):
        success = ObjectiveSuccess(assertions=["exercise-passed"])
        assert success.assertions == ["exercise-passed"]

    def test_mode_placeholder(self):
        success = ObjectiveSuccess(
            mode="${objective_mode}",
            assertions=["exercise-passed"],
        )
        assert success.mode == "${objective_mode}"


class TestObjective:
    def test_requires_exactly_one_actor_binding(self):
        with pytest.raises(ValidationError, match="exactly one"):
            Objective(
                success={"assertions": ["c1"]},
            )

        with pytest.raises(ValidationError, match="exactly one"):
            Objective(
                agent="red-agent",
                entity="red-team",
                success={"assertions": ["c1"]},
            )

    def test_valid_agent_objective(self):
        objective = Objective(
            agent="red-agent",
            actions=["Scan"],
            targets=["web-server"],
            success={"assertions": ["initial-access"]},
            window={
                "scripts": ["main-timeline"],
                "events": ["attack-wave"],
                "workflows": ["response-flow"],
                "steps": ["response-flow.validate"],
            },
            depends_on=["recon"],
        )
        assert objective.agent == "red-agent"
        assert objective.success.assertions == ["initial-access"]
        assert isinstance(objective.window, ObjectiveWindow)
        assert objective.window.steps == ["response-flow.validate"]

    def test_valid_entity_objective(self):
        objective = Objective(
            entity="blue-team",
            success={"assertions": ["report-quality"]},
        )
        assert objective.entity == "blue-team"


# ---------------------------------------------------------------------------
# Extension models (G1-G9, G12-G13)
# ---------------------------------------------------------------------------

from raes.accounts import Account, PasswordStrength
from raes.content import Content, ContentItem, ContentType, ServiceSearchIndexSchemaMaterialization
from raes.nodes import AssetValue, AssetValueLevel, OSFamily, ServicePort


def _search_index_schema_materialization() -> dict[str, object]:
    return {
        "interface_profile": "service-search-index-schema",
        "profile_version": "1",
        "target_service_ref": "search",
        "readback_assertion_refs": ["schema-ready"],
        "evidence_requirement_refs": ["schema-readback"],
        "observation_boundary_refs": ["participant-view"],
        "requirements": {
            "field_semantics": {"key": "exact-token"},
        },
    }


class TestContent:
    def test_file_content(self):
        c = Content(type="file", target="victim", path="/tmp/flag.txt", text="FLAG{x}")
        assert c.type == ContentType.FILE
        assert c.text == "FLAG{x}"

    def test_dataset_content(self):
        c = Content(
            type="dataset",
            target="exchange",
            format="eml",
            items=[ContentItem(name="email", display_name="email.eml", tags=["phishing"])],
        )
        assert len(c.items) == 1
        assert c.items[0].tags == ["phishing"]

    def test_sensitive_flag(self):
        c = Content(type="file", target="fs", path="/keys/id_rsa", sensitive=True)
        assert c.sensitive is True

    def test_sensitive_placeholder(self):
        c = Content(
            type="file",
            target="fs",
            path="/tmp/flag.txt",
            sensitive="${contains_sensitive_data}",
        )
        assert c.sensitive == "${contains_sensitive_data}"

    def test_requires_target(self):
        with pytest.raises(ValidationError, match="Content requires 'target'"):
            Content(type="file", path="/tmp/flag.txt")

    def test_file_requires_path(self):
        with pytest.raises(ValidationError, match="File content requires 'path'"):
            Content(type="file", target="victim")

    def test_dataset_requires_source_or_items(self):
        with pytest.raises(
            ValidationError,
            match="Dataset content requires either 'source' or non-empty 'items'",
        ):
            Content(type="dataset", target="victim")

    def test_directory_requires_destination(self):
        with pytest.raises(
            ValidationError,
            match="Directory content requires 'destination'",
        ):
            Content(type="directory", target="victim")

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            (
                {
                    "type": "file",
                    "target": "victim",
                    "path": "/tmp/flag.txt",
                    "service_materialization": _search_index_schema_materialization(),
                },
                "Search-index schema materialization requires dataset content",
            ),
            (
                {
                    "type": "dataset",
                    "target": "victim",
                    "source": {"name": "schema"},
                    "service_materialization": _search_index_schema_materialization(),
                },
                "Search-index schema materialization must not carry source or items",
            ),
            (
                {
                    "type": "dataset",
                    "target": "victim",
                    "items": [{"name": "schema"}],
                    "service_materialization": _search_index_schema_materialization(),
                },
                "Search-index schema materialization must not carry source or items",
            ),
            (
                {
                    "type": "file",
                    "path": "/tmp/flag.txt",
                    "service_materialization": _search_index_schema_materialization(),
                },
                "Content requires 'target'",
            ),
        ],
    )
    def test_search_index_schema_content_shape_rules(
        self,
        content: dict[str, object],
        message: str,
    ) -> None:
        with pytest.raises(ValidationError, match=message):
            Content.model_validate(content)

    def test_search_index_schema_dataset_does_not_require_payload(self) -> None:
        content = Content.model_validate(
            {
                "type": "dataset",
                "target": "victim",
                "service_materialization": _search_index_schema_materialization(),
            }
        )

        assert isinstance(content.service_materialization, ServiceSearchIndexSchemaMaterialization)
        assert content.source is None
        assert content.items == []


class TestAccount:
    def test_basic_account(self):
        a = Account(username="admin", node="dc")
        assert a.password_strength == PasswordStrength.MEDIUM

    def test_weak_account(self):
        a = Account(username="svc", node="dc", password_strength="weak")
        assert a.password_strength == PasswordStrength.WEAK

    def test_account_with_ad_fields(self):
        a = Account(
            username="svc_sql",
            node="dc",
            groups=["Domain Users"],
            spn="MSSQL/db.corp.local",
            password_strength="weak",
        )
        assert a.spn == "MSSQL/db.corp.local"

    def test_key_auth(self):
        a = Account(username="labadmin", node="victim", auth_method="key", password_strength="none")
        assert a.auth_method == "key"

    def test_disabled_placeholder(self):
        a = Account(username="svc", node="dc", disabled="${is_disabled}")
        assert a.disabled == "${is_disabled}"

    def test_password_strength_placeholder(self):
        a = Account(
            username="svc",
            node="dc",
            password_strength="${password_strength}",
        )
        assert a.password_strength == "${password_strength}"

    def test_requires_node(self):
        with pytest.raises(ValidationError, match="Account requires 'node'"):
            Account(username="admin")


class TestACLRule:
    def test_allow_rule(self):
        r = ACLRule(direction="in", from_net="wan", protocol="tcp", ports=[80, 443], action="allow")
        assert r.action == ACLAction.ALLOW
        assert r.ports == [80, 443]

    def test_deny_rule(self):
        r = ACLRule(direction="out", to_net="wan", action="deny")
        assert r.action == ACLAction.DENY

    def test_named_rule(self):
        r = ACLRule(name="allow-admin", direction="out", to_net="wan")
        assert r.name == "allow-admin"

    def test_port_placeholder(self):
        r = ACLRule(direction="in", from_net="wan", ports=["${https_port}"])
        assert r.ports == ["${https_port}"]

    def test_action_placeholder(self):
        r = ACLRule(direction="in", from_net="wan", action="${acl_action}")
        assert r.action == "${acl_action}"


class TestOSFamily:
    def test_windows(self):
        n = Node(type="compute", os="windows", resources={"ram": "1 gib", "cpu": 1})
        assert n.os == OSFamily.WINDOWS

    def test_linux(self):
        n = Node(type="compute", os="linux", resources={"ram": "1 gib", "cpu": 1})
        assert n.os == OSFamily.LINUX

    def test_no_os(self):
        n = Node(type="compute", resources={"ram": "1 gib", "cpu": 1})
        assert n.os is None

    def test_os_placeholder(self):
        n = Node(
            type="compute",
            os="${node_os}",
            resources={"ram": "1 gib", "cpu": 1},
        )
        assert n.os == "${node_os}"


class TestAssetValue:
    def test_defaults(self):
        av = AssetValue()
        assert av.confidentiality == AssetValueLevel.MEDIUM

    def test_custom(self):
        av = AssetValue(confidentiality="critical", availability="high")
        assert av.confidentiality == AssetValueLevel.CRITICAL

    def test_on_node(self):
        n = Node(
            type="compute",
            resources={"ram": "1 gib", "cpu": 1},
            asset_value={"confidentiality": "high", "availability": "critical"},
        )
        assert n.asset_value.confidentiality == AssetValueLevel.HIGH

    def test_placeholder(self):
        av = AssetValue(confidentiality="${cia_value}")
        assert av.confidentiality == "${cia_value}"


class TestServicePort:
    def test_basic(self):
        sp = ServicePort(port=443, name="https")
        assert sp.protocol == "tcp"

    def test_on_node(self):
        n = Node(
            type="compute",
            resources={"ram": "1 gib", "cpu": 1},
            services=[{"port": 22, "name": "ssh"}, {"port": 80, "name": "http"}],
        )
        assert len(n.services) == 2

    def test_duplicate_port_protocol_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate service binding"):
            Node(
                type="compute",
                resources={"ram": "1 gib", "cpu": 1},
                services=[
                    {"port": 443, "protocol": "tcp", "name": "https"},
                    {"port": 443, "protocol": "tcp", "name": "alt-https"},
                ],
            )

    def test_duplicate_named_service_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate named service"):
            Node(
                type="compute",
                resources={"ram": "1 gib", "cpu": 1},
                services=[
                    {"port": 22, "name": "admin"},
                    {"port": 443, "name": "admin"},
                ],
            )

    def test_same_port_with_different_protocols_allowed(self):
        n = Node(
            type="compute",
            resources={"ram": "1 gib", "cpu": 1},
            services=[
                {"port": 53, "protocol": "tcp", "name": "dns-tcp"},
                {"port": 53, "protocol": "udp", "name": "dns-udp"},
            ],
        )
        assert len(n.services) == 2

    def test_placeholder(self):
        sp = ServicePort(port="${service_port}", name="https")
        assert sp.port == "${service_port}"

    def test_rejects_unmodeled_role_as_reachability_policy(self):
        with pytest.raises(ValidationError, match="role"):
            ServicePort.model_validate({"port": 80, "protocol": "tcp", "name": "http", "role": "internal"})


class TestConditionExtensions:
    def test_timeout_and_retries(self):
        from raes.conditions import Condition

        c = Condition(command="/check", interval=15, timeout=5, retries=3, start_period=10)
        assert c.timeout == 5
        assert c.retries == 3
        assert c.start_period == 10


class TestSimplePropertiesInternal:
    def test_internal_flag(self):
        from raes.infrastructure import SimpleProperties

        p = SimpleProperties(cidr="10.0.0.0/24", gateway="10.0.0.1", internal=True)
        assert p.internal is True

    def test_default_not_internal(self):
        from raes.infrastructure import SimpleProperties

        p = SimpleProperties(cidr="10.0.0.0/24", gateway="10.0.0.1")
        assert p.internal is False


class TestWorkflow:
    def test_objective_step(self):
        step = WorkflowStep(
            type="objective",
            objective="verify-release",
            **{"on_success": "done"},
        )
        assert step.type == WorkflowStepType.OBJECTIVE
        assert step.objective == "verify-release"

    def test_decision_step_requires_branches(self):
        with pytest.raises(
            ValidationError,
            match="requires 'when', 'then', and 'else'",
        ):
            WorkflowStep(type="decision", when={"assertions": ["c1"]})

    def test_parallel_step_requires_unique_branches(self):
        with pytest.raises(ValidationError, match="branches must be unique"):
            WorkflowStep(type="parallel", branches=["a", "a"], join="done")

    def test_valid_workflow(self):
        workflow = Workflow(
            start="validate",
            steps={
                "validate": {
                    "type": "objective",
                    "objective": "verify-release",
                    "on_success": "done",
                },
                "done": {"type": "end"},
            },
        )
        assert workflow.start == "validate"
        assert set(workflow.steps) == {"validate", "done"}

    def test_retry_step(self):
        step = WorkflowStep(
            type="retry",
            objective="verify-release",
            **{"on_success": "done", "max_attempts": 5},
        )
        assert step.type == WorkflowStepType.RETRY
        assert step.objective == "verify-release"
        assert step.on_success == "done"
        assert step.max_attempts == 5

    def test_retry_step_requires_objective_attempts_and_success_target(self):
        with pytest.raises(
            ValidationError,
            match="requires 'objective', 'max-attempts', and 'on-success'",
        ):
            WorkflowStep(type="retry", objective="verify-release")

    def test_switch_step(self):
        step = WorkflowStep(
            type="switch",
            cases=[
                {
                    "when": {"assertions": ["c1"]},
                    "next": "done",
                }
            ],
            default="fallback",
        )
        assert step.type == WorkflowStepType.SWITCH
        assert step.default_step == "fallback"
        assert step.cases[0].next_step == "done"

    def test_call_step(self):
        step = WorkflowStep(
            type="call",
            workflow="child",
            **{"on_success": "done"},
        )
        assert step.type == WorkflowStepType.CALL
        assert step.workflow == "child"

    def test_workflow_timeout_scalar_parses_to_policy(self):
        workflow = Workflow(
            start="validate",
            timeout="5 min",
            steps={
                "validate": {
                    "type": "objective",
                    "objective": "verify-release",
                    "on_success": "done",
                },
                "done": {"type": "end"},
            },
        )
        assert workflow.timeout is not None
        assert workflow.timeout.seconds == 300

    def test_retry_step_forbids_decision_fields(self):
        with pytest.raises(
            ValidationError,
            match="Retry workflow step only supports",
        ):
            WorkflowStep(
                type="retry",
                objective="verify-release",
                **{
                    "on_success": "done",
                    "max_attempts": 3,
                    "then": "a",
                    "else": "b",
                },
            )

    def test_retry_max_attempts_must_be_positive(self):
        with pytest.raises(ValidationError, match="must be >= 1"):
            WorkflowStep(
                type="retry",
                objective="verify-release",
                **{"on_success": "done", "max_attempts": 0},
            )

    def test_retry_max_attempts_accepts_variable(self):
        step = WorkflowStep(
            type="retry",
            objective="verify-release",
            **{"on_success": "done", "max_attempts": "${max_retries}"},
        )
        assert step.max_attempts == "${max_retries}"

    def test_on_failure_on_objective_step(self):
        step = WorkflowStep(
            type="objective",
            objective="verify-release",
            **{"on_success": "done", "on_failure": "recover"},
        )
        assert step.on_failure == "recover"

    def test_on_failure_on_parallel_step(self):
        step = WorkflowStep(
            type="parallel",
            branches=["a", "b"],
            join="done",
            **{"on_failure": "recover"},
        )
        assert step.on_failure == "recover"

    def test_on_exhausted_accepts_variable(self):
        step = WorkflowStep(
            type="retry",
            objective="verify-release",
            **{
                "on_success": "done",
                "max_attempts": 3,
                "on_exhausted": "${recovery_step}",
            },
        )
        assert step.on_exhausted == "${recovery_step}"

    def test_on_failure_forbidden_on_decision_step(self):
        with pytest.raises(
            ValidationError,
            match="Decision workflow step only supports",
        ):
            WorkflowStep(
                type="decision",
                when={"assertions": ["c1"]},
                **{"then": "a", "else": "b", "on_failure": "recover"},
            )

    def test_join_step_requires_next(self):
        with pytest.raises(ValidationError, match="Join workflow step requires 'next'"):
            WorkflowStep(type="join")

    def test_step_state_predicate(self):
        pred = WorkflowPredicate(steps=[{"step": "step-a", "outcomes": ["failed"], "min_attempts": 2}])
        assert pred.steps[0].step == "step-a"
        assert pred.steps[0].outcomes == [WorkflowStepOutcome.FAILED]
        assert pred.steps[0].min_attempts == 2

    def test_predicate_with_only_step_state_is_valid(self):
        pred = WorkflowPredicate(
            steps=[
                {"step": "step-a", "outcomes": ["failed"]},
                {"step": "step-b", "outcomes": ["succeeded"]},
            ]
        )
        assert len(pred.steps) == 2

    def test_legacy_workflow_step_type_rejected(self):
        with pytest.raises(ValidationError, match="no longer supported"):
            WorkflowStep(type="if", when={"assertions": ["c1"]}, **{"then": "a", "else": "b"})

    def test_predicate_empty_rejected(self):
        with pytest.raises(ValidationError, match="must reference at least one"):
            WorkflowPredicate()


# ---------------------------------------------------------------------------
# Relationships, Agents, Variables (G10, G11, Identity)
# ---------------------------------------------------------------------------

from raes.agents import Agent, InitialKnowledge
from raes.relationships import Relationship, RelationshipType
from raes.variables import Variable, VariableType


class TestRelationship:
    def test_authenticates_with(self):
        r = Relationship(type="authenticates_with", source="exchange", target="ad-ds")
        assert r.type == RelationshipType.AUTHENTICATES_WITH

    def test_trusts_with_properties(self):
        r = Relationship(
            type="trusts",
            source="child-domain",
            target="parent-domain",
            properties={"trust_type": "parent-child", "trust_direction": "bidirectional"},
        )
        assert r.properties["trust_type"] == "parent-child"

    def test_connects_to(self):
        r = Relationship(
            type="connects_to", source="webapp", target="db", properties={"protocol": "tcp", "port": "5432"}
        )
        assert r.source == "webapp"
        assert r.type == RelationshipType.CONNECTS_TO
        assert r.properties == {"protocol": "tcp", "port": "5432"}

    def test_federates_with(self):
        r = Relationship(type="federates_with", source="adfs", target="azure-ad", properties={"protocol": "SAML"})
        assert r.type == RelationshipType.FEDERATES_WITH


class TestAgent:
    def test_basic_agent(self):
        a = Agent(entity="red-team", actions=["Scan", "Exploit"])
        assert len(a.actions) == 2

    def test_agent_with_starting_accounts(self):
        a = Agent(
            entity="red-team",
            starting_accounts=["phished-user"],
            allowed_subnets=["user-net"],
        )
        assert a.starting_accounts == ["phished-user"]

    def test_agent_with_initial_knowledge(self):
        a = Agent(
            entity="blue-team",
            initial_knowledge=InitialKnowledge(
                hosts=["defender", "server1"],
                subnets=["enterprise-net"],
            ),
        )
        assert len(a.initial_knowledge.hosts) == 2

    def test_initial_knowledge_defaults(self):
        ik = InitialKnowledge()
        assert ik.hosts == []
        assert ik.subnets == []
        assert ik.services == []
        assert ik.accounts == []

    def test_requires_entity(self):
        with pytest.raises(ValidationError, match="Agent requires 'entity'"):
            Agent(actions=["Scan"])

    def test_default_framing_lists_are_empty(self):
        a = Agent(entity="red-team")
        assert a.starting_assertions == []
        assert a.authority_anchors == []
        assert a.operating_scope == []

    def test_starting_assertions_field(self):
        a = Agent(entity="red-team", starting_assertions=["beacon-online", "vpn-up"])
        assert a.starting_assertions == ["beacon-online", "vpn-up"]

    def test_authority_anchors_field(self):
        a = Agent(
            entity="red-team",
            authority_anchors=["red-team", "trusts-blue-domain"],
        )
        assert a.authority_anchors == ["red-team", "trusts-blue-domain"]

    def test_operating_scope_field(self):
        a = Agent(
            entity="red-team",
            operating_scope=["corp-net", "dmz-net"],
        )
        assert a.operating_scope == ["corp-net", "dmz-net"]

    def test_framing_fields_accept_variable_placeholders(self):
        a = Agent(
            entity="red-team",
            starting_assertions=["${beacon_condition}"],
            authority_anchors=["${authority_ref}"],
            operating_scope=["${scope_ref}"],
        )
        assert a.starting_assertions == ["${beacon_condition}"]
        assert a.authority_anchors == ["${authority_ref}"]
        assert a.operating_scope == ["${scope_ref}"]

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            Agent(entity="red-team", unknown_field=["x"])


class TestVariable:
    def test_string_variable(self):
        v = Variable(type="string", default="techvault.local", description="Domain name")
        assert v.type == VariableType.STRING

    def test_integer_variable(self):
        v = Variable(type="integer", default=5)
        assert v.default == 5

    def test_variable_with_allowed_values(self):
        v = Variable(type="string", default="weak", allowed_values=["weak", "medium", "strong"])
        assert len(v.allowed_values) == 3

    def test_required_variable(self):
        v = Variable(type="string", required=True)
        assert v.required is True
        assert v.default is None

    def test_boolean_variable(self):
        v = Variable(type="boolean", default=True)
        assert v.type == VariableType.BOOLEAN

    def test_rejects_default_with_wrong_type(self):
        with pytest.raises(ValidationError, match="default must match"):
            Variable(type="integer", default="five")

    def test_rejects_allowed_values_with_wrong_type(self):
        with pytest.raises(ValidationError, match="allowed_values must match"):
            Variable(type="boolean", allowed_values=[True, "false"])

    def test_rejects_default_outside_allowed_values(self):
        with pytest.raises(ValidationError, match="default must be one of allowed_values"):
            Variable(type="string", default="critical", allowed_values=["low", "medium", "high"])

    def test_number_variable_accepts_int_and_float_allowed_values(self):
        v = Variable(type="number", default=1.5, allowed_values=[1, 1.5, 2.0])
        assert v.default == 1.5


class TestBooleanPlaceholders:
    def test_vulnerability_technical_placeholder(self):
        v = Vulnerability(
            name="SQLi",
            description="SQL injection",
            technical="${is_technical}",
            **{"class": "CWE-89"},
        )
        assert v.technical == "${is_technical}"


# ---------------------------------------------------------------------------
# Runtime application HTTP surface inventory (ADR-026)
# ---------------------------------------------------------------------------


class TestRuntimeApplicationSurface:
    def test_vm_runtime_application_surface(self):
        n = Node(
            type="compute",
            services=[{"port": 8080, "name": "techvault-http"}],
            runtime={
                "applications": [
                    {
                        "application_id": "techvault-webapp",
                        "service": "techvault-http",
                        "protocol": "http",
                        "name": "TechVault Webapp",
                        "base_path": "/",
                        "framework": "flask",
                        "description": "Observed Flask route surface.",
                        "routes": [
                            {
                                "route_id": "login",
                                "path": "/login",
                                "methods": ["get", "post"],
                                "name": "login",
                                "auth_required": False,
                                "session_required": False,
                                "auth_scheme": "form_login",
                                "parameters": [
                                    {"name": "username", "location": "form", "required": True},
                                    {"name": "password", "location": "form", "required": True},
                                ],
                                "responses": [
                                    {"status_code": 200, "content_type": "text/html"},
                                    {"status_code": "302", "content_type": "text/html"},
                                ],
                                "templates": ["/app/templates/login.html"],
                                "static_assets": ["/app/static/style.css"],
                                "redirects": [
                                    {
                                        "target": "/dashboard",
                                        "status_code": 302,
                                        "condition": "valid credentials",
                                    }
                                ],
                            },
                            {
                                "route_id": "upload",
                                "path": "/files/upload",
                                "methods": ["POST"],
                                "auth_required": True,
                                "session_required": True,
                                "parameters": [
                                    {"name": "document", "location": "uploaded_file", "required": True},
                                ],
                            },
                            {
                                "route_id": "diagnostics",
                                "path": "/debug/info",
                                "methods": ["GET"],
                                "exposed_fields": [
                                    {
                                        "name": "build_token",
                                        "sensitivity": "secret_fixture",
                                        "value": "fixture-token-1234",
                                    }
                                ],
                                "disclosures": [
                                    {
                                        "trigger": "any request",
                                        "status_code": 200,
                                        "disclosure": "internal package versions and host paths",
                                        "sensitivity": "plain",
                                    }
                                ],
                            },
                        ],
                    }
                ]
            },
        )
        surface = n.runtime.applications[0]
        assert surface.application_id == "techvault-webapp"
        assert surface.service == "techvault-http"
        assert surface.protocol == RuntimeApplicationProtocol.HTTP
        assert surface.base_path == "/"
        assert len(surface.routes) == 3
        login = surface.routes[0]
        # HTTP methods normalize to uppercase.
        assert login.methods == ["GET", "POST"]
        assert login.parameters[0].location == RuntimeApplicationParameterLocation.FORM
        assert login.parameters[0].required is True
        assert login.responses[1].status_code == 302
        assert login.redirects[0].status_code == 302
        upload = surface.routes[1]
        assert upload.auth_required is True
        assert upload.parameters[0].location == RuntimeApplicationParameterLocation.UPLOADED_FILE
        diag = surface.routes[2]
        assert diag.exposed_fields[0].sensitivity == RuntimeSensitivityClassification.SECRET_FIXTURE
        assert diag.disclosures[0].disclosure == "internal package versions and host paths"

    def test_route_path_must_be_url_path(self):
        with pytest.raises(ValidationError, match="route path must be a URL path starting with"):
            RuntimeApplicationRoute(route_id="r1", path="login", methods=["GET"])

    def test_route_path_rejects_whitespace(self):
        with pytest.raises(ValidationError, match="must not contain whitespace"):
            RuntimeApplicationRoute(route_id="r1", path="/log in", methods=["GET"])

    def test_route_methods_must_not_be_empty(self):
        with pytest.raises(ValidationError, match="route methods must not be empty"):
            RuntimeApplicationRoute(route_id="r1", path="/login", methods=[])

    def test_route_method_must_be_known(self):
        with pytest.raises(ValidationError, match="must be one of"):
            RuntimeApplicationRoute(route_id="r1", path="/login", methods=["FETCH"])

    def test_route_id_rejects_variable_placeholder(self):
        with pytest.raises(ValidationError, match="portable SDL identifier"):
            RuntimeApplicationRoute(route_id="${rid}", path="/login", methods=["GET"])

    def test_application_id_rejects_variable_placeholder(self):
        with pytest.raises(ValidationError, match="portable SDL identifier"):
            RuntimeApplicationSurface(application_id="${aid}")

    def test_response_status_code_range(self):
        with pytest.raises(ValidationError, match="status_code must be <= 599"):
            RuntimeApplicationResponse(status_code=600)

    def test_redirect_status_code_must_be_3xx(self):
        with pytest.raises(ValidationError, match="redirect status_code must be >= 300"):
            RuntimeApplicationRedirect(target="/x", status_code=200)

    def test_redirect_target_must_be_non_empty(self):
        with pytest.raises(ValidationError, match="redirect target must be a non-empty string"):
            RuntimeApplicationRedirect(target="")

    def test_parameter_name_must_be_non_empty(self):
        with pytest.raises(ValidationError, match="parameter name must be a non-empty string"):
            RuntimeApplicationParameter(name="  ")

    def test_duplicate_parameter_in_same_location_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate runtime application parameter 'id'"):
            RuntimeApplicationRoute(
                route_id="r1",
                path="/items",
                methods=["GET"],
                parameters=[
                    {"name": "id", "location": "query"},
                    {"name": "id", "location": "query"},
                ],
            )

    def test_same_parameter_name_in_different_locations_allowed(self):
        route = RuntimeApplicationRoute(
            route_id="r1",
            path="/items/<id>",
            methods=["GET"],
            parameters=[
                {"name": "id", "location": "path"},
                {"name": "id", "location": "query"},
            ],
        )
        assert len(route.parameters) == 2

    def test_exposed_field_redacted_must_omit_value(self):
        with pytest.raises(ValidationError, match="must omit its raw value"):
            RuntimeApplicationExposedField(name="api_key", sensitivity="redacted", value="secret")

    def test_exposed_field_operator_secret_must_omit_value(self):
        with pytest.raises(ValidationError, match="must omit its raw value"):
            RuntimeApplicationExposedField(name="api_key", sensitivity="operator_secret", value="secret")

    def test_disclosure_classified_description_only(self):
        disclosure = RuntimeApplicationDisclosure(
            trigger="malformed id",
            status_code=500,
            disclosure="stack trace exposed",
            sensitivity="plain",
        )
        assert disclosure.status_code == 500

    def test_duplicate_route_id_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate runtime application route_id 'r1'"):
            RuntimeApplicationSurface(
                application_id="app",
                routes=[
                    {"route_id": "r1", "path": "/a", "methods": ["GET"]},
                    {"route_id": "r1", "path": "/b", "methods": ["GET"]},
                ],
            )

    def test_duplicate_method_path_binding_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate runtime application route binding 'GET /a'"):
            RuntimeApplicationSurface(
                application_id="app",
                routes=[
                    {"route_id": "r1", "path": "/a", "methods": ["GET"]},
                    {"route_id": "r2", "path": "/a", "methods": ["GET", "POST"]},
                ],
            )

    def test_same_path_different_methods_allowed(self):
        surface = RuntimeApplicationSurface(
            application_id="app",
            routes=[
                {"route_id": "r1", "path": "/a", "methods": ["GET"]},
                {"route_id": "r2", "path": "/a", "methods": ["POST"]},
            ],
        )
        assert len(surface.routes) == 2

    def test_duplicate_application_id_on_node_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate runtime application_id 'app'"):
            Node(
                type="compute",
                runtime={
                    "applications": [
                        {"application_id": "app"},
                        {"application_id": "app"},
                    ]
                },
            )

    def test_route_path_variable_placeholder_allowed_in_value_fields(self):
        route = RuntimeApplicationRoute(
            route_id="r1",
            path="/items",
            methods=["GET"],
            auth_required="${needs_auth}",
        )
        assert route.auth_required == "${needs_auth}"

    def test_base_path_must_be_url_path(self):
        with pytest.raises(ValidationError, match="base_path must be a URL path starting with"):
            RuntimeApplicationSurface(application_id="app", base_path="api")

    def test_duplicate_template_ref_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate runtime application templates entry"):
            RuntimeApplicationRoute(
                route_id="r1",
                path="/a",
                methods=["GET"],
                templates=["/app/t.html", "/app/t.html"],
            )

    def test_route_upstream_target_normalized(self):
        route = RuntimeApplicationRoute(
            route_id="proxy-root",
            path="/",
            methods=["GET"],
            upstream_target={
                "target_node_ref": "app-backend",
                "target_service": "nodes.app-backend.services.gunicorn",
                "scheme": "HTTPS",
                "tls_terminated_here": True,
            },
        )
        assert route.upstream_target is not None
        assert route.upstream_target.target_node_ref == "app-backend"
        assert route.upstream_target.scheme == RuntimeApplicationRouteUpstreamScheme.HTTPS
        assert route.upstream_target.tls_terminated_here is True

    def test_route_upstream_target_defaults(self):
        target = RuntimeApplicationRouteUpstreamTarget()
        assert target.scheme == RuntimeApplicationRouteUpstreamScheme.HTTP
        assert target.target_node_ref == ""
        assert target.tls_terminated_here is None

    def test_route_upstream_scheme_is_closed(self):
        # The CLOSED scheme taxonomy carries neither ``other`` nor ``unknown``.
        with pytest.raises(ValidationError, match="scheme must be one of: http, https"):
            RuntimeApplicationRouteUpstreamTarget(scheme="ftp")

    def test_route_upstream_scheme_variable_placeholder_allowed(self):
        target = RuntimeApplicationRouteUpstreamTarget(scheme="${proxy_scheme}")
        assert target.scheme == "${proxy_scheme}"


class TestRelationshipProxyUpstream:
    def test_full_proxy_upstream(self):
        access = RelationshipProxyUpstream(
            route_ref="proxy-root",
            upstream_node_ref="app-backend",
            upstream_service_ref="gunicorn",
            client_tls_terminated=True,
            origin_plaintext=True,
            body_limit="10 MiB",
            description="nginx reverse proxy to gunicorn origin",
        )
        assert access.route_ref == "proxy-root"
        assert access.client_tls_terminated is True
        assert access.origin_plaintext is True
        assert access.body_limit == "10 MiB"

    def test_route_ref_required(self):
        with pytest.raises(ValidationError, match="route_ref must be a non-empty route_id"):
            RelationshipProxyUpstream(route_ref="  ")

    def test_route_ref_allows_variable_placeholder(self):
        access = RelationshipProxyUpstream(route_ref="${route_id}")
        assert access.route_ref == "${route_id}"

    def test_flags_accept_variable_placeholders(self):
        access = RelationshipProxyUpstream(
            route_ref="proxy-root",
            client_tls_terminated="${tls_terminated}",
            origin_plaintext="${plaintext}",
        )
        assert access.client_tls_terminated == "${tls_terminated}"
        assert access.origin_plaintext == "${plaintext}"

    def test_flag_rejects_non_bool(self):
        with pytest.raises(ValidationError):
            RelationshipProxyUpstream(route_ref="proxy-root", origin_plaintext="maybe")


# ---------------------------------------------------------------------------
# Runtime DNS service logical-state inventory (ADR-039)
# ---------------------------------------------------------------------------


class TestRuntimeDnsService:
    def test_vm_runtime_dns_service_inventory(self):
        n = Node(
            type="compute",
            services=[
                {"port": 53, "protocol": "udp", "name": "dns-udp"},
                {"port": 53, "protocol": "tcp", "name": "dns-tcp"},
            ],
            runtime={
                "filesystem_inventory": [
                    {"path": "/etc/bind/named.conf", "entry_type": "file"},
                    {"path": "/etc/bind/db.techvault.local", "entry_type": "file"},
                    {"path": "/var/log/named/query.log", "entry_type": "file"},
                ],
                "dns_services": [
                    {
                        "dns_service_id": "techvault-bind",
                        "service": "dns-udp",
                        "implementation": "BIND",
                        "version": "BIND 9.18.39-0ubuntu0.22.04.3-Ubuntu",
                        "roles": ["authoritative", "recursive-resolver"],
                        "configuration_file_refs": ["/etc/bind/named.conf"],
                        "log_file_refs": ["/var/log/named/query.log"],
                        "resolver_policy": {
                            "recursion_enabled": True,
                            "allow_recursion": ["172.20.0.0/16"],
                            "forwarders": [{"address": "8.8.8.8", "port": 53}],
                            "forwarding_policy": "first",
                            "dnssec_validation": "auto",
                            "query_logging": True,
                            "default_logging": True,
                        },
                        "dynamic_update": {"enabled": False},
                        "zones": [
                            {
                                "zone_id": "techvault-local",
                                "name": "techvault.local.",
                                "kind": "primary",
                                "purpose": "forward",
                                "zone_class": "IN",
                                "provenance": "axfr",
                                "zone_file_refs": ["/etc/bind/db.techvault.local"],
                                "transfer": {
                                    "axfr_enabled": True,
                                    "ixfr_enabled": False,
                                    "allowed_clients": ["172.20.0.0/16"],
                                },
                                "rrsets": [
                                    {
                                        "rrset_id": "soa",
                                        "owner": "techvault.local.",
                                        "record_type": "SOA",
                                        "zone_class": "IN",
                                        "ttl": 3600,
                                        "records": [
                                            {
                                                "soa": {
                                                    "mname": "ns1.techvault.local.",
                                                    "rname": "hostmaster.techvault.local.",
                                                    "serial": 2026010101,
                                                    "refresh": 3600,
                                                    "retry": 600,
                                                    "expire": 604800,
                                                    "minimum": 300,
                                                },
                                                "rdata": (
                                                    "ns1.techvault.local. hostmaster.techvault.local. "
                                                    "2026010101 3600 600 604800 300"
                                                ),
                                            }
                                        ],
                                    },
                                    {
                                        "rrset_id": "mx",
                                        "owner": "techvault.local.",
                                        "record_type": "MX",
                                        "ttl": 300,
                                        "records": [{"mx": {"preference": 10, "exchange": "mail.techvault.local."}}],
                                    },
                                    {
                                        "rrset_id": "ldap-srv",
                                        "owner": "_ldap._tcp.techvault.local.",
                                        "record_type": "SRV",
                                        "ttl": 300,
                                        "records": [
                                            {
                                                "srv": {
                                                    "priority": 0,
                                                    "weight": 100,
                                                    "port": 389,
                                                    "target": "ad.techvault.local.",
                                                }
                                            }
                                        ],
                                    },
                                    {
                                        "rrset_id": "web-a",
                                        "owner": "web.techvault.local.",
                                        "record_type": "A",
                                        "ttl": 300,
                                        "records": [{"address": "172.20.10.20"}],
                                    },
                                    {
                                        "rrset_id": "root-txt",
                                        "owner": "techvault.local.",
                                        "record_type": "TXT",
                                        "ttl": 300,
                                        "records": [{"text": ["site=techvault"]}],
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
        )

        service = n.runtime.dns_services[0]
        assert service.dns_service_id == "techvault-bind"
        assert service.implementation == DnsServerImplementation.BIND
        assert service.roles == [DnsServiceRole.AUTHORITATIVE, DnsServiceRole.RECURSIVE_RESOLVER]
        assert service.resolver_policy.dnssec_validation == DnssecValidationMode.AUTO
        assert service.resolver_policy.recursion_enabled is True
        assert service.resolver_policy.allow_recursion == ["172.20.0.0/16"]
        assert service.resolver_policy.forwarding_policy == "first"
        assert service.resolver_policy.query_logging is True
        assert service.resolver_policy.default_logging is True
        assert len(service.resolver_policy.forwarders) == 1
        assert service.resolver_policy.forwarders[0].address == "8.8.8.8"
        assert service.resolver_policy.forwarders[0].port == 53
        assert service.dynamic_update is not None
        assert service.dynamic_update.enabled is False
        zone = service.zones[0]
        assert zone.zone_class == DnsRecordClass.IN
        assert zone.transfer is not None
        assert zone.transfer.axfr_enabled is True
        assert zone.transfer.ixfr_enabled is False
        assert zone.transfer.allowed_clients == ["172.20.0.0/16"]
        assert zone.rrsets[0].record_type == DnsRecordType.SOA
        assert zone.rrsets[0].records[0].soa.serial == 2026010101
        assert zone.rrsets[1].records[0].mx.preference == 10
        assert zone.rrsets[2].records[0].srv.port == 389
        assert zone.rrsets[3].records[0].address == "172.20.10.20"

    def test_dns_rrset_ttl_range_enforced(self):
        with pytest.raises(ValidationError, match="ttl must be >= 0"):
            DnsResourceRecordSet(
                rrset_id="web-a",
                owner="web.example.test.",
                record_type="A",
                ttl=-1,
                records=[{"address": "192.0.2.10"}],
            )

    def test_dns_a_record_requires_ipv4_address_when_typed_address_present(self):
        with pytest.raises(ValidationError, match="A record address must be a valid IPv4 address"):
            DnsResourceRecordSet(
                rrset_id="web-a",
                owner="web.example.test.",
                record_type="A",
                ttl=300,
                records=[{"address": "2001:db8::10"}],
            )

    def test_dns_a_record_accepts_unresolved_address_placeholder(self):
        rrset = DnsResourceRecordSet(
            rrset_id="web-a",
            owner="web.example.test.",
            record_type="A",
            ttl=300,
            records=[{"address": "${web_ip}"}],
        )

        assert rrset.records[0].address == "${web_ip}"

    @pytest.mark.parametrize(
        "record",
        [
            {"address": "${web_ip}"},
            {"target": "${dns_target}"},
            {"text": ["${txt_value}"]},
            {
                "soa": {
                    "mname": "${soa_mname}",
                    "rname": "${soa_rname}",
                    "serial": "${soa_serial}",
                    "refresh": "${soa_refresh}",
                    "retry": "${soa_retry}",
                    "expire": "${soa_expire}",
                    "minimum": "${soa_minimum}",
                }
            },
            {"mx": {"preference": "${mx_preference}", "exchange": "${mx_exchange}"}},
            {
                "srv": {
                    "priority": "${srv_priority}",
                    "weight": "${srv_weight}",
                    "port": "${srv_port}",
                    "target": "${srv_target}",
                }
            },
        ],
    )
    def test_dns_variable_record_type_defers_typed_payload_matching(self, record):
        rrset = DnsResourceRecordSet(
            rrset_id="runtime-record",
            owner="${dns_owner}",
            record_type="${dns_record_type}",
            type_code="${dns_type_code}",
            ttl="${dns_ttl}",
            records=[record],
        )

        assert rrset.record_type == "${dns_record_type}"

    def test_dns_target_payload_accepts_target_style_records(self):
        rrset = DnsResourceRecordSet(
            rrset_id="ns",
            owner="example.test.",
            record_type="NS",
            ttl=300,
            records=[{"target": "ns1.example.test."}],
        )

        assert rrset.records[0].target == "ns1.example.test."

    def test_dns_target_payload_rejects_unrelated_record_types(self):
        with pytest.raises(ValidationError, match="target typed payload is only valid"):
            DnsResourceRecordSet(
                rrset_id="web-a",
                owner="web.example.test.",
                record_type="A",
                ttl=300,
                records=[{"target": "ns1.example.test."}],
            )

    def test_dns_unknown_record_type_preserves_type_code_and_rdata(self):
        rrset = DnsResourceRecordSet(
            rrset_id="https",
            owner="web.example.test.",
            record_type="other",
            type_code=65,
            ttl=300,
            records=[{"rdata": "1 . alpn=h2,h3"}],
        )

        assert rrset.record_type == DnsRecordType.OTHER
        assert rrset.type_code == 65
        assert rrset.records[0].rdata == "1 . alpn=h2,h3"

    @pytest.mark.parametrize("name", ["tsig_secret", "api_key", "update_key", "rndc.key", "key"])
    def test_dns_secret_named_setting_accepts_scenario_value(self, name):
        setting = DnsRuntimeSetting(name=name, value="base64secret", value_classification="plain")

        assert setting.value == "base64secret"

    def test_dns_setting_secret_name_detection_is_boundary_aware(self):
        setting = DnsRuntimeSetting(name="keyboard_layout", value="us", value_classification="plain")

        assert setting.value == "us"

    def test_duplicate_dns_rrset_binding_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate DNS RRset binding"):
            Node(
                type="compute",
                runtime={
                    "dns_services": [
                        {
                            "dns_service_id": "dns",
                            "zones": [
                                {
                                    "zone_id": "example",
                                    "name": "example.test.",
                                    "rrsets": [
                                        {
                                            "rrset_id": "web-a",
                                            "owner": "web.example.test.",
                                            "record_type": "A",
                                            "ttl": 300,
                                            "records": [{"address": "192.0.2.10"}],
                                        },
                                        {
                                            "rrset_id": "web-a-alt",
                                            "owner": "web.example.test.",
                                            "record_type": "A",
                                            "ttl": 300,
                                            "records": [{"address": "192.0.2.11"}],
                                        },
                                    ],
                                }
                            ],
                        }
                    ]
                },
            )


# ---------------------------------------------------------------------------
# Runtime database logical-state surface inventory (ADR-027)
# ---------------------------------------------------------------------------


class TestRuntimeDatabaseService:
    def test_vm_runtime_database_service(self):
        n = Node(
            type="compute",
            services=[{"port": 5432, "name": "techvault-pg"}],
            runtime={
                "database_services": [
                    {
                        "database_service_id": "techvault-postgres",
                        "service": "techvault-pg",
                        "engine": "postgresql",
                        "protocol": "postgresql",
                        "version": "16.13",
                        "name": "TechVault PostgreSQL",
                        "listeners": [
                            {"address": "*", "port": 5432},
                            {"address": "/var/run/postgresql", "description": "unix socket"},
                        ],
                        "databases": [
                            {
                                "database_id": "techvault-db",
                                "name": "techvault",
                                "origin": "scenario",
                                "schemas": [
                                    {
                                        "schema_id": "public-schema",
                                        "name": "public",
                                        "tables": [
                                            {"table_id": "users-tbl", "name": "users"},
                                            {"table_id": "audit-tbl", "name": "audit_log"},
                                        ],
                                    }
                                ],
                            },
                            {"database_id": "template0-db", "name": "template0", "origin": "built_in"},
                        ],
                        "roles": [
                            {"role_id": "app-role", "name": "techvault", "role_type": "application", "can_login": True},
                            {"role_id": "su-role", "name": "postgres", "role_type": "admin", "origin": "built_in"},
                        ],
                        "grants": [
                            {
                                "grantee_role_ref": "app-role",
                                "object_type": "table",
                                "object_ref": "users-tbl",
                                "privileges": ["SELECT", "INSERT", "UPDATE"],
                                "with_grant_option": False,
                            }
                        ],
                        "settings": [
                            {
                                "name": "listen_addresses",
                                "value": "*",
                                "provenance": "configuration_file",
                            },
                            {
                                "name": "log_statement",
                                "value": "all",
                                "provenance": "operator_override",
                            },
                        ],
                    }
                ]
            },
        )
        dbsvc = n.runtime.database_services[0]
        # Engine, protocol, and version are first-class — no protocol: other.
        assert dbsvc.engine == DatabaseEngine.POSTGRESQL
        assert dbsvc.protocol == DatabaseProtocol.POSTGRESQL
        assert dbsvc.version == "16.13"
        assert dbsvc.service == "techvault-pg"
        # Listener address union: wildcard and Unix socket both accepted.
        assert dbsvc.listeners[0].address == "*"
        assert dbsvc.listeners[0].port == 5432
        assert dbsvc.listeners[1].address == "/var/run/postgresql"
        # Databases, schemas, tables are typed data.
        techvault = dbsvc.databases[0]
        assert techvault.name == "techvault"
        assert techvault.origin == DatabaseObjectOrigin.SCENARIO
        assert techvault.schemas[0].name == "public"
        assert [t.name for t in techvault.schemas[0].tables] == ["users", "audit_log"]
        # Built-in objects classified, not scenario-authored.
        assert dbsvc.databases[1].origin == DatabaseObjectOrigin.BUILT_IN
        # Roles are typed database-local principals.
        assert dbsvc.roles[0].role_type == DatabaseRoleType.APPLICATION
        assert dbsvc.roles[0].can_login is True
        assert dbsvc.roles[1].origin == DatabaseObjectOrigin.BUILT_IN
        # Grants are typed privilege facts.
        assert dbsvc.grants[0].privileges == ["SELECT", "INSERT", "UPDATE"]
        # Settings carry provenance.
        assert dbsvc.settings[0].provenance == DatabaseSettingProvenance.CONFIGURATION_FILE

    def test_listener_address_accepts_ip_and_hostname(self):
        assert DatabaseListener(address="10.0.0.5").address == "10.0.0.5"
        assert DatabaseListener(address="::1").address == "::1"
        assert DatabaseListener(address="db.internal.example").address == "db.internal.example"

    def test_listener_address_rejects_garbage(self):
        with pytest.raises(ValidationError, match="must be '\\*', an IP address, a hostname"):
            DatabaseListener(address="bad!host")

    def test_listener_port_range_enforced(self):
        with pytest.raises(ValidationError, match="listener port must be <="):
            DatabaseListener(address="*", port=70000)

    def test_database_service_id_rejects_variable_placeholder(self):
        with pytest.raises(ValidationError, match="database_service_id must be a portable SDL identifier"):
            RuntimeDatabaseService(database_service_id="${svc}")

    def test_table_id_rejects_variable_placeholder(self):
        with pytest.raises(ValidationError, match="table_id must be a portable SDL identifier"):
            DatabaseTable(table_id="${t}", name="users")

    def test_object_name_allows_variable_placeholder(self):
        # Names are data, not symbols — a placeholder is a legal value field.
        assert DatabaseTable(table_id="users-tbl", name="${table_name}").name == "${table_name}"

    def test_object_name_rejects_empty(self):
        with pytest.raises(ValidationError, match="table name must be a non-empty string"):
            DatabaseTable(table_id="users-tbl", name="")

    def test_duplicate_database_id_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate database database_id 'dup'"):
            RuntimeDatabaseService(
                database_service_id="svc",
                databases=[
                    {"database_id": "dup", "name": "a"},
                    {"database_id": "dup", "name": "b"},
                ],
            )

    def test_duplicate_role_id_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate role role_id 'dup'"):
            RuntimeDatabaseService(
                database_service_id="svc",
                roles=[
                    {"role_id": "dup", "name": "a"},
                    {"role_id": "dup", "name": "b"},
                ],
            )

    def test_duplicate_table_id_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate database table_id 't'"):
            DatabaseSchema(
                schema_id="s",
                name="public",
                tables=[{"table_id": "t", "name": "a"}, {"table_id": "t", "name": "b"}],
            )

    def test_duplicate_setting_name_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate database setting 'port'"):
            RuntimeDatabaseService(
                database_service_id="svc",
                settings=[
                    {"name": "port", "value": "5432"},
                    {"name": "port", "value": "5433"},
                ],
            )

    def test_redacted_setting_must_omit_raw_value(self):
        with pytest.raises(ValidationError, match="must omit its raw value"):
            DatabaseSetting(name="password", value="hunter2", value_classification="redacted")

    def test_operator_secret_setting_must_omit_raw_value(self):
        with pytest.raises(ValidationError, match="must omit its raw value"):
            DatabaseSetting(name="primary_conninfo", value="host=x password=y", value_classification="operator_secret")

    def test_redacted_setting_without_value_is_valid(self):
        setting = DatabaseSetting(name="password", value_classification="redacted", provenance="operator_override")
        assert setting.value == ""

    @pytest.mark.parametrize(
        "secret_name",
        [
            "password",
            "PASSWORD",
            "shared_password",
            "primary_conninfo",
            "ssl_passphrase",
            "pg_hba_file_contents",
            "service_credential",
        ],
    )
    def test_secret_bearing_name_preserves_value_regardless_of_classification(self, secret_name):
        setting = DatabaseSetting(name=secret_name, value="leak")

        assert setting.value == "leak"

    def test_secret_bearing_name_with_empty_value_allows_plain_classification(self):
        setting = DatabaseSetting(name="password", value_classification="plain")

        assert setting.value_classification == RuntimeSensitivityClassification.PLAIN

    def test_secret_bearing_name_with_variable_classification_is_skipped(self):
        setting = DatabaseSetting(name="password", value_classification="${cls}")
        assert setting.value_classification == "${cls}"

    def test_non_secret_setting_keeps_default_unknown_classification(self):
        setting = DatabaseSetting(name="shared_buffers", value="128MB")
        assert setting.value == "128MB"

    def test_grant_privileges_must_not_be_empty(self):
        with pytest.raises(ValidationError, match="grant privileges must not be empty"):
            DatabaseGrant(grantee_role_ref="r", object_type="table", object_ref="t", privileges=[])

    def test_grant_rejects_duplicate_privilege(self):
        with pytest.raises(ValidationError, match="Duplicate grant privilege"):
            DatabaseGrant(
                grantee_role_ref="r",
                object_type="table",
                object_ref="t",
                privileges=["SELECT", "SELECT"],
            )

    def test_engine_normalizes_case_and_hyphens(self):
        svc = RuntimeDatabaseService(database_service_id="svc", engine="PostgreSQL", protocol="postgresql")
        assert svc.engine == DatabaseEngine.POSTGRESQL

    def test_unknown_engine_rejected(self):
        with pytest.raises(ValidationError, match="engine must be one of"):
            RuntimeDatabaseService(database_service_id="svc", engine="cobol-db")

    def test_engine_protocol_accept_variable_placeholder(self):
        svc = RuntimeDatabaseService(database_service_id="svc", engine="${engine}", protocol="${proto}")
        assert svc.engine == "${engine}"
        assert svc.protocol == "${proto}"

    @pytest.mark.parametrize(
        "engine,bad_protocol,expected_protocol",
        [
            ("postgresql", "other", "postgresql"),
            ("mysql", "other", "mysql"),
            ("mariadb", "tds", "mysql"),
            ("mssql", "mysql", "tds"),
            ("mongodb", "other", "mongodb"),
            ("redis", "other", "redis"),
        ],
    )
    def test_known_engine_rejects_wrong_or_other_protocol(self, engine, bad_protocol, expected_protocol):
        with pytest.raises(ValidationError, match=f"requires protocol to be one of: {expected_protocol}"):
            RuntimeDatabaseService(database_service_id="svc", engine=engine, protocol=bad_protocol)

    def test_postgresql_engine_default_protocol_other_is_rejected(self):
        # Without a cross-field check, defaulting protocol leaves PostgreSQL
        # at protocol=other — the exact ADR-027 §3 anti-pattern.
        with pytest.raises(ValidationError, match="requires protocol to be one of: postgresql"):
            RuntimeDatabaseService(database_service_id="svc", engine="postgresql")

    def test_engine_with_variable_protocol_is_skipped(self):
        svc = RuntimeDatabaseService(database_service_id="svc", engine="postgresql", protocol="${proto}")
        assert svc.protocol == "${proto}"

    def test_mariadb_engine_accepts_mysql_protocol(self):
        svc = RuntimeDatabaseService(database_service_id="svc", engine="mariadb", protocol="mysql")
        assert svc.engine == DatabaseEngine.MARIADB
        assert svc.protocol == DatabaseProtocol.MYSQL

    def test_sqlite_engine_unconstrained_protocol(self):
        # SQLite has no wire protocol; default ``other`` is acceptable.
        svc = RuntimeDatabaseService(database_service_id="svc", engine="sqlite")
        assert svc.engine == DatabaseEngine.SQLITE

    def test_duplicate_schema_id_across_databases_is_rejected(self):
        # Service-wide uniqueness for grant target resolution.
        with pytest.raises(ValidationError, match="Duplicate schema schema_id 'public' in database service 'svc'"):
            RuntimeDatabaseService(
                database_service_id="svc",
                databases=[
                    {"database_id": "a", "name": "a", "schemas": [{"schema_id": "public", "name": "public"}]},
                    {"database_id": "b", "name": "b", "schemas": [{"schema_id": "public", "name": "public"}]},
                ],
            )

    def test_duplicate_table_id_across_schemas_is_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate table table_id 'users' in database service 'svc'"):
            RuntimeDatabaseService(
                database_service_id="svc",
                databases=[
                    {
                        "database_id": "a",
                        "name": "a",
                        "schemas": [
                            {"schema_id": "s1", "name": "s1", "tables": [{"table_id": "users", "name": "users"}]},
                            {"schema_id": "s2", "name": "s2", "tables": [{"table_id": "users", "name": "users"}]},
                        ],
                    }
                ],
            )

    def test_relationship_database_access_auth_method_normalized(self):
        from raes.relationships import Relationship, RelationshipDatabaseAccess

        access = RelationshipDatabaseAccess(role_ref="app-role", auth_method="SCRAM-SHA-256")
        assert access.auth_method == DatabaseAuthMethod.SCRAM_SHA_256
        rel = Relationship(
            type="connects_to",
            source="webapp",
            target="db",
            database_access={"role_ref": "app-role", "auth_method": "password"},
        )
        assert rel.database_access.role_ref == "app-role"
        assert rel.database_access.auth_method == DatabaseAuthMethod.PASSWORD

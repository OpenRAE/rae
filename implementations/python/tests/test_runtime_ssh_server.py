"""Model-level tests for the SSH server configuration runtime surface.

Covers ``raes.runtime_ssh_server`` (see ADR-031). These tests construct
``RuntimeSshServer`` / ``SshMatchRule`` / ``SshForcedCommand`` directly to
exercise field validators, redaction invariants, and stable-identifier
discipline without going through the YAML parser.
"""

import pytest
import raes._runtime_service_families as runtime_family_registry
import raes.nodes as compat_nodes
import raes.nodes as nodes_facade
import raes.runtime_configuration as runtime_configuration_facade
from pydantic import ValidationError
from raes import parse_sdl_file
from raes._errors import SDLValidationError
from raes._module_symbols import symbol_index
from raes._runtime_service_families import (
    RUNTIME_SERVICE_FAMILIES,
    RuntimeServiceFamily,
    runtime_service_family_export_names,
)
from raes.runtime_configuration import RuntimeConfiguration
from raes.runtime_ssh_server import (
    RuntimeSshServer,
    SshForcedCommand,
    SshForcedCommandKind,
    SshMatchCriterion,
    SshMatchCriterionKind,
    SshMatchRule,
)
from raes.scenario import ModuleDescriptor, Scenario
from raes.validator import SemanticValidator


def _validate(scenario: Scenario) -> list[str]:
    validator = SemanticValidator(scenario)
    try:
        validator.validate()
        return []
    except SDLValidationError as exc:
        return exc.errors


def _ssh_node() -> dict:
    return {
        "type": "compute",
        "services": [{"port": 22, "name": "ssh"}],
        "runtime": {
            "ssh_servers": [
                {
                    "ssh_server_id": "sshd-default",
                    "service": "ssh",
                    "match_rules": [
                        {
                            "match_id": "m-kali",
                            "criteria": [{"kind": "user", "pattern": "kali"}],
                        }
                    ],
                }
            ]
        },
    }


# ---------------------------------------------------------------------------
# SshForcedCommand
# ---------------------------------------------------------------------------


class TestSshForcedCommand:
    def test_absolute_path_command_accepted(self):
        cmd = SshForcedCommand(
            command_kind=SshForcedCommandKind.ABSOLUTE_PATH,
            command="/usr/local/bin/aptl-wrap-shell.sh",
        )
        assert cmd.command == "/usr/local/bin/aptl-wrap-shell.sh"
        assert cmd.command_kind == SshForcedCommandKind.ABSOLUTE_PATH
        assert cmd.command_redacted is False

    def test_absolute_path_command_must_be_absolute(self):
        with pytest.raises(ValidationError) as exc:
            SshForcedCommand(
                command_kind=SshForcedCommandKind.ABSOLUTE_PATH,
                command="relative/path",
            )
        assert "absolute path" in str(exc.value)

    def test_absolute_path_command_rejects_empty_string(self):
        with pytest.raises(ValidationError) as exc:
            SshForcedCommand(
                command_kind=SshForcedCommandKind.ABSOLUTE_PATH,
                command="",
            )
        assert "command" in str(exc.value)

    def test_internal_sftp_accepted(self):
        cmd = SshForcedCommand(
            command_kind=SshForcedCommandKind.INTERNAL_SFTP,
            command="internal-sftp",
        )
        assert cmd.command == "internal-sftp"

    def test_internal_sftp_rejects_mismatched_command(self):
        with pytest.raises(ValidationError) as exc:
            SshForcedCommand(
                command_kind=SshForcedCommandKind.INTERNAL_SFTP,
                command="/usr/libexec/openssh/sftp-server",
            )
        assert "internal-sftp" in str(exc.value)

    def test_redacted_must_have_empty_command(self):
        cmd = SshForcedCommand(
            command_kind=SshForcedCommandKind.REDACTED,
            command_redacted=True,
        )
        assert cmd.command == ""
        assert cmd.command_redacted is True

    def test_redacted_rejects_populated_command(self):
        with pytest.raises(ValidationError) as exc:
            SshForcedCommand(
                command_kind=SshForcedCommandKind.REDACTED,
                command_redacted=True,
                command="/usr/local/bin/wrap.sh",
            )
        assert "redacted" in str(exc.value).lower()

    def test_absolute_path_variable_ref_accepted(self):
        cmd = SshForcedCommand(
            command_kind=SshForcedCommandKind.ABSOLUTE_PATH,
            command="${wrapper_path}",
        )
        assert cmd.command == "${wrapper_path}"

    def test_command_kind_variable_ref_accepted(self):
        cmd = SshForcedCommand(command_kind="${command_kind}", command="${cmd}")
        assert cmd.command_kind == "${command_kind}"

    def test_command_kind_rejects_unknown_value(self):
        with pytest.raises(ValidationError, match="command_kind"):
            SshForcedCommand(command_kind="exec", command="/bin/sh")

    def test_redacted_kind_requires_command_redacted_flag(self):
        # ADR-031: command_kind='redacted' carries an out-of-band secret-bearing
        # command; the redaction flag is the consumer-visible signal and must
        # be set explicitly, not left at the default False.
        with pytest.raises(ValidationError) as exc:
            SshForcedCommand(command_kind=SshForcedCommandKind.REDACTED)
        assert "command_redacted" in str(exc.value)

    def test_redacted_flag_requires_redacted_kind(self):
        # The redaction flag asserts a redacted forced-command shape; pairing
        # it with a concrete kind is a contract conflict.
        with pytest.raises(ValidationError) as exc:
            SshForcedCommand(
                command_kind=SshForcedCommandKind.ABSOLUTE_PATH,
                command="",
                command_redacted=True,
            )
        assert "command_kind" in str(exc.value)

    def test_variable_command_kind_does_not_bypass_redaction_invariant(self):
        # Security: a variable command_kind must not let a raw command slip
        # through when command_redacted is the literal True. command_redacted
        # is the unconditional signal that command must be empty.
        with pytest.raises(ValidationError) as exc:
            SshForcedCommand(
                command_kind="${kind}",
                command="/usr/local/bin/secret-wrap.sh",
                command_redacted=True,
            )
        assert "redacted" in str(exc.value).lower()

    def test_variable_command_redacted_does_not_bypass_redacted_kind_invariant(self):
        # Security: a variable command_redacted must not let a populated
        # command slip through when command_kind is the literal 'redacted'.
        with pytest.raises(ValidationError) as exc:
            SshForcedCommand(
                command_kind=SshForcedCommandKind.REDACTED,
                command="/usr/local/bin/secret-wrap.sh",
                command_redacted="${is_redacted}",
            )
        assert "redacted" in str(exc.value).lower()

    def test_variable_command_redacted_with_redacted_kind_and_empty_command_accepted(self):
        # Defer only the parts that genuinely depend on variable resolution:
        # an empty command paired with command_kind='redacted' is consistent
        # with any concrete value of command_redacted.
        cmd = SshForcedCommand(
            command_kind=SshForcedCommandKind.REDACTED,
            command="",
            command_redacted="${is_redacted}",
        )
        assert cmd.command_redacted == "${is_redacted}"

    def test_variable_command_kind_with_redacted_flag_and_empty_command_accepted(self):
        # Mirror: command_redacted=True with empty command is consistent with
        # any concrete value of command_kind that resolves to 'redacted'.
        cmd = SshForcedCommand(
            command_kind="${kind}",
            command="",
            command_redacted=True,
        )
        assert cmd.command_redacted is True


# ---------------------------------------------------------------------------
# SshMatchCriterion
# ---------------------------------------------------------------------------


class TestSshMatchCriterion:
    def test_user_criterion_accepted(self):
        c = SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali")
        assert c.kind == SshMatchCriterionKind.USER

    def test_pattern_must_be_non_empty(self):
        with pytest.raises(ValidationError, match="pattern"):
            SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="")

    def test_unknown_kind_rejected(self):
        with pytest.raises(ValidationError, match="kind"):
            SshMatchCriterion(kind="invalid", pattern="x")

    def test_kind_normalizes_kebab_to_underscore(self):
        c = SshMatchCriterion(kind="local-user", pattern="kali")
        assert c.kind == SshMatchCriterionKind.LOCAL_USER


# ---------------------------------------------------------------------------
# SshMatchRule
# ---------------------------------------------------------------------------


class TestSshMatchRule:
    def test_minimal_rule_accepted(self):
        rule = SshMatchRule(
            match_id="m-kali",
            criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali")],
        )
        assert rule.match_id == "m-kali"
        assert len(rule.criteria) == 1

    def test_empty_match_id_rejected(self):
        with pytest.raises(ValidationError, match="match_id"):
            SshMatchRule(
                match_id="",
                criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali")],
            )

    def test_whitespace_match_id_rejected(self):
        with pytest.raises(ValidationError, match="match_id"):
            SshMatchRule(
                match_id="   ",
                criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali")],
            )

    def test_variable_ref_match_id_rejected(self):
        with pytest.raises(ValidationError) as exc:
            SshMatchRule(
                match_id="${match_id}",
                criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali")],
            )
        assert "match_id" in str(exc.value)

    def test_at_least_one_criterion_required(self):
        with pytest.raises(ValidationError) as exc:
            SshMatchRule(match_id="m1", criteria=[])
        assert "criteria" in str(exc.value).lower()

    def test_duplicate_criteria_within_rule_rejected(self):
        with pytest.raises(ValidationError) as exc:
            SshMatchRule(
                match_id="m1",
                criteria=[
                    SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali"),
                    SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali"),
                ],
            )
        assert "duplicate" in str(exc.value).lower()

    def test_per_rule_forced_command_accepted(self):
        rule = SshMatchRule(
            match_id="m-kali",
            criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali")],
            forced_command=SshForcedCommand(
                command_kind=SshForcedCommandKind.ABSOLUTE_PATH,
                command="/usr/local/bin/aptl-wrap-shell.sh",
            ),
        )
        assert rule.forced_command is not None
        assert rule.forced_command.command == "/usr/local/bin/aptl-wrap-shell.sh"

    def test_per_rule_accept_env_accepted(self):
        rule = SshMatchRule(
            match_id="m-kali",
            criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali")],
            accept_env=["APTL_SESSION_ID", "APTL_RUN_ID", "APTL_TRACE_ID"],
        )
        assert rule.accept_env == ["APTL_SESSION_ID", "APTL_RUN_ID", "APTL_TRACE_ID"]

    def test_per_rule_chroot_directory_must_be_absolute(self):
        with pytest.raises(ValidationError) as exc:
            SshMatchRule(
                match_id="m1",
                criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali")],
                chroot_directory="relative/chroot",
            )
        assert "absolute" in str(exc.value).lower()

    def test_per_rule_authorized_keys_file_must_be_absolute(self):
        with pytest.raises(ValidationError) as exc:
            SshMatchRule(
                match_id="m1",
                criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali")],
                authorized_keys_file="relative/keys",
            )
        assert "absolute" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# RuntimeSshServer
# ---------------------------------------------------------------------------


class TestRuntimeSshServer:
    def test_minimal_accepted(self):
        cfg = RuntimeSshServer(ssh_server_id="sshd-default", service="ssh")
        assert cfg.ssh_server_id == "sshd-default"
        assert cfg.service == "ssh"

    def test_empty_server_id_rejected(self):
        with pytest.raises(ValidationError, match="ssh_server_id"):
            RuntimeSshServer(ssh_server_id="", service="ssh")

    def test_whitespace_server_id_rejected(self):
        with pytest.raises(ValidationError, match="ssh_server_id"):
            RuntimeSshServer(ssh_server_id="   ", service="ssh")

    def test_variable_ref_server_id_rejected(self):
        with pytest.raises(ValidationError) as exc:
            RuntimeSshServer(ssh_server_id="${server_id}", service="ssh")
        assert "ssh_server_id" in str(exc.value)

    def test_service_required(self):
        with pytest.raises(ValidationError, match="service"):
            RuntimeSshServer(ssh_server_id="sshd-default", service="")

    def test_accept_env_scalar_string_coerced_to_list(self):
        cfg = RuntimeSshServer(
            ssh_server_id="sshd-default",
            service="ssh",
            accept_env="APTL_SESSION_ID",
        )
        assert cfg.accept_env == ["APTL_SESSION_ID"]

    def test_accept_env_motivating_fact_accepted(self):
        cfg = RuntimeSshServer(
            ssh_server_id="sshd-default",
            service="ssh",
            accept_env=["APTL_SESSION_ID", "APTL_RUN_ID", "APTL_TRACE_ID"],
        )
        assert cfg.accept_env == ["APTL_SESSION_ID", "APTL_RUN_ID", "APTL_TRACE_ID"]

    @pytest.mark.parametrize(
        "bad_entry",
        ["FOO=bar", "FOO BAR", " FOO", "FOO ", "", "  "],
    )
    def test_accept_env_rejects_invalid_entry(self, bad_entry):
        with pytest.raises(ValidationError) as exc:
            RuntimeSshServer(
                ssh_server_id="sshd-default",
                service="ssh",
                accept_env=["GOOD", bad_entry],
            )
        msg = str(exc.value).lower()
        assert "accept_env" in msg

    def test_accept_env_duplicate_rejected(self):
        with pytest.raises(ValidationError) as exc:
            RuntimeSshServer(
                ssh_server_id="sshd-default",
                service="ssh",
                accept_env=["APTL_SESSION_ID", "APTL_SESSION_ID"],
            )
        assert "duplicate" in str(exc.value).lower()

    def test_accept_env_case_sensitive(self):
        cfg = RuntimeSshServer(
            ssh_server_id="sshd-default",
            service="ssh",
            accept_env=["foo", "FOO"],
        )
        assert cfg.accept_env == ["foo", "FOO"]

    def test_duplicate_match_id_rejected(self):
        with pytest.raises(ValidationError) as exc:
            RuntimeSshServer(
                ssh_server_id="sshd-default",
                service="ssh",
                match_rules=[
                    SshMatchRule(
                        match_id="m1",
                        criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="a")],
                    ),
                    SshMatchRule(
                        match_id="m1",
                        criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="b")],
                    ),
                ],
            )
        assert "duplicate" in str(exc.value).lower()
        assert "match_id" in str(exc.value).lower() or "match id" in str(exc.value).lower()

    def test_duplicate_match_criteria_tuple_rejected(self):
        with pytest.raises(ValidationError) as exc:
            RuntimeSshServer(
                ssh_server_id="sshd-default",
                service="ssh",
                match_rules=[
                    SshMatchRule(
                        match_id="m1",
                        criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali")],
                    ),
                    SshMatchRule(
                        match_id="m2",
                        criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali")],
                    ),
                ],
            )
        assert "duplicate" in str(exc.value).lower()

    def test_chroot_directory_variable_ref_accepted(self):
        cfg = RuntimeSshServer(
            ssh_server_id="sshd-default",
            service="ssh",
            chroot_directory="${chroot}",
        )
        assert cfg.chroot_directory == "${chroot}"

    def test_chroot_directory_concrete_must_be_absolute(self):
        with pytest.raises(ValidationError, match="absolute"):
            RuntimeSshServer(
                ssh_server_id="sshd-default",
                service="ssh",
                chroot_directory="rel/chroot",
            )

    def test_authorized_keys_file_concrete_must_be_absolute(self):
        with pytest.raises(ValidationError, match="absolute"):
            RuntimeSshServer(
                ssh_server_id="sshd-default",
                service="ssh",
                authorized_keys_file="rel/keys",
            )

    @pytest.mark.parametrize("field", ["password_authentication", "pubkey_authentication", "permit_tty"])
    @pytest.mark.parametrize("value, expected", [(True, True), (False, False), ("yes", True), ("no", False)])
    def test_optional_bool_fields_parse(self, field, value, expected):
        cfg = RuntimeSshServer(ssh_server_id="sshd-default", service="ssh", **{field: value})
        assert getattr(cfg, field) is expected

    @pytest.mark.parametrize("field", ["password_authentication", "pubkey_authentication", "permit_tty"])
    def test_optional_bool_fields_accept_variable_ref(self, field):
        cfg = RuntimeSshServer(ssh_server_id="sshd-default", service="ssh", **{field: "${flag}"})
        assert getattr(cfg, field) == "${flag}"

    def test_full_motivating_fact_parses(self):
        """The APTL TechVault kali fact end-to-end at the model level."""
        cfg = RuntimeSshServer(
            ssh_server_id="sshd-default",
            service="ssh",
            accept_env=["APTL_SESSION_ID", "APTL_RUN_ID", "APTL_TRACE_ID"],
            match_rules=[
                SshMatchRule(
                    match_id="m-kali",
                    criteria=[SshMatchCriterion(kind=SshMatchCriterionKind.USER, pattern="kali")],
                    forced_command=SshForcedCommand(
                        command_kind=SshForcedCommandKind.ABSOLUTE_PATH,
                        command="/usr/local/bin/aptl-wrap-shell.sh",
                    ),
                ),
            ],
        )
        assert cfg.match_rules[0].forced_command.command == "/usr/local/bin/aptl-wrap-shell.sh"

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError, match="unknown_field"):
            RuntimeSshServer(ssh_server_id="sshd-default", service="ssh", unknown_field=True)


# ---------------------------------------------------------------------------
# RuntimeConfiguration.ssh_servers
# ---------------------------------------------------------------------------


class TestRuntimeConfigurationSshServers:
    def test_ssh_servers_default_empty(self):
        cfg = RuntimeConfiguration()
        assert cfg.ssh_servers == []

    def test_ssh_servers_accepts_list(self):
        cfg = RuntimeConfiguration(
            ssh_servers=[RuntimeSshServer(ssh_server_id="sshd-default", service="ssh")],
        )
        assert len(cfg.ssh_servers) == 1
        assert cfg.ssh_servers[0].ssh_server_id == "sshd-default"

    def test_duplicate_server_id_rejected(self):
        with pytest.raises(ValidationError) as exc:
            RuntimeConfiguration(
                ssh_servers=[
                    RuntimeSshServer(ssh_server_id="dup", service="ssh"),
                    RuntimeSshServer(ssh_server_id="dup", service="ssh-alt"),
                ],
            )
        msg = str(exc.value).lower()
        assert "duplicate" in msg
        assert "ssh" in msg


class TestRuntimeFamilyRegistrySshCoverage:
    def test_runtime_family_registry_is_the_complete_runtime_service_field_set(self):
        registered_fields = tuple(family.collection_name for family in RUNTIME_SERVICE_FAMILIES)

        assert registered_fields == (
            "service_listeners",
            "applications",
            "database_services",
            "dns_services",
            "identity_authorities",
            "file_services",
            "mail_services",
            "network_sensors",
            "network_detection_engines",
            "security_monitoring_managers",
            "ssh_servers",
            "app_authorizations",
            "scheduled_jobs",
            "datastore_services",
            "platform_applications",
            "forwarding_agents",
            "orchestration_authorities",
        )
        assert all(field in RuntimeConfiguration.model_fields for field in registered_fields)

    def test_runtime_family_registry_includes_ssh_servers(self):
        fields = {family.collection_name for family in RUNTIME_SERVICE_FAMILIES}

        assert "ssh_servers" in fields

    def test_runtime_family_exports_are_available_from_public_facades(self):
        names = runtime_service_family_export_names()

        assert len(names) == len(set(names))
        for name in names:
            assert name in runtime_configuration_facade.__all__
            assert name in nodes_facade.__all__
            assert getattr(runtime_configuration_facade, name) is getattr(nodes_facade, name)

        assert nodes_facade.RuntimeSshServer is RuntimeSshServer
        assert compat_nodes.RuntimeSshServer is RuntimeSshServer

    def test_runtime_family_exports_reject_duplicate_public_symbols(self, monkeypatch):
        ssh_family = next(family for family in RUNTIME_SERVICE_FAMILIES if family.collection_name == "ssh_servers")
        duplicate_family = RuntimeServiceFamily(
            key="duplicate-ssh-servers",
            module=ssh_family.module,
            collection_name="duplicate_ssh_servers",
            id_field="ssh_server_id",
            reference_policy=ssh_family.reference_policy,
        )
        monkeypatch.setattr(
            runtime_family_registry,
            "RUNTIME_SERVICE_FAMILIES",
            (*RUNTIME_SERVICE_FAMILIES, duplicate_family),
        )

        with pytest.raises(RuntimeError, match="RuntimeSshServer"):
            runtime_family_registry.runtime_service_family_export_names()

    def test_symbol_index_rewrites_runtime_ssh_refs(self):
        scenario = Scenario(
            name="shared",
            module=ModuleDescriptor(id="acme/shared", version="1.0.0", exports={"nodes": ["kali"]}),
            nodes={"kali": _ssh_node()},
        )

        named = symbol_index(
            scenario,
            namespace="shared",
            descriptor=scenario.module,
        )["named"]

        assert named["nodes.kali.runtime.ssh_servers.sshd-default"] == (
            "nodes.shared.kali.runtime.ssh_servers.sshd-default"
        )
        assert named["nodes.kali.runtime.ssh_servers.sshd-default.match_rules.m-kali"] == (
            "nodes.shared.kali.runtime.ssh_servers.sshd-default.match_rules.m-kali"
        )

    def test_semantic_validator_resolves_runtime_ssh_refs(self):
        scenario = Scenario(
            name="ssh-refs",
            nodes={"kali": _ssh_node()},
            relationships={
                "ssh-policy": {
                    "type": "depends_on",
                    "source": "nodes.kali.runtime.ssh_servers.sshd-default",
                    "target": "nodes.kali.runtime.ssh_servers.sshd-default.match_rules.m-kali",
                }
            },
        )

        assert _validate(scenario) == []

    def test_ssh_runtime_refs_rewrite_on_module_import(self, tmp_path):
        shared = tmp_path / "shared-ssh.yaml"
        shared.write_text(
            """
name: shared-ssh
version: 1.0.0
module:
  id: raes/shared-ssh
  version: 1.0.0
  exports:
    nodes: [kali]
    relationships: [ssh-policy]
nodes:
  kali:
    type: compute
    services:
      - {port: 22, name: ssh}
    runtime:
      ssh_servers:
        - ssh_server_id: sshd-default
          service: ssh
          match_rules:
            - match_id: m-kali
              criteria:
                - {kind: user, pattern: kali}
relationships:
  ssh-policy:
    type: depends_on
    source: nodes.kali.runtime.ssh_servers.sshd-default
    target: nodes.kali.runtime.ssh_servers.sshd-default.match_rules.m-kali
""",
            encoding="utf-8",
        )
        root = tmp_path / "root.yaml"
        root.write_text(
            """
name: root
imports:
  - path: shared-ssh.yaml
    namespace: shared
    version: 1.0.0
""",
            encoding="utf-8",
        )

        scenario = parse_sdl_file(root)

        rel = scenario.relationships["shared.ssh-policy"]
        assert rel.source == "nodes.shared.kali.runtime.ssh_servers.sshd-default"
        assert rel.target == "nodes.shared.kali.runtime.ssh_servers.sshd-default.match_rules.m-kali"

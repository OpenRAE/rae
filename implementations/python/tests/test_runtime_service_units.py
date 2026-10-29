"""Model-level tests for the service-manager unit state runtime surface.

Covers ``raes.runtime_service_units`` (see ADR-035). These tests construct
``ServiceManagerUnit`` and ``ServiceUnitExecStart`` directly to exercise field
validators, redaction invariants, duplicate detection, and stable-identifier
discipline without going through the YAML parser.
"""

import pytest
from pydantic import ValidationError
from raes.runtime_configuration import RuntimeConfiguration
from raes.runtime_service_units import (
    ServiceManagerKind,
    ServiceManagerUnit,
    ServiceUnitActiveState,
    ServiceUnitEnabledState,
    ServiceUnitExecStart,
    ServiceUnitExecStartKind,
    ServiceUnitKind,
    ServiceUnitLoadState,
    ServiceUnitResult,
)

# ---------------------------------------------------------------------------
# ServiceUnitExecStart
# ---------------------------------------------------------------------------


class TestServiceUnitExecStart:
    def test_absolute_path_command_accepted(self):
        cmd = ServiceUnitExecStart(
            command_kind=ServiceUnitExecStartKind.ABSOLUTE_PATH,
            command="/opt/purple-team/scripts/install-all.sh",
        )
        assert cmd.command == "/opt/purple-team/scripts/install-all.sh"
        assert cmd.command_kind == ServiceUnitExecStartKind.ABSOLUTE_PATH
        assert cmd.command_redacted is False

    def test_absolute_path_command_must_be_absolute(self):
        with pytest.raises(ValidationError) as exc:
            ServiceUnitExecStart(
                command_kind=ServiceUnitExecStartKind.ABSOLUTE_PATH,
                command="opt/purple-team/scripts/install-all.sh",
            )
        assert "absolute path" in str(exc.value)

    def test_absolute_path_command_rejects_empty_string(self):
        with pytest.raises(ValidationError) as exc:
            ServiceUnitExecStart(
                command_kind=ServiceUnitExecStartKind.ABSOLUTE_PATH,
                command="",
            )
        assert "command" in str(exc.value)

    def test_redacted_must_have_empty_command(self):
        cmd = ServiceUnitExecStart(
            command_kind=ServiceUnitExecStartKind.REDACTED,
            command_redacted=True,
        )
        assert cmd.command == ""
        assert cmd.command_redacted is True

    def test_redacted_rejects_populated_command(self):
        with pytest.raises(ValidationError) as exc:
            ServiceUnitExecStart(
                command_kind=ServiceUnitExecStartKind.REDACTED,
                command_redacted=True,
                command="/usr/bin/secret",
            )
        assert "redacted" in str(exc.value).lower()

    def test_redacted_kind_requires_redacted_flag(self):
        with pytest.raises(ValidationError) as exc:
            ServiceUnitExecStart(
                command_kind=ServiceUnitExecStartKind.REDACTED,
                command_redacted=False,
            )
        assert "command_redacted" in str(exc.value).lower() or "redacted" in str(exc.value).lower()

    def test_redacted_flag_requires_redacted_kind(self):
        with pytest.raises(ValidationError) as exc:
            ServiceUnitExecStart(
                command_kind=ServiceUnitExecStartKind.ABSOLUTE_PATH,
                command_redacted=True,
            )
        assert "redacted" in str(exc.value).lower()

    def test_absolute_path_variable_ref_accepted(self):
        cmd = ServiceUnitExecStart(
            command_kind=ServiceUnitExecStartKind.ABSOLUTE_PATH,
            command="${install_script}",
        )
        assert cmd.command == "${install_script}"

    def test_command_kind_variable_ref_accepted(self):
        cmd = ServiceUnitExecStart(command_kind="${exec_kind}", command="${cmd}")
        assert cmd.command_kind == "${exec_kind}"
        # Guard against a covert-reset regression: the variable-kind branch is
        # the one path that bypasses _enforce_concrete_kind_command_shape, so a
        # future change that silently zeroed `command` here would break the
        # ExecStart redaction invariant without any other test noticing.
        assert cmd.command == "${cmd}"

    def test_command_kind_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            ServiceUnitExecStart(command_kind="exec", command="/bin/sh")


# ---------------------------------------------------------------------------
# ServiceManagerUnit — basic fields and enums
# ---------------------------------------------------------------------------


class TestServiceManagerUnitBasics:
    def _minimal_kwargs(self, **overrides):
        kwargs = {
            "unit_id": "sshd",
            "manager_kind": ServiceManagerKind.SYSTEMD,
            "unit_name": "sshd.service",
        }
        kwargs.update(overrides)
        return kwargs

    def test_minimal_unit_accepted_with_defaults(self):
        unit = ServiceManagerUnit(**self._minimal_kwargs())
        assert unit.unit_id == "sshd"
        assert unit.manager_kind == ServiceManagerKind.SYSTEMD
        assert unit.unit_name == "sshd.service"
        assert unit.unit_type == ServiceUnitKind.OTHER
        assert unit.load_state == ServiceUnitLoadState.UNKNOWN
        assert unit.active_state == ServiceUnitActiveState.UNKNOWN
        assert unit.enabled_state == ServiceUnitEnabledState.UNKNOWN
        assert unit.result == ServiceUnitResult.UNKNOWN
        assert unit.sub_state == ""
        assert unit.exit_code is None
        assert unit.status_text == ""
        assert unit.main_pid is None
        assert unit.unit_file_path == ""
        assert unit.exec_start is None
        assert unit.service == ""
        assert unit.description == ""

    def test_sshd_running_example(self):
        unit = ServiceManagerUnit(
            unit_id="sshd",
            manager_kind=ServiceManagerKind.SYSTEMD,
            unit_name="sshd.service",
            unit_type=ServiceUnitKind.SERVICE,
            load_state=ServiceUnitLoadState.LOADED,
            active_state=ServiceUnitActiveState.ACTIVE,
            sub_state="running",
            enabled_state=ServiceUnitEnabledState.ENABLED,
            result=ServiceUnitResult.SUCCESS,
            main_pid=55,
            service="ssh",
        )
        assert unit.main_pid == 55
        assert unit.service == "ssh"
        assert unit.sub_state == "running"

    def test_failed_unit_with_exit_code(self):
        unit = ServiceManagerUnit(
            unit_id="lab-install",
            manager_kind=ServiceManagerKind.SYSTEMD,
            unit_name="lab-install.service",
            unit_type=ServiceUnitKind.SERVICE,
            load_state=ServiceUnitLoadState.LOADED,
            active_state=ServiceUnitActiveState.FAILED,
            sub_state="failed",
            enabled_state=ServiceUnitEnabledState.ENABLED,
            result=ServiceUnitResult.EXIT_CODE,
            exit_code=1,
            unit_file_path="/etc/systemd/system/lab-install.service",
            exec_start=ServiceUnitExecStart(
                command_kind=ServiceUnitExecStartKind.ABSOLUTE_PATH,
                command="/opt/purple-team/scripts/install-all.sh",
            ),
        )
        assert unit.result == ServiceUnitResult.EXIT_CODE
        assert unit.exit_code == 1
        assert unit.unit_file_path == "/etc/systemd/system/lab-install.service"
        assert unit.exec_start.command == "/opt/purple-team/scripts/install-all.sh"

    def test_active_exited_example(self):
        unit = ServiceManagerUnit(
            unit_id="systemd-user-sessions",
            manager_kind=ServiceManagerKind.SYSTEMD,
            unit_name="systemd-user-sessions.service",
            unit_type=ServiceUnitKind.SERVICE,
            load_state=ServiceUnitLoadState.LOADED,
            active_state=ServiceUnitActiveState.ACTIVE,
            sub_state="exited",
            enabled_state=ServiceUnitEnabledState.STATIC,
            result=ServiceUnitResult.SUCCESS,
        )
        assert unit.active_state == ServiceUnitActiveState.ACTIVE
        assert unit.sub_state == "exited"

    def test_disabled_unit_example(self):
        unit = ServiceManagerUnit(
            unit_id="wazuh",
            manager_kind=ServiceManagerKind.SYSTEMD,
            unit_name="wazuh-agent.service",
            unit_type=ServiceUnitKind.SERVICE,
            load_state=ServiceUnitLoadState.LOADED,
            active_state=ServiceUnitActiveState.INACTIVE,
            enabled_state=ServiceUnitEnabledState.DISABLED,
        )
        assert unit.enabled_state == ServiceUnitEnabledState.DISABLED

    def test_status_text_records_systemd_status_code(self):
        unit = ServiceManagerUnit(
            unit_id="rsyslog",
            manager_kind=ServiceManagerKind.SYSTEMD,
            unit_name="rsyslog.service",
            active_state=ServiceUnitActiveState.FAILED,
            result=ServiceUnitResult.EXIT_CODE,
            status_text="226/NAMESPACE",
        )
        assert unit.status_text == "226/NAMESPACE"


class TestServiceManagerUnitValidation:
    def _minimal(self, **overrides):
        kwargs = {
            "unit_id": "u",
            "manager_kind": ServiceManagerKind.SYSTEMD,
            "unit_name": "u.service",
        }
        kwargs.update(overrides)
        return kwargs

    def test_unit_id_rejects_empty(self):
        with pytest.raises(ValidationError):
            ServiceManagerUnit(**self._minimal(unit_id=""))

    def test_unit_id_rejects_variable_placeholder(self):
        with pytest.raises(ValidationError) as exc:
            ServiceManagerUnit(**self._minimal(unit_id="${uid}"))
        assert "unit_id" in str(exc.value)

    def test_unit_name_rejects_empty(self):
        with pytest.raises(ValidationError):
            ServiceManagerUnit(**self._minimal(unit_name=""))

    def test_unit_name_rejects_whitespace(self):
        with pytest.raises(ValidationError) as exc:
            ServiceManagerUnit(**self._minimal(unit_name="sshd service"))
        assert "unit_name" in str(exc.value)

    def test_unit_name_requires_dot(self):
        with pytest.raises(ValidationError) as exc:
            ServiceManagerUnit(**self._minimal(unit_name="sshd"))
        assert "unit_name" in str(exc.value)

    def test_unit_name_rejects_variable_placeholder(self):
        # unit_name is data, not a stable id, but a placeholder leaves the
        # field uselessly opaque for duplicate detection and downstream consumers.
        with pytest.raises(ValidationError) as exc:
            ServiceManagerUnit(**self._minimal(unit_name="${name}"))
        assert "unit_name" in str(exc.value)

    def test_manager_kind_normalizes_hyphenated_value(self):
        unit = ServiceManagerUnit(**self._minimal(manager_kind="systemd"))
        assert unit.manager_kind == ServiceManagerKind.SYSTEMD

    def test_manager_kind_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            ServiceManagerUnit(**self._minimal(manager_kind="upstart-classic"))

    def test_manager_kind_variable_ref_accepted(self):
        unit = ServiceManagerUnit(**self._minimal(manager_kind="${manager}"))
        assert unit.manager_kind == "${manager}"

    def test_unit_type_accepts_socket(self):
        unit = ServiceManagerUnit(
            **self._minimal(unit_name="dbus.socket", unit_type=ServiceUnitKind.SOCKET),
        )
        assert unit.unit_type == ServiceUnitKind.SOCKET

    def test_unit_type_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            ServiceManagerUnit(**self._minimal(unit_type="container"))

    def test_load_state_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            ServiceManagerUnit(**self._minimal(load_state="garbage"))

    def test_active_state_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            ServiceManagerUnit(**self._minimal(active_state="zombie"))

    def test_enabled_state_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            ServiceManagerUnit(**self._minimal(enabled_state="latent"))

    def test_result_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            ServiceManagerUnit(**self._minimal(result="ok"))

    def test_main_pid_rejects_zero(self):
        with pytest.raises(ValidationError) as exc:
            ServiceManagerUnit(**self._minimal(main_pid=0))
        assert "main_pid" in str(exc.value)

    def test_main_pid_rejects_negative(self):
        with pytest.raises(ValidationError):
            ServiceManagerUnit(**self._minimal(main_pid=-1))

    def test_main_pid_accepts_string_integer(self):
        unit = ServiceManagerUnit(**self._minimal(main_pid="55"))
        assert unit.main_pid == 55

    def test_main_pid_variable_ref_accepted(self):
        unit = ServiceManagerUnit(**self._minimal(main_pid="${pid}"))
        assert unit.main_pid == "${pid}"

    def test_exit_code_rejects_out_of_range(self):
        # systemd exit codes are 8-bit. Anything outside 0..255 is suspect data.
        with pytest.raises(ValidationError):
            ServiceManagerUnit(**self._minimal(exit_code=256))

    def test_exit_code_accepts_boundary(self):
        unit = ServiceManagerUnit(
            **self._minimal(result=ServiceUnitResult.EXIT_CODE, exit_code=255),
        )
        assert unit.exit_code == 255

    def test_exit_code_rejects_negative(self):
        with pytest.raises(ValidationError):
            ServiceManagerUnit(**self._minimal(exit_code=-1))

    def test_exit_code_requires_exit_code_result(self):
        with pytest.raises(ValidationError) as exc:
            ServiceManagerUnit(
                **self._minimal(result=ServiceUnitResult.SUCCESS, exit_code=1),
            )
        assert "exit_code" in str(exc.value)

    def test_exit_code_allowed_when_result_is_exit_code(self):
        unit = ServiceManagerUnit(
            **self._minimal(result=ServiceUnitResult.EXIT_CODE, exit_code=1),
        )
        assert unit.exit_code == 1

    def test_exit_code_allowed_when_result_is_variable(self):
        unit = ServiceManagerUnit(**self._minimal(result="${result}", exit_code=1))
        assert unit.exit_code == 1

    def test_unit_file_path_must_be_absolute(self):
        with pytest.raises(ValidationError) as exc:
            ServiceManagerUnit(**self._minimal(unit_file_path="etc/systemd/u.service"))
        assert "absolute" in str(exc.value)

    def test_unit_file_path_accepts_variable_ref(self):
        unit = ServiceManagerUnit(**self._minimal(unit_file_path="${unit_path}"))
        assert unit.unit_file_path == "${unit_path}"

    def test_service_rejects_whitespace_only(self):
        with pytest.raises(ValidationError):
            ServiceManagerUnit(**self._minimal(service="   "))

    def test_sub_state_length_capped(self):
        with pytest.raises(ValidationError) as exc:
            ServiceManagerUnit(**self._minimal(sub_state="x" * 65))
        assert "sub_state" in str(exc.value)

    def test_status_text_length_capped(self):
        with pytest.raises(ValidationError) as exc:
            ServiceManagerUnit(**self._minimal(status_text="x" * 257))
        assert "status_text" in str(exc.value)


# ---------------------------------------------------------------------------
# RuntimeConfiguration — duplicate detection at the container level
# ---------------------------------------------------------------------------


def _unit(unit_id: str, unit_name: str) -> ServiceManagerUnit:
    return ServiceManagerUnit(
        unit_id=unit_id,
        manager_kind=ServiceManagerKind.SYSTEMD,
        unit_name=unit_name,
    )


class TestRuntimeConfigurationServiceManagerUnits:
    def test_distinct_units_coexist(self):
        runtime = RuntimeConfiguration(
            service_manager_units=[
                _unit("sshd", "sshd.service"),
                _unit("rsyslog", "rsyslog.service"),
            ],
        )
        assert len(runtime.service_manager_units) == 2

    def test_duplicate_unit_id_rejected(self):
        with pytest.raises(ValidationError) as exc:
            RuntimeConfiguration(
                service_manager_units=[
                    _unit("sshd", "sshd.service"),
                    _unit("sshd", "ssh.service"),
                ],
            )
        assert "service_manager_unit" in str(exc.value) or "unit_id" in str(exc.value)

    def test_duplicate_unit_name_rejected(self):
        with pytest.raises(ValidationError) as exc:
            RuntimeConfiguration(
                service_manager_units=[
                    _unit("sshd-1", "sshd.service"),
                    _unit("sshd-2", "sshd.service"),
                ],
            )
        assert "unit_name" in str(exc.value)


# ---------------------------------------------------------------------------
# SemanticValidator — same-node service ref + unit-file path cross-check
# ---------------------------------------------------------------------------


def _validate(scenario) -> list[str]:
    """Run validation and return errors (empty list = valid). Mirrors
    test_sdl_validator.py's helper so failures surface as readable lists."""
    from raes._errors import SDLValidationError
    from raes.validator import SemanticValidator

    try:
        SemanticValidator(scenario).validate()
    except SDLValidationError as e:
        return e.errors
    else:
        return []


def _scenario_with_units(units: list[dict], *, fs_inventory: list[dict] | None = None, nodes: dict | None = None):
    """Build a Scenario where `box` carries the units (and optional fs inventory)."""
    from raes.scenario import Scenario

    runtime: dict = {"service_manager_units": units}
    if fs_inventory is not None:
        runtime["filesystem_inventory"] = fs_inventory
    node = {
        "type": "compute",
        "resources": {"ram": "1 gib", "cpu": 1},
        "services": [{"port": 22, "name": "ssh"}],
        "runtime": runtime,
    }
    all_nodes = {"box": node}
    if nodes:
        all_nodes.update(nodes)
    return Scenario(name="t", nodes=all_nodes)


_BASE_UNIT: dict = {
    "unit_id": "sshd",
    "manager_kind": "systemd",
    "unit_name": "sshd.service",
}


class TestSemanticValidatorServiceManagerUnits:
    def test_bare_service_ref_resolves(self):
        s = _scenario_with_units([{**_BASE_UNIT, "service": "ssh"}])
        assert _validate(s) == []

    def test_qualified_service_ref_same_node_resolves(self):
        s = _scenario_with_units([{**_BASE_UNIT, "service": "nodes.box.services.ssh"}])
        assert _validate(s) == []

    def test_unknown_service_ref_rejected(self):
        s = _scenario_with_units([{**_BASE_UNIT, "service": "ghost"}])
        errors = _validate(s)
        assert any("service_manager_unit 'sshd'" in e and "'ghost'" in e for e in errors)

    def test_qualified_service_ref_other_node_rejected(self):
        s = _scenario_with_units(
            [{**_BASE_UNIT, "service": "nodes.other.services.ssh"}],
            nodes={
                "other": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "services": [{"port": 22, "name": "ssh"}],
                }
            },
        )
        errors = _validate(s)
        assert any("same node" in e for e in errors)

    def test_variable_service_ref_deferred(self):
        from raes.scenario import Scenario

        s = Scenario(
            name="t",
            variables={"svc": {"type": "string", "required": True}},
            nodes={
                "box": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "services": [{"port": 22, "name": "ssh"}],
                    "runtime": {
                        "service_manager_units": [{**_BASE_UNIT, "service": "${svc}"}],
                    },
                },
            },
        )
        assert _validate(s) == []

    def test_unit_file_path_matching_inventory_passes(self):
        s = _scenario_with_units(
            [{**_BASE_UNIT, "unit_file_path": "/etc/systemd/system/sshd.service"}],
            fs_inventory=[
                {
                    "path": "/etc/systemd/system/sshd.service",
                    "entry_type": "file",
                    "stability": "stable",
                },
            ],
        )
        assert _validate(s) == []

    def test_unit_file_path_missing_from_inventory_rejected(self):
        s = _scenario_with_units(
            [{**_BASE_UNIT, "unit_file_path": "/etc/systemd/system/sshd.service"}],
            fs_inventory=[
                {
                    "path": "/etc/systemd/system/other.service",
                    "entry_type": "file",
                    "stability": "stable",
                },
            ],
        )
        errors = _validate(s)
        assert any("unit_file_path" in e and "sshd.service" in e for e in errors)

    def test_unit_file_path_skipped_when_inventory_absent(self):
        # ADR-035 §4: "may be cross-checked... when present".
        s = _scenario_with_units(
            [{**_BASE_UNIT, "unit_file_path": "/etc/systemd/system/sshd.service"}],
        )
        assert _validate(s) == []

    def test_variable_unit_file_path_deferred(self):
        from raes.scenario import Scenario

        s = Scenario(
            name="t",
            variables={"unit_path": {"type": "string", "required": True}},
            nodes={
                "box": {
                    "type": "compute",
                    "resources": {"ram": "1 gib", "cpu": 1},
                    "services": [{"port": 22, "name": "ssh"}],
                    "runtime": {
                        "service_manager_units": [{**_BASE_UNIT, "unit_file_path": "${unit_path}"}],
                        "filesystem_inventory": [
                            {
                                "path": "/etc/systemd/system/sshd.service",
                                "entry_type": "file",
                                "stability": "stable",
                            },
                        ],
                    },
                },
            },
        )
        assert _validate(s) == []

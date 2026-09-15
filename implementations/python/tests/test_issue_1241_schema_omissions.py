"""Review F1: schema-only readers enforce native runtime omission rules."""

import ast
import importlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from raes_contracts.contracts import schema_bundle

VALUE_CASES = [
    ("runtime_forwarding_agent", "RuntimeForwardingSetting", "classification", "value", {"setting_id": "setting"}),
    (
        "runtime_platform_application_content",
        "RuntimePlatformApplicationSetting",
        "classification",
        "value",
        {"setting_id": "setting"},
    ),
    ("runtime_datastore_partitions", "RuntimeDatastoreSetting", "classification", "value", {"setting_id": "setting"}),
    ("runtime_directory_identity", "RuntimeIdentityAttribute", "value_classification", "values", {"name": "attribute"}),
    (
        "runtime_mail_service",
        "RuntimeMailSetting",
        "value_classification",
        "value",
        {"setting_id": "setting", "name": "setting"},
    ),
    (
        "runtime_security_monitoring",
        "RuntimeSecurityMonitoringSetting",
        "value_classification",
        "value",
        {"setting_id": "setting", "name": "setting"},
    ),
    ("runtime_database", "DatabaseSetting", "value_classification", "value", {"name": "setting"}),
    ("runtime_dns", "DnsRuntimeSetting", "value_classification", "value", {"name": "setting"}),
    ("runtime_application", "RuntimeApplicationExposedField", "sensitivity", "value", {"name": "field"}),
    ("runtime_environment", "RuntimeEnvironmentVariable", "value_classification", "value", {"name": "SETTING"}),
    ("image_provenance", "ImageBuildArg", "value_classification", "value", {"name": "SETTING"}),
    ("image_provenance", "ImageEnvironmentDefault", "value_classification", "value", {"name": "SETTING"}),
]


def test_redaction_regressions_cover_every_shared_value_omission_consumer():
    root = Path(__file__).resolve().parents[1] / "packages/raes"
    consumers = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "enforce_observed_value_redaction"
                for call in ast.walk(node)
            ):
                consumers.add(node.name)
    assert consumers == {case[1] for case in VALUE_CASES}


@pytest.fixture(scope="module")
def phase_schemas():
    bundle = schema_bundle()
    root = Path(__file__).resolve().parents[3]
    schemas = [
        bundle[name]
        for name in ("sdl-authoring-input-v1", "instantiated-scenario-snapshot-v1", "materialized-scenario-v1")
    ]
    schemas.append(json.loads((root / "contracts/schemas/sdl/materialized-scenario-v1.json").read_text()))
    return schemas


def assert_schema_admission(schemas, name, payload, expected):
    for schema in schemas:
        validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": f"#/$defs/{name}"})
        assert validator.is_valid(payload) is expected, (name, schema.get("title"), payload)


@pytest.mark.parametrize(
    "module,name,raw,seed",
    [
        ("runtime_container", "RuntimeInitProcess", "argv", {"argv_redacted": True}),
        ("runtime_identity", "RuntimeSudoRule", "commands", {"principal": "user", "command_redacted": True}),
        ("runtime_ssh_server", "SshForcedCommand", "command", {"command_kind": "redacted", "command_redacted": True}),
        (
            "runtime_service_units",
            "ServiceUnitExecStart",
            "command",
            {"command_kind": "redacted", "command_redacted": True},
        ),
    ],
)
@pytest.mark.parametrize("flag", [True, "true", "YES", "on", " 1 "])
def test_redacted_commands_are_omitted_in_every_phase_schema(phase_schemas, module, name, raw, seed, flag):
    model = getattr(importlib.import_module(f"raes.{module}"), name)
    seed = {key: flag if value is True else value for key, value in seed.items()}
    model.model_validate(seed)
    assert_schema_admission(phase_schemas, name, seed, True)
    invalid = {**seed, raw: "/bin/withheld" if raw == "command" else ["/bin/withheld"]}
    with pytest.raises(ValueError):
        model.model_validate(invalid)
    assert_schema_admission(phase_schemas, name, invalid, False)


def test_redacted_process_limit_subject_omits_command(phase_schemas):
    from raes.runtime_resource_limits import RuntimeProcessResourceLimit

    payload = {
        "resource": "open_file_descriptors",
        "soft": 10,
        "hard": 20,
        "subject": {"pid": 1, "command_redacted": True},
    }
    RuntimeProcessResourceLimit.model_validate(payload)
    assert_schema_admission(phase_schemas, "RuntimeProcessResourceLimit", payload, True)
    payload["subject"]["command"] = ["/bin/withheld"]
    with pytest.raises(ValueError):
        RuntimeProcessResourceLimit.model_validate(payload)
    assert_schema_admission(phase_schemas, "RuntimeProcessResourceLimit", payload, False)


@pytest.mark.parametrize("module,name,classification,raw,seed", VALUE_CASES)
@pytest.mark.parametrize("label", ["redacted", "operator_secret", "OPERATOR-SECRET"])
def test_redacted_values_are_omitted_in_every_phase_schema(
    phase_schemas, module, name, classification, raw, seed, label
):
    model = getattr(importlib.import_module(f"raes.{module}"), name)
    valid = {**seed, classification: label}
    model.model_validate(valid)
    assert_schema_admission(phase_schemas, name, valid, True)
    empty = [] if raw == "values" else ""
    assert_schema_admission(phase_schemas, name, {**valid, raw: empty}, True)
    invalid = {**valid, raw: ["withheld"] if raw == "values" else "withheld"}
    with pytest.raises(ValueError):
        model.model_validate(invalid)
    assert_schema_admission(phase_schemas, name, invalid, False)
    visible = {**invalid, classification: "plain"}
    model.model_validate(visible)
    assert_schema_admission(phase_schemas, name, visible, True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_user", "user"),
        ("owner_group", "group"),
        ("uid", 0),
        ("gid", 0),
        ("mode", "0600"),
        ("size", 0),
        ("content_digest", "abc"),
        ("digest_algorithm", "sha256"),
    ],
)
def test_absent_filesystem_entries_omit_present_only_facts(phase_schemas, field, value):
    from raes.runtime_filesystem import RuntimeFilesystemEntry

    valid = {"path": "/missing", "presence": "expected_absent", "entry_type": "file"}
    RuntimeFilesystemEntry.model_validate(valid)
    assert_schema_admission(phase_schemas, "RuntimeFilesystemEntry", valid, True)
    invalid = {**valid, field: value}
    if field in {"content_digest", "digest_algorithm"}:
        invalid.update(content_digest="abc", digest_algorithm="sha256")
    with pytest.raises(ValueError):
        RuntimeFilesystemEntry.model_validate(invalid)
    assert_schema_admission(phase_schemas, "RuntimeFilesystemEntry", invalid, False)
    present = {**invalid, "presence": "present"}
    RuntimeFilesystemEntry.model_validate(present)
    assert_schema_admission(phase_schemas, "RuntimeFilesystemEntry", present, True)

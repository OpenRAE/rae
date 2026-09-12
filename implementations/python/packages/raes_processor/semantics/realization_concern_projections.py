"""Canonical comparison projections for portable realization concerns."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError
from pydantic_core import to_jsonable_python
from raes.runtime_capabilities import RuntimeProcessIdentity
from raes.runtime_generated_value import GeneratedArtifactValueSource
from raes.runtime_resource_limits import project_process_resource_limit
from raes_contracts.canonical import canonical_json_digest

from .realization_concern_observations import validate_value_commitment
from .realization_runtime_concern_profiles import RUNTIME_NON_REALIZATION_FIELDS

_COMMITMENT_PREFIX = "raes-runtime-value-jcs-sha256-v1:"
_PROTECTED = frozenset({"redacted", "operator_secret"})


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, *, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be an array")
    return value


def _require_observation_mode(observed: bool) -> None:
    if not isinstance(observed, bool):
        raise TypeError("observed must be boolean")


def _commitment(*, concern_kind: str, identity: str, value: object) -> str:
    digest = canonical_json_digest(
        {
            "domain": "raes.runtime.realization-concern-value",
            "version": 1,
            "concern_kind": concern_kind,
            "identity": identity,
            "value": value,
        }
    )
    return f"{_COMMITMENT_PREFIX}{digest}"


def _committed_value(
    record: Mapping[str, Any],
    *,
    concern_kind: str,
    identity: str,
    classification_field: str,
    observed: bool,
) -> dict[str, object]:
    classification = record.get(classification_field, "")
    raw_value = record.get("value", "")
    supplied_commitment = record.get("value_commitment")
    if classification in _PROTECTED and raw_value not in ("", None):
        raise ValueError("protected realization values must not carry raw material")
    if observed and classification == "secret_fixture" and raw_value not in ("", None):
        raise ValueError("observed secret fixtures must use a value commitment")
    if supplied_commitment is not None:
        if raw_value not in ("", None):
            raise ValueError("realization values must not carry raw material beside a commitment")
        validate_value_commitment(supplied_commitment)
        return {
            "value_present": True,
            "value_commitment": supplied_commitment,
        }
    if raw_value not in ("", None):
        return {
            "value_present": True,
            "value_commitment": _commitment(
                concern_kind=concern_kind,
                identity=identity,
                value=raw_value,
            ),
        }
    return {
        "value_present": classification in _PROTECTED,
    }


def project_environment(value: object, observed: bool = False) -> object:
    _require_observation_mode(observed)
    projected: list[dict[str, object]] = []
    for item in _sequence(value, label="runtime environment"):
        record = _mapping(item, label="runtime environment entry")
        name = record.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("runtime environment entries require a name")
        entry: dict[str, object] = {
            "name": name,
            "value_classification": record.get("value_classification", "unknown"),
            "provenance": record.get("provenance", "unknown"),
            "source": record.get("source", ""),
        }
        # A value-free generated-artifact source (issue #1074) is exact realization
        # metadata (artifact id + output name), not a secret, so pin it into the
        # projection; entries without it keep their prior shape.
        value_from = record.get("value_from")
        if value_from is not None:
            try:
                source = GeneratedArtifactValueSource.model_validate(value_from)
            except ValidationError:
                raise ValueError(
                    "runtime environment value_from must be a closed generated-artifact output reference"
                ) from None
            entry["value_from"] = {
                "generated_artifact": source.generated_artifact,
                "output": source.output,
            }
        entry.update(
            _committed_value(
                record,
                concern_kind="runtime-environment",
                identity=name,
                classification_field="value_classification",
                observed=observed,
            )
        )
        projected.append(entry)
    return sorted(projected, key=lambda item: str(item["name"]))


def project_recursive_environment(value: object, observed: bool = False) -> object:
    """Keep source occurrences for metadata binding; the profile owns set identity."""

    return [
        project_environment([item], observed)[0]
        for item in _sequence(to_jsonable_python(value), label="runtime environment")
    ]


def _project_mounts(
    value: object,
    *,
    include_stateful: bool,
) -> list[dict[str, object]]:
    records = (_mapping(item, label="runtime mount") for item in _sequence(value, label="runtime mounts"))
    projected = [
        _project_mount_record(record)
        for record in records
        if include_stateful or record.get("source_kind") in {"bind", "tmpfs"}
    ]
    return sorted(projected, key=lambda item: str(item["target"]))


def _project_mount_record(record: Mapping[str, Any]) -> dict[str, object]:
    target = record.get("target")
    if not isinstance(target, str) or not target:
        raise ValueError("runtime mounts require a target")
    source, source_present = _project_mount_sensitive_text(
        record.get("source", ""),
        record.get("source_sensitivity", "unknown"),
        label="source",
    )
    options, options_present = _project_mount_sensitive_options(
        record.get("options", []),
        record.get("options_sensitivity", "unknown"),
        label="options",
    )
    return {
        "target": target,
        "source": source,
        "source_present": source_present,
        "source_sensitivity": record.get("source_sensitivity", "unknown"),
        "source_kind": record.get("source_kind"),
        "filesystem_type": record.get("filesystem_type", ""),
        "read_only": record.get("read_only", False),
        "options": sorted(options),
        "options_present": options_present,
        "options_sensitivity": record.get("options_sensitivity", "unknown"),
        "propagation": record.get("propagation", "unknown"),
        "stability": record.get("stability", "unknown"),
        "backend_generated": record.get("backend_generated"),
    }


def _project_mount_sensitive_text(
    value: object,
    sensitivity: object,
    *,
    label: str,
) -> tuple[str, bool]:
    if not isinstance(value, str):
        raise ValueError(f"runtime mount {label} must be a string")
    if sensitivity in _PROTECTED:
        if value:
            raise ValueError(f"protected runtime mount {label} must not carry raw material")
        return "", True
    return value, bool(value)


def _project_mount_sensitive_options(
    value: object,
    sensitivity: object,
    *,
    label: str,
) -> tuple[list[object], bool]:
    options = list(_sequence(value, label=f"runtime mount {label}"))
    if sensitivity in _PROTECTED:
        if options:
            raise ValueError(f"protected runtime mount {label} must not carry raw material")
        return [], True
    return options, bool(options)


def project_mounts(value: object, observed: bool = False) -> object:
    """Project the bind/tmpfs realization concern for portable comparison."""

    _require_observation_mode(observed)
    return _project_mounts(value, include_stateful=False)


def sanitize_mount_observation(value: object, observed: bool = False) -> object:
    """Return a safe persisted mount inventory, including stateful records."""

    _require_observation_mode(observed)
    return _project_mounts(value, include_stateful=True)


def project_capability_policy(value: object, observed: bool = False) -> object:
    _require_observation_mode(observed)
    record = _mapping(value, label="Linux capability policy")
    overrides: list[dict[str, object]] = []
    for item in _sequence(record.get("process_overrides", []), label="process capability overrides"):
        override = _mapping(item, label="process capability override")
        subject = RuntimeProcessIdentity.model_validate(
            _mapping(override.get("subject"), label="process capability override subject")
        ).model_dump(mode="json")
        projected_subject = {
            key: subject[key]
            for key in (
                "name",
                "pid",
                "parent_pid",
                "command",
                "command_redacted",
                "role",
                "user",
                "group",
                "working_directory",
            )
        }
        if projected_subject["command_redacted"]:
            projected_subject["command"] = []
        overrides.append(
            {
                "subject": projected_subject,
                "scope": override.get("scope", "process"),
                "effective": sorted(override.get("effective", [])),
                "add": sorted(override.get("add", [])),
                "drop": sorted(override.get("drop", [])),
            }
        )
    return {
        "required": sorted(record.get("required", [])),
        "effective": sorted(record.get("effective", [])),
        "add": sorted(record.get("add", [])),
        "drop": sorted(record.get("drop", [])),
        "process_overrides": sorted(overrides, key=canonical_json_digest),
    }


def project_process_resource_limits(value: object, observed: bool = False) -> object:
    """Project process limits by semantic identity, without native evidence."""

    _require_observation_mode(observed)
    projected = [
        project_process_resource_limit(_mapping(item, label="process resource limit"))
        for item in _sequence(value, label="process resource limits")
    ]
    return sorted(projected, key=canonical_json_digest)


def project_published_ports(value: object, observed: bool = False) -> object:
    _require_observation_mode(observed)
    projected = []
    for item in _sequence(value, label="published ports"):
        record = _mapping(item, label="published port")
        projected.append(
            {
                "host_ip": record.get("host_ip", ""),
                "host_port": record.get("host_port"),
                "container_port": record.get("container_port"),
                "protocol": record.get("protocol", "tcp"),
            }
        )
    return sorted(
        projected,
        key=lambda item: (
            str(item["host_ip"]),
            str(item["host_port"]),
            str(item["container_port"]),
            str(item["protocol"]),
        ),
    )


def _without_annotations(record: Mapping[str, Any]) -> dict[str, object]:
    return {key: value for key, value in record.items() if key not in RUNTIME_NON_REALIZATION_FIELDS}


def _sorted_records(value: object, *, label: str, identity: str) -> list[dict[str, object]]:
    projected = [_without_annotations(_mapping(item, label=label)) for item in _sequence(value, label=label)]
    return sorted(projected, key=lambda item: str(item.get(identity, "")))


def project_forwarding_agents(value: object, observed: bool = False) -> object:
    _require_observation_mode(observed)
    projected: list[dict[str, object]] = []
    for item in _sequence(value, label="forwarding agents"):
        record = _mapping(item, label="forwarding agent")
        agent_id = record.get("forwarding_agent_id")
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("forwarding agents require a forwarding_agent_id")
        agent = _without_annotations(record)
        # Ownership is authored experiment meaning, not backend-observed
        # forwarding-agent configuration.
        agent.pop("ownership_role", None)
        for field, identity in (
            ("sources", "source_id"),
            ("transforms", "transform_id"),
            ("ship_targets", "target_id"),
            ("reload_channels", "reload_channel_id"),
        ):
            agent[field] = _sorted_records(record.get(field, []), label=field, identity=identity)
        settings = []
        for setting_value in _sequence(record.get("settings", []), label="forwarding settings"):
            setting = _mapping(setting_value, label="forwarding setting")
            setting_id = setting.get("setting_id")
            if not isinstance(setting_id, str) or not setting_id:
                raise ValueError("forwarding settings require a setting_id")
            projected_setting: dict[str, object] = {
                "setting_id": setting_id,
                "name": setting.get("name", ""),
                "provenance": setting.get("provenance", "unknown"),
                "classification": setting.get("classification", "plain"),
            }
            projected_setting.update(
                _committed_value(
                    setting,
                    concern_kind="forwarding-agents",
                    identity=f"{agent_id}:{setting_id}",
                    classification_field="classification",
                    observed=observed,
                )
            )
            settings.append(projected_setting)
        agent["settings"] = sorted(settings, key=lambda setting: str(setting["setting_id"]))
        buffer_policy = record.get("buffer_policy")
        agent["buffer_policy"] = (
            _without_annotations(_mapping(buffer_policy, label="forwarding buffer policy"))
            if buffer_policy is not None
            else None
        )
        projected.append(agent)
    return sorted(projected, key=lambda item: str(item["forwarding_agent_id"]))


def project_service_listeners(value: object, observed: bool = False) -> object:
    from raes.runtime_listeners import RuntimeServiceListener

    _require_observation_mode(observed)
    projected: list[dict[str, object]] = []
    for item in _sequence(value, label="service listeners"):
        record = _mapping(item, label="service listener")
        listener_id = record.get("service_listener_id")
        if not isinstance(listener_id, str) or not listener_id:
            raise ValueError("service listeners require a service_listener_id")
        normalized = RuntimeServiceListener.model_validate(record).model_dump(mode="json")
        listener = {
            key: normalized[key]
            for key in (
                "service_listener_id",
                "service",
                "address",
                "port",
                "protocol",
                "address_family",
                "scope",
                "bind_interface",
                "socket_path",
                "process_ref",
                "process_name",
            )
        }
        projected.append(listener)
    return sorted(projected, key=lambda item: str(item["service_listener_id"]))


__all__ = [
    "project_capability_policy",
    "project_environment",
    "project_forwarding_agents",
    "project_mounts",
    "project_published_ports",
    "project_process_resource_limits",
    "project_service_listeners",
    "sanitize_mount_observation",
]

"""Runtime target construction for the libvirt/QEMU backend."""

from __future__ import annotations

from typing import Any

from raes_backend_protocols.capabilities import BackendManifest, OperatingSystemCompatibility
from raes_runtime.registry import (
    BackendRegistry,
    RuntimeTarget,
    RuntimeTargetComponents,
    backend_selection_observation_runtime,
)

from .driver import LibvirtDriver
from .drivers.libvirt import LibvirtDeploymentDriver
from .envelopes import LibvirtDriverMode
from .manifest import LIBVIRT_BACKEND_NAME, create_libvirt_manifest, realized_target_architecture
from .participant_runtime import LibvirtParticipantRuntime
from .provisioner import LibvirtProvisioner


def create_libvirt_components(
    *,
    manifest: BackendManifest,
    driver: LibvirtDriver | None = None,
    **config: Any,
) -> RuntimeTargetComponents:
    """Build libvirt backend components for a manifest."""

    if manifest.has_orchestrator or manifest.has_evaluator:
        raise ValueError("libvirt backend does not support orchestrator or evaluator.")
    mode = _selected_driver_mode(config, driver=driver)
    _validate_manifest_mode(manifest, mode)
    deployment_driver = driver if driver is not None else LibvirtDeploymentDriver(**_driver_config(config))
    participant_runtime = LibvirtParticipantRuntime() if manifest.has_participant_runtime else None
    return RuntimeTargetComponents(
        provisioner=LibvirtProvisioner(
            deployment_driver,
            provisioner_capabilities=manifest.provisioner,
            realization_envelope=manifest.realization_envelope.identity,
        ),
        participant_runtime=participant_runtime,
        observation_runtime=backend_selection_observation_runtime(manifest),
    )


def create_libvirt_target(**config: Any) -> RuntimeTarget:
    """Return a fully configured libvirt provisioning target."""

    _validate_config_keys(config)
    mode = _selected_driver_mode(config, driver=config.get("driver"))
    normalized = {**config, "driver_mode": mode.value}
    manifest = create_libvirt_manifest(**normalized)
    components = create_libvirt_components(manifest=manifest, **normalized)
    return RuntimeTarget(
        name=LIBVIRT_BACKEND_NAME,
        manifest=manifest,
        provisioner=components.provisioner,
        orchestrator=components.orchestrator,
        evaluator=components.evaluator,
        participant_runtime=components.participant_runtime,
        observation_runtime=components.observation_runtime,
    )


def register_libvirt_backend(registry: BackendRegistry) -> None:
    """Register the libvirt backend descriptor on ``registry``."""

    registry.register(LIBVIRT_BACKEND_NAME, create_libvirt_manifest, create_libvirt_components)


def _driver_config(config: dict[str, Any]) -> dict[str, Any]:
    accepted = {
        "connection",
        "connection_uri",
        "connector",
        "name_prefix",
        "workspace",
        "seed_builder",
    }
    driver_config = {key: value for key, value in config.items() if key in accepted}
    if "uri" in config and "connection_uri" not in driver_config:
        driver_config["connection_uri"] = config["uri"]
    return driver_config


_CONFIG_KEYS = {
    "connection",
    "connection_uri",
    "connector",
    "driver",
    "driver_mode",
    "name_prefix",
    "participant_runtime",
    "seed_builder",
    "uri",
    "workspace",
}


def _validate_config_keys(config: dict[str, Any]) -> None:
    unknown = sorted(set(config) - _CONFIG_KEYS)
    if unknown:
        raise ValueError("unknown libvirt target configuration: " + ", ".join(unknown))


def _selected_driver_mode(config: dict[str, Any], *, driver: object | None) -> LibvirtDriverMode:
    raw_mode = config.get("driver_mode")
    declared = getattr(driver, "driver_mode", None)
    if driver is not None and raw_mode is None and declared is None:
        raise ValueError("driver_mode is required when injecting a libvirt driver that declares no mode")
    mode = LibvirtDriverMode(raw_mode or declared or LibvirtDriverMode.GENERIC.value)
    if declared is not None and declared != mode.value:
        raise ValueError(f"injected driver mode '{declared}' does not match driver_mode '{mode.value}'")
    return mode


def _validate_manifest_mode(manifest: BackendManifest, mode: LibvirtDriverMode) -> None:
    envelope = manifest.realization_envelope
    if envelope is None or envelope.configuration.mode != mode.value:
        raise ValueError("libvirt manifest realization envelope does not match driver_mode")
    configuration = envelope.configuration
    expected = {
        "supported_node_types": frozenset(configuration.supported_node_types),
        "supported_os_families": frozenset(configuration.supported_os_families),
        "operating_systems": tuple(
            OperatingSystemCompatibility(
                family=entry.family,
                distribution=entry.distribution,
                versions=frozenset(entry.versions),
            )
            for entry in configuration.operating_systems
        ),
        "supported_node_architectures": frozenset({realized_target_architecture(configuration)}),
        "supported_content_types": frozenset(configuration.supported_content_types),
        "supported_account_features": frozenset(configuration.supported_account_features),
        "supported_domain_profiles": frozenset(configuration.supported_domain_profiles),
        "supported_service_materialization_profiles": frozenset(),
        "supports_accounts": bool(configuration.supported_account_features),
        "supports_acls": configuration.supports_acls,
    }
    actual = {field: getattr(manifest.provisioner, field) for field in expected}
    if actual != expected:
        raise ValueError("libvirt manifest capabilities do not match realization envelope")

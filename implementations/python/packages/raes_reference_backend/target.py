"""Runtime target construction + registry registration (RUN-314).

Constructs the reference backend's components and target through the
existing ``BackendRegistry`` descriptor seam. Config kwargs flow to both
the manifest factory and ``create_reference_backend_components``; the
default driver is the hermetic :class:`InProcessDriver`.
"""

from __future__ import annotations

from raes_backend_protocols.capabilities import BackendManifest
from raes_runtime.registry import (
    BackendRegistry,
    ReferenceTimeRuntime,
    RuntimeTarget,
    RuntimeTargetComponents,
    backend_selection_observation_runtime,
)

from .driver import DeploymentDriver
from .drivers.inprocess import InProcessDriver
from .envelopes import ReferenceDriverMode
from .evaluator import ReferenceEvaluator
from .manifest import REFERENCE_BACKEND_NAME, create_reference_backend_manifest
from .orchestrator import ReferenceOrchestrator
from .participant_runtime import ReferenceParticipantRuntime
from .provisioner import ReferenceProvisioner


def create_reference_backend_components(
    *,
    manifest: BackendManifest,
    driver: DeploymentDriver | None = None,
    **config,
) -> RuntimeTargetComponents:
    """Build the reference backend components for a manifest.

    The default ``driver`` is the hermetic in-process driver. Component
    presence matches the manifest's declared capabilities.
    """

    deployment_driver = driver if driver is not None else InProcessDriver()
    mode = ReferenceDriverMode(getattr(deployment_driver, "driver_mode", ""))
    envelope = manifest.realization_envelope
    if envelope is None or envelope.configuration.mode != mode.value:
        raise ValueError("reference manifest realization envelope does not match deployment driver mode")
    return RuntimeTargetComponents(
        provisioner=ReferenceProvisioner(
            deployment_driver,
            envelope,
            domain_profile_context=config.get("domain_profile_context"),
            profile_choices=config.get("profile_choices"),
        ),
        orchestrator=ReferenceOrchestrator() if manifest.has_orchestrator else None,
        evaluator=ReferenceEvaluator() if manifest.has_evaluator else None,
        participant_runtime=ReferenceParticipantRuntime() if manifest.has_participant_runtime else None,
        time_runtime=ReferenceTimeRuntime() if manifest.has_time else None,
        observation_runtime=backend_selection_observation_runtime(manifest),
    )


def create_reference_backend_target(**config) -> RuntimeTarget:
    """Return a fully configured reference emulation backend target."""

    config.setdefault("with_time", True)
    manifest = create_reference_backend_manifest(**config)
    components = create_reference_backend_components(manifest=manifest, **config)
    return RuntimeTarget(
        name=REFERENCE_BACKEND_NAME,
        manifest=manifest,
        provisioner=components.provisioner,
        orchestrator=components.orchestrator,
        evaluator=components.evaluator,
        participant_runtime=components.participant_runtime,
        time_runtime=components.time_runtime,
        observation_runtime=components.observation_runtime,
    )


def register_reference_backend(registry: BackendRegistry) -> None:
    """Register the reference emulation backend descriptor on ``registry``."""

    registry.register(
        REFERENCE_BACKEND_NAME,
        create_reference_backend_manifest,
        create_reference_backend_components,
    )

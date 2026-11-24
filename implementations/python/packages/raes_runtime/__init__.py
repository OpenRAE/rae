"""Live runtime control surfaces for RAES SDL, loaded at their public boundary.

Lazy exports keep deterministic delivery workers from initializing backend,
contract-corpus and state-owner integrations merely by importing their package.
"""

from __future__ import annotations

from importlib import import_module

_LAZY_EXPORTS = {
    "raes_runtime.control_plane": ("RuntimeControlPlane",),
    "raes_runtime.control_plane_profiles": (
        "ControlPlaneActorBoundary",
        "ControlPlaneCapability",
        "ControlPlaneClaim",
        "ControlPlaneProfile",
        "ControlPlaneProfileDeclaration",
        "ControlPlaneStoreCapabilities",
        "RecoveryObservationRequirement",
        "profile_declaration",
    ),
    "raes_runtime.experiment_records": (
        "ExperimentRunMetadata",
        "ExperimentRecordBundle",
        "ExperimentRecordSource",
        "ExperimentAccounting",
        "ExperimentRecordArchive",
        "ExperimentEvidenceReader",
    ),
    "raes_runtime.manager": ("RuntimeManager",),
    "raes_runtime.mixed_runtime": ("MixedPhaseTransitionEvaluation", "MixedRuntimeBinding", "MixedRuntimeComponent"),
    "raes_runtime.mixed_backend_installation": ("MixedBackendInstallation", "MixedBackendService"),
    "raes_runtime.registry": ("BackendRegistry", "RuntimeTarget", "RuntimeTargetComponents", "RuntimeTargetDescriptor"),
    "raes_runtime.runtime_fact_bindings": (
        "RuntimeFactActionDisposition",
        "RuntimeFactBindingAdmission",
        "RuntimeFactBindingPlane",
        "RuntimeFactBindingResult",
        "RuntimeFactDispatchCommand",
    ),
}


def __getattr__(name: str) -> object:
    for module, names in _LAZY_EXPORTS.items():
        if name in names:
            value = getattr(import_module(module), name)
            globals()[name] = value
            return value
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


__all__ = [
    "ExperimentRunMetadata",
    "ExperimentRecordBundle",
    "ExperimentRecordSource",
    "ExperimentAccounting",
    "ExperimentRecordArchive",
    "ExperimentEvidenceReader",
    "BackendRegistry",
    "ControlPlaneActorBoundary",
    "ControlPlaneCapability",
    "ControlPlaneClaim",
    "ControlPlaneProfile",
    "ControlPlaneProfileDeclaration",
    "ControlPlaneStoreCapabilities",
    "RecoveryObservationRequirement",
    "RuntimeControlPlane",
    "RuntimeFactActionDisposition",
    "RuntimeFactBindingAdmission",
    "RuntimeFactBindingPlane",
    "RuntimeFactBindingResult",
    "RuntimeFactDispatchCommand",
    "RuntimeManager",
    "MixedPhaseTransitionEvaluation",
    "MixedRuntimeBinding",
    "MixedBackendInstallation",
    "MixedBackendService",
    "MixedRuntimeComponent",
    "RuntimeTarget",
    "RuntimeTargetComponents",
    "RuntimeTargetDescriptor",
    "profile_declaration",
]

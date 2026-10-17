"""Live runtime control surfaces for RAES SDL, loaded at their public boundary.

Lazy exports keep deterministic delivery workers from initializing backend,
contract-corpus and state-owner integrations merely by importing their package.
"""

from __future__ import annotations

from importlib import import_module

_EXPORT_MODULES = {
    "control_plane": ("RuntimeControlPlane",),
    "control_plane_profiles": (
        "ControlPlaneActorBoundary",
        "ControlPlaneCapability",
        "ControlPlaneClaim",
        "ControlPlaneProfile",
        "ControlPlaneProfileDeclaration",
        "ControlPlaneStoreCapabilities",
        "RecoveryObservationRequirement",
        "profile_declaration",
    ),
    "manager": ("RuntimeManager",),
    "mixed_runtime": ("MixedPhaseTransitionEvaluation", "MixedRuntimeBinding", "MixedRuntimeComponent"),
    "mixed_backend_installation": ("MixedBackendInstallation", "MixedBackendService"),
    "registry": ("BackendRegistry", "RuntimeTarget", "RuntimeTargetComponents", "RuntimeTargetDescriptor"),
    "runtime_fact_bindings": (
        "RuntimeFactActionDisposition",
        "RuntimeFactBindingAdmission",
        "RuntimeFactBindingPlane",
        "RuntimeFactBindingResult",
        "RuntimeFactDispatchCommand",
    ),
}


def __getattr__(name: str) -> object:
    for module, names in _EXPORT_MODULES.items():
        if name in names:
            value = getattr(import_module(f".{module}", __name__), name)
            globals()[name] = value
            return value
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


__all__ = [
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

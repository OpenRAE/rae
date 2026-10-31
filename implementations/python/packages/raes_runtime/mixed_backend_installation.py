"""Trusted, role-specific installation of portable mixed execution services."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from raes_backend_protocols.mixed_backend import require_mixed_backend_service
from raes_contracts.contracts import MixedBackendExecutionBindingModel, MixedBackendServiceModel
from raes_contracts.errors import ConflictError

from .operation_supervision_configuration import OperationEvidenceResolver

if TYPE_CHECKING:
    from raes_contracts.contracts.mixed_composition import MixedCompositionEdgeModel

    from .mixed_runtime import MixedRuntimeBinding


@dataclass(frozen=True)
class MixedBackendService:
    """An embedder-authenticated implementation pin; never resolved from backend input."""

    identity: MixedBackendServiceModel
    implementation: object
    declared_contracts: tuple[str, ...]


@dataclass(frozen=True)
class MixedBackendInstallation:
    """One obligation's installed services and protected native artifact authority."""

    binding: MixedBackendExecutionBindingModel
    services: Mapping[str, MixedBackendService]
    time_runtime: object
    evidence: OperationEvidenceResolver

    def __post_init__(self) -> None:
        binding = MixedBackendExecutionBindingModel.model_validate(self.binding.model_dump(mode="json"))
        subject = binding.subject
        pins = [(subject.time.coordinator, "coordinator")]
        if subject.kind == "edge":
            pins += [(subject.bridge, "bridge"), (subject.delivery_reader, "reader")]
            if subject.observation_reader is not None:
                pins.append((subject.observation_reader, "reader"))
        else:
            pins += [(subject.transfer, "bridge"), (subject.owner_reader, "reader")]
        if set(self.services) != {pin.service_ref for pin, _ in pins}:
            raise ValueError("mixed services must exactly cover the pinned roles")
        implementations = []
        for pin, role in pins:
            service = self.services[pin.service_ref]
            if not isinstance(service, MixedBackendService) or service.identity != pin:
                raise ValueError("installed mixed service differs from its authenticated pin")
            require_mixed_backend_service(service.implementation, role, service.declared_contracts)
            implementations.append(id(service.implementation))
        if len(set(implementations)) != len(implementations):
            raise ValueError("mixed roles require independent installed implementations")
        if not callable(getattr(self.time_runtime, "state", None)):
            raise ValueError("mixed services require trusted time readback")
        if not all(callable(getattr(self.evidence, name, None)) for name in ("validate_effects", "resolve_result")):
            raise ValueError("mixed services require native evidence resolution")
        object.__setattr__(self, "binding", binding)
        object.__setattr__(self, "services", MappingProxyType(dict(self.services)))

    @property
    def provider(self) -> object:
        subject = self.binding.subject
        pin = subject.bridge if subject.kind == "edge" else subject.transfer
        return self.service(pin)

    def service(self, pin: MixedBackendServiceModel) -> object:
        service = self.services[pin.service_ref]
        if service.identity != pin:
            raise ValueError("mixed service pin changed")
        return service.implementation


def mixed_installation(plane: object, invocation: object) -> MixedBackendInstallation | None:
    """Resolve controls by the original retained command, never the current phase."""

    declaration = invocation.mixed_binding
    if declaration is None:
        return None
    runtime = getattr(plane, "_mixed_runtime", None)
    installed = None if runtime is None else runtime.backend_installations.get(declaration.binding_id)
    if installed is None or installed.binding != declaration:
        raise ConflictError("original mixed invocation installation is unavailable")
    return installed


def action_installation(
    binding: MixedRuntimeBinding,
    edge: MixedCompositionEdgeModel | None,
) -> MixedBackendInstallation | None:
    """Select only the installation pinned to the admitted edge."""

    if edge is None:
        return None
    return next(
        (
            item
            for item in binding.backend_installations.values()
            if item.binding.subject.kind == "edge" and item.binding.subject.edge_id == edge.edge_id
        ),
        None,
    )

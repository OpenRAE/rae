"""Planning admission of typed descriptor selections (ADR-120)."""

from __future__ import annotations

from raes.descriptor_profiles import descriptor_profiles_admitted
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.domain_profiles import DomainProfileResolutionContextModel

from ..models import RuntimeModel


def descriptor_profile_diagnostics(
    model: RuntimeModel,
    manifest: BackendManifest,
    context: DomainProfileResolutionContextModel | None,
) -> list[Diagnostic]:
    """Refuse typed descriptor selections that the target's committed context does not admit."""

    if descriptor_profiles_admitted(model.descriptor_profile_bindings, context, manifest.domain_profile_context_digest):
        return []
    # Fixed text: a diagnostic never shows a profile value.
    return [
        Diagnostic(
            code="realization.descriptor-profile-unsupported",
            domain="runtime-realization",
            address="profiles.descriptors",
            message="Typed descriptor profiles lack admission by the target profile context.",
        )
    ]


__all__ = ["descriptor_profile_diagnostics"]

"""Compiler-side realization-authority contract."""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.addressing import require_compiled_address
from raes_contracts.explicitness import ExplicitnessProvenance
from raes_contracts.planning import RealizationAuthorityMode, RealizationResolutionSource
from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope


@dataclass(frozen=True)
class CompiledRealizationAuthority:
    """Complete compiler-side posture, including denials and delegation origin."""

    field_path: str
    address: str
    domain: str
    requirement_kind: str
    payload_path: tuple[str, ...]
    mode: RealizationAuthorityMode
    source: RealizationResolutionSource
    provenance: ExplicitnessProvenance
    governing_scope: str | None = None
    delegated: bool = False
    verification_scope: RealizationVerificationScope | None = None
    required_observation_strength: ObservationStrength | None = None

    def __post_init__(self) -> None:
        require_compiled_address(self.address)
        if not self.field_path or not self.domain or not self.requirement_kind or not self.payload_path:
            raise ValueError("compiled realization authority requires a complete concern identity")
        if self.delegated != (self.source is RealizationResolutionSource.APPARATUS_DEFAULT):
            raise ValueError("only apparatus-default realization authority may remain delegated")


__all__ = ["CompiledRealizationAuthority"]

"""Security policy for the per-target runtime control plane."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType

from raes_contracts.operation_lifecycle import (
    OPERATION_AUTHORIZATION_SCOPE_MAX_ENTRIES,
    OPERATION_CONTEXT_STRING_MAX_LENGTH,
)

from .control_plane_operation_context import operation_actor_scope


class ControlPlaneRole(str, Enum):
    """Authorization roles for control-plane callers."""

    BACKEND = "backend"
    OPERATOR = "operator"
    AUDITOR = "auditor"


class ControlPlaneRouteAuthority(str, Enum):
    """Transport authority that one served P2 route declares.

    P2 is a host-mediated, administrative-only surface (issue #1356). Every
    authority except the value-free public probe admits a privileged,
    target-bound service identity; none is participant, controller or
    disclosure authority. Participant/audience and participant/controller
    bindings are applied by the core operation after this admission.
    """

    PUBLIC_PROBE = "public-probe"
    ADMINISTRATIVE_READ = "administrative-read"
    ADMINISTRATIVE_MUTATION = "administrative-mutation"
    OPERATOR_RESOLUTION = "operator-resolution"


ROUTE_AUTHORITY_ROLES: Mapping[ControlPlaneRouteAuthority, frozenset[ControlPlaneRole]] = MappingProxyType(
    {
        ControlPlaneRouteAuthority.ADMINISTRATIVE_READ: frozenset(
            {ControlPlaneRole.BACKEND, ControlPlaneRole.OPERATOR, ControlPlaneRole.AUDITOR}
        ),
        ControlPlaneRouteAuthority.ADMINISTRATIVE_MUTATION: frozenset(
            {ControlPlaneRole.BACKEND, ControlPlaneRole.OPERATOR}
        ),
        ControlPlaneRouteAuthority.OPERATOR_RESOLUTION: frozenset({ControlPlaneRole.OPERATOR}),
    }
)
"""Roles admitted by each authenticated route authority.

A read role admits full snapshots and operational reads as well as participant
views (API-404-C3); an audience binding does not narrow it.
"""


def _require_binding_fields(participant_address: object, subject_ref: object, *, kind: str) -> None:
    """Require non-empty string binding fields that encode unambiguously as scopes.

    Bindings become ``participant-{kind}:{participant_address}:{subject_ref}``
    authorization scopes, and readback splits them after the participant prefix,
    so a participant address must not contain ``:``.
    """

    if not isinstance(participant_address, str) or not isinstance(subject_ref, str):
        raise ValueError(f"participant {kind} subject binding fields must be strings")
    if not participant_address or not subject_ref:
        raise ValueError(f"participant {kind} subject binding fields must be non-empty")
    if ":" in participant_address:
        raise ValueError(f"participant {kind} subject binding address must not contain ':'")


@dataclass(frozen=True)
class ParticipantControlSubjectBinding:
    """One authenticated principal-to-participant/controller binding."""

    participant_address: str
    controller_ref: str

    def __post_init__(self) -> None:
        _require_binding_fields(self.participant_address, self.controller_ref, kind="control")


@dataclass(frozen=True)
class ParticipantAudienceSubjectBinding:
    """One authenticated principal-to-participant/audience binding."""

    participant_address: str
    audience_scope_ref: str

    def __post_init__(self) -> None:
        _require_binding_fields(self.participant_address, self.audience_scope_ref, kind="audience")


@dataclass(frozen=True)
class ControlPlaneIdentity:
    """Authenticated control-plane principal."""

    identity: str
    roles: frozenset[ControlPlaneRole] = field(default_factory=frozenset)
    target_name: str | None = None
    participant_control_subjects: tuple[ParticipantControlSubjectBinding, ...] = ()
    participant_audience_subjects: tuple[ParticipantAudienceSubjectBinding, ...] = ()


def _require_identity_headers(verified: str, identity: str) -> None:
    headers = (verified, identity)
    if any(not isinstance(name, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) for name in headers):
        raise ValueError("identity header names must be valid HTTP field names")
    normalized = {name.lower() for name in headers}
    if len(normalized) != 2 or "authorization" in normalized:
        raise ValueError("identity headers must be distinct and must not alias Authorization")


def _require_principal_shape(principal: ControlPlaneIdentity) -> None:
    """Reject configured principals whose authority fields are mistyped or mutable.

    Annotations do not validate: a mutable role set or binding list could grant
    authority after the principal maps are frozen, and a mistyped role or
    binding would silently change admission. Messages stay value-free.
    """

    roles = principal.roles
    if not isinstance(roles, frozenset) or not all(isinstance(role, ControlPlaneRole) for role in roles):
        raise ValueError("configured principal roles must be a frozenset of ControlPlaneRole")
    target_name = principal.target_name
    if target_name is not None and (not isinstance(target_name, str) or not target_name.strip()):
        raise ValueError("configured principal target must be a non-empty string")
    for bindings, binding_type in (
        (principal.participant_control_subjects, ParticipantControlSubjectBinding),
        (principal.participant_audience_subjects, ParticipantAudienceSubjectBinding),
    ):
        if not isinstance(bindings, tuple) or not all(isinstance(binding, binding_type) for binding in bindings):
            raise ValueError(f"configured principal subject bindings must be a tuple of {binding_type.__name__}")
    # Reuse the canonical actor/scope derivation so an over-bound principal
    # fails here rather than at its first admitted request or audit event.
    actor, authorization_scope = operation_actor_scope(principal)
    if len(actor) > OPERATION_CONTEXT_STRING_MAX_LENGTH:
        raise ValueError("configured principal identity exceeds the operation-context bound")
    if len(authorization_scope) > OPERATION_AUTHORIZATION_SCOPE_MAX_ENTRIES or any(
        len(entry) > OPERATION_CONTEXT_STRING_MAX_LENGTH for entry in authorization_scope
    ):
        raise ValueError("configured principal authorization scope exceeds the operation-context bound")


def _frozen_principals(principals: Mapping[str, ControlPlaneIdentity]) -> Mapping[str, ControlPlaneIdentity]:
    copied = dict(principals)
    for key, principal in copied.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("configured credentials and principal names must be non-empty")
        if (
            not isinstance(principal, ControlPlaneIdentity)
            or not isinstance(principal.identity, str)
            or not principal.identity.strip()
        ):
            raise ValueError("configured principal must have a non-empty identity")
        _require_principal_shape(principal)
    return MappingProxyType(copied)


@dataclass(frozen=True)
class ControlPlaneSecurityConfig:
    """Reference security settings for the HTTP/JSON control-plane adapter.

    Header identities are only trustworthy behind an authenticated proxy that
    strips caller-supplied identity headers before setting its own values.
    """

    require_verified_identity: bool = True
    verified_header: str = "x-raes-client-verified"
    identity_header: str = "x-raes-client-identity"
    trust_proxy_identity_headers: bool = False
    max_request_bytes: int = 1_000_000
    max_pending_mutations: int = 32
    max_pending_rejection_audits: int = 8
    trusted_identities: Mapping[str, ControlPlaneIdentity] = field(default_factory=dict)
    bearer_tokens: Mapping[str, ControlPlaneIdentity] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_identity_headers(self.verified_header, self.identity_header)
        if self.max_pending_mutations <= 0:
            raise ValueError("max_pending_mutations must be positive")
        if self.max_pending_rejection_audits <= 0:
            raise ValueError("max_pending_rejection_audits must be positive")
        # ``frozen=True`` only blocks rebinding the attributes; a caller (or a
        # later code path) could still mutate the underlying dicts and grant
        # principals or tokens after construction, defeating ``strict_defaults``.
        # Read-only proxies keep dict equality while blocking that mutation.
        object.__setattr__(self, "trusted_identities", _frozen_principals(self.trusted_identities))
        object.__setattr__(self, "bearer_tokens", _frozen_principals(self.bearer_tokens))

    @classmethod
    def strict_defaults(cls) -> ControlPlaneSecurityConfig:
        """Return fail-closed defaults with no built-in principals or tokens."""

        return cls(
            require_verified_identity=True,
            trust_proxy_identity_headers=False,
            trusted_identities={},
            bearer_tokens={},
        )

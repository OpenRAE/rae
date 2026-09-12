"""Realization-envelope relation: membership, subsumption, witness, negative probes.

One deterministic semantic relation over :class:`RealizationEnvelopeModel` and
validated SDL instances (ADR-070 §2, ``specs/formal/realization/envelope-semantics.md``
R1-R8). Membership, subsumption, witness generation, and negative-probe generation
share a single flattening/closure engine (:mod:`raes._realization_envelope_engine`)
and domain-kind dispatch (:mod:`raes._realization_envelope_domains`) — there are
no separate author-side, backend-side, or conformance-side interpretations.

Guarantees:

- **Membership (R1)** — a concrete instance is in an envelope only when it is
  structurally and semantically valid SDL with no unresolved variables *and* every
  effective binding and closed-world scope is satisfied. Invalid SDL is never a
  member.
- **Subsumption (R4)** — ``subsumes(offered, requested)`` is set inclusion reduced
  to bounded per-path domain-subset, closed-scope key-set, and closure-compatibility
  checks. No sampling, approximation, solver, or backend probing.
- **Witness (R5)** — ``witness`` deterministically selects one candidate from the
  envelope's own bindings (no externally supplied scenario) and then runs the
  ordinary ``parse``/``instantiate``/``validate`` pipeline. A witness is one
  executable in-envelope instance; it is not proof of subsumption or backend honesty.
- **Negative probes (R6)** — ``generate_negative_probes`` derives out-of-envelope
  variants of a valid witness for the closed dimensions that can be varied, so
  conformance can require refusal.

Diagnostics name the relation kind, envelope id, SDL path, and domain kind — never
raw sensitive values (R8 / ADR-070 §7).
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass

from pydantic import ValidationError
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.realization_envelope import RealizationEnvelopeModel, WitnessPolicy, scalar_in_domain

from ._errors import SDLInstantiationError, SDLValidationError
from ._realization_envelope_domains import domain_subset, positive_probe_values
from ._realization_envelope_engine import (
    LeafConstraint,
    assign_path,
    effective_constraints,
    navigate,
    normalize_scalar,
    overridability_violations,
    present_children,
    tokenize_path,
    witness_value,
)
from ._realization_envelope_probe_payloads import closed_scope_probe_payloads, value_probe_payloads
from .instantiate import instantiate_scenario
from .scenario import InstantiatedScenario, Scenario
from .validator import SemanticValidator

__all__ = [
    "NegativeProbe",
    "PositiveProbe",
    "RelationKind",
    "RelationResult",
    "WitnessResult",
    "generate_negative_probes",
    "generate_positive_probes",
    "effective_constraints",
    "member",
    "member_projection",
    "subsumes",
    "tokenize_path",
    "witness",
]

_DOMAIN = "realization-envelope"


class RelationKind:
    """Relation kind labels used in diagnostic codes."""

    MEMBERSHIP = "membership"
    SUBSUMPTION = "subsumption"
    WITNESS = "witness"
    NEGATIVE_PROBE = "negative-probe"


@dataclass(frozen=True)
class RelationResult:
    """Result of a membership or subsumption evaluation."""

    holds: bool
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class WitnessResult:
    """A generated witness scenario, or diagnostics proving none can be generated."""

    scenario: InstantiatedScenario | None
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class NegativeProbe:
    """An out-of-envelope variant of a valid witness for a closed dimension."""

    path: str
    domain_kind: str
    variation: str
    payload: dict[str, object]


@dataclass(frozen=True)
class PositiveProbe:
    """A validated in-envelope witness covering one bounded variation."""

    path: str
    domain_kind: str
    variation: str
    digest: str
    payload: dict[str, object]


def _diag(code: str, address: str, message: str, severity: Severity = Severity.ERROR) -> Diagnostic:
    return Diagnostic(code=f"{_DOMAIN}.{code}", domain=_DOMAIN, address=address, message=message, severity=severity)


def _envelope_r2_diagnostics(envelope: RealizationEnvelopeModel) -> tuple[Diagnostic, ...]:
    """R2 well-formedness: reject a more-specific binding that widens a fixed value.

    An envelope that violates the overridability rule is ill-formed; the relation
    answers deny (not a member / no witness) rather than silently resolving against
    a broader-than-authored set.
    """

    return tuple(
        _diag(
            "invalid.non-overrideable-widen", path, "a more-specific binding widens a non-overrideable inherited value"
        )
        for path in overridability_violations(envelope)
    )


# --------------------------------------------------------------------------- #
# Membership (R1, R3)                                                          #
# --------------------------------------------------------------------------- #


def _member_sdl_invalid(instance: InstantiatedScenario, envelope: RealizationEnvelopeModel) -> RelationResult | None:
    """Return a deny result when the instance is not semantically valid SDL (R1)."""

    if getattr(instance, "semantic_validated", False):
        return None
    try:
        SemanticValidator(instance).validate()
    except SDLValidationError:
        return RelationResult(
            False,
            (_diag(f"{RelationKind.MEMBERSHIP}.invalid-sdl", envelope.id, "instance failed SDL semantic validation"),),
        )
    return None


def _member_constraint_diagnostics(instance: object, constraints: dict[str, LeafConstraint]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for path, constraint in constraints.items():
        found, value = navigate(instance, tokenize_path(path))
        if not found or value is None:
            # A constrained/exact dimension left unspecified (missing field, or an
            # optional field defaulting to ``None``) is not a member. Domains never
            # admit ``None`` (they range over scalars), so this is always absence.
            diagnostics.append(
                _diag(f"{RelationKind.MEMBERSHIP}.path-absent", path, "constrained path is unspecified in the instance")
            )
        elif not scalar_in_domain(normalize_scalar(value), constraint.domain):
            diagnostics.append(
                _diag(
                    f"{RelationKind.MEMBERSHIP}.domain-mismatch",
                    path,
                    f"value is not in the {constraint.domain.kind} domain",
                )
            )
    return diagnostics


_UNRESOLVED = object()


def _resolve_scope_value(instance: object, scope_path: str) -> object:
    """Value at ``scope_path`` (the whole instance for the root), or ``_UNRESOLVED``."""

    if not scope_path:
        return instance
    found, value = navigate(instance, tokenize_path(scope_path))
    return value if found else _UNRESOLVED


def _closed_extra_diagnostics(
    scope_path: str,
    scope_value: object,
    admitted: set[str],
    *,
    children: set[str] | None = None,
) -> list[Diagnostic]:
    """Diagnostics for realizable child dimensions not admitted under a closed scope."""

    diagnostics: list[Diagnostic] = []
    for child in sorted(present_children(scope_value) if children is None else children):
        if child not in admitted:
            address = f"{scope_path}.{child}" if scope_path else child
            diagnostics.append(
                _diag(
                    f"{RelationKind.MEMBERSHIP}.closed-world-extra",
                    address,
                    "closed-world scope admits no unspecified realizable dimension",
                )
            )
    return diagnostics


def _member_closed_diagnostics(instance: object, closed: dict[str, set[str]]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for scope_path in sorted(closed):
        scope_value = _resolve_scope_value(instance, scope_path)
        if scope_value is not _UNRESOLVED:
            diagnostics.extend(_closed_extra_diagnostics(scope_path, scope_value, closed[scope_path]))
    return diagnostics


def member(instance: InstantiatedScenario, envelope: RealizationEnvelopeModel) -> RelationResult:
    """Decide whether ``instance`` is a member of ``envelope`` (R1)."""

    invalid = _envelope_r2_diagnostics(envelope)
    if invalid:
        return RelationResult(False, invalid)

    sdl_invalid = _member_sdl_invalid(instance, envelope)
    if sdl_invalid is not None:
        return sdl_invalid

    constraints, closed = effective_constraints(envelope)
    diagnostics = _member_constraint_diagnostics(instance, constraints) + _member_closed_diagnostics(instance, closed)
    return RelationResult(not diagnostics, tuple(diagnostics))


def member_projection(
    value: object,
    field_path: str,
    envelope: RealizationEnvelopeModel,
    *,
    typed_value: object = None,
) -> RelationResult:
    """Check an already admitted subtree, not whole-instance SDL membership."""

    from ._realization_envelope_projection import projected_member

    return projected_member(value, field_path, envelope, typed_value=typed_value)


# --------------------------------------------------------------------------- #
# Subsumption (R4)                                                            #
# --------------------------------------------------------------------------- #


def _subsumption_domain_diagnostics(
    offered: dict[str, LeafConstraint], requested: dict[str, LeafConstraint]
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for path in sorted(set(offered) | set(requested)):
        offered_constraint = offered.get(path)
        if offered_constraint is None:
            # offered is open/universal here: it admits any requested value
            continue
        requested_constraint = requested.get(path)
        if requested_constraint is None:
            diagnostics.append(
                _diag(
                    f"{RelationKind.SUBSUMPTION}.requested-unconstrained",
                    path,
                    "requested leaves a path open that offered constrains",
                )
            )
        elif not domain_subset(requested_constraint.domain, offered_constraint.domain):
            diagnostics.append(
                _diag(
                    f"{RelationKind.SUBSUMPTION}.domain-not-subset",
                    path,
                    "requested domain is not a subset of the offered domain",
                )
            )
    return diagnostics


def _subsumption_closure_diagnostics(offered: dict[str, set[str]], requested: dict[str, set[str]]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for scope_path in sorted(offered):
        label = scope_path or "<scenario>"
        if scope_path not in requested:
            diagnostics.append(
                _diag(
                    f"{RelationKind.SUBSUMPTION}.closure-mismatch",
                    label,
                    "offered is closed-world where requested is open-world",
                )
            )
        elif not requested[scope_path].issubset(offered[scope_path]):
            diagnostics.append(
                _diag(
                    f"{RelationKind.SUBSUMPTION}.closed-extra",
                    label,
                    "requested admits a closed dimension offered does not",
                )
            )
    return diagnostics


def subsumes(offered: RealizationEnvelopeModel, requested: RealizationEnvelopeModel) -> RelationResult:
    """Decide whether every scenario in ``requested`` is in ``offered`` (R4)."""

    invalid = _envelope_r2_diagnostics(offered) + _envelope_r2_diagnostics(requested)
    if invalid:
        return RelationResult(False, invalid)

    offered_constraints, offered_closed = effective_constraints(offered)
    requested_constraints, requested_closed = effective_constraints(requested)
    diagnostics = _subsumption_domain_diagnostics(
        offered_constraints, requested_constraints
    ) + _subsumption_closure_diagnostics(offered_closed, requested_closed)
    return RelationResult(not diagnostics, tuple(diagnostics))


# --------------------------------------------------------------------------- #
# Witness generation (R5)                                                     #
# --------------------------------------------------------------------------- #


def _build_witness_payload(
    envelope: RealizationEnvelopeModel, policy: WitnessPolicy | None
) -> tuple[dict[str, object], list[Diagnostic]]:
    effective_policy = policy if policy is not None else envelope.witness_policy
    constraints, _closed = effective_constraints(envelope)
    payload: dict[str, object] = {}
    diagnostics: list[Diagnostic] = []
    for path in sorted(constraints):
        value, error = witness_value(constraints[path], effective_policy)
        if error is None:
            error = assign_path(payload, tokenize_path(path), value)
        if error is not None:
            diagnostics.append(_diag(f"{RelationKind.WITNESS}.no-witness", path, error))
    return payload, diagnostics


def _validate_witness_payload(payload: dict[str, object], envelope: RealizationEnvelopeModel) -> WitnessResult:
    try:
        raw = Scenario.model_validate(payload)
        raw._set_semantic_validated(False)
        instantiated = instantiate_scenario(raw)
    except (ValidationError, SDLValidationError, SDLInstantiationError):
        return WitnessResult(
            None,
            (
                _diag(
                    f"{RelationKind.WITNESS}.invalid",
                    envelope.id,
                    "generated witness did not pass SDL structural/semantic validation "
                    "(the envelope does not fully determine a valid scenario instance)",
                ),
            ),
        )
    return WitnessResult(instantiated, ())


def witness(envelope: RealizationEnvelopeModel, policy: WitnessPolicy | None = None) -> WitnessResult:
    """Deterministically derive one in-envelope scenario instance (R5)."""

    invalid = _envelope_r2_diagnostics(envelope)
    if invalid:
        return WitnessResult(None, invalid)
    payload, diagnostics = _build_witness_payload(envelope, policy)
    if diagnostics:
        return WitnessResult(None, tuple(diagnostics))
    return _validate_witness_payload(payload, envelope)


# --------------------------------------------------------------------------- #
# Positive probes (ASR-519)                                                    #
# --------------------------------------------------------------------------- #


def _probe_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _positive_probe(payload: dict[str, object], *, path: str, domain_kind: str, variation: str) -> PositiveProbe:
    return PositiveProbe(path, domain_kind, variation, _probe_digest(payload), payload)


def generate_positive_probes(
    envelope: RealizationEnvelopeModel,
) -> tuple[tuple[PositiveProbe, ...], tuple[Diagnostic, ...]]:
    """Derive deterministic, structurally valid witnesses for bounded dimensions.

    The base witness is always retained. Each finite member and safe numeric
    boundary is substituted through the shared path engine, then revalidated by
    the ordinary SDL and envelope-membership gates. Invalid candidates remain
    explicit diagnostics rather than silently increasing conformance coverage.
    """

    base_payload, build_diagnostics = _build_witness_payload(envelope, None)
    base = _validate_witness_payload(base_payload, envelope) if not build_diagnostics else WitnessResult(None)
    if base.scenario is None:
        return (), (
            _diag(
                "positive-probe.no-witness",
                envelope.id,
                "cannot derive positive probes from a non-constructive envelope",
            ),
        )
    probes: dict[str, PositiveProbe] = {}
    initial = _positive_probe(base_payload, path=envelope.id, domain_kind="witness", variation="base-witness")
    probes[initial.digest] = initial
    diagnostics: list[Diagnostic] = []
    constraints, _closed = effective_constraints(envelope)
    for path in sorted(constraints):
        constraint = constraints[path]
        for value in positive_probe_values(constraint.domain):
            payload = deepcopy(base_payload)
            if assign_path(payload, tokenize_path(path), value) is not None:
                diagnostics.append(
                    _diag("positive-probe.invalid-candidate", path, "bounded variation could not be assigned")
                )
                continue
            candidate = _validate_witness_payload(payload, envelope)
            if candidate.scenario is None or not member(candidate.scenario, envelope).holds:
                diagnostics.append(
                    _diag(
                        "positive-probe.invalid-candidate",
                        path,
                        "bounded variation did not pass ordinary SDL and membership validation",
                    )
                )
                continue
            probe = _positive_probe(
                payload,
                path=path,
                domain_kind=constraint.domain.kind,
                variation="bounded-member",
            )
            probes.setdefault(probe.digest, probe)
    return tuple(probes.values()), tuple(diagnostics)


# --------------------------------------------------------------------------- #
# Negative probes (R6)                                                        #
# --------------------------------------------------------------------------- #


def generate_negative_probes(
    envelope: RealizationEnvelopeModel,
) -> tuple[tuple[NegativeProbe, ...], tuple[Diagnostic, ...]]:
    """Derive out-of-envelope probes for the envelope's closed dimensions (R6)."""

    base_payload, build_diagnostics = _build_witness_payload(envelope, None)
    base = _validate_witness_payload(base_payload, envelope) if not build_diagnostics else WitnessResult(None)
    if base.scenario is None:
        return (), (
            _diag(
                f"{RelationKind.NEGATIVE_PROBE}.no-witness",
                envelope.id,
                "cannot derive a witness base for negative probes",
            ),
        )

    constraints, closed = effective_constraints(envelope)
    probes = []
    for path in sorted(constraints):
        probes.extend(value_probe_payloads(base_payload, base.scenario, path, constraints[path]))
    probes.extend(closed_scope_probe_payloads(base_payload, base.scenario, closed))
    safe: list[NegativeProbe] = []
    seen: set[tuple[str, str]] = set()
    for probe in probes:
        candidate = _validate_witness_payload(probe.payload, envelope)
        key = (probe.path, _probe_digest(probe.payload))
        if candidate.scenario is not None and not member(candidate.scenario, envelope).holds and key not in seen:
            safe.append(NegativeProbe(probe.path, probe.domain_kind, probe.variation, probe.payload))
            seen.add(key)
    return tuple(safe), ()

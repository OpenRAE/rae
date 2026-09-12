"""SEM-218 compiled realization demand, apparatus matching, and disclosure.

The normative boundary is ``explicitness-and-realization.md``. Domain and kind
strings remain opaque; matching is exact membership plus support compatibility.
"""

from __future__ import annotations

from raes.explicitness import ExplicitnessClass
from raes.realization_envelope import effective_constraints, subsumes, tokenize_path
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.apparatus import (
    DECLARED_CAPABILITY_MATCH_REQUIREMENT_KIND,
    RUNTIME_REALIZATION_DOMAIN,
)
from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.bounded_domains import scalar_in_domain
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.realization_envelope import (
    BackendRealizationEnvelopeModel,
    ClosureOverlay,
    EnvelopeBinding,
    EnvelopeScope,
    Posture,
    RealizationConcernDisclosureModel,
    RealizationEnvelopeModel,
)
from raes_contracts.runtime_state import RealizationProvenanceEntry, RuntimeSnapshot
from raes_contracts.vocabulary import (
    Closure,
    observation_strength_satisfies,
)

from .artifact_realization import (
    artifact_requirement_diagnostics,
    evaluate_artifact_realization,
)
from .realization_apparatus_defaults import (
    ApparatusRealizationDecisions,
    ApparatusRealizationDefaultResolver,
    effective_realization_explicitness,
    materialize_realization_requirements,
    resolve_apparatus_realization_defaults,
)
from .realization_authority_contract import CompiledRealizationAuthority
from .realization_concerns import (
    CONCERN_PAYLOAD_PATH,
    project_realization_concern,
    registered_realization_concern_descriptors,
    registered_realization_concerns,
    resolve_realization_concern,
)
from .realization_process_limits import (
    ProcessResourceLimitDemand,
    RealizationValueConstraint,
)
from .realization_requirement import CompiledRealizationRequirement
from .realization_runtime_evaluation import evaluate_registered_realization
from .realization_snapshot_sanitization import (
    sanitize_realization_snapshot,
)
from .realization_support import realization_support_diagnostics

__all__ = [
    "CONCERN_PAYLOAD_PATH",
    "EXACT_REQUIREMENT_KIND",
    "REALIZATION_DOMAIN",
    "ApparatusRealizationDefaultResolver",
    "ApparatusRealizationDecisions",
    "CompiledRealizationRequirement",
    "CompiledRealizationAuthority",
    "ProcessResourceLimitDemand",
    "RealizationValueConstraint",
    "artifact_requirement_diagnostics",
    "materialize_realization_requirements",
    "project_realization_concern",
    "realization_disclosure",
    "realization_envelope_diagnostics",
    "realization_support_diagnostics",
    "resolve_apparatus_realization_defaults",
    "registered_realization_concern_descriptors",
    "registered_realization_concerns",
    "resolve_realization_concern",
    "sanitize_realization_snapshot",
]

_BACKEND_CONTRACT_INVALID = "runtime.backend-contract-invalid"

# The single coarse realization domain string already published by backend
# manifests (see ``raes_backend_stubs.stubs``). Kept opaque per the SEM-218
# extensibility seam.
REALIZATION_DOMAIN = RUNTIME_REALIZATION_DOMAIN

# The exact-requirement kind every concrete (exact) author declaration maps to.
# A backend that honors exact declarations lists this in
# ``supported_exact_requirement_kinds``; one that cannot must reject (I2).
EXACT_REQUIREMENT_KIND = DECLARED_CAPABILITY_MATCH_REQUIREMENT_KIND


def realization_envelope_diagnostics(
    requirements: tuple[CompiledRealizationRequirement, ...],
    manifest: BackendManifest,
    *,
    apparatus_default: ApparatusRealizationDefaultResolver | None = None,
    preparation: bool = False,
) -> list[Diagnostic]:
    """Check open compiled demand against the offered envelope via subsumption."""

    carrier = manifest.realization_envelope
    if carrier is None:
        return [
            Diagnostic(
                code="realization.compute-substrate-envelope-required",
                domain=requirement.domain,
                address=requirement.address,
                message=(
                    "Selected apparatus provides no realization envelope for the bounded "
                    f"compute-substrate demand at '{requirement.field_path}'."
                ),
                severity=Severity.ERROR,
            )
            for requirement in requirements
            if requirement.requirement_kind == "compute-substrate"
            and effective_realization_explicitness(requirement, manifest, apparatus_default)
            in {ExplicitnessClass.EXACT, ExplicitnessClass.CONSTRAINED}
        ]
    diagnostics = _compute_substrate_envelope_diagnostics(requirements, carrier)
    open_paths = tuple(
        requirement.field_path
        for requirement in requirements
        if requirement.requirement_kind != "compute-substrate"
        and effective_realization_explicitness(requirement, manifest, apparatus_default) is ExplicitnessClass.OPEN
    )
    if not open_paths or (preparation and "backend-realization-preparation-v1" in manifest.supported_contract_versions):
        return diagnostics
    requested = _open_request_envelope(open_paths)
    offered = _offered_open_projection(carrier.expression, open_paths)
    return [*diagnostics, *subsumes(offered, requested).diagnostics]


def _compute_substrate_envelope_diagnostics(
    requirements: tuple[CompiledRealizationRequirement, ...],
    carrier: BackendRealizationEnvelopeModel,
) -> list[Diagnostic]:
    claim = next(
        (item for item in carrier.concerns if item.concern.value == "compute-substrate"),
        None,
    )
    diagnostics: list[Diagnostic] = []
    for requirement in requirements:
        if requirement.requirement_kind != "compute-substrate":
            continue
        if not _compute_substrate_claim_admits(requirement, claim):
            diagnostics.append(
                Diagnostic(
                    code="realization.compute-substrate-not-admitted",
                    domain=requirement.domain,
                    address=requirement.address,
                    message=(
                        "Selected realization envelope cannot satisfy the governed compute-substrate "
                        f"demand at '{requirement.field_path}'."
                    ),
                    severity=Severity.ERROR,
                )
            )
    return diagnostics


def _compute_substrate_claim_admits(
    requirement: CompiledRealizationRequirement,
    claim: RealizationConcernDisclosureModel | None,
) -> bool:
    if claim is None or claim.disposition.value == "unsupported" or claim.mechanism is None:
        return False
    domain_admitted = requirement.value_domain is None or scalar_in_domain(claim.mechanism, requirement.value_domain)
    strength_admitted = requirement.required_observation_strength is None or observation_strength_satisfies(
        claim.observation_strength,
        requirement.required_observation_strength,
    )
    return domain_admitted and strength_admitted


def _open_request_envelope(paths: tuple[str, ...]) -> RealizationEnvelopeModel:
    return RealizationEnvelopeModel(
        id="compiled-open-realization-request",
        scope=EnvelopeScope.SCENARIO,
        bindings=[
            EnvelopeBinding(path=path, scope=EnvelopeScope.FIELD, posture=Posture.OPEN) for path in sorted(set(paths))
        ],
    )


def _offered_open_projection(
    offered: RealizationEnvelopeModel,
    paths: tuple[str, ...],
) -> RealizationEnvelopeModel:
    constraints, closed = effective_constraints(offered)
    domains = {}
    bindings = []
    for index, path in enumerate(sorted(set(paths))):
        constraint = constraints.get(path)
        if constraint is None:
            continue
        domain_name = f"offered-domain-{index}"
        domains[domain_name] = constraint.domain
        bindings.append(
            EnvelopeBinding(
                path=path,
                scope=EnvelopeScope.FIELD,
                posture=constraint.posture,
                domain=domain_name,
                overrideable=constraint.overrideable,
            )
        )
    excludes_open_path = any(_closed_scope_excludes(path, closed) for path in paths)
    closure = (
        [
            ClosureOverlay(
                path="",
                scope=EnvelopeScope.SCENARIO,
                closure=Closure.CLOSED_WORLD,
            )
        ]
        if excludes_open_path
        else []
    )
    return RealizationEnvelopeModel(
        id=f"{offered.id}.open-demand-projection",
        scope=offered.scope,
        domains=domains,
        bindings=bindings,
        closure=closure,
    )


def _closed_scope_excludes(path: str, closed: dict[str, set[str]]) -> bool:
    target = tuple(tokenize_path(path))
    for scope_path, admitted_children in closed.items():
        scope = tuple(tokenize_path(scope_path)) if scope_path else ()
        if len(scope) >= len(target) or target[: len(scope)] != scope:
            continue
        child = target[len(scope)]
        if not isinstance(child, str) or child not in admitted_children:
            return True
    return False


def realization_disclosure(
    requirements: tuple[CompiledRealizationRequirement, ...],
    declared_plan: ProvisioningPlan,
    returned_snapshot: RuntimeSnapshot,
    *,
    manifest: BackendManifest | None = None,
    artifact_availability: ArtifactAvailabilityContext | None = None,
) -> tuple[list[Diagnostic], tuple[RealizationProvenanceEntry, ...]]:
    """SEM-218 runtime non-approximation gate (I2) + provenance disclosure (I5).

    Compares each compiled realization concern's author-declared value (from the
    provisioning plan the processor emitted) against the value the backend
    realized in its returned snapshot. For an exact concern, a backend that
    realizes a *different* value — or *omits* the value entirely (a returned
    snapshot with no entry for the resource, or an entry missing the concern
    field) — is a silent approximation and yields a rejecting
    ``runtime.backend-contract-invalid`` diagnostic. Absent *backend* evidence is
    not a non-event: an exact declaration the backend never realized is exactly
    the I2 failure this gate exists to catch. This is the spec's Execution-phase
    non-approximation rule.

    Absent *plan-side* evidence is different and is not a backend fault: when the
    plan declares no provisioning op for the resource, removes it (a ``DELETE``
    op — expected absence), or carries no value for the concern, there is no
    author baseline for this run to enforce, so the requirement is skipped.

    Every honoured/realized concern is recorded as a
    ``RealizationProvenanceEntry``: ``author-declared`` when the backend honoured
    the declaration, ``backend-realized`` when it realized a different value for
    a constrained surface. Diagnostics and entries name the field path and kind
    only, never the realized value (SEM-218 host-exposure gate).

    This is the runtime sibling of ``realization_support_diagnostics``: the
    planner gate rejects an unrealizable exact requirement before deployment;
    this gate rejects a backend that realized one dishonestly. The runtime
    adapter (``raes_runtime``) invokes it at the backend-call boundary.
    """

    diagnostics: list[Diagnostic] = []
    provenance: list[RealizationProvenanceEntry] = []
    declared_ops = {op.address: op for op in declared_plan.operations}
    for requirement in requirements:
        if requirement.artifact_requirement is not None:
            diagnostic, entry = evaluate_artifact_realization(
                requirement,
                declared_ops,
                returned_snapshot,
                manifest=manifest,
                availability=artifact_availability,
            )
        else:
            diagnostic, entry = evaluate_registered_realization(
                requirement,
                declared_plan,
                returned_snapshot,
                manifest=manifest,
            )
        if diagnostic is not None:
            diagnostics.append(diagnostic)
        if entry is not None:
            provenance.append(entry)
    return diagnostics, tuple(provenance)

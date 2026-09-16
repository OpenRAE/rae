"""Evaluate addition permission over the same SDL effects used by attestation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import cache

from raes import admit_instantiated_scenario, parse_sdl
from raes.observation_scope import semantic_scope_namespace
from raes.prospective_content import admit_prospective_content
from raes.scenario import ScenarioContent
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_contracts.augmentation_preparation import AugmentationPreparation, augmentation_binding_digest
from raes_contracts.augmentation_scope import (
    AugmentationScopeDecision,
    AugmentationScopePolicy,
    effective_augmentation_scope,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.json_ingress import parse_bounded_json_object
from raes_contracts.materialization import MATERIALIZATION_MAX_BYTES
from raes_contracts.planning import RealizationAuthorityMode
from raes_contracts.realization_structure import (
    canonical_semantic_address,
    semantic_address_contains,
    validate_realization_value,
)
from raes_contracts.runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

from ..compiler.materialization_origins import (
    compose_materialization_content,
    materialization_collection_profiles,
    materialization_differences,
)
from ..semantics.realization_concerns import registered_realization_concern_descriptors
from .materialization_admission import validate_materialization_archive_record


@dataclass(frozen=True)
class AugmentationAdmission:
    preparation: AugmentationPreparation
    diagnostics: tuple[Diagnostic, ...]
    cumulative_content: ScenarioContent | None = None

    @property
    def is_valid(self) -> bool:
        return not self.diagnostics


def validate_actual_augmentation(submission, admission: AugmentationAdmission | None) -> None:
    """Actual SDL must match the admitted prospective world, not a widened policy."""
    if admission is None:
        return
    prospective = admission.cumulative_content or admit_prospective_content(
        parse_bounded_json_object(admission.preparation.content, max_bytes=MATERIALIZATION_MAX_BYTES)
    )
    actual = parse_sdl(submission.sdl)
    if materialization_differences(prospective, actual):
        raise ValueError("actual effects differ from admitted prospective SDL")


def compose_augmentation_admission(admission, request, previous, archive, *, preceding=None):
    """Compose phase-owned changes over the authenticated preceding common SDL."""
    source = request.materialization_source
    original = parse_bounded_json_object(source.snapshot, max_bytes=MATERIALIZATION_MAX_BYTES)["scenario"]
    original.pop("instantiation_provenance")
    original = admit_prospective_content(original)
    if preceding is None:
        preceding = original
        retained = [record for record in previous.materialization_attestations if record.run_id == source.run_id]
        if retained:
            submission = archive.read(retained[-1])
            validate_materialization_archive_record(submission, retained[-1])
            preceding = parse_sdl(submission.sdl)
            provenance = preceding.materialization_provenance
            if (provenance.authored_digest.value, provenance.instantiated_digest.value) != (
                source.authored_digest,
                source.instantiated_digest,
            ):
                raise ValueError("preceding materialization does not bind this source")
    local = admit_prospective_content(
        parse_bounded_json_object(admission.preparation.content, max_bytes=MATERIALIZATION_MAX_BYTES)
    )
    return replace(admission, cumulative_content=compose_materialization_content(original, preceding, local))


def admit_augmentation_preparation(report, request, manifest, previous) -> AugmentationAdmission:
    """Reject incomplete/unbound reports; render refusals only from resolved facts."""
    if not validate_realization_value(report, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS, python_carriers=True).conformant:
        raise ValueError("prospective report exceeds portable bounds")
    report = AugmentationPreparation.model_validate(report.model_dump(mode="json"))
    if report.binding_digest != augmentation_binding_digest(request, backend_manifest_v2_model(manifest), previous):
        raise ValueError("augmentation preparation does not bind this source and execution")
    original = admit_instantiated_scenario(
        parse_bounded_json_object(request.materialization_source.snapshot, max_bytes=MATERIALIZATION_MAX_BYTES)[
            "scenario"
        ]
    )
    prospective = admit_prospective_content(
        parse_bounded_json_object(report.content, max_bytes=MATERIALIZATION_MAX_BYTES)
    )
    for field in ("augmentation_scope", "evidence_requirements"):
        if getattr(original, field) != getattr(prospective, field):
            raise ValueError("prospective content cannot change author policy or evidence requirements")
    differences = materialization_differences(original, prospective)
    if {item.field_pointer for item in differences} != {item.field_pointer for item in report.effects}:
        raise ValueError("prospective effects must exactly cover materialization differences")
    source_scope = _scope_resolver(original)
    prospective_scope = _scope_resolver(prospective)
    policy = _canonical_policy(original.augmentation_scope, source_scope)
    effects = {item.field_pointer: item for item in report.effects}
    for difference in differences:
        effect = effects[difference.field_pointer]
        _require_requirement_references(effect.requirement_refs, source_scope)
        resolve = source_scope if difference.change == "removed" else prospective_scope
        locations = tuple(resolve(scope) for scope in (difference.field_pointer, *effect.affected_scopes))
        failures = _effect_diagnostics(
            effect,
            difference,
            locations,
            policy,
            source_scope,
            ordinary_selection=_ordinary_selection(difference, original, request),
        )
        if failures:
            return AugmentationAdmission(report, failures)
    return AugmentationAdmission(report, ())


ScopeResolver = Callable[[str], tuple[str, tuple[str, ...]]]


def _scope_resolver(content: ScenarioContent) -> ScopeResolver:
    value, profiles = content.model_dump(mode="json"), materialization_collection_profiles(content)

    @cache
    def resolve(scope: str) -> tuple[str, tuple[str, ...]]:
        canonical = canonical_semantic_address(scope, value, collection_profiles=profiles)
        return canonical, semantic_scope_namespace(value, canonical)

    return resolve


def _canonical_policy(policy: AugmentationScopePolicy | None, resolve: ScopeResolver) -> AugmentationScopePolicy | None:
    if policy is None:
        return None
    return AugmentationScopePolicy(
        default=policy.default,
        scopes=tuple(rule.model_copy(update={"scope": resolve(rule.scope)[0]}) for rule in policy.scopes),
    )


def _require_requirement_references(references: tuple[str, ...], resolve: ScopeResolver) -> None:
    for reference in references:
        if reference == "backend-operational":
            continue
        tokens = reference.split("/")
        if len(tokens) != 3 or tokens[1] not in {"evidence_requirements", "objectives", "assertions", "propositions"}:
            raise ValueError("augmentation requirement must name an admitted requirement")
        resolve(reference)


def _scope_decision(policy, location, namespace, source_scope) -> AugmentationScopeDecision:
    decision = effective_augmentation_scope(policy, location, namespace=namespace)
    if policy is None or decision.permission == "closed":
        return decision
    for rule in policy.scopes:
        if semantic_address_contains(location, rule.scope):
            child = effective_augmentation_scope(policy, rule.scope, namespace=source_scope(rule.scope)[1])
            if child.permission == "closed":
                return child
    return decision


def _effect_diagnostics(
    effect, difference, locations, policy, source_scope, *, ordinary_selection
) -> tuple[Diagnostic, ...]:
    for location, namespace in locations:
        if location == difference.field_pointer and ordinary_selection:
            continue
        decision = _scope_decision(policy, location, namespace, source_scope)
        if decision.permission == "closed":
            return tuple(
                Diagnostic(
                    code="augmentation.scope-closed",
                    domain="augmentation",
                    address=difference.field_pointer,
                    message=f"Requirement {reference[:120]} needs {difference.change} {difference.field_pointer[:160]}; augmentation scope {decision.governing_scope[:120] or '/'} is closed.",
                )
                for reference in effect.requirement_refs
            )
    return ()


def _ordinary_selection(difference, original, request) -> bool:
    """Selecting a delegated platform is not installing apparatus or content."""
    if difference.change != "selected":
        return False
    ordinary = {"os-family", "os-distribution", "os-version", "node-architecture", "node-type", "content-type"}
    for registered in registered_realization_concern_descriptors(
        declaration_names={"nodes": original.nodes, "content": original.content}
    ):
        descriptor = registered.descriptor
        pointer = "/" + "/".join(
            token.replace("~", "~0").replace("/", "~1")
            for token in (descriptor.section, registered.declaration_name, *descriptor.authored_path)
        )
        if descriptor.concern_kind in ordinary and pointer == difference.field_pointer:
            return any(
                authority.field_path == registered.field_path
                and authority.mode in {RealizationAuthorityMode.OPEN, RealizationAuthorityMode.CONSTRAINED}
                for authority in getattr(request, "realization_authority", ())
            )
    return False

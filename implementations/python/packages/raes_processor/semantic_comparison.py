"""Pure trusted adapters, semantic comparison, and bounded impact analysis."""

from __future__ import annotations

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    ArtifactTransformationReportModel,
    ArtifactTransformationStatus,
)
from raes_contracts.semantic_comparison import (
    ArtifactCoordinate,
    ArtifactKind,
    ComparisonCompleteness,
    ComparisonLimitsModel,
    ComparisonReason,
    DependencyChangeModel,
    DependencyRelation,
    DependencyResolutionStatus,
    DependencyStateModel,
    IdentityRelation,
    ImpactClosureStatus,
    ImpactScopeModel,
    ModuleCoordinateModel,
    RelationStatus,
    ScenarioCoordinateModel,
    SemanticChangeModel,
    SemanticComparisonContextModel,
    SemanticComparisonProfileModel,
    SemanticComparisonRequestModel,
    SemanticComparisonResultModel,
    canonical_semantic_comparison_profile_digest,
    canonical_semantic_comparison_request_digest,
)

from .semantic_comparison_adapters import (
    AdmittedArtifact,
    _Dependency,
    _Projection,
    _Subject,
    build_impact_scope,
    coordinate_for_artifact,
    project_artifact,
)
from .semantic_comparison_impact import impact_paths as _impact_paths


def analyze_semantic_comparison(
    profile: SemanticComparisonProfileModel,
    request: SemanticComparisonRequestModel,
    before: AdmittedArtifact,
    after: AdmittedArtifact,
    *,
    before_scope: tuple[AdmittedArtifact, ...] | None = None,
    after_scope: tuple[AdmittedArtifact, ...] | None = None,
    context: SemanticComparisonContextModel | None = None,
) -> SemanticComparisonResultModel:
    """Compare admitted artifacts without I/O, caller projections, or ambient registries."""

    _require_profile(profile, request)
    scenario_version = profile.owner_projection_versions[ArtifactKind.SCENARIO]
    supplied_before_scope = before_scope or (before,)
    supplied_after_scope = after_scope or (after,)
    _require_scope(
        request.impact_scope,
        supplied_before_scope,
        supplied_after_scope,
        scenario_projection_version=profile.owner_projection_versions[ArtifactKind.SCENARIO],
    )
    before_projection = project_artifact(profile, before, request.before)
    after_projection = project_artifact(profile, after, request.after)
    scope_before = tuple(
        project_artifact(profile, item, coordinate_for_artifact(item, scenario_projection_version=scenario_version))
        for item in supplied_before_scope
    )
    scope_after = tuple(
        project_artifact(profile, item, coordinate_for_artifact(item, scenario_projection_version=scenario_version))
        for item in supplied_after_scope
    )
    supplied_context = context or SemanticComparisonContextModel()
    reasons: set[ComparisonReason] = set()

    changes = _compare_subjects(request, before_projection, after_projection, supplied_context, reasons)
    dependencies = _compare_dependencies(request, scope_before, scope_after, reasons)
    paths = _impact_paths(request, changes, dependencies, reasons)
    _record_scope_status(request.impact_scope.closure_status, reasons)
    _record_transformation_limitations(supplied_context, reasons)
    completeness = _completeness(reasons)
    context_digests = set(supplied_context.evidence_digests)
    if supplied_context.transformation_report is not None:
        context_digests.add(canonical_json_digest(supplied_context.transformation_report.model_dump(mode="json")))

    return SemanticComparisonResultModel(
        comparison_profile=request.comparison_profile,
        comparison_profile_digest=request.comparison_profile_digest,
        analyzer_profile=request.analyzer_profile,
        request_digest=canonical_semantic_comparison_request_digest(request),
        before=request.before,
        after=request.after,
        impact_scope=request.impact_scope,
        impact_scope_digest=request.impact_scope.scope_digest,
        changes=changes,
        dependencies=dependencies,
        impact_paths=paths,
        completeness=completeness,
        reason_codes=tuple(sorted(reasons, key=lambda item: item.value)),
        context_digests=tuple(sorted(context_digests)),
        diagnostics=(),
    )


def _require_profile(profile: SemanticComparisonProfileModel, request: SemanticComparisonRequestModel) -> None:
    if request.comparison_profile != profile.profile_id:
        raise ValueError("request comparison profile id does not match the supplied profile")
    if request.comparison_profile_digest != canonical_semantic_comparison_profile_digest(profile):
        raise ValueError("request comparison profile digest does not match the supplied profile")
    if request.analyzer_profile != profile.analyzer_profile:
        raise ValueError("request analyzer profile does not match the supplied profile")
    for name in ComparisonLimitsModel.model_fields:
        if getattr(request.limits, name) > getattr(profile.limits, name):
            raise ValueError("request limits must not exceed the governed comparison profile")


def _require_scope(
    expected: ImpactScopeModel,
    before: tuple[AdmittedArtifact, ...],
    after: tuple[AdmittedArtifact, ...],
    *,
    scenario_projection_version: str = "2",
) -> None:
    actual_before = tuple(
        sorted(
            (coordinate_for_artifact(item, scenario_projection_version=scenario_projection_version) for item in before),
            key=_coordinate_key,
        )
    )
    actual_after = tuple(
        sorted(
            (coordinate_for_artifact(item, scenario_projection_version=scenario_projection_version) for item in after),
            key=_coordinate_key,
        )
    )
    if expected.before_artifacts != actual_before or expected.after_artifacts != actual_after:
        raise ValueError("supplied artifacts must exactly match the declared two-sided impact scope")


def _compare_subjects(
    request: SemanticComparisonRequestModel,
    before: _Projection,
    after: _Projection,
    context: SemanticComparisonContextModel,
    reasons: set[ComparisonReason],
) -> tuple[SemanticChangeModel, ...]:
    before_map = {item.identity: item for item in before.subjects}
    after_map = {item.identity: item for item in after.subjects}
    rename_map = _rename_map(request, context, reasons)
    allowed = _bounded_subject_identities(request, before_map, after_map, reasons)
    changes, consumed_before, consumed_after = _paired_subject_changes(
        before_map, after_map, rename_map, allowed, reasons
    )
    changes.extend(
        _unpaired_change(identity, IdentityRelation.ADDED)
        for identity in sorted((set(after_map) & allowed) - consumed_after)
    )
    changes.extend(
        _unpaired_change(identity, IdentityRelation.REMOVED)
        for identity in sorted((set(before_map) & allowed) - consumed_before)
    )
    return tuple(
        sorted(changes, key=lambda item: (item.identity, item.before_identity or "", item.after_identity or ""))
    )


def _bounded_subject_identities(
    request: SemanticComparisonRequestModel,
    before: dict[str, _Subject],
    after: dict[str, _Subject],
    reasons: set[ComparisonReason],
) -> set[str]:
    identities = sorted(set(before) | set(after))
    if len(identities) > request.limits.max_subjects:
        identities = identities[: request.limits.max_subjects]
        reasons.add(ComparisonReason.SUBJECT_BOUND_EXHAUSTED)
    return set(identities)


def _paired_subject_changes(
    before: dict[str, _Subject],
    after: dict[str, _Subject],
    rename_map: dict[str, str],
    allowed: set[str],
    reasons: set[ComparisonReason],
) -> tuple[list[SemanticChangeModel], set[str], set[str]]:
    same = sorted(set(before) & set(after) & allowed)
    changes = [_paired_change(before[item], after[item], IdentityRelation.SAME, reasons) for item in same]
    consumed_before = set(same)
    consumed_after = set(same)
    for old, new in sorted(rename_map.items()):
        if old in before and new in after and old in allowed and new in allowed:
            changes.append(_paired_change(before[old], after[new], IdentityRelation.RENAMED, reasons))
            consumed_before.add(old)
            consumed_after.add(new)
    return changes, consumed_before, consumed_after


def _unpaired_change(identity: str, relation: IdentityRelation) -> SemanticChangeModel:
    return SemanticChangeModel(
        identity=identity,
        before_identity=identity if relation == IdentityRelation.REMOVED else None,
        after_identity=identity if relation == IdentityRelation.ADDED else None,
        identity_relation=relation,
        textual_relation=RelationStatus.NOT_APPLICABLE,
        structural_relation=RelationStatus.NOT_APPLICABLE,
        semantic_relation=RelationStatus.NOT_APPLICABLE,
    )


def _paired_change(
    before: _Subject,
    after: _Subject,
    identity_relation: IdentityRelation,
    aggregate_reasons: set[ComparisonReason],
) -> SemanticChangeModel:
    reasons: set[ComparisonReason] = set()
    textual = _digest_relation(before.representation_digest, after.representation_digest)
    if textual == RelationStatus.UNKNOWN:
        reasons.add(ComparisonReason.REPRESENTATION_EVIDENCE_MISSING)
        aggregate_reasons.add(ComparisonReason.REPRESENTATION_EVIDENCE_MISSING)
    structural = (
        _digest_relation(before.structural_digest, after.structural_digest)
        if before.structural_profile == after.structural_profile
        else RelationStatus.INCOMPARABLE
    )
    semantic = (
        _digest_relation(before.semantic_digest, after.semantic_digest)
        if before.semantic_profile == after.semantic_profile
        else RelationStatus.INCOMPARABLE
    )
    if structural == RelationStatus.INCOMPARABLE or semantic == RelationStatus.INCOMPARABLE:
        reasons.add(ComparisonReason.VERSION_PAIR_INCOMPARABLE)
        aggregate_reasons.add(ComparisonReason.VERSION_PAIR_INCOMPARABLE)
    return SemanticChangeModel(
        identity=after.identity,
        before_identity=before.identity,
        after_identity=after.identity,
        identity_relation=identity_relation,
        textual_relation=textual,
        structural_relation=structural,
        semantic_relation=semantic,
        reason_codes=tuple(sorted(reasons, key=lambda item: item.value)),
    )


def _digest_relation(before: str | None, after: str | None) -> RelationStatus:
    if before is None or after is None:
        return RelationStatus.UNKNOWN
    return RelationStatus.UNCHANGED if before == after else RelationStatus.CHANGED


def _rename_map(
    request: SemanticComparisonRequestModel,
    context: SemanticComparisonContextModel,
    reasons: set[ComparisonReason],
) -> dict[str, str]:
    report = context.transformation_report
    rename_map: dict[str, str] = {}
    if report is not None:
        if report.status != ArtifactTransformationStatus.SUCCESS:
            reasons.add(ComparisonReason.TRANSFORMATION_EVIDENCE_NOT_SUCCESSFUL)
        elif not _transformation_digests_match(request, report.source_digest, report.target_digest):
            reasons.add(ComparisonReason.TRANSFORMATION_EVIDENCE_DIGEST_MISMATCH)
        elif not _transformation_profiles_match(request, report):
            reasons.add(ComparisonReason.TRANSFORMATION_EVIDENCE_PROFILE_MISMATCH)
        else:
            rename_map = {item.before: item.after for item in report.identity_map}
    return rename_map


def _transformation_digests_match(
    request: SemanticComparisonRequestModel,
    source_digest: str,
    target_digest: str,
) -> bool:
    return source_digest == request.before.canonical_digest and target_digest == request.after.canonical_digest


def _transformation_profiles_match(
    request: SemanticComparisonRequestModel,
    report: ArtifactTransformationReportModel,
) -> bool:
    expected_before_profile = _coordinate_owner_profile(request.before)
    expected_after_profile = _coordinate_owner_profile(request.after)
    return (
        report.source_profile == expected_before_profile
        and report.target_profile == expected_after_profile
        and report.canonicalization_profile == request.before.canonicalization_profile
        and report.canonicalization_profile == request.after.canonicalization_profile
    )


def _compare_dependencies(
    request: SemanticComparisonRequestModel,
    before_scope: tuple[_Projection, ...],
    after_scope: tuple[_Projection, ...],
    reasons: set[ComparisonReason],
) -> tuple[DependencyChangeModel, ...]:
    before_known = {projection.coordinate.canonical_identity for projection in before_scope}
    after_known = {projection.coordinate.canonical_identity for projection in after_scope}
    before = [_stateful(item, before_known, reasons) for projection in before_scope for item in projection.dependencies]
    after = [_stateful(item, after_known, reasons) for projection in after_scope for item in projection.dependencies]
    changes: list[DependencyChangeModel] = []
    grouped_before = _group_dependencies(before)
    grouped_after = _group_dependencies(after)
    for key in sorted(set(grouped_before) | set(grouped_after)):
        changes.extend(_dependency_group_changes(key, grouped_before.get(key, []), grouped_after.get(key, [])))
    if len(changes) > request.limits.max_dependency_edges:
        changes = changes[: request.limits.max_dependency_edges]
        reasons.add(ComparisonReason.DEPENDENCY_EDGE_BOUND_EXHAUSTED)
    return tuple(sorted(changes, key=_dependency_change_key))


def _dependency_group_changes(
    key: tuple[str, str],
    old: list[DependencyStateModel],
    new: list[DependencyStateModel],
) -> list[DependencyChangeModel]:
    old_by_key = {_state_key(item): item for item in old}
    new_by_key = {_state_key(item): item for item in new}
    unchanged = [old_by_key[state_key] for state_key in sorted(set(old_by_key) & set(new_by_key))]
    changes = [_dependency_change(key, DependencyRelation.UNCHANGED, state, state) for state in unchanged]
    old_remaining = sorted((item for item in old if item not in unchanged), key=_state_key)
    new_remaining = sorted((item for item in new if item not in unchanged), key=_state_key)
    changes.extend(
        _dependency_change(key, DependencyRelation.CHANGED, old_state, new_state)
        for old_state, new_state in zip(old_remaining, new_remaining, strict=False)
    )
    changes.extend(
        _dependency_change(key, DependencyRelation.REMOVED, state, None)
        for state in old_remaining[len(new_remaining) :]
    )
    changes.extend(
        _dependency_change(key, DependencyRelation.ADDED, None, state) for state in new_remaining[len(old_remaining) :]
    )
    return changes


def _stateful(
    dependency: _Dependency,
    known: set[str],
    reasons: set[ComparisonReason],
) -> tuple[str, str, DependencyStateModel]:
    resolved = dependency.dependency_identity in known
    reason_codes = () if resolved else (ComparisonReason.UNRESOLVED_REFERENCE,)
    reasons.update(reason_codes)
    return (
        dependency.dependent_identity,
        dependency.rule_id,
        DependencyStateModel(
            dependency_identity=dependency.dependency_identity,
            resolution_status=(
                DependencyResolutionStatus.RESOLVED if resolved else DependencyResolutionStatus.UNRESOLVED
            ),
            provenance_digests=(dependency.provenance_digest,),
            reason_codes=reason_codes,
        ),
    )


def _group_dependencies(
    dependencies: list[tuple[str, str, DependencyStateModel]],
) -> dict[tuple[str, str], list[DependencyStateModel]]:
    grouped: dict[tuple[str, str], list[DependencyStateModel]] = {}
    for dependent, rule, state in dependencies:
        grouped.setdefault((dependent, rule), []).append(state)
    return grouped


def _dependency_change(
    key: tuple[str, str],
    relation: DependencyRelation,
    before: DependencyStateModel | None,
    after: DependencyStateModel | None,
) -> DependencyChangeModel:
    return DependencyChangeModel(
        dependent_identity=key[0],
        rule_id=key[1],
        relation=relation,
        before=before,
        after=after,
    )


def _record_scope_status(status: ImpactClosureStatus, reasons: set[ComparisonReason]) -> None:
    mapping = {
        ImpactClosureStatus.PARTIAL: ComparisonReason.IMPACT_SCOPE_PARTIAL,
        ImpactClosureStatus.REDACTED: ComparisonReason.IMPACT_SCOPE_REDACTED,
        ImpactClosureStatus.UNVERIFIED: ComparisonReason.IMPACT_SCOPE_UNVERIFIED,
    }
    reason = mapping.get(status)
    if reason is not None:
        reasons.add(reason)


def _record_transformation_limitations(
    context: SemanticComparisonContextModel,
    reasons: set[ComparisonReason],
) -> None:
    report = context.transformation_report
    if report is not None and report.preservation.limitations:
        reasons.add(ComparisonReason.TRANSFORMATION_EVIDENCE_LOSSY)


def _completeness(reasons: set[ComparisonReason]) -> ComparisonCompleteness:
    bounded = {
        ComparisonReason.SUBJECT_BOUND_EXHAUSTED,
        ComparisonReason.DEPENDENCY_EDGE_BOUND_EXHAUSTED,
        ComparisonReason.IMPACT_PATH_BOUND_EXHAUSTED,
    }
    if reasons & bounded and not (reasons - bounded):
        return ComparisonCompleteness.BOUNDED
    return ComparisonCompleteness.INDETERMINATE if reasons else ComparisonCompleteness.COMPLETE


def _coordinate_key(coordinate: ArtifactCoordinate) -> tuple[str, str, str]:
    return (coordinate.artifact_kind.value, coordinate.canonical_identity, coordinate.canonical_digest)


def _coordinate_owner_profile(coordinate: ArtifactCoordinate) -> str:
    if isinstance(coordinate, ScenarioCoordinateModel):
        return coordinate.source_profile
    if isinstance(coordinate, ModuleCoordinateModel):
        return coordinate.provenance_profile
    return coordinate.schema_version


def _state_key(state: DependencyStateModel) -> tuple[str, str, tuple[str, ...]]:
    return (state.dependency_identity, state.resolution_status.value, state.provenance_digests)


def _dependency_change_key(change: DependencyChangeModel) -> tuple[str, str, str, str]:
    return (
        change.dependent_identity,
        change.rule_id,
        change.before.dependency_identity if change.before else "",
        change.after.dependency_identity if change.after else "",
    )


__all__ = ["AdmittedArtifact", "analyze_semantic_comparison", "build_impact_scope", "coordinate_for_artifact"]

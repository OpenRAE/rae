"""Finite, offline comparisons of two authoring paths against published vectors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from raes import SDLError
from raes.scenario import Scenario
from raes_contracts.authoring_adapters import (
    AuthoringAdapterComparisonModel,
    AuthoringAdapterProfileModel,
    AuthoringAdapterVectorModel,
    AuthoringObservationModel,
    parse_authoring_vector,
)
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.corpus import FIXTURES, PROFILES, corpus_family_root
from raes_contracts.json_ingress import parse_bounded_json_object
from raes_contracts.semantic_comparison import (
    ComparisonReason,
    IdentityRelation,
    ImpactClosureStatus,
    RelationStatus,
    SemanticComparisonProfileModel,
    SemanticComparisonRequestModel,
    SemanticComparisonResultModel,
)
from raes_processor.semantic_comparison import analyze_semantic_comparison, build_impact_scope, coordinate_for_artifact

from ._authoring_observations import AuthoringPathOutput, observe_output, reference_authoring_output


@dataclass(frozen=True)
class AuthoringPathComparison:
    report: AuthoringAdapterComparisonModel
    semantic_result: SemanticComparisonResultModel | None


def _read_bounded(path: Path, max_bytes: int) -> bytes:
    with path.open("rb") as stream:
        content = stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError("published conformance artifact exceeds byte limit")
    return content


def _profiles() -> tuple[AuthoringAdapterProfileModel, SemanticComparisonProfileModel]:
    root = corpus_family_root(PROFILES)
    profile = AuthoringAdapterProfileModel.model_validate(
        parse_bounded_json_object(
            _read_bounded(root / "authoring-adapters/reference-v1.json", 16384),
            max_bytes=16384,
        )
    )
    semantic = SemanticComparisonProfileModel.model_validate(
        parse_bounded_json_object(
            _read_bounded(root / "semantic-comparison/reference-v2.json", 16384),
            max_bytes=16384,
        )
    )
    if canonical_json_digest(semantic.model_dump(mode="json")) != profile.semantic_profile_digest:
        raise ValueError("semantic profile digest does not match the pinned authoring profile")
    return profile, semantic


def load_authoring_vectors(*, root: Path | None = None) -> tuple[AuthoringAdapterVectorModel, ...]:
    """Load the confined, bounded corpus; missing cases cannot vacuously pass."""
    cases_root = (corpus_family_root(FIXTURES) / "authoring-adapters-v1/cases" if root is None else root).resolve()
    profile, _ = _profiles()
    paths = sorted(cases_root.glob("*.json"))
    if not paths:
        raise ValueError("authoring vector corpus is empty")
    if len(paths) > profile.max_cases:
        raise ValueError("authoring vector count exceeds the profile limit")
    vectors = []
    for path in paths:
        if not path.resolve().is_relative_to(cases_root):
            raise ValueError("vector resolves outside the corpus")
        vector = parse_authoring_vector(_read_bounded(path, 128 * 1024))
        _require_profile(vector, profile)
        if vector.case_id != path.stem:
            raise ValueError("vector case id must match its corpus filename")
        vectors.append(vector)
    return tuple(vectors)


def _require_profile(vector: AuthoringAdapterVectorModel, profile: AuthoringAdapterProfileModel) -> None:
    if vector.profile_digest != canonical_json_digest(profile.model_dump(mode="json")):
        raise ValueError("vector profile digest does not match the published profile")


def _observation(
    vector: AuthoringAdapterVectorModel,
    output: AuthoringPathOutput,
    side: str,
    reasons: list[str],
) -> tuple[AuthoringObservationModel | None, Scenario | None]:
    if output.input_source != vector.input_source:
        reasons.append(f"{side}-input-mismatch")
        return None, None
    try:
        return observe_output(vector, output)
    except (SDLError, ValueError, TypeError, AttributeError):
        # Only fixed typed reasons enter a persisted comparison. No raw exception data.
        reasons.append(f"{side}-invalid")
        return None, None


def _semantic_comparison(
    profile: SemanticComparisonProfileModel,
    left: Scenario,
    right: Scenario,
) -> SemanticComparisonResultModel:
    before, after = coordinate_for_artifact(left), coordinate_for_artifact(right)
    scope = build_impact_scope(
        (left,), (right,), traversal_roots=(after.canonical_identity,), closure_status=ImpactClosureStatus.COMPLETE
    )
    request = SemanticComparisonRequestModel(
        comparison_profile=profile.profile_id,
        comparison_profile_digest=canonical_json_digest(profile.model_dump(mode="json")),
        analyzer_profile=profile.analyzer_profile,
        before=before,
        after=after,
        impact_scope=scope,
    )
    return analyze_semantic_comparison(profile, request, left, right)


def _semantic_relation(result: SemanticComparisonResultModel) -> str:
    # Exact textual representations are deliberately not a semantic assertion in v1.
    if set(result.reason_codes) - {ComparisonReason.REPRESENTATION_EVIDENCE_MISSING}:
        return "incomparable"
    if any(
        change.semantic_relation in {RelationStatus.UNKNOWN, RelationStatus.INCOMPARABLE} for change in result.changes
    ):
        return "incomparable"
    if any(
        change.identity_relation != IdentityRelation.SAME or change.semantic_relation == RelationStatus.CHANGED
        for change in result.changes
    ):
        return "different"
    return "equivalent"


def compare_authoring_paths(
    vector: AuthoringAdapterVectorModel,
    left: AuthoringPathOutput,
    right: AuthoringPathOutput,
    *,
    left_path: str = "left",
    right_path: str = "right",
) -> AuthoringPathComparison:
    """Re-admit outputs, compare each axis, and independently check the fixed oracle."""
    vector = parse_authoring_vector(vector.model_dump_json())
    profile, semantic_profile = _profiles()
    _require_profile(vector, profile)
    reasons: list[str] = []
    left_observed, left_artifact = _observation(vector, left, "left", reasons)
    right_observed, right_artifact = _observation(vector, right, "right", reasons)
    left_expected = left_observed == vector.expected
    right_expected = right_observed == vector.expected
    if not left_expected:
        reasons.append("left-unexpected")
    if not right_expected:
        reasons.append("right-unexpected")
    artifact = diagnostics = provenance = semantics = "incomparable"
    semantic_result = None
    if left_observed is not None and right_observed is not None:
        artifact = _relation(left_observed.canonical_artifact_digest, right_observed.canonical_artifact_digest)
        diagnostics = _relation(left_observed.diagnostics_digest, right_observed.diagnostics_digest)
        provenance = _relation(left_observed.transformation_digest, right_observed.transformation_digest)
        semantics = "not-applicable"
        if left_observed.outcome != right_observed.outcome:
            reasons.append("outcomes-differ")
        if left_artifact is not None and right_artifact is not None:
            semantic_result = _semantic_comparison(semantic_profile, left_artifact, right_artifact)
            semantics = _semantic_relation(semantic_result)
        reasons.extend(_difference_reasons((artifact, diagnostics, provenance, semantics)))
        if semantics == "incomparable":
            reasons.append("semantic-context-incomplete")
    report = AuthoringAdapterComparisonModel(
        case_id=vector.case_id,
        vector_digest=canonical_json_digest(vector.model_dump(mode="json")),
        left_path=left_path,
        right_path=right_path,
        left=left_observed,
        right=right_observed,
        left_matches_expected=left_expected,
        right_matches_expected=right_expected,
        artifact_relation=artifact,
        diagnostic_relation=diagnostics,
        provenance_relation=provenance,
        semantic_relation=semantics,
        semantic_result_digest=canonical_json_digest(semantic_result.model_dump(mode="json"))
        if semantic_result
        else None,
        reason_codes=tuple(sorted(set(reasons))),
    )
    return AuthoringPathComparison(report, semantic_result)


def _difference_reasons(relations: tuple[str, ...]) -> list[str]:
    codes = ("artifacts-differ", "diagnostics-differ", "provenance-differs", "semantics-differ")
    return [code for relation, code in zip(relations, codes, strict=True) if relation == "different"]


def _relation(left: str | None, right: str | None) -> str:
    if left is None and right is None:
        return "not-applicable"
    return "equivalent" if left == right else "different"


__all__ = [
    "AuthoringPathComparison",
    "AuthoringPathOutput",
    "compare_authoring_paths",
    "load_authoring_vectors",
    "reference_authoring_output",
]

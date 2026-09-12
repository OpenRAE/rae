"""Coverage-aware, conservative projections into the existing realization relation."""

from __future__ import annotations

from collections.abc import Iterator

from ._description_assertions import assertion_conflict
from .canonical import canonical_json_digest
from .contracts.realization_descriptions import DescriptionFactModel, TypedRealizationDescriptionModel
from .description_coverage import DescriptionCoverageScope, coverage_matches
from .diagnostics import Diagnostic
from .realization_structure import (
    RealizationConstraintDocument,
    RealizationKeyedCollectionConstraint,
    RealizationLiteral,
    RealizationPresence,
    RealizationRecordConstraint,
    RealizationRelationResult,
    RealizationRelationStatus,
    RealizationSequenceConstraint,
    RecursiveRealizationStructure,
    evaluate_realization_constraint,
    validate_realization_value,
)
from .realization_structure._common import closure_for, json_equal, pointer, pointer_tokens


def description_result(status: str, code: str, message: str) -> RealizationRelationResult:
    return RealizationRelationResult(
        RealizationRelationStatus(status),
        (
            Diagnostic(
                code=f"description.{code}",
                domain="realization",
                address="",
                message=message,
            ),
        ),
    )


def readmit_description(description: TypedRealizationDescriptionModel) -> TypedRealizationDescriptionModel:
    """Bound mutable nested inputs before serialization and return an isolated copy."""
    if not validate_realization_value(description, python_carriers=True).conformant:
        raise ValueError("description exceeds the supported finite value bounds")
    return TypedRealizationDescriptionModel.model_validate(description.model_dump(mode="json"))


def descriptive_value(value: RecursiveRealizationStructure) -> object:
    """Project supplied values only; no deployment model or default participates."""
    if isinstance(value, RealizationLiteral):
        projected = value.value
    elif isinstance(value, RealizationRecordConstraint):
        projected = {name: descriptive_value(child) for name, child in value.fields.items()}
    else:
        projected = [descriptive_value(child) for child in _descriptive_items(value)]
    return projected


def _descriptive_items(value: RecursiveRealizationStructure) -> tuple[RecursiveRealizationStructure, ...]:
    if isinstance(value, RealizationSequenceConstraint):
        return value.items
    if isinstance(value, RealizationKeyedCollectionConstraint):
        return tuple(
            member.constraint
            for member in sorted(value.members, key=lambda member: canonical_json_digest(list(member.identity)))
        )
    raise ValueError("unsupported descriptive value")


def description_conflict(description: TypedRealizationDescriptionModel) -> RealizationRelationResult | None:
    conflict = assertion_conflict(description)
    if conflict == "contradictory":
        return description_result("invalid", conflict, "Comparable assertions disagree about one subject.")
    if conflict:
        return description_result("unresolved", conflict, "Assertions require an explicit common observation window.")
    return None


def _bind_author(
    description: TypedRealizationDescriptionModel, authored: RealizationConstraintDocument
) -> RealizationRelationResult | None:
    result = None
    if not validate_realization_value(authored, python_carriers=True).conformant:
        result = description_result(
            "limit-exceeded", "limit-exceeded", "Author constraints exceed the supported bounds."
        )
    elif description.semantic_profile != authored.semantic_profile:
        result = description_result("unsupported", "profile", "Description and author semantic profiles differ.")
    elif description.authored_ref.ref_digest != canonical_json_digest(authored.model_dump(mode="json")):
        result = description_result(
            "invalid", "author-binding", "The description names a different original author artifact."
        )
    return result


def _extra_scope_failure(
    authored: RealizationConstraintDocument,
    rule: RealizationRecordConstraint,
    tokens: tuple[str, ...],
    traversed: tuple[str, ...],
) -> RealizationRelationResult | None:
    for count in range(len(traversed), len(tokens)):
        closure = closure_for(authored, rule.closure, tokens[:count])
        if closure is None or closure.posture.value != "open":
            return description_result(
                "nonconformant", "closed-scope", "A supplied fact is outside the closed author scope."
            )
    return None


def _rule_at(
    authored: RealizationConstraintDocument, subject: str
) -> tuple[RecursiveRealizationStructure | None, RealizationRelationResult | None]:
    rule: RecursiveRealizationStructure | None = authored.root
    traversed: tuple[str, ...] = ()
    failure = None
    tokens = pointer_tokens(subject)
    for token in tokens:
        if rule.presence is RealizationPresence.FORBIDDEN:
            failure = description_result(
                "nonconformant", "forbidden", "A supplied fact is inside a forbidden author scope."
            )
            break
        if not isinstance(rule, RealizationRecordConstraint):
            rule = None
            failure = description_result(
                "unsupported", "projection", "Partial projection through this author structure is unsupported."
            )
            break
        if token not in rule.fields:
            failure = _extra_scope_failure(authored, rule, tokens, traversed)
            rule = None
            break
        rule = rule.fields[token]
        traversed += (token,)
    return rule, failure


def _literal_violation(
    rule: RecursiveRealizationStructure, literal: RealizationLiteral, authored: RealizationConstraintDocument
) -> RealizationRelationResult | None:
    if isinstance(
        rule, (RealizationRecordConstraint, RealizationKeyedCollectionConstraint, RealizationSequenceConstraint)
    ):
        return description_result(
            "nonconformant", "value", "A supplied scalar contradicts the authored structured value."
        )
    result = evaluate_realization_constraint(authored.model_copy(update={"root": rule, "scopes": ()}), literal.value)
    return None if result.conformant else result


def _resolved_fact_violation(
    fact: DescriptionFactModel, rule: RecursiveRealizationStructure | None, authored: RealizationConstraintDocument
) -> RealizationRelationResult | None:
    result = None
    if rule is None:
        return None
    if fact.state == "known-absent":
        if rule.presence is RealizationPresence.REQUIRED:
            result = description_result(
                "nonconformant", "known-absent", "A required author field is positively known absent."
            )
    elif rule.presence is RealizationPresence.FORBIDDEN:
        result = description_result(
            "nonconformant", "forbidden", "A supplied fact contradicts an author absence constraint."
        )
    elif isinstance(fact.value, RealizationLiteral):
        result = _literal_violation(rule, fact.value, authored)
    return result


def _fact_violation(
    fact: DescriptionFactModel, authored: RealizationConstraintDocument
) -> RealizationRelationResult | None:
    if fact.state not in {"known", "known-absent"}:
        return None
    rule, failure = _rule_at(authored, fact.subject)
    if failure is not None:
        return failure if fact.state == "known" else None
    return _resolved_fact_violation(fact, rule, authored)


def known_fact_violation(
    description: TypedRealizationDescriptionModel, authored: RealizationConstraintDocument
) -> RealizationRelationResult | None:
    """A supplied scalar can disprove an exact constraint even in a partial report."""
    for fact in _comparison_facts(description.facts):
        if violation := _fact_violation(fact, authored):
            return violation
    return None


def _comparison_facts(facts: tuple[DescriptionFactModel, ...]) -> Iterator[DescriptionFactModel]:
    for fact in facts:
        if fact.state == "known" and isinstance(fact.value, RealizationRecordConstraint):
            children = tuple(
                fact.model_copy(
                    update={
                        "subject": pointer((*pointer_tokens(fact.subject), key)),
                        "value": value,
                    }
                )
                for key, value in fact.value.fields.items()
            )
            yield from _comparison_facts(children)
        else:
            yield fact


def description_values(facts: tuple[DescriptionFactModel, ...]) -> object:
    """Assemble explicit disjoint record facts; never fill missing descendants."""
    root: dict[str, object] = {}
    supplied = {}
    for fact in facts:
        if fact.state != "known":
            continue
        value = descriptive_value(fact.value)
        if fact.subject in supplied and not json_equal(supplied[fact.subject], value):
            raise ValueError("overlapping description facts require explicit reconciliation")
        supplied[fact.subject] = value
    paths = sorted(pointer_tokens(subject) for subject in supplied)
    if any(b[: len(a)] == a for a, b in zip(paths, paths[1:], strict=False)):
        raise ValueError("overlapping description fact projections require explicit reconciliation")
    for fact in facts:
        if fact.state != "known":
            continue
        value = descriptive_value(fact.value)
        tokens = pointer_tokens(fact.subject)
        if not tokens:
            return value
        current = root
        for token in tokens[:-1]:
            current = current.setdefault(token, {})
        current[tokens[-1]] = value
    return root


def assess_realization_description(
    description: TypedRealizationDescriptionModel, authored: RealizationConstraintDocument
) -> RealizationRelationResult:
    """Assess facts at their actual coverage; a schema pass never establishes delivery."""
    bounded = validate_realization_value(description, python_carriers=True)
    if not bounded.conformant:
        return bounded
    try:
        description = readmit_description(description)
    except ValueError:
        return description_result("invalid", "invalid", "Description failed bounded contract admission.")
    return _assess_admitted_description(description, authored)


def _assess_admitted_description(
    description: TypedRealizationDescriptionModel, authored: RealizationConstraintDocument
) -> RealizationRelationResult:
    conflict = description_conflict(description)
    precondition = _bind_author(description, authored) or (
        conflict if conflict and conflict.status.value != "unresolved" else None
    )
    if precondition is not None:
        return precondition
    if any(fact.profile_bindings for fact in description.facts):
        return description_result(
            "unsupported", "profile-comparison", "Private profile carriage does not establish comparison support."
        )
    return (
        known_fact_violation(description, authored) or conflict or _assess_complete_description(description, authored)
    )


def _complete_author_coverage(
    description: TypedRealizationDescriptionModel, authored: RealizationConstraintDocument
) -> bool:
    closure = closure_for(authored, getattr(authored.root, "closure", authored.default_closure), ())
    if closure is None:
        return False
    kind = (
        "collection"
        if isinstance(authored.root, (RealizationSequenceConstraint, RealizationKeyedCollectionConstraint))
        else "field"
    )
    requested = DescriptionCoverageScope(
        scope="", kind=kind, profile=closure.profile or authored.semantic_profile, universe=closure.universe
    )
    return any(coverage_matches(description, coverage, requested, complete=True) for coverage in description.coverage)


def _assess_complete_description(
    description: TypedRealizationDescriptionModel, authored: RealizationConstraintDocument
) -> RealizationRelationResult:
    if not _complete_author_coverage(description, authored):
        return description_result(
            "unresolved", "coverage", "The report does not establish complete coverage of the requested realization."
        )
    try:
        values = description_values(description.facts)
    except ValueError:
        return description_result(
            "unsupported", "overlapping-projection", "Overlapping facts require an explicit reconciled projection."
        )
    return evaluate_realization_constraint(authored, values)


__all__ = ["assess_realization_description"]

"""Coverage-aware, conservative projections into the existing realization relation."""

from __future__ import annotations

from ._description_assertions import assertion_conflict
from .canonical import canonical_json_digest
from .contracts.realization_descriptions import DescriptionFactModel, TypedRealizationDescriptionModel
from .description_coverage import coverage_matches
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
        return value.value
    if isinstance(value, RealizationRecordConstraint):
        return {name: descriptive_value(child) for name, child in value.fields.items()}
    if isinstance(value, RealizationSequenceConstraint):
        return [descriptive_value(child) for child in value.items]
    if isinstance(value, RealizationKeyedCollectionConstraint):
        return [
            descriptive_value(member.constraint)
            for member in sorted(value.members, key=lambda member: canonical_json_digest(list(member.identity)))
        ]
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
    if not validate_realization_value(authored, python_carriers=True).conformant:
        return description_result("limit-exceeded", "limit-exceeded", "Author constraints exceed the supported bounds.")
    if description.semantic_profile != authored.semantic_profile:
        return description_result("unsupported", "profile", "Description and author semantic profiles differ.")
    if description.authored_ref.ref_digest != canonical_json_digest(authored.model_dump(mode="json")):
        return description_result(
            "invalid", "author-binding", "The description names a different original author artifact."
        )
    return None


def _rule_at(authored: RealizationConstraintDocument, subject: str):
    rule = authored.root
    traversed = ()
    for token in pointer_tokens(subject):
        if rule.presence is RealizationPresence.FORBIDDEN:
            return rule, description_result(
                "nonconformant", "forbidden", "A supplied fact is inside a forbidden author scope."
            )
        if not isinstance(rule, RealizationRecordConstraint):
            return None, description_result(
                "unsupported", "projection", "Partial projection through this author structure is unsupported."
            )
        if token not in rule.fields:
            closure = closure_for(authored, rule.closure, traversed)
            if closure is None or closure.posture.value != "open":
                return None, description_result(
                    "nonconformant", "closed-scope", "A supplied fact is outside the closed author scope."
                )
            # Additional descendants remain subject to any explicit lexical scopes.
            for count in range(len(traversed) + 1, len(pointer_tokens(subject))):
                inherited = closure_for(authored, rule.closure, pointer_tokens(subject)[:count])
                if inherited is None or inherited.posture.value != "open":
                    return None, description_result(
                        "nonconformant", "closed-scope", "A supplied fact is outside the closed author scope."
                    )
            return None, None
        rule = rule.fields[token]
        traversed += (token,)
    return rule, None


def known_fact_violation(
    description: TypedRealizationDescriptionModel, authored: RealizationConstraintDocument
) -> RealizationRelationResult | None:
    """A supplied scalar can disprove an exact constraint even in a partial report."""
    for fact in _comparison_facts(description.facts):
        if fact.state not in {"known", "known-absent"}:
            continue
        rule, failure = _rule_at(authored, fact.subject)
        if failure is not None:
            if fact.state == "known":
                return failure
            continue
        if rule is not None and fact.state == "known-absent":
            if rule.presence is RealizationPresence.REQUIRED:
                return description_result(
                    "nonconformant", "known-absent", "A required author field is positively known absent."
                )
            continue
        if rule is not None and rule.presence is RealizationPresence.FORBIDDEN:
            return description_result(
                "nonconformant", "forbidden", "A supplied fact contradicts an author absence constraint."
            )
        if rule is None or not isinstance(fact.value, RealizationLiteral):
            continue
        if isinstance(
            rule, (RealizationRecordConstraint, RealizationKeyedCollectionConstraint, RealizationSequenceConstraint)
        ):
            return description_result(
                "nonconformant", "value", "A supplied scalar contradicts the authored structured value."
            )
        result = evaluate_realization_constraint(
            authored.model_copy(update={"root": rule, "scopes": ()}), fact.value.value
        )
        if not result.conformant:
            return result
    return None


def _comparison_facts(facts):
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
    if violation := known_fact_violation(description, authored):
        return violation
    if conflict is not None:
        return conflict
    root_closure = closure_for(authored, getattr(authored.root, "closure", authored.default_closure), ())
    kind = (
        "collection"
        if isinstance(authored.root, (RealizationSequenceConstraint, RealizationKeyedCollectionConstraint))
        else "field"
    )
    complete = root_closure is not None and any(
        coverage_matches(
            description,
            coverage,
            scope="",
            kind=kind,
            profile=root_closure.profile or authored.semantic_profile,
            universe=root_closure.universe,
            complete=True,
        )
        for coverage in description.coverage
    )
    if not complete:
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

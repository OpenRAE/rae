"""SEM-215 outcome-interpretation rule-conformance validation."""

from collections.abc import Iterable, Mapping

from raes_contracts.participant_outcome_semantics import (
    PROVENANCE_REQUIRED_OUTCOME_SOURCE_LAYERS,
    OutcomeInterpretationSourceLayer,
)

from .behavior_resources import ParticipantOutcomeInterpretationRuleRuntime
from .outcome import ParticipantOutcomeInterpretationRecord
from .resources import _as_string_set


def _contract_sem215_source_bindings(
    rule: ParticipantOutcomeInterpretationRuleRuntime,
) -> dict[tuple[str, str], dict[str, str | set[str]]]:
    bindings = rule.spec.get("source_bindings", ())
    if isinstance(bindings, (str, bytes, Mapping)) or not isinstance(bindings, Iterable):
        return {}
    declarations: dict[tuple[str, str], dict[str, str | set[str]]] = {}
    for index, binding in enumerate(bindings):
        if not isinstance(binding, Mapping) or not binding.get("source_id") or not binding.get("source_layer"):
            continue
        declarations[(str(binding.get("source_id")), str(binding.get("source_layer")))] = {
            "ref": rule.source_refs[index] if index < len(rule.source_refs) else str(binding.get("ref", "")),
            "evidence_refs": _as_string_set(binding.get("evidence_refs", ())),
            "provenance_refs": _as_string_set(binding.get("provenance_refs", ())),
        }
    return declarations


def _contract_sem215_target_bindings(
    rule: ParticipantOutcomeInterpretationRuleRuntime,
) -> dict[tuple[str, str], dict[str, str | set[str] | None]]:
    bindings = rule.spec.get("target_bindings", ())
    if isinstance(bindings, (str, bytes, Mapping)) or not isinstance(bindings, Iterable):
        return {}
    declarations: dict[tuple[str, str], dict[str, str | set[str] | None]] = {}
    for index, binding in enumerate(bindings):
        if not isinstance(binding, Mapping) or not binding.get("target_id") or not binding.get("target_layer"):
            continue
        governance_ref = binding.get("governance_ref")
        declarations[(str(binding.get("target_id")), str(binding.get("target_layer")))] = {
            "ref": rule.target_refs[index] if index < len(rule.target_refs) else str(binding.get("ref", "")),
            "governance_ref": str(governance_ref) if governance_ref is not None else None,
            "evidence_refs": _as_string_set(binding.get("evidence_refs", ())),
            "limitations": _as_string_set(binding.get("limitations", ())),
        }
    return declarations


def _outcome_source_layer_requires_provenance(layer: str) -> bool:
    try:
        source_layer = OutcomeInterpretationSourceLayer(layer)
    except ValueError:
        return False
    return source_layer in PROVENANCE_REQUIRED_OUTCOME_SOURCE_LAYERS


def _sem215_unreported_source_violations(
    record: ParticipantOutcomeInterpretationRecord,
    declared_sources: Iterable[tuple[str, str]],
    reported_sources: set[tuple[str, str]],
) -> list[str]:
    violations: list[str] = []
    for source_id, source_layer in sorted(declared_sources):
        if not _outcome_source_layer_requires_provenance(source_layer):
            continue
        if (source_id, source_layer) not in reported_sources:
            violations.append(
                f"outcome interpretation {record.interpretation_id!r} source {source_id!r} "
                f"with provenance-required layer {source_layer!r} is not reported"
            )
    return violations


def _sem215_source_binding_violations(
    record: ParticipantOutcomeInterpretationRecord,
    rule: ParticipantOutcomeInterpretationRuleRuntime,
) -> list[str]:
    violations: list[str] = []
    declared_sources = _contract_sem215_source_bindings(rule)
    reported_sources: set[tuple[str, str]] = set()
    for source in record.source_bindings:
        source_key = (source.source_id, source.source_layer.value)
        reported_sources.add(source_key)
        if source_key not in declared_sources:
            violations.append(
                f"outcome interpretation {record.interpretation_id!r} source {source.source_id!r} "
                f"is not declared by {rule.address}"
            )
            continue
        declared_refs = declared_sources[source_key]
        if source.ref != declared_refs["ref"]:
            violations.append(
                f"outcome interpretation {record.interpretation_id!r} source {source.source_id!r} "
                f"ref {source.ref!r} does not match declared ref {declared_refs['ref']!r}"
            )
        for ref in sorted(set(source.evidence_refs) - declared_refs["evidence_refs"]):
            violations.append(
                f"outcome interpretation {record.interpretation_id!r} source {source.source_id!r} "
                f"reports undeclared evidence_ref {ref!r}"
            )
        for ref in sorted(set(source.provenance_refs) - declared_refs["provenance_refs"]):
            violations.append(
                f"outcome interpretation {record.interpretation_id!r} source {source.source_id!r} "
                f"reports undeclared provenance_ref {ref!r}"
            )
        for ref in sorted(declared_refs["provenance_refs"] - set(source.provenance_refs)):
            violations.append(
                f"outcome interpretation {record.interpretation_id!r} source {source.source_id!r} "
                f"omits declared provenance_ref {ref!r}"
            )
    violations.extend(_sem215_unreported_source_violations(record, declared_sources, reported_sources))
    return violations


def _sem215_target_binding_violations(
    record: ParticipantOutcomeInterpretationRecord,
    rule: ParticipantOutcomeInterpretationRuleRuntime,
) -> list[str]:
    violations: list[str] = []
    declared_targets = _contract_sem215_target_bindings(rule)
    for target in record.target_bindings:
        target_key = (target.target_id, target.target_layer.value)
        if target_key not in declared_targets:
            violations.append(
                f"outcome interpretation {record.interpretation_id!r} target {target.target_id!r} "
                f"is not declared by {rule.address}"
            )
            continue
        declared_refs = declared_targets[target_key]
        if target.ref != declared_refs["ref"]:
            violations.append(
                f"outcome interpretation {record.interpretation_id!r} target {target.target_id!r} "
                f"ref {target.ref!r} does not match declared ref {declared_refs['ref']!r}"
            )
        if target.governance_ref != declared_refs["governance_ref"]:
            violations.append(
                f"outcome interpretation {record.interpretation_id!r} target {target.target_id!r} "
                f"governance_ref {target.governance_ref!r} does not match declared governance_ref "
                f"{declared_refs['governance_ref']!r}"
            )
        for ref in sorted(set(target.evidence_refs) - declared_refs["evidence_refs"]):
            violations.append(
                f"outcome interpretation {record.interpretation_id!r} target {target.target_id!r} "
                f"reports undeclared evidence_ref {ref!r}"
            )
        if declared_refs["limitations"] and not set(target.limitations) <= declared_refs["limitations"]:
            violations.append(
                f"outcome interpretation {record.interpretation_id!r} target {target.target_id!r} "
                "reports limitations outside the declared rule"
            )
    return violations


def validate_participant_outcome_interpretation_record(
    record: ParticipantOutcomeInterpretationRecord,
    rule: ParticipantOutcomeInterpretationRuleRuntime,
) -> list[str]:
    """Return SEM-215 rule-conformance violations for a runtime interpretation."""

    violations: list[str] = []
    violations.extend(_sem215_source_binding_violations(record, rule))
    violations.extend(_sem215_target_binding_violations(record, rule))
    declared_rule_evidence_refs = _as_string_set(rule.spec.get("evidence_refs", ()))
    for ref in sorted(set(record.evidence_refs) - declared_rule_evidence_refs):
        violations.append(
            f"outcome interpretation {record.interpretation_id!r} reports undeclared evidence_ref {ref!r}"
        )
    return violations

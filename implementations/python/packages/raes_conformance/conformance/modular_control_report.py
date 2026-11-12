"""Validate the subset and binding claims carried by modular runtime results."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .modular_control_types import ModularControlEvidence

if TYPE_CHECKING:
    from .report import BackendConformanceReport, ConformanceCaseResult

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REFUSAL_OBLIGATIONS = frozenset(
    {"mandatory-coverage", "strict-denial", "authority", "stale-cut", "conflict", "integrity"}
)


def _validate_subset(cases: list[ConformanceCaseResult]) -> None:
    subsets = {(case.modular_control.selected_obligations, case.modular_control.claimed_effect_kinds) for case in cases}
    if len(subsets) != 1:
        raise ValueError("modular cases disagree on the selected subset")
    selected, effects = next(iter(subsets))
    required = {*selected, *("effect:" + kind for kind in effects)}
    covered = {case.modular_control.obligation for case in cases}
    if not required or covered != required:
        raise ValueError("modular report omits or adds a selected obligation")


def _validate_measurements(binding: ModularControlEvidence) -> None:
    for counts in (binding.expected_calls, binding.actual_calls):
        if any(type(value) is not int or value < 0 for value in counts.values()):
            raise ValueError("modular execution counts must be nonnegative integers")
    if any(not _DIGEST.fullmatch(value) for value in binding.artifact_digests.values()):
        raise ValueError("modular artifact identities require exact digests")


def _validate_replay_and_refusal(binding: ModularControlEvidence) -> None:
    if binding.obligation in {"duplicate", "restart"} and (
        binding.exact_replays < 1 or "ledger" not in binding.artifact_digests
    ):
        raise ValueError("modular replay claim requires exact retained identity evidence")
    if binding.obligation == "restart" and not binding.replayed_after_reopen:
        raise ValueError("modular restart claim requires matching replay after reopening")
    if binding.obligation in _REFUSAL_OBLIGATIONS and binding.obligation not in binding.refusal_causes:
        raise ValueError("modular refusal claim requires its own cause evidence")


def _validate_pass(case: ConformanceCaseResult) -> None:
    binding = case.modular_control
    _validate_replay_and_refusal(binding)
    if case.execution_basis not in {"hermetic-live", "fixture-only"}:
        raise ValueError("modular runner cannot upgrade runtime evidence to native evidence")
    required_bindings = {"policy"} if binding.obligation == "authored-recovery" else {"selection", "apparatus"}
    if not required_bindings <= binding.artifact_digests.keys() or not case.probe_digest:
        raise ValueError("modular pass is missing exact artifact bindings")
    if case.residual_state:
        raise ValueError("modular pass cannot hide residual state")


def validate_modular_report(report: BackendConformanceReport) -> None:
    modular = [case for case in report.cases if case.modular_control is not None]
    if not modular:
        if report.profile == "modular-control-runtime/v2" and report.passed:
            raise ValueError("modular conformance requires measured cases")
        return
    if report.profile == "modular-control-runtime/v2" and report.native_conformance:
        raise ValueError("modular runtime evidence cannot grant native conformance")
    _validate_subset(modular)
    for case in modular:
        _validate_measurements(case.modular_control)
        if case.passed:
            _validate_pass(case)

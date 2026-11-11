"""Bounded modular-control conformance for independently installed targets."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from pydantic import TypeAdapter
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_decisions_v2 import ControlExecutableEffectTargetV2
from raes_contracts.errors import InvalidInputError, RaesError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.published_schemas import published_schema
from raes_runtime.registry import RuntimeTarget

from .diagnostics import _diagnostic, sanitized_failure_message
from .modular_control_checks import artifact_bindings, case_checks
from .modular_control_execution import _Measurement, execute_case
from .modular_control_types import (
    MODULAR_CONTROL_OBLIGATIONS,
    ModularControlCase,
    ModularControlEvidence,
    ModularControlHarness,
    ModularControlOperation,
    ModularControlStep,
)
from .report import BackendConformanceReport, ConformanceCaseResult, _bounded_conformance_claim

_LOGGER = get_logger(__name__)
_PROFILE = "modular-control-runtime/v2"
_LIMITATIONS = (
    "Finite cases cover only the selected obligation/effect subset and exact installed bindings.",
    "Harness inputs and independent observation sources are trusted installed operator code.",
    "Runtime conformance does not establish native backend realization or experimental claims.",
)
_NON_CLAIMS = (
    "No universal noninterference, backend equivalence, native resume or exactly-once external-effect guarantee.",
    "No coverage of excluded mechanisms, effects, stores, deployments or undeclared channels.",
)


def modular_control_obligations() -> tuple[str, ...]:
    """Return the installed finite obligation catalog; effect cases are parameterized."""

    return (*MODULAR_CONTROL_OBLIGATIONS, "authored-recovery")


def _effect_kinds() -> tuple[str, ...]:
    # The governed target union remains the sole effect-kind authority.
    return tuple(sorted(TypeAdapter(ControlExecutableEffectTargetV2).json_schema()["discriminator"]["mapping"]))


def _evidence(
    obligation: str,
    obligations: tuple[str, ...],
    effects: tuple[str, ...],
    case: ModularControlCase | None = None,
    measured: _Measurement | None = None,
) -> ModularControlEvidence:
    measured = measured or _Measurement()
    support = tuple(
        {
            "obligation_digest": canonical_json_digest(item.obligation_id),
            "required_strength": item.required_strength,
            "constraints_digest": canonical_json_digest(
                [ref.model_dump(mode="json") for ref in item.required_constraints]
            ),
            "effective_level": item.effective_support.effective_level,
            "relation": item.relation,
        }
        for evaluation in measured.evaluations
        for item in evaluation.support
    )
    return ModularControlEvidence(
        obligation=obligation,
        selected_obligations=obligations,
        claimed_effect_kinds=effects,
        excluded_effect_kinds=tuple(kind for kind in _effect_kinds() if kind not in effects),
        artifact_digests=artifact_bindings(case, measured) if case is not None else {},
        support=support,
        expected_calls=dict(case.expected_calls) if case else {},
        actual_calls=dict(measured.counts),
        owner_outcomes=dict(measured.outcomes),
        owner_observations=measured.observations,
        reopened=measured.reopened,
        exact_replays=measured.exact_replays,
        replayed_after_reopen=measured.replayed_after_reopen,
        refusal_causes=tuple(sorted(measured.refusal_causes)),
    )


def _missing(obligation: str, obligations: tuple[str, ...], effects: tuple[str, ...]) -> ConformanceCaseResult:
    return ConformanceCaseResult(
        name=obligation,
        contract_name="participant-control-evaluation-v2",
        valid=True,
        passed=False,
        outcome="unsupported",
        probe_kind="modular-control",
        modular_control=_evidence(obligation, obligations, effects),
        diagnostics=(
            _diagnostic("conformance.modular-coverage-missing", obligation, "Required runtime probe is absent."),
        ),
        limitations=_LIMITATIONS,
        explicit_non_claims=_NON_CLAIMS,
    )


def _run_case(
    target: RuntimeTarget,
    case: ModularControlCase,
    obligations: tuple[str, ...],
    effects: tuple[str, ...],
    store_root: Path | None,
) -> ConformanceCaseResult:
    measured = _Measurement()
    diagnostics = []
    try:
        execute_case(target, case, measured, store_root)
        failures = case_checks(case, measured)
        if failures:
            diagnostics.append(
                _diagnostic(
                    "conformance.modular-obligation-failed",
                    case.obligation,
                    "Runtime probe failed: " + ", ".join(failures) + ".",
                )
            )
    except Exception as exc:
        if not isinstance(exc, RaesError):
            # Isolation of the harness inputs and installed operator code: a refusal category needs no record.
            _LOGGER.exception("modular-control probe failed", exc_info=foreign_failure_record(exc))
        diagnostics.append(
            _diagnostic("conformance.modular-probe-failed", case.obligation, sanitized_failure_message(exc))
        )
    evidence = _evidence(case.obligation, obligations, effects, case, measured)
    return ConformanceCaseResult(
        name=case.name,
        contract_name="participant-control-evaluation-v2",
        valid=True,
        passed=not diagnostics,
        execution_basis="hermetic-live",
        probe_kind="modular-control",
        probe_digest=canonical_json_digest(
            {
                "obligation": case.obligation,
                "expectations": [case.expected_compositions, dict(case.expected_calls), dict(case.expected_effects)],
                "artifacts": dict(evidence.artifact_digests),
            }
        ),
        target_binding=canonical_json_digest(backend_manifest_payload(target.manifest)),
        manifest_digest=canonical_json_digest(backend_manifest_payload(target.manifest)),
        configuration_digest=evidence.artifact_digests.get("configuration"),
        profile_digest=evidence.artifact_digests.get("profiles"),
        modular_control=evidence,
        evidence_refs=tuple(
            sorted(
                set(evidence.artifact_digests.values())
                | {ref for observation in measured.observations for ref in observation.evidence_refs}
            )
        ),
        expected_operations=tuple(sorted(case.expected_calls)),
        accounted_operations=tuple(sorted(measured.counts)),
        cleanup_verified=measured.cleanup_verified,
        residual_state=measured.residual_state,
        diagnostics=tuple(diagnostics),
        limitations=_LIMITATIONS,
        explicit_non_claims=_NON_CLAIMS,
    )


def _validate_cases(cases: tuple[ModularControlCase, ...], required: tuple[str, ...]) -> None:
    if any(type(case) is not ModularControlCase for case in cases):
        raise InvalidInputError("modular harness requires typed cases")
    if any(case.obligation not in required for case in cases):
        raise InvalidInputError("modular harness contains an unselected case")
    if len({case.name for case in cases}) != len(cases):
        raise InvalidInputError("modular case identities must be unique")
    for case in cases:
        _validate_case(case)


def _validate_case(case: ModularControlCase) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{0,95}", case.name):
        raise InvalidInputError("modular case identity must be a bounded safe identifier")
    if not isinstance(case.steps, tuple) or not 1 <= len(case.steps) <= 256:
        raise InvalidInputError("modular steps require a bounded nonempty tuple")
    if any(
        type(step) is not ModularControlStep or not isinstance(step.operation, ModularControlOperation)
        for step in case.steps
    ):
        raise InvalidInputError("modular steps require typed operation inputs")
    if not isinstance(case.options, Mapping) or not isinstance(case.expected_calls, Mapping):
        raise InvalidInputError("modular case configuration and counts require mappings")
    if any(type(value) is not int or value < 0 for value in case.expected_calls.values()):
        raise InvalidInputError("modular expected counts require nonnegative integers")


def _validate_subset(selected: tuple[str, ...], effects: tuple[str, ...], required: tuple[str, ...]) -> None:
    if not required or len(set(required)) != len(required):
        raise InvalidInputError("modular subset must be nonempty and unique")
    if set(selected) - set(modular_control_obligations()) or set(effects) - set(_effect_kinds()):
        raise InvalidInputError("modular subset contains an unknown obligation or effect")


def _obligation_cases(
    target: RuntimeTarget,
    obligation: str,
    supplied: tuple[ModularControlCase, ...],
    selected: tuple[str, ...],
    effects: tuple[str, ...],
    store_root: Path | None,
) -> tuple[ConformanceCaseResult, ...]:
    if obligation == "authored-recovery":
        from .modular_control_policy import authored_recovery_case

        return (authored_recovery_case(target, selected, effects),)
    matching = tuple(case for case in supplied if case.obligation == obligation)
    if not matching:
        return (_missing(obligation, selected, effects),)
    return tuple(_run_case(target, case, selected, effects, store_root) for case in matching)


def _supplied_cases(
    harness: ModularControlHarness | None, target: RuntimeTarget, required: tuple[str, ...]
) -> tuple[ModularControlCase, ...]:
    supplied = harness.cases(target) if harness is not None else ()
    if not isinstance(supplied, tuple) or len(supplied) > 256:
        raise InvalidInputError("modular harness requires a bounded case tuple")
    _validate_cases(supplied, required)
    return supplied


def run_modular_control_conformance(
    target: RuntimeTarget,
    *,
    harness: ModularControlHarness | None = None,
    obligations: tuple[str, ...] | None = None,
    effect_kinds: tuple[str, ...] = (),
    store_root: Path | None = None,
) -> BackendConformanceReport:
    """Execute the selected finite subset with no checkout or concrete backend dependency.

    Effects require one ``effect:<kind>`` case each. Missing coverage is a
    failure. No native certification is granted by this runtime runner.
    """

    selected = tuple(obligations) if obligations is not None else modular_control_obligations()
    effects = tuple(effect_kinds)
    required = (*selected, *("effect:" + kind for kind in effects))
    diagnostics = []
    cases: list[ConformanceCaseResult] = []
    subset_valid = False
    try:
        _validate_subset(selected, effects, required)
        subset_valid = True
        supplied = _supplied_cases(harness, target, required)
        for obligation in required:
            cases.extend(_obligation_cases(target, obligation, supplied, selected, effects, store_root))
    except Exception as exc:
        if not isinstance(exc, RaesError):
            # Isolation of the harness case supply: a refusal category needs no record.
            _LOGGER.exception("modular-control harness failed", exc_info=foreign_failure_record(exc))
        diagnostics.append(_diagnostic("conformance.modular-harness-invalid", _PROFILE, sanitized_failure_message(exc)))
        covered = {case.modular_control.obligation for case in cases}
        if subset_valid:
            cases.extend(_missing(item, selected, effects) for item in required if item not in covered)
    case_tuple = tuple(cases)
    digest = canonical_json_digest(
        [
            {
                "name": case.name,
                "obligation": case.modular_control.obligation,
                "probe": case.probe_digest,
            }
            for case in cases
        ]
    )
    claim = _bounded_conformance_claim(
        profile=_PROFILE, cases=case_tuple, left_carrier_ref=f"backend-target:{target.name}"
    ).model_copy(
        update={
            "subject": "Bounded modular-control runtime probes",
            "right_carrier_ref": "runtime-probe-suite:" + _PROFILE,
        }
    )
    return BackendConformanceReport(
        profile=_PROFILE,
        passed=bool(cases) and not diagnostics and all(case.passed for case in cases),
        claim=claim,
        cases=case_tuple,
        diagnostics=tuple(diagnostics),
        probe_set_digest=digest,
        contract_versions={
            key: canonical_json_digest(published_schema(key))
            for key in ("participant-control-selection-v2", "participant-control-evaluation-v2")
        },
    )

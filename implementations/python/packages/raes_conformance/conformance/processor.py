"""Finite processor checks through an explicitly supplied implementation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from typing import Protocol, cast

from raes import SDLParseError
from raes_backend_protocols.manifest import BackendManifest, backend_manifest_payload
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ProcessorManifestV2Model, SemanticProfileModel, schema_bundle
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import InvalidInputError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.plan_projection import evaluation_plan_model, orchestration_plan_model, provisioning_plan_model
from raes_contracts.semantic_profiles import load_semantic_profile
from raes_contracts.validation_profiles import ValidationProfileDefinitionModel, select_validation_profile
from raes_processor.reference import ReferenceProcessorResult

from .diagnostics import sanitized_failure_message
from .report import (
    BackendConformanceReport,
    ConformanceCaseResult,
    bounded_conformance_claim,
    conformance_tool_version,
    contract_content_digests,
)
from .validators import validate_contract_payload

_LOGGER = get_logger(__name__)
_PROFILE = "processor-compile-plan/v1"
_CHECKED_FEATURES = ("compilation", "planning")
_LIMIT = "Finite processor checks only; no full semantic-profile qualification or native backend execution."


class ProcessorConformanceTarget(Protocol):
    """Explicit installed implementation; no discovery or dynamic module loading."""

    def manifest_payload(self) -> dict[str, object]: ...

    def realize(self, scenario: str, backend_manifest: BackendManifest) -> ReferenceProcessorResult: ...


@dataclass(frozen=True)
class ProcessorConformanceProbe:
    """A selected finite input, with explicit refusal codes for semantic negatives.

    A negative with no codes requires an SDL parser refusal. An arbitrary
    operational exception never satisfies a negative expectation.
    """

    name: str
    source: str
    valid: bool = True
    expected_error_codes: tuple[str, ...] = ()
    expected_plan_addresses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", self.name):
            raise InvalidInputError("processor probe requires a bounded case identifier")
        if len(self.source.encode("utf-8")) > 1024 * 1024:
            raise InvalidInputError("processor probe exceeds the SDL input limit")


DEFAULT_PROCESSOR_PROBES = (
    ProcessorConformanceProbe(
        "valid-scenario",
        "name: conformance\nnodes:\n  vm:\n    type: compute\n    resources: {ram: 1 gib, cpu: 1}\n",
        expected_plan_addresses=("provision.node.vm",),
    ),
    ProcessorConformanceProbe("invalid-syntax", "name: [\n", valid=False),
)


def _diagnostic(code: str, message: str) -> Diagnostic:
    return Diagnostic(code, "conformance", "processor", message)


def _stage_diagnostics(result: ReferenceProcessorResult) -> tuple[Diagnostic, ...]:
    """Retain bounded codes and stage ownership without private values."""

    diagnostics: dict[tuple[str, str], Diagnostic] = {}
    stages = (
        ("compilation", result.runtime_model.diagnostics),
        ("planning", result.execution_plan.diagnostics),
        ("result", result.diagnostics),
    )
    stage_codes: set[str] = set()
    for stage, values in stages:
        for diagnostic in values:
            if stage == "result" and diagnostic.code in stage_codes:
                continue
            code = (
                diagnostic.code
                if re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", diagnostic.code) and len(diagnostic.code) <= 128
                else "conformance.processor-diagnostic"
            )
            diagnostics[(stage, code)] = Diagnostic(
                code,
                "processor",
                f"/processor/{stage}",
                (
                    "Processor returned a diagnostic. "
                    "Inspect that stage through the implementation's safe diagnostic interface."
                ),
                diagnostic.severity,
            )
            stage_codes.add(diagnostic.code)
    return tuple(diagnostics.values())


def _planning_diagnostics(
    result: ReferenceProcessorResult,
    probe: ProcessorConformanceProbe,
    backend_manifest: BackendManifest,
) -> tuple[Diagnostic, ...]:
    plan = result.execution_plan
    plans = (
        ("provisioning-plan-v1", provisioning_plan_model(plan.provisioning)),
        ("orchestration-plan-v1", orchestration_plan_model(plan.orchestration)),
        ("evaluation-plan-v1", evaluation_plan_model(plan.evaluation)),
    )
    diagnostics = [
        diagnostic
        for name, payload in plans
        for diagnostic in validate_contract_payload(name, payload.model_dump(mode="json"))
    ]
    addresses = {
        operation.address
        for part in (plan.provisioning, plan.orchestration, plan.evaluation)
        for operation in part.operations
    }
    if not set(probe.expected_plan_addresses) <= addresses:
        diagnostics.append(
            _diagnostic(
                "conformance.processor-plan-incomplete",
                "The plan omits an expected probe address. Repair planning coverage.",
            )
        )
    if canonical_json_digest(backend_manifest_payload(plan.manifest)) != canonical_json_digest(
        backend_manifest_payload(backend_manifest)
    ):
        diagnostics.append(
            _diagnostic(
                "conformance.processor-backend-mismatch",
                "The returned plan uses a different backend declaration.",
            )
        )
    return tuple(diagnostics)


def _positive_probe_result(
    result: ReferenceProcessorResult,
    probe: ProcessorConformanceProbe,
    feature: str,
    backend_manifest: BackendManifest,
    diagnostics: tuple[Diagnostic, ...],
) -> tuple[bool, tuple[Diagnostic, ...]]:
    compiled = not any(diagnostic.is_error for diagnostic in result.runtime_model.diagnostics)
    if feature == "planning":
        diagnostics += _planning_diagnostics(result, probe, backend_manifest)
        compiled = compiled and result.execution_plan.is_valid
    return compiled and not any(diagnostic.is_error for diagnostic in diagnostics), diagnostics


def _evaluate_probe(
    result: ReferenceProcessorResult,
    probe: ProcessorConformanceProbe,
    feature: str,
    backend_manifest: BackendManifest,
) -> tuple[bool, tuple[Diagnostic, ...]]:
    if not isinstance(result, ReferenceProcessorResult):
        raise InvalidInputError("processor must return its portable ReferenceProcessorResult")
    diagnostics = _stage_diagnostics(result)
    if feature == "compilation":
        diagnostics = tuple(item for item in diagnostics if item.address != "/processor/planning")
    if not probe.valid:
        observed = {item.code for item in result.runtime_model.diagnostics if item.is_error}
        return bool(probe.expected_error_codes) and set(probe.expected_error_codes) <= observed, diagnostics
    return _positive_probe_result(result, probe, feature, backend_manifest, diagnostics)


def _probe_case(
    processor: ProcessorConformanceTarget,
    backend_manifest: BackendManifest,
    probe: ProcessorConformanceProbe,
    feature: str,
    manifest: ProcessorManifestV2Model,
) -> ConformanceCaseResult:
    try:
        result = processor.realize(probe.source, backend_manifest)
        passed, diagnostics = _evaluate_probe(result, probe, feature, backend_manifest)
    except SDLParseError as exc:
        passed = not probe.valid and not probe.expected_error_codes
        diagnostics = (_diagnostic("conformance.processor-parse-refused", sanitized_failure_message(exc)),)
    except Exception as exc:
        _LOGGER.exception("processor conformance call failed", exc_info=foreign_failure_record(exc))
        passed = False
        diagnostics = (_diagnostic("conformance.processor-check-failed", sanitized_failure_message(exc)),)
    if not passed:
        diagnostics += (
            _diagnostic(
                "conformance.processor-check-failed",
                "The requested processor check did not meet its expectation. "
                "Repair the implementation or narrow its declaration.",
            ),
        )
    probe_digest = canonical_json_digest(asdict(probe))
    return ConformanceCaseResult(
        name=f"{probe.name}-{feature}",
        contract_name="processor-manifest-v2",
        valid=probe.valid,
        passed=passed,
        diagnostics=diagnostics,
        execution_basis="hermetic-live",
        probe_kind="processor",
        capability_feature=feature,
        declared_support_level="declared",
        evidence_origin="observed-execution",
        realization_owner="processor",
        manifest_digest=canonical_json_digest(manifest.model_dump(mode="json")),
        probe_digest=probe_digest,
        evidence_refs=(f"processor-probe:{probe.name}:{probe_digest}",),
        finite_scope="The selected SDL input and planning backend only.",
        limitations=(_LIMIT,),
        validation_strength="structural" if passed and probe.valid and feature == "planning" else None,
    )


def _load_manifest(
    processor: ProcessorConformanceTarget,
) -> tuple[ProcessorManifestV2Model | None, tuple[Diagnostic, ...]]:
    try:
        manifest = ProcessorManifestV2Model.model_validate(processor.manifest_payload())
    except Exception as exc:
        _LOGGER.exception("processor manifest validation failed", exc_info=foreign_failure_record(exc))
        return None, (_diagnostic("conformance.processor-manifest-invalid", sanitized_failure_message(exc)),)
    return manifest, ()


def _unsupported_feature(feature: str, declared: set[str], ordinal: int) -> ConformanceCaseResult:
    return ConformanceCaseResult(
        name=f"support-{ordinal}",
        contract_name="processor-manifest-v2",
        valid=True,
        passed=False,
        outcome="unsupported",
        capability_feature=feature,
        declared_support_level="declared" if feature in declared else "undeclared",
        limitations=("No behavioral check is available for this requested feature in this suite.",),
        diagnostics=(
            _diagnostic(
                "conformance.processor-feature-unverified",
                "Select an available and declared feature, or supply a governed specialist check.",
            ),
        ),
    )


def _feature_cases(
    processor: ProcessorConformanceTarget,
    backend_manifest: BackendManifest,
    manifest: ProcessorManifestV2Model,
    requested_features: tuple[str, ...],
    probes: tuple[ProcessorConformanceProbe, ...],
) -> tuple[list[ConformanceCaseResult], tuple[str, ...]]:
    cases = [
        ConformanceCaseResult(
            name="manifest",
            contract_name="processor-manifest-v2",
            valid=True,
            passed=True,
            validation_strength="structural",
            evidence_origin="declared",
        )
    ]
    declared = {feature.value for feature in manifest.capabilities.supported_features}
    gaps = []
    for feature in requested_features:
        if feature not in declared or feature not in _CHECKED_FEATURES:
            gaps.append(feature)
            cases.append(_unsupported_feature(feature, declared, len(cases)))
            continue
        cases.extend(
            _probe_case(processor, backend_manifest, probe, feature, manifest)
            for probe in probes
            if probe.valid or feature == "compilation"
        )
    return cases, tuple(gaps)


def _scope_diagnostics(
    profile: SemanticProfileModel,
    manifest: ProcessorManifestV2Model,
    probes: tuple[ProcessorConformanceProbe, ...],
) -> tuple[Diagnostic, ...]:
    diagnostics = []
    bindings = {(item.scope, item.family) for item in manifest.concept_bindings}
    if any((item.scope, item.family) not in bindings for item in profile.processing.required_bindings):
        diagnostics.append(
            _diagnostic(
                "conformance.processor-bindings-missing",
                "Declare the processing profile's required concept bindings.",
            )
        )
    if not any(probe.valid for probe in probes):
        diagnostics.append(
            _diagnostic(
                "conformance.processor-probes-missing",
                "Select at least one positive processor probe; absent execution cannot qualify support.",
            )
        )
    return tuple(diagnostics)


def _provenance(
    profile: SemanticProfileModel,
    validation: ValidationProfileDefinitionModel,
    features: tuple[str, ...],
    probes: tuple[ProcessorConformanceProbe, ...],
    configuration_digest: str,
) -> dict[str, object]:
    return {
        "requested_features": list(features),
        "selected_probes": [
            {"name": probe.name, "valid": probe.valid, "digest": canonical_json_digest(asdict(probe))}
            for probe in probes
        ],
        "semantic_profile": {
            "id": profile.profile_id,
            "version": profile.schema_version,
            "digest": canonical_json_digest(profile.model_dump(mode="json")),
        },
        "planning_backend_digest": configuration_digest,
        "validation_profile_reference": {
            "profile_id": validation.profile_id,
            "profile_version": validation.profile_version,
            "subject_kind": "published_claim",
        },
        "validation_profile_limitation": (
            "Reference for interpreting report checks; "
            "no validation disclosure or report-wide achieved strength is asserted."
        ),
    }


def _validate_selection(requested_features: tuple[str, ...], probes: tuple[ProcessorConformanceProbe, ...]) -> None:
    if len({probe.name for probe in probes}) != len(probes):
        raise InvalidInputError("processor probe identities must be unique")
    if not requested_features or len(set(requested_features)) != len(requested_features):
        raise InvalidInputError("processor feature selection must be nonempty and unique")


def _passed(
    cases: tuple[ConformanceCaseResult, ...], diagnostics: tuple[Diagnostic, ...], contract_gaps: tuple[str, ...]
) -> bool:
    return bool(cases) and not diagnostics and not contract_gaps and all(case.passed for case in cases)


def run_processor_conformance(
    processor: ProcessorConformanceTarget,
    *,
    backend_manifest: BackendManifest,
    requested_features: tuple[str, ...] = _CHECKED_FEATURES,
    probes: tuple[ProcessorConformanceProbe, ...] = DEFAULT_PROCESSOR_PROBES,
) -> BackendConformanceReport:
    """Check the named finite suite, without qualifying the full semantic profile.

    The installed processor and backend manifest are trusted caller selections.
    The backend is used for planning only. Unknown and unchecked requested
    features remain unsupported by this suite, regardless of manifest claims.
    """
    _validate_selection(requested_features, probes)
    profile = load_semantic_profile("reference-stack-v1")
    validation = select_validation_profile("raes-structural-validation", "v1", subject_kind="published_claim")
    bundle = schema_bundle()
    required = profile.processing.required_contracts
    manifest, diagnostics = _load_manifest(processor)
    cases: list[ConformanceCaseResult] = []
    contract_gaps: tuple[str, ...] = ()
    capability_gaps: tuple[str, ...] = ()
    if manifest is not None:
        contract_gaps = tuple(sorted(set(required) - set(manifest.supported_contract_versions)))
        cases, capability_gaps = _feature_cases(processor, backend_manifest, manifest, requested_features, probes)
        diagnostics += _scope_diagnostics(profile, manifest, probes)
    configuration_digest = canonical_json_digest(backend_manifest_payload(backend_manifest))
    case_tuple = tuple(
        cast(ConformanceCaseResult, replace(case, configuration_digest=configuration_digest)) for case in cases
    )
    suite = {"suite": _PROFILE, "features": requested_features, "probes": [asdict(probe) for probe in probes]}
    return BackendConformanceReport(
        profile=_PROFILE,
        passed=_passed(case_tuple, diagnostics, contract_gaps),
        claim=bounded_conformance_claim(
            profile=_PROFILE,
            cases=case_tuple,
            left_carrier_ref="processor-conformance:selected-implementation",
            right_carrier_ref=f"processor-suite:{_PROFILE}",
            subject="Finite processor compile and plan conformance",
            evidence_boundary=(
                "Only the selected processor inputs, requested features, and planning backend. "
                "No full semantic profile or native backend qualification."
            ),
        ),
        cases=case_tuple,
        diagnostics=diagnostics,
        subject_kind="processor",
        subject_name=manifest.identity.name if manifest else None,
        subject_version=manifest.identity.version if manifest else None,
        profile_version="v1",
        profile_digest=canonical_json_digest(suite),
        tool_version=conformance_tool_version(),
        contract_versions={name: name for name in required},
        contract_digests=contract_content_digests({name: bundle[name] for name in required}),
        unsupported_contract_gaps=contract_gaps,
        unsupported_capability_gaps=capability_gaps,
        required_case_refs=tuple(f"conformance-case:{case.contract_name}:{case.name}" for case in case_tuple),
        provenance=_provenance(profile, validation, requested_features, probes, configuration_digest),
    )

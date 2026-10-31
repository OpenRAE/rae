"""Finite processor checks through an explicitly supplied implementation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from typing import Protocol

from raes import SDLParseError
from raes_backend_protocols.manifest import BackendManifest, backend_manifest_payload
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ProcessorManifestV2Model, schema_bundle
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import InvalidInputError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.plan_projection import evaluation_plan_model, orchestration_plan_model, provisioning_plan_model
from raes_contracts.semantic_profiles import load_semantic_profile
from raes_contracts.validation_profiles import select_validation_profile
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
                "Processor returned a diagnostic. Inspect that stage through the implementation's safe diagnostic interface.",
                diagnostic.severity,
            )
            stage_codes.add(diagnostic.code)
    return tuple(diagnostics.values())


def _probe_case(
    processor: ProcessorConformanceTarget,
    backend_manifest: BackendManifest,
    probe: ProcessorConformanceProbe,
    feature: str,
    manifest: ProcessorManifestV2Model,
) -> ConformanceCaseResult:
    diagnostics: tuple[Diagnostic, ...] = ()
    passed = False
    try:
        result = processor.realize(probe.source, backend_manifest)
        if not isinstance(result, ReferenceProcessorResult):
            raise InvalidInputError("processor must return its portable ReferenceProcessorResult")
        diagnostics = _stage_diagnostics(result)
        if feature == "compilation":
            diagnostics = tuple(diag for diag in diagnostics if diag.address != "/processor/planning")
        if probe.valid:
            passed = not any(diag.is_error for diag in result.runtime_model.diagnostics) and not any(
                diag.is_error for diag in diagnostics
            )
            if feature == "planning":
                passed = passed and result.execution_plan.is_valid
                plans = (
                    ("provisioning-plan-v1", provisioning_plan_model(result.execution_plan.provisioning)),
                    ("orchestration-plan-v1", orchestration_plan_model(result.execution_plan.orchestration)),
                    ("evaluation-plan-v1", evaluation_plan_model(result.execution_plan.evaluation)),
                )
                diagnostics += tuple(
                    diag
                    for name, plan in plans
                    for diag in validate_contract_payload(name, plan.model_dump(mode="json"))
                )
                addresses = {
                    operation.address
                    for plan in (
                        result.execution_plan.provisioning,
                        result.execution_plan.orchestration,
                        result.execution_plan.evaluation,
                    )
                    for operation in plan.operations
                }
                if not set(probe.expected_plan_addresses) <= addresses:
                    diagnostics += (
                        _diagnostic(
                            "conformance.processor-plan-incomplete",
                            "The plan omits an expected probe address. Repair planning coverage.",
                        ),
                    )
                if canonical_json_digest(
                    backend_manifest_payload(result.execution_plan.manifest)
                ) != canonical_json_digest(backend_manifest_payload(backend_manifest)):
                    diagnostics += (
                        _diagnostic(
                            "conformance.processor-backend-mismatch",
                            "The returned plan uses a different backend declaration.",
                        ),
                    )
                passed = passed and not any(diag.is_error for diag in diagnostics)
        else:
            observed = {diag.code for diag in result.runtime_model.diagnostics if diag.is_error}
            passed = bool(probe.expected_error_codes) and set(probe.expected_error_codes) <= observed
    except SDLParseError as exc:
        passed = not probe.valid and not probe.expected_error_codes
        diagnostics = (_diagnostic("conformance.processor-parse-refused", sanitized_failure_message(exc)),)
    except Exception as exc:
        # This isolates an explicitly installed implementation, like the specialist harness boundaries.
        _LOGGER.exception("processor conformance call failed", exc_info=foreign_failure_record(exc))
        diagnostics = (_diagnostic("conformance.processor-check-failed", sanitized_failure_message(exc)),)
    if not passed:
        diagnostics += (
            _diagnostic(
                "conformance.processor-check-failed",
                "The requested processor check did not meet its expectation. Repair the implementation or narrow its declaration.",
            ),
        )
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
        probe_digest=canonical_json_digest(asdict(probe)),
        evidence_refs=(f"processor-probe:{probe.name}:{canonical_json_digest(asdict(probe))}",),
        finite_scope="The selected SDL input and planning backend only.",
        limitations=(_LIMIT,),
        validation_strength="structural" if passed and probe.valid and feature == "planning" else None,
    )


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

    if len({probe.name for probe in probes}) != len(probes):
        raise InvalidInputError("processor probe identities must be unique")
    if not requested_features or len(set(requested_features)) != len(requested_features):
        raise InvalidInputError("processor feature selection must be nonempty and unique")
    profile = load_semantic_profile("reference-stack-v1")
    validation_profile = select_validation_profile("raes-structural-validation", "v1", subject_kind="published_claim")
    bundle = schema_bundle()
    required = profile.processing.required_contracts
    cases: list[ConformanceCaseResult] = []
    diagnostics: list[Diagnostic] = []
    contract_gaps: tuple[str, ...] = ()
    capability_gaps: list[str] = []
    manifest: ProcessorManifestV2Model | None = None
    try:
        manifest = ProcessorManifestV2Model.model_validate(processor.manifest_payload())
    except Exception as exc:
        _LOGGER.exception("processor manifest validation failed", exc_info=foreign_failure_record(exc))
        diagnostics.append(_diagnostic("conformance.processor-manifest-invalid", sanitized_failure_message(exc)))
    if manifest is not None:
        contract_gaps = tuple(sorted(set(required) - set(manifest.supported_contract_versions)))
        bindings = {(item.scope, item.family) for item in manifest.concept_bindings}
        if any((item.scope, item.family) not in bindings for item in profile.processing.required_bindings):
            diagnostics.append(
                _diagnostic(
                    "conformance.processor-bindings-missing",
                    "Declare the processing profile's required concept bindings.",
                )
            )
        cases.append(
            ConformanceCaseResult(
                name="manifest",
                contract_name="processor-manifest-v2",
                valid=True,
                passed=True,
                validation_strength="structural",
                evidence_origin="declared",
            )
        )
        declared = {feature.value for feature in manifest.capabilities.supported_features}
        for feature in requested_features:
            if feature not in declared or feature not in _CHECKED_FEATURES:
                capability_gaps.append(feature)
                cases.append(
                    ConformanceCaseResult(
                        name="support-" + str(len(cases)),
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
                )
                continue
            cases.extend(
                _probe_case(processor, backend_manifest, probe, feature, manifest)
                for probe in probes
                if probe.valid or feature == "compilation"
            )
        if not any(probe.valid for probe in probes):
            diagnostics.append(
                _diagnostic(
                    "conformance.processor-probes-missing",
                    "Select at least one positive processor probe; absent execution cannot qualify support.",
                )
            )
    case_tuple = tuple(cases)
    pins = contract_content_digests({name: bundle[name] for name in required})
    suite = {"suite": _PROFILE, "features": requested_features, "probes": [asdict(probe) for probe in probes]}
    configuration_digest = canonical_json_digest(backend_manifest_payload(backend_manifest))
    case_tuple = tuple(replace(case, configuration_digest=configuration_digest) for case in case_tuple)
    return BackendConformanceReport(
        profile=_PROFILE,
        passed=bool(case_tuple) and not diagnostics and not contract_gaps and all(case.passed for case in case_tuple),
        claim=bounded_conformance_claim(
            profile=_PROFILE,
            cases=case_tuple,
            left_carrier_ref="processor-conformance:selected-implementation",
            right_carrier_ref=f"processor-suite:{_PROFILE}",
            subject="Finite processor compile and plan conformance",
            evidence_boundary="Only the selected processor inputs, requested features, and planning backend. No full semantic profile or native backend qualification.",
        ),
        cases=case_tuple,
        diagnostics=tuple(diagnostics),
        subject_kind="processor",
        subject_name=manifest.identity.name if manifest else None,
        subject_version=manifest.identity.version if manifest else None,
        profile_version="v1",
        profile_digest=canonical_json_digest(suite),
        tool_version=conformance_tool_version(),
        contract_versions={name: name for name in required},
        contract_digests=pins,
        unsupported_contract_gaps=contract_gaps,
        unsupported_capability_gaps=tuple(capability_gaps),
        required_case_refs=tuple(f"conformance-case:{case.contract_name}:{case.name}" for case in case_tuple),
        provenance={
            "requested_features": list(requested_features),
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
                "profile_id": validation_profile.profile_id,
                "profile_version": validation_profile.profile_version,
                "subject_kind": "published_claim",
            },
            "validation_profile_limitation": "Reference for interpreting report checks; no validation disclosure or report-wide achieved strength is asserted.",
        },
    )

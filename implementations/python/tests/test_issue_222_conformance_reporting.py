"""ASR-526: one honest result for machine and human consumers."""

import json
from dataclasses import replace

import pytest
from raes_conformance.conformance import report as reports
from raes_contracts.diagnostics import Diagnostic


def report_for(*cases, **changes):
    profile = "test-suite/v1"
    report = reports.BackendConformanceReport(
        profile=profile,
        passed=bool(cases) and all(case.passed for case in cases),
        claim=reports._bounded_conformance_claim(profile=profile, cases=cases, left_carrier_ref="test:subject"),
        cases=cases,
    )
    return replace(report, **changes)


def case_for(name="positive", **changes):
    return reports.ConformanceCaseResult(name=name, contract_name="test-v1", valid=True, passed=True, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"unsupported_contract_gaps": ("required-v1",)},
        {"unsupported_capability_gaps": ("planning",)},
        {"diagnostics": (Diagnostic("test.failed", "conformance", "test", "Repair the required check."),)},
    ],
)
def test_passing_report_cannot_hide_required_gaps_or_top_level_errors(changes):
    with pytest.raises(ValueError):
        reports.backend_conformance_report_payload(report_for(case_for(), **changes))


def test_duplicate_case_identity_cannot_satisfy_coverage():
    case = case_for()
    with pytest.raises(ValueError, match="duplicate"):
        reports.backend_conformance_report_payload(report_for(case, case))


def test_failed_report_cannot_keep_a_native_qualification():
    case = replace(case_for(execution_basis="native-live"), passed=False, outcome="failed")
    with pytest.raises(ValueError, match="native"):
        reports.backend_conformance_report_payload(report_for(case, native_conformance=True))


def test_expected_rejection_is_a_pass_and_retains_its_diagnostic():
    case = replace(case_for(), valid=False, diagnostics=(Diagnostic("test.rejected", "conformance", "x", "Rejected."),))
    payload = reports.backend_conformance_report_payload(report_for(case))
    assert payload["summary"]["checks"] == {"passed": 1, "failed": 0, "unsupported": 0}
    assert payload["summary"]["achieved_profile"] == payload["profile"]
    assert payload["cases"][0]["diagnostics"][0]["code"] == "test.rejected"
    assert payload["summary"]["validation_basis"]["execution_bases"] == ["fixture-only"]
    assert payload["native_conformance"] is False


def test_omitted_required_check_is_reported_without_achievement():
    case = case_for()
    required = ("conformance-case:test-v1:positive", "conformance-case:test-v1:absent")
    report = report_for(case, passed=False, required_case_refs=required)
    payload = reports.backend_conformance_report_payload(report)
    assert payload["summary"]["missing_checks"] == [required[1]]
    assert payload["summary"]["achieved_profile"] is None
    with pytest.raises(ValueError, match="required"):
        reports.backend_conformance_report_payload(replace(report, passed=True))


def test_human_view_preserves_support_gaps_limits_and_escapes_controls():
    from raes_conformance.conformance.report_text import backend_conformance_report_text

    case = replace(
        case_for("unsafe\x1b[2J"),
        passed=False,
        outcome="unsupported",
        capability_feature="planning",
        declared_support_level="exact",
        effective_support_level="bounded",
        limitations=("Only the selected cases.",),
        evidence_refs=("evidence:original/v1",),
    )
    report = report_for(case, unsupported_capability_gaps=("planning",))
    payload = reports.backend_conformance_report_payload(report)
    text = backend_conformance_report_text(report)
    assert payload["summary"]["support"][0]["observed"] is None
    for value in (
        "unsupported",
        "planning",
        "exact",
        "bounded",
        "Only the selected cases.",
        "evidence:original/v1",
        "fixture-only",
    ):
        assert value in text
    assert "\x1b" not in text
    assert "\\u001b" in text
    assert "achieved: none" in text
    assert json.dumps(payload)


def test_empty_valid_fixture_directory_is_incomplete(tmp_path):
    from raes_conformance.conformance import run_fixture_suite

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "minimal.json").write_text(
        json.dumps(
            {
                "schema_version": "backend-profile/v1",
                "profile": "minimal",
                "required_contracts": ["backend-manifest-v2"],
            }
        )
    )
    (tmp_path / "fixtures" / "backend-manifest-v2" / "valid").mkdir(parents=True)
    report = run_fixture_suite(profile="minimal", root=tmp_path / "fixtures", profiles_root=profiles)
    assert not report.passed
    assert any(diag.code == "conformance.fixture-missing" for diag in report.diagnostics)


def processor_report(processor=None, **options):
    from raes_backend_stubs.manifest import create_stub_manifest
    from raes_conformance.conformance.processor import run_processor_conformance
    from raes_processor.reference import ReferenceProcessor

    return run_processor_conformance(
        processor or ReferenceProcessor(), backend_manifest=create_stub_manifest(), **options
    )


def test_processor_reports_actual_checks_versions_and_bounded_evidence():
    report = processor_report()
    payload = reports.backend_conformance_report_payload(report)
    assert report.passed
    assert payload["subject_kind"] == "processor"
    assert payload["subject_name"] == "raes-reference-processor"
    assert payload["subject_version"]
    assert payload["profile"] == "processor-compile-plan/v1"
    assert payload["profile_version"] == "v1"
    assert payload["provenance"]["semantic_profile"]["version"] == "semantic-profile/v1"
    assert payload["profile_digest"].startswith("sha256:")
    assert payload["tool_version"]
    assert payload["contract_digests"]["processor-manifest-v2"].startswith("sha256:")
    assert report.required_case_refs
    assert report.claim.quantifier_scope == "finite-cases"
    assert not report.native_conformance
    observed = [row for row in payload["summary"]["support"] if row["observed"] == "passed"]
    assert {row["feature"] for row in observed} == {"compilation", "planning"}
    assert all(
        case.manifest_digest and case.probe_digest
        for case in report.cases
        if case.evidence_origin == "observed-execution"
    )


@pytest.mark.parametrize("features", [("runtime-control-plane",), ("unregistered-feature",)])
def test_processor_unsupported_request_never_achieves_a_profile(features):
    payload = reports.backend_conformance_report_payload(processor_report(requested_features=features))
    assert not payload["passed"]
    assert payload["summary"]["achieved_profile"] is None
    assert payload["summary"]["checks"]["unsupported"]
    assert payload["unsupported_capability_gaps"]


def test_processor_missing_probes_remain_incomplete():
    payload = reports.backend_conformance_report_payload(processor_report(probes=()))
    assert not payload["passed"]
    assert payload["summary"]["achieved_profile"] is None
    assert any(diag["code"] == "conformance.processor-probes-missing" for diag in payload["diagnostics"])


def test_false_processor_support_and_unrelated_negative_failure_are_not_passes():
    from raes_processor.reference import ReferenceProcessor

    class BrokenProcessor(ReferenceProcessor):
        @staticmethod
        def realize(*args, **kwargs):
            raise RuntimeError("SECRET-provider-error")

    payload = reports.backend_conformance_report_payload(processor_report(BrokenProcessor()))
    assert not payload["passed"]
    assert "SECRET-provider-error" not in json.dumps(payload)
    assert all(case["outcome"] == "failed" for case in payload["cases"] if case["probe_kind"] == "processor")
    support = payload["summary"]["support"]
    assert any(row["declared"] == "declared" and row["observed"] == "failed" for row in support)


def test_processor_manifest_failure_stays_structured_and_does_not_execute():
    class InvalidProcessor:
        def manifest_payload(self):
            return {"identity": {"SECRET-key": "SECRET-value"}}

        def realize(self, *args, **kwargs):
            pytest.fail("an invalid declaration must not execute")

    payload = reports.backend_conformance_report_payload(processor_report(InvalidProcessor()))
    assert not payload["passed"]
    assert payload["subject_kind"] == "processor"
    assert payload["summary"]["achieved_profile"] is None
    assert "SECRET" not in json.dumps(payload)


def test_default_processor_probe_detects_a_canned_empty_plan():
    from raes_processor.reference import ReferenceProcessor

    class EmptyPlanProcessor(ReferenceProcessor):
        @staticmethod
        def realize(source, backend_manifest):
            if source == "name: [\n":
                return ReferenceProcessor.realize(source, backend_manifest)
            return ReferenceProcessor.realize("name: conformance\n", backend_manifest)

    report = processor_report(EmptyPlanProcessor())
    assert not report.passed
    assert any(case.capability_feature == "planning" and not case.passed for case in report.cases)


def test_backend_fixture_report_binds_profile_contracts_and_fixture_provenance():
    from raes_conformance.conformance import run_fixture_suite

    payload = reports.backend_conformance_report_payload(run_fixture_suite(profile="provisioning-only"))
    assert payload["profile_version"] == "backend-profile/v1"
    assert payload["profile_digest"].startswith("sha256:")
    assert payload["tool_version"]
    assert payload["contract_digests"]["backend-manifest-v2"].startswith("sha256:")
    assert payload["provenance"]["fixture_origin"] == "unknown"
    assert all(case["evidence_origin"] is None for case in payload["cases"])
    assert all(case["probe_digest"] and case["evidence_refs"] for case in payload["cases"])


def test_a_mixed_native_and_hermetic_report_cannot_claim_native_qualification():
    native = case_for("native", execution_basis="native-live")
    hermetic = case_for("hermetic", execution_basis="hermetic-live")
    with pytest.raises(ValueError, match="native"):
        reports.backend_conformance_report_payload(report_for(native, hermetic, native_conformance=True))


def test_specialist_unsupported_combinations_keep_their_exact_evidence(tmp_path):
    from mixed_conformance_harness import PortableHarness
    from raes_conformance.conformance import run_mixed_backend_conformance
    from raes_conformance.conformance.mixed_backend_types import mixed_case_binding_payload
    from raes_conformance.conformance.report_text import backend_conformance_report_text

    report = run_mixed_backend_conformance(
        PortableHarness(tmp_path),
        cases=("combination-reusable-control-with-mixed-runtime", "combination-distributed-portable-mixed"),
    )
    payload = reports.backend_conformance_report_payload(report)
    text = backend_conformance_report_text(report)
    assert not payload["passed"]
    assert payload["summary"]["checks"]["unsupported"] == 2
    assert "achieved: none" in text
    for original, projected in zip(report.cases, payload["cases"], strict=True):
        assert projected["mixed_binding"] == mixed_case_binding_payload(original.mixed_binding)
        assert original.name in text
        for limitation in original.limitations:
            assert limitation in text


def test_partial_declared_support_does_not_become_observed_support():
    case = case_for(
        capability_feature="tool_affordances", declared_support_level="bounded", effective_support_level="bounded"
    )
    payload = reports.backend_conformance_report_payload(report_for(case))
    assert payload["summary"]["support"][0]["declared"] == "bounded"
    assert payload["summary"]["support"][0]["observed"] is None


def test_processor_keeps_stage_codes_without_private_diagnostic_values():
    from raes_processor.reference import ReferenceProcessor

    class DiagnosticProcessor(ReferenceProcessor):
        @staticmethod
        def realize(source, backend_manifest):
            result = ReferenceProcessor.realize(source, backend_manifest)
            diagnostic = Diagnostic("processor.test-failed", "processor", "SECRET-address", "SECRET-message")
            result.runtime_model.diagnostics.append(diagnostic)
            return replace(result, diagnostics=(diagnostic,))

    payload = reports.backend_conformance_report_payload(processor_report(DiagnosticProcessor()))
    assert not payload["passed"]
    assert "SECRET" not in json.dumps(payload)
    stage = [
        diag for case in payload["cases"] for diag in case["diagnostics"] if diag["code"] == "processor.test-failed"
    ]
    assert stage
    assert all(diag["address"] == "/processor/compilation" for diag in stage)


def test_compilation_only_success_is_independent_of_planning_refusal():
    from raes_processor.reference import ReferenceProcessor

    class PlanningRefusedProcessor(ReferenceProcessor):
        @staticmethod
        def realize(source, backend_manifest):
            result = ReferenceProcessor.realize(source, backend_manifest)
            diagnostic = Diagnostic(
                "provisioner.unsupported-node-type",
                "provisioner",
                "provision.node.vm",
                "This backend cannot plan compute nodes.",
            )
            result.execution_plan.diagnostics.append(diagnostic)
            return replace(result, diagnostics=(*result.diagnostics, diagnostic))

    compilation = processor_report(PlanningRefusedProcessor(), requested_features=("compilation",))
    assert compilation.passed
    assert all(case.passed for case in compilation.cases)
    assert all(diag.address != "/processor/planning" for case in compilation.cases for diag in case.diagnostics)
    planning = processor_report(PlanningRefusedProcessor(), requested_features=("planning",))
    assert not planning.passed
    assert any(diag.code == "provisioner.unsupported-node-type" for case in planning.cases for diag in case.diagnostics)


def test_text_preserves_cleanup_and_residual_state_without_terminal_controls():
    from raes_conformance.conformance.report_text import backend_conformance_report_text

    case = replace(
        case_for(),
        passed=False,
        outcome="failed",
        cleanup_verified=False,
        residual_state=("owned-resource:abc\x1b[2J",),
    )
    report = report_for(case)
    payload = reports.backend_conformance_report_payload(report)
    text = backend_conformance_report_text(report)
    assert payload["cases"][0]["cleanup_verified"] is False
    assert "cleanup verified: false" in text
    assert "owned-resource:abc\\u001b[2J" in text
    assert "\x1b" not in text


def test_native_label_without_bound_observations_is_rejected():
    native = case_for(execution_basis="native-live")
    with pytest.raises(ValueError, match="native.*evidence"):
        reports.backend_conformance_report_payload(report_for(native, native_conformance=True))


def test_compilation_negative_cannot_borrow_a_planning_refusal():
    from raes_conformance.conformance import ProcessorConformanceProbe
    from raes_processor.reference import ReferenceProcessor

    class PlanningRefusedProcessor(ReferenceProcessor):
        @staticmethod
        def realize(source, backend_manifest):
            result = ReferenceProcessor.realize(source, backend_manifest)
            diagnostic = Diagnostic("provisioner.unsupported-node-type", "provisioner", "x", "Planning refused.")
            result.execution_plan.diagnostics.append(diagnostic)
            return replace(result, diagnostics=(diagnostic,))

    probe = ProcessorConformanceProbe(
        "negative", "name: conformance\n", valid=False, expected_error_codes=("provisioner.unsupported-node-type",)
    )
    report = processor_report(PlanningRefusedProcessor(), requested_features=("compilation",), probes=(probe,))
    negative = next(case for case in report.cases if case.name == "negative-compilation")
    assert not negative.passed


def test_failed_target_report_preserves_known_subject_identity(tmp_path):
    from raes_backend_stubs.stubs import create_stub_target
    from raes_conformance.conformance import run_target_conformance

    target = create_stub_target()
    report = run_target_conformance(target, profile="missing-profile", profiles_root=tmp_path)
    assert not report.passed
    assert report.subject_name == target.manifest.name
    assert report.subject_version == target.manifest.version
    assert report.profile == "missing-profile"

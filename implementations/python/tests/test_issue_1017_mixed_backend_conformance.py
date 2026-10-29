"""Executable mixed-backend conformance probes (issue #1017)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from mixed_conformance_harness import ENVIRONMENT, Dispatcher, PortableHarness
from raes_conformance.conformance import (
    MIXED_BACKEND_CASES,
    MixedBackendCondition,
    backend_conformance_report_payload,
    run_mixed_backend_conformance,
)
from raes_conformance.conformance.report import _bounded_conformance_claim, validate_backend_conformance_report
from test_issue_1371_mixed_backend_contracts import _binding, _time_model, _time_state


@pytest.mark.parametrize(
    ("source", "destination", "expected"),
    [
        ((0, 4, 0), (0, 4, 1), "ordered"),
        ((0, 4, 0), (0, 4, 0), "ordered"),
        ((0, 5, 0), (0, 4, 1), "incomparable"),
        ((0, 4, 0), (1, 9, 0), "incomparable"),
    ],
)
def test_time_comparison_is_the_contract_owners_mapped_order(source, destination, expected):
    from raes_contracts.contracts import mixed_backend_time_comparison

    state = _time_state(source, destination)
    required = _binding().subject.time
    comparison = mixed_backend_time_comparison(
        required,
        _time_model(),
        state.clocks[required.source_clock_address].coordinate,
        state.clocks[required.destination_clock_address].coordinate,
    )
    assert comparison == expected


def test_time_comparison_applies_an_affine_mapping_exactly():
    from raes_contracts.contracts import mixed_backend_time_comparison

    model = _time_model()
    fields = model.model_dump(mode="python")
    mapping = next(iter(fields["mappings"].values()))
    mapping.update(mapping_kind="affine_rational", scale={"numerator": 2, "denominator": 1})
    affine = type(model).model_validate(fields)
    required = _binding().subject.time
    state = _time_state((0, 2, 0), (0, 3, 1), declaration=affine)
    source = state.clocks[required.source_clock_address].coordinate
    destination = state.clocks[required.destination_clock_address].coordinate

    # Identity would order tick 2 before tick 3; the admitted mapping yields 4.
    assert mixed_backend_time_comparison(required, affine, source, destination) == "incomparable"
    assert mixed_backend_time_comparison(required, model, source, destination) == "ordered"


# --- Runner-owned probe family -------------------------------------------------

COMBINATIONS = ("combination-reusable-control-with-mixed-runtime", "combination-distributed-portable-mixed")


@pytest.fixture(scope="module")
def healthy(tmp_path_factory):
    harness = PortableHarness(tmp_path_factory.mktemp("mixed"), dispatcher=Dispatcher())
    return harness, run_mixed_backend_conformance(harness)


def _case(report, name):
    return next(case for case in report.cases if case.name == name)


def test_every_supported_case_passes_and_combinations_stay_unsupported(healthy):
    _, report = healthy
    outcomes = {case.name: case.outcome for case in report.cases}

    assert list(outcomes) == [case.case_id for case in MIXED_BACKEND_CASES]
    assert {name for name, outcome in outcomes.items() if outcome != "passed"} == set(COMBINATIONS)
    assert all(outcomes[name] == "unsupported" for name in COMBINATIONS)
    assert report.unsupported_capability_gaps == COMBINATIONS
    assert not report.passed
    assert not report.native_conformance
    codes = {diagnostic.code for name in COMBINATIONS for diagnostic in _case(report, name).diagnostics}
    assert codes == {"conformance.mixed-combination-unsupported"}


def test_cases_carry_exact_coordinates_and_runtime_attributed_evidence(healthy):
    from raes_contracts.contracts import mixed_backend_binding_reference

    harness, report = healthy
    case = _case(report, "edge-executes")
    coordinates = case.mixed_binding
    declaration = next(item.declaration for item in harness.composed if item.declaration.subject.kind == "edge")
    subject = declaration.subject

    assert (case.execution_basis, case.realization_owner, case.evidence_origin) == (
        "hermetic-live",
        "installed-service",
        "observed-execution",
    )
    assert {item.component_id for item in coordinates.components} == {"sim", "emu"}
    assert all(item.manifest_digest.startswith("sha256:") for item in coordinates.components)
    assert all(item.envelope_digest for item in coordinates.components)
    assert [item.role for item in coordinates.services] == [
        "coordinator",
        "bridge",
        "delivery-reader",
        "observation-reader",
    ]
    assert [(item.kind, item.producer_ref) for item in coordinates.evidence] == [
        ("time-grant", subject.time.coordinator.service_ref),
        ("execution", subject.bridge.service_ref),
        ("delivery", subject.delivery_reader.service_ref),
        ("observation", subject.observation_reader.service_ref),
    ]
    assert coordinates.binding_digest == mixed_backend_binding_reference(declaration).digest
    assert coordinates.mapping_loss_ref == subject.mapping_loss.limitation_ref
    assert (coordinates.expected_state, coordinates.observed_state) == ("succeeded", "succeeded")
    assert case.configuration_digest
    assert case.tool_digest
    assert case.environment_digest == ENVIRONMENT
    assert {"coordinator.grant=1", "bridge.start_operation=1"} <= set(case.accounted_operations)
    assert case.accounted_operations == case.expected_operations
    payload = backend_conformance_report_payload(report)
    rendered = next(item for item in payload["cases"] if item["name"] == "edge-executes")
    assert rendered["mixed_binding"]["evidence"][0]["kind"] == "time-grant"
    json.dumps(payload)


def test_handoff_and_control_cases_record_their_own_facts(healthy):
    _, report = healthy
    handoff = _case(report, "handoff-repeated-transition")
    control = _case(report, "control-repeated-cycles")

    assert [item.kind for item in handoff.mixed_binding.evidence] == ["time-grant", "handoff", "owner-readback"]
    assert {"coordinator.grant=2", "transfer.start_operation=2"} <= set(handoff.accounted_operations)
    statuses = [item.status for item in control.mixed_binding.evidence]
    assert statuses == ["accepted"] * 4 + ["rejected"]
    assert control.accounted_operations == ("participant-runtime.admit_action=1",)
    refused = _case(report, "control-dispatch-refused")
    assert refused.passed
    assert refused.mixed_binding.condition == "dispatch-refused"


def test_each_case_requests_its_own_configuration(healthy):
    harness, _ = healthy
    collections = [request.collection_id for request in harness.requests]

    assert len(collections) == len(set(collections))
    assert {request.case_id for request in harness.requests} == {case.case_id for case in MIXED_BACKEND_CASES}
    restarts = [request for request in harness.requests if request.restart_of is not None]
    assert [request.case_id for request in restarts] == ["edge-restart-no-reissue"]


def test_a_selected_case_runs_and_passes_alone(tmp_path):
    report = run_mixed_backend_conformance(PortableHarness(tmp_path), cases=["handoff-commits"])

    assert report.passed
    assert [case.name for case in report.cases] == ["handoff-commits"]
    validate_backend_conformance_report(report)


@pytest.mark.parametrize("cases", [[], ["edge-unknown"]])
def test_selection_must_name_known_cases(tmp_path, cases):
    harness = PortableHarness(tmp_path)

    with pytest.raises(ValueError, match="mixed-backend"):
        run_mixed_backend_conformance(harness, cases=cases)


def test_harness_environment_digest_is_required(tmp_path):
    harness = PortableHarness(tmp_path)
    harness.environment_digest = "environment:unbound"

    with pytest.raises(ValueError, match="environment digest"):
        run_mixed_backend_conformance(harness, cases=["edge-executes"])


# --- Backends that only claim the capability ----------------------------------


def _constant_order(configured, request):
    coordinator = configured.roles["coordinator"]
    original = coordinator.grant

    def grant(operation_request, time_state):
        report = original(operation_request, time_state)
        return report.model_copy(update={"stage": report.stage.model_copy(update={"comparison": "ordered"})})

    coordinator.grant = grant


def _canned_delivery(configured, request):
    reader = configured.roles["delivery"]
    original = reader.read_stage

    def read_stage(control):
        missing, configured.state.missing_delivery = configured.state.missing_delivery, False
        try:
            return original(control)
        finally:
            configured.state.missing_delivery = missing

    reader.read_stage = read_stage


def _rewritten_status(configured, request, old, new):
    bridge = configured.roles["bridge"]
    original = bridge.stage_reports

    def stage_reports(control):
        reports = original(control)
        return tuple(
            report.model_copy(update={"stage": report.stage.model_copy(update={"status": new})})
            if report.stage.status == old
            else report
            for report in reports
        )

    bridge.stage_reports = stage_reports


def _hidden_partial(configured, request):
    _rewritten_status(configured, request, "partial", "succeeded")


def _hidden_stale(configured, request):
    _rewritten_status(configured, request, "stale", "committed")


def _ignored_willingness(configured, request):
    bridge = configured.roles["bridge"]
    original = bridge.check_operation

    def check_operation(operation_request):
        refuse, bridge.refuse = bridge.refuse, False
        try:
            return original(operation_request)
        finally:
            bridge.refuse = refuse

    bridge.check_operation = check_operation


@pytest.mark.parametrize(
    ("mutation", "cases"),
    [
        (_constant_order, ("edge-time-mapped-incomparable", "edge-time-segment-incomparable")),
        (_canned_delivery, ("edge-missing-delivery",)),
        (_hidden_partial, ("edge-partial-execution",)),
        (_ignored_willingness, ("edge-refused-before-claim", "edge-refused-after-time-grant")),
        (_hidden_stale, ("handoff-stale-transfer",)),
    ],
)
def test_a_backend_that_only_claims_the_capability_fails(tmp_path, mutation, cases):
    report = run_mixed_backend_conformance(PortableHarness(tmp_path, mutate=mutation), cases=cases)

    assert [case.outcome for case in report.cases] == ["failed"] * len(cases)
    assert all(
        any(diagnostic.code == "conformance.mixed-case-failed" for diagnostic in case.diagnostics)
        for case in report.cases
    )


def test_a_harness_that_ignores_the_requested_cut_fails(tmp_path):
    report = run_mixed_backend_conformance(
        PortableHarness(tmp_path, honor_time=False), cases=["edge-time-segment-incomparable"]
    )

    case = report.cases[0]
    assert case.outcome == "failed"
    assert "requested time cut" in case.diagnostics[-1].message


def test_the_requested_cut_distinguishes_an_affine_mapping_from_identity(tmp_path):
    report = run_mixed_backend_conformance(
        PortableHarness(tmp_path / "affine", affine_destination=4),
        cases=["edge-executes", "edge-time-mapped-incomparable"],
    )
    assert report.passed
    assert any("distinguishes the admitted mapping" in item for item in report.cases[1].limitations)

    def identity_coordinator(configured, request):
        coordinator = configured.roles["coordinator"]
        fields = coordinator.model.model_dump(mode="python")
        mapping = next(iter(fields["mappings"].values()))
        mapping.update(mapping_kind="identity", scale={"numerator": 1, "denominator": 1})
        coordinator.model = type(coordinator.model).model_validate(fields)

    ignored = run_mixed_backend_conformance(
        PortableHarness(tmp_path / "identity", affine_destination=4, mutate=identity_coordinator),
        cases=["edge-time-mapped-incomparable"],
    )
    assert ignored.cases[0].outcome == "failed"


def test_a_backend_that_accepts_despite_refusal_fails_the_dispatch_case(tmp_path):
    class Ignoring(PortableHarness):
        def control(self, request):
            configuration = super().control(request)
            return replace(configuration, apply_condition=lambda condition: True)

    report = run_mixed_backend_conformance(Ignoring(tmp_path), cases=["control-dispatch-refused"])

    assert report.cases[0].outcome == "failed"


# --- Unsupported is never a pass ------------------------------------------------


def _strip_installations(configured, request):
    configured.binding = replace(configured.binding, backend_installations={})


@pytest.mark.parametrize(
    ("options", "cases", "code"),
    [
        (
            {"conditions": {MixedBackendCondition.NOMINAL}},
            ("edge-partial-execution", "handoff-stale-transfer", "control-dispatch-refused"),
            "conformance.mixed-condition-unrealized",
        ),
        (
            {"mutate": _strip_installations},
            ("edge-executes", "edge-unbound-refused"),
            "conformance.mixed-portable-installation-missing",
        ),
        ({"durable": False}, ("edge-restart-no-reissue",), "conformance.mixed-condition-unrealized"),
        (
            {"control": False},
            ("control-repeated-cycles", "combination-reusable-control-with-mixed-runtime"),
            "conformance.mixed-configuration-unavailable",
        ),
        ({}, ("combination-distributed-portable-mixed",), "conformance.mixed-combination-unsupported"),
    ],
)
def test_unavailable_capability_is_unsupported_not_passed(tmp_path, options, cases, code):
    report = run_mixed_backend_conformance(PortableHarness(tmp_path, **options), cases=cases)

    assert [case.outcome for case in report.cases] == ["unsupported"] * len(cases)
    assert all(case.diagnostics[0].code == code for case in report.cases)
    assert report.unsupported_capability_gaps == cases
    assert not report.passed


def test_harness_failures_are_reported_without_their_content(tmp_path):
    class Leaking(PortableHarness):
        def composition(self, request):
            raise RuntimeError("token=hunter2-secret at /private/backend/path")

    report = run_mixed_backend_conformance(Leaking(tmp_path), cases=["edge-executes"])

    assert report.cases[0].outcome == "failed"
    rendered = json.dumps(backend_conformance_report_payload(report))
    assert "hunter2" not in rendered
    assert "/private/backend" not in rendered


def test_recording_wrappers_keep_the_installed_call_shape():
    from mixed_execution_fixtures import portable_configuration
    from raes_conformance.conformance.mixed_backend_execution import instrument

    configured = portable_configuration()
    configured.roles["coordinator"].grant = lambda: None

    with pytest.raises(ValueError, match="call shape"):
        instrument(configured.binding, configured.declaration.subject.edge_id)


# --- Report honesty --------------------------------------------------------------


def _report(report, cases, **changes):
    claim = _bounded_conformance_claim(
        profile=report.profile, cases=cases, left_carrier_ref="mixed-backend-harness:test"
    )
    return replace(report, cases=cases, claim=claim, unsupported_capability_gaps=(), **changes)


def test_report_honesty_refuses_inconsistent_or_unresolvable_mixed_cases(healthy):
    _, report = healthy
    case = _case(report, "edge-executes")

    inconsistent = _report(report, (replace(case, outcome="unsupported"),), passed=False)
    empty = _report(report, (), passed=True)
    native = replace(case, name="native-other", mixed_binding=None, execution_basis="native-live")
    partly_native = _report(report, (native, case), passed=True, native_conformance=True)
    unresolved = _report(
        report, (replace(case, mixed_binding=replace(case.mixed_binding, components=())),), passed=True
    )

    with pytest.raises(ValueError, match="inconsistent outcome"):
        validate_backend_conformance_report(inconsistent)
    with pytest.raises(ValueError, match="without any case"):
        validate_backend_conformance_report(empty)
    with pytest.raises(ValueError, match="native basis"):
        validate_backend_conformance_report(partly_native)
    with pytest.raises(ValueError, match="component coordinates"):
        validate_backend_conformance_report(unresolved)
    validate_backend_conformance_report(_report(report, (case,), passed=True))


# --- Review regressions (#1017 core-F1, core-F2, core-F3) ----------------------


def test_negative_cases_refuse_configuration_without_valid_baseline_inputs(tmp_path):
    report = run_mixed_backend_conformance(
        PortableHarness(tmp_path, behavior_supplied=False), cases=["edge-unbound-refused", "edge-refused-before-claim"]
    )

    assert [case.outcome for case in report.cases] == ["failed", "failed"]
    assert all("supplies no behavior" in case.diagnostics[-1].message for case in report.cases)


def _broken_evidence_owner(configured, request):
    installation = next(iter(configured.binding.backend_installations.values()))
    installation.evidence.validate_effects = None


def test_an_unrelated_installation_defect_fails_binding_variants(tmp_path):
    report = run_mixed_backend_conformance(
        PortableHarness(tmp_path, mutate=_broken_evidence_owner),
        cases=["edge-missing-mapping-refused", "edge-undeclared-loss-refused"],
    )

    assert [case.outcome for case in report.cases] == ["failed", "failed"]


def _admission_fails_after_commit(configured, request):
    bridge = configured.roles["bridge"]
    original = bridge.check_operation

    def check_operation(operation_request):
        if bridge.starts >= 2:
            raise RuntimeError("admission service unavailable")
        return original(operation_request)

    bridge.check_operation = check_operation


def test_a_moved_phase_attempt_requires_the_claim_refusal(tmp_path):
    report = run_mixed_backend_conformance(
        PortableHarness(tmp_path, mutate=_admission_fails_after_commit), cases=["handoff-repeated-transition"]
    )

    case = report.cases[0]
    assert case.outcome == "failed"
    assert "current-state claim boundary" in case.diagnostics[-1].message


@pytest.fixture
def failing_close(monkeypatch):
    from raes_runtime.control_plane import RuntimeControlPlane

    original = RuntimeControlPlane.close

    def close(self):
        original(self)
        raise RuntimeError("backend calls remain unresolved")

    monkeypatch.setattr(RuntimeControlPlane, "close", close)


@pytest.mark.parametrize(
    ("options", "case_id"),
    [
        ({"conditions": {MixedBackendCondition.NOMINAL}}, "edge-partial-execution"),
        ({"supply_cuts": False}, "edge-time-segment-incomparable"),
    ],
)
def test_an_unsupported_case_keeps_its_failed_cleanup(tmp_path, failing_close, options, case_id):
    report = run_mixed_backend_conformance(PortableHarness(tmp_path, **options), cases=[case_id])

    case = report.cases[0]
    assert case.outcome == "failed"
    assert case.cleanup_verified is False
    assert {"conformance.mixed-condition-unrealized", "conformance.mixed-case-failed"} <= {
        diagnostic.code for diagnostic in case.diagnostics
    }


def test_an_unsupported_control_condition_keeps_an_earlier_control_failure(tmp_path):
    class Reversed(PortableHarness):
        def control(self, request):
            configuration = super().control(request)
            return replace(
                configuration,
                take_transition=configuration.return_transition,
                return_transition=configuration.take_transition,
                apply_condition=lambda condition: condition is MixedBackendCondition.NOMINAL,
            )

    report = run_mixed_backend_conformance(Reversed(tmp_path), cases=["control-dispatch-refused"])

    case = report.cases[0]
    assert case.outcome == "failed"
    assert case.cleanup_verified is True


def test_control_configuration_digest_binds_the_compiled_policy_content():
    from mixed_conformance_harness import control_configuration
    from raes_conformance.conformance.mixed_control_probes import _control_policies, control_configuration_digest

    original = control_configuration()
    address, specification = next(
        (address, spec)
        for address, spec in original.behavior_specifications.items()
        if spec.mixed_control_policy is not None
    )
    changed_policy = replace(specification.mixed_control_policy, policy_revision="changed")
    changed = replace(
        original,
        behavior_specifications={
            **original.behavior_specifications,
            address: replace(specification, mixed_control_policy=changed_policy),
        },
    )

    assert set(changed.behavior_specifications) == set(original.behavior_specifications)
    assert control_configuration_digest(changed) != control_configuration_digest(original)
    assert _control_policies(changed) != _control_policies(original)


def test_a_binding_variant_passes_only_when_the_binding_owner_refuses_it(tmp_path, monkeypatch):
    import raes_conformance.conformance.mixed_backend_probes as probes

    monkeypatch.setattr(probes, "validate_mixed_backend_bindings", lambda profile, context, bindings: None)

    report = run_mixed_backend_conformance(PortableHarness(tmp_path), cases=["edge-reversed-mapping-refused"])

    case = report.cases[0]
    assert case.outcome == "failed"
    assert "binding owner admitted the variant" in case.diagnostics[-1].message

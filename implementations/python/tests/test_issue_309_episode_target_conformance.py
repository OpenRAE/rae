"""The public target runner includes ACT-623 findings in its report and verdict."""

from types import SimpleNamespace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_conformance import participant_episode_structure_conformance_diagnostics
from raes_conformance.conformance import run_target_conformance
from raes_conformance.conformance import target as runner
from raes_conformance.conformance.participant_episode_case import participant_episode_structure_case
from raes_conformance.conformance.report import (
    BackendConformanceReport,
    ConformanceCaseResult,
    _bounded_conformance_claim,
    backend_conformance_report_payload,
)
from raes_conformance.conformance.target_probes import TargetAdapterRun
from raes_contracts.participant_episode import ParticipantEpisodeTerminalReason
from raes_runtime.control_plane import RuntimeControlPlane
from test_issue_309_episode_runtime_binding import PARTICIPANT, episode_model


@pytest.fixture
def isolated_runner(monkeypatch):
    """Keep unrelated backend provisioning and fixture corpora outside these unit cases."""
    case = ConformanceCaseResult(name="fixture-control", contract_name="operation-status-v1", valid=True, passed=True)
    profile = "full-remote-control-plane"
    fixture = BackendConformanceReport(
        profile=profile,
        passed=True,
        cases=(case,),
        claim=_bounded_conformance_claim(profile=profile, cases=(case,), left_carrier_ref="test:episode"),
    )
    monkeypatch.setattr(runner, "run_fixture_suite", lambda **kwargs: fixture)
    monkeypatch.setattr(runner, "target_adapter_run", lambda *args, **kwargs: TargetAdapterRun(()))
    monkeypatch.setattr(runner, "_participant_feature_cases", lambda *args: ())
    monkeypatch.setattr(runner, "participant_policy_cases", lambda *args: ())
    monkeypatch.setattr(runner, "participant_opacity_cases", lambda *args: ())
    monkeypatch.setattr(
        runner,
        "run_realization_conformance",
        lambda *args, **kwargs: SimpleNamespace(
            cases=(), target_binding="", probe_set_digest=None, native_conformance=False
        ),
    )


def recorded_snapshot(reason=ParticipantEpisodeTerminalReason.TIMED_OUT, *, restart=False):
    with RuntimeControlPlane(create_stub_target()) as plane:
        plane.initialize_participant_episode(PARTICIPANT)
        plane.terminate_participant_episode(PARTICIPANT, terminal_reason=reason)
        if restart:
            plane.restart_participant_episode(PARTICIPANT)
        return plane.snapshot


@pytest.mark.parametrize(
    ("reason", "restart", "expected"),
    [
        (ParticipantEpisodeTerminalReason.COMPLETED, False, "terminal reason 'completed'"),
        (ParticipantEpisodeTerminalReason.TIMED_OUT, True, "control action 'restart'"),
    ],
)
def test_target_runner_reports_recorded_policy_violations(isolated_runner, reason, restart, expected):
    report = run_target_conformance(
        create_stub_target(),
        participant_episode_model=episode_model(),
        participant_episode_snapshot=recorded_snapshot(reason, restart=restart),
    )
    episode = next(case for case in report.cases if case.name == "participant-episode-structure")
    assert not episode.passed
    assert not report.passed
    assert any(expected in diagnostic.message for diagnostic in episode.diagnostics)
    assert any(expected in diagnostic.message for diagnostic in report.diagnostics)
    payload = backend_conformance_report_payload(report)
    assert payload["summary"]["checks"]["failed"] == 1
    assert payload["native_conformance"] is False


def test_target_runner_passes_only_the_supplied_consistent_recorded_history(isolated_runner):
    report = run_target_conformance(
        create_stub_target(),
        participant_episode_model=episode_model(),
        participant_episode_snapshot=recorded_snapshot(),
    )
    assert report.passed
    assert backend_conformance_report_payload(report)["summary"]["checks"]["failed"] == 0


def test_target_runner_refuses_missing_episode_evidence(isolated_runner):
    report = run_target_conformance(create_stub_target(), participant_episode_model=episode_model())
    assert not report.passed
    episode = next(case for case in report.cases if case.name == "participant-episode-structure")
    assert episode.outcome == "unsupported"
    assert episode.diagnostics[0].code == "conformance.participant-episode-evidence-missing"


def test_target_runner_inspects_the_probe_scenario_model_it_compiled_once(isolated_runner, monkeypatch):
    # The probe run returns the model it compiled; the episode case uses it without a second compilation.
    monkeypatch.setattr(runner, "target_adapter_run", lambda *args, **kwargs: TargetAdapterRun((), episode_model()))
    report = run_target_conformance(create_stub_target(), participant_episode_snapshot=recorded_snapshot())
    episode = next(case for case in report.cases if case.name == "participant-episode-structure")
    assert episode.outcome == "passed"
    assert not hasattr(runner, "run_reference_processor")


def test_target_without_episode_support_reports_not_applicable(isolated_runner):
    report = run_target_conformance(
        create_stub_target(with_participant_runtime=False), participant_episode_model=episode_model()
    )
    episode = next(case for case in report.cases if case.name == "participant-episode-structure")
    assert episode.outcome == "not-applicable"
    assert not episode.passed
    payload = backend_conformance_report_payload(report)
    assert payload["summary"]["checks"]["not-applicable"] == 1


def test_corrupt_history_cannot_pass_the_episode_case():
    snapshot = recorded_snapshot()
    broken = snapshot.with_entries(dict(snapshot.entries), participant_episode_history={PARTICIPANT: []})
    case = participant_episode_structure_case(create_stub_target(), episode_model(), broken)
    assert not case.passed
    assert any(diagnostic.code == "conformance.participant-episode-evidence-missing" for diagnostic in case.diagnostics)


def test_top_level_episode_export_is_the_same_public_function():
    from raes_conformance.conformance import participant_episode_structure_conformance_diagnostics as nested

    assert participant_episode_structure_conformance_diagnostics is nested


def test_snapshot_integrity_failures_are_in_the_episode_case():
    snapshot = recorded_snapshot()
    history = list(snapshot.participant_episode_history[PARTICIPANT])[:-1]
    broken = snapshot.with_entries(dict(snapshot.entries), participant_episode_history={PARTICIPANT: history})
    case = participant_episode_structure_case(create_stub_target(), episode_model(), broken)
    assert not case.passed
    assert any(diagnostic.code == "conformance.participant-episode-snapshot-invalid" for diagnostic in case.diagnostics)


def test_not_applicable_is_never_counted_as_a_pass_or_used_to_hide_an_error():
    from dataclasses import replace

    from raes_contracts.diagnostics import Diagnostic

    case = participant_episode_structure_case(create_stub_target(with_participant_runtime=False), episode_model(), None)
    profile = "test-suite/v1"
    report = BackendConformanceReport(
        profile=profile,
        passed=True,
        cases=(case,),
        claim=_bounded_conformance_claim(profile=profile, cases=(case,), left_carrier_ref="test:episode"),
    )
    checks = backend_conformance_report_payload(report)["summary"]["checks"]
    assert checks["passed"] == 0
    assert checks["not-applicable"] == 1
    corrupted = replace(case, diagnostics=(Diagnostic("test.failed", "conformance", "test", "Failure."),))
    with pytest.raises(ValueError, match="not-applicable"):
        backend_conformance_report_payload(replace(report, cases=(corrupted,)))

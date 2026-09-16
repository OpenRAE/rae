"""Tests for the #935 CI feedback-latency measurement helper."""

from __future__ import annotations

from tools.ci_latency_report import RunTiming, parse_run, percentile, summarize


def _job(name: str, completed_at: str, conclusion: str) -> dict:
    return {"name": name, "completed_at": completed_at, "conclusion": conclusion}


def test_parse_run_splits_queue_and_execution() -> None:
    run = {
        "id": 1,
        "head_sha": "a" * 40,
        "conclusion": "success",
        "created_at": "2026-09-16T00:00:00Z",
        "run_started_at": "2026-09-16T00:01:00Z",
    }
    jobs = [
        _job("verify", "2026-09-16T00:05:00Z", "success"),
        _job("sonar", "2026-09-16T00:06:00Z", "success"),
    ]
    timing = parse_run(run, jobs, ("verify", "sonar"))
    assert timing.queue_s == 60.0
    assert timing.execution_s == 300.0
    assert timing.time_to_first_failure_s is None
    assert timing.final_required_completion_s == 300.0


def test_parse_run_measures_first_failure_over_required_and_fast_feedback() -> None:
    run = {"id": 2, "created_at": "2026-09-16T00:00:00Z", "run_started_at": "2026-09-16T00:00:00Z"}
    jobs = [
        _job("fast-feedback", "2026-09-16T00:02:00Z", "failure"),
        _job("verify", "2026-09-16T00:08:00Z", "failure"),
        _job("interpreters", "2026-09-16T00:01:00Z", "failure"),  # not a tracked check
    ]
    timing = parse_run(run, jobs, ("verify", "sonar"))
    assert timing.time_to_first_failure_s == 120.0


def test_parse_run_ignores_negative_and_missing_timestamps() -> None:
    run = {"id": 3, "created_at": "2026-09-16T00:05:00Z", "run_started_at": "2026-09-16T00:00:00Z"}
    jobs = [_job("verify", "", "success"), {"name": "sonar", "conclusion": "success"}]
    timing = parse_run(run, jobs, ("verify", "sonar"))
    assert timing.queue_s is None  # created_at after run_started_at -> discarded
    assert timing.final_required_completion_s is None


def test_percentile_interpolates() -> None:
    assert percentile([], 0.5) is None
    assert percentile([7.0], 0.95) == 7.0
    assert percentile([0.0, 10.0], 0.5) == 5.0
    assert percentile([0.0, 10.0], 0.95) == 9.5


def test_summarize_reports_median_and_p95() -> None:
    timings = [
        RunTiming(1, "s", "success", 10.0, 100.0, None, 100.0),
        RunTiming(2, "s", "failure", 20.0, 200.0, 50.0, 200.0),
        RunTiming(3, "s", "success", 30.0, 300.0, None, 300.0),
    ]
    summary = summarize(timings)
    assert summary["runs"] == 3
    assert summary["queue_seconds"]["median"] == 20.0
    assert summary["execution_seconds"]["median"] == 200.0
    # Only the failing run contributes a first-failure measurement.
    assert summary["time_to_first_failure_seconds"]["count"] == 1
    assert summary["final_required_completion_seconds"]["median"] == 200.0

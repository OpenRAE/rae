"""Tests for the #935 CI feedback-latency measurement helper."""

from __future__ import annotations

import io
import json

import pytest
from raes_contracts.errors import InvalidInputError
from tools.ci_latency_report import RunTiming, load_cohort, main, parse_run, percentile, summarize


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


# Run 38071594250 (CI, pull_request) as GitHub returns its third attempt: created_at is
# kept from attempt 1 while run_started_at is reset for attempt 3.
_RERUN = {
    "id": 38071594250,
    "run_attempt": 3,
    "created_at": "2026-10-10T17:24:19Z",
    "run_started_at": "2026-10-11T07:17:05Z",
}
_RERUN_JOBS = [
    # Not repeated by the partial re-run, so attempt 3 lists it with attempt 1's timestamps.
    _job("fast-feedback", "2026-10-10T17:25:09Z", "success"),
    _job("verify", "2026-10-11T07:20:01Z", "success"),
    _job("sonar", "2026-10-11T07:20:02Z", "success"),
]


def test_parse_run_treats_a_missing_run_attempt_as_a_first_attempt() -> None:
    run = {"id": 4, "created_at": "2026-09-16T00:00:00Z", "run_started_at": "2026-09-16T00:01:00Z"}
    jobs = [_job("verify", "2026-09-16T00:05:00Z", "success")]
    timing = parse_run(run, jobs, ("verify", "sonar"))
    assert timing.run_attempt == 1
    assert timing.queue_s == 60.0
    assert parse_run({**run, "run_attempt": 1}, jobs, ("verify", "sonar")) == timing


def test_parse_run_does_not_count_the_wait_before_a_rerun_as_queue_time() -> None:
    timing = parse_run(_RERUN, _RERUN_JOBS, ("verify", "sonar"))
    assert timing.queue_s is None
    assert timing.run_attempt == 3
    # Timed from the attempt's own start; the carried-over fast-feedback job is ignored.
    assert timing.execution_s == 177.0
    assert timing.final_required_completion_s == 177.0


def test_parse_run_does_not_time_a_rerun_from_its_first_attempt() -> None:
    run = {key: value for key, value in _RERUN.items() if key != "run_started_at"}
    timing = parse_run(run, _RERUN_JOBS, ("verify", "sonar"))
    assert timing.queue_s is None
    assert timing.execution_s is None
    assert timing.final_required_completion_s is None


@pytest.mark.parametrize("run_attempt", [0, -1, "3", True])
def test_parse_run_gives_an_invalid_run_attempt_no_queue_time(run_attempt: object) -> None:
    timing = parse_run({**_RERUN, "run_attempt": run_attempt}, _RERUN_JOBS, ("verify", "sonar"))
    assert timing.queue_s is None
    assert timing.run_attempt == 0
    assert timing.execution_s == 177.0


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


def test_load_cohort_parses_entries_and_fails_closed() -> None:
    payload = [
        {
            "run": {
                "id": 1,
                "created_at": "2026-09-16T00:00:00Z",
                "run_started_at": "2026-09-16T00:00:30Z",
            },
            "jobs": [_job("verify", "2026-09-16T00:05:30Z", "success")],
        }
    ]
    timings = load_cohort(payload, ("verify", "sonar"))
    assert len(timings) == 1
    assert timings[0].queue_s == 30.0

    with pytest.raises(InvalidInputError, match="JSON array"):
        load_cohort({"run": {}}, ("verify",))
    with pytest.raises(InvalidInputError, match="'run' object"):
        load_cohort([{"jobs": []}], ("verify",))
    with pytest.raises(InvalidInputError, match="'jobs' must be"):
        load_cohort([{"run": {"id": 1}, "jobs": {}}], ("verify",))


@pytest.mark.parametrize(
    ("stdin", "message"),
    [
        ('{"run": {}}', "ci-latency-report: cohort payload must be a JSON array of {run, jobs} entries\n"),
        ("[not json secret-sentinel", "ci-latency-report: cohort payload on stdin is not valid JSON\n"),
    ],
)
def test_main_reports_an_invalid_cohort_as_a_message(
    capsys: pytest.CaptureFixture[str], stdin: str, message: str
) -> None:
    assert main([], stdin=io.StringIO(stdin)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == message


def test_main_reads_stdin_and_prints_summary(capsys: pytest.CaptureFixture[str]) -> None:
    payload = [
        {
            "run": {"id": 1, "created_at": "2026-09-16T00:00:00Z", "run_started_at": "2026-09-16T00:01:00Z"},
            "jobs": [
                _job("verify", "2026-09-16T00:05:00Z", "success"),
                _job("sonar", "2026-09-16T00:06:00Z", "success"),
            ],
        }
    ]
    exit_code = main(
        ["--required-check", "verify", "--required-check", "sonar"], stdin=io.StringIO(json.dumps(payload))
    )
    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["runs"] == 1
    assert report["queue_seconds"]["median"] == 60.0
    assert report["final_required_completion_seconds"]["median"] == 300.0


def test_main_defaults_required_checks(capsys: pytest.CaptureFixture[str]) -> None:
    payload = [{"run": {"id": 9}, "jobs": []}]
    assert main([], stdin=io.StringIO(json.dumps(payload))) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["runs"] == 1


def test_main_counts_rerun_attempts_outside_queue_time(capsys: pytest.CaptureFixture[str]) -> None:
    first = {"id": 1, "run_attempt": 1, "created_at": "2026-09-16T00:00:00Z", "run_started_at": "2026-09-16T00:01:00Z"}
    payload = [
        {"run": first, "jobs": [_job("sonar", "2026-09-16T00:06:00Z", "success")]},
        {"run": _RERUN, "jobs": _RERUN_JOBS},
    ]
    assert main([], stdin=io.StringIO(json.dumps(payload))) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["runs"] == 2
    assert report["rerun_attempts"] == 1
    assert report["queue_seconds"] == {"count": 1, "median": 60.0, "p95": 60.0}
    assert report["final_required_completion_seconds"]["count"] == 2

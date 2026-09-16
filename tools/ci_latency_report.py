#!/usr/bin/env python3
"""Measure PR CI feedback latency from native GitHub run/job timestamps (#935).

Reads a cohort of workflow runs as JSON on **stdin** — each entry shaped
``{"run": <run>, "jobs": [<job>, ...]}`` using GitHub's native run/jobs objects —
and reports median and p95 for the two issue #935 acceptance metrics without
adding any telemetry service, database, or credential-bearing log scraper (per
the measurement contract in
``docs/decisions/issue-935-ci-shard-fast-feedback-preflight.md``):

- time to first actionable failure: from a run's ``run_started_at`` to the
  earliest terminal failing required or fast-feedback job;
- final required-check completion: the latest terminal timestamp among the
  required checks for that run.

Produce the cohort with the GitHub CLI, then pipe it in, for example:

    gh api 'repos/OpenRAE/rae/actions/workflows/ci.yml/runs?branch=dev&event=pull_request&per_page=20' \
      --jq '[.workflow_runs[] | {run: ., jobs: []}]' \
      | python tools/ci_latency_report.py

(populate each entry's ``jobs`` from ``.../actions/runs/<id>/jobs``). Reading the
cohort from stdin means the tool invokes no subprocess and opens no caller-named
path, so it adds no command-execution or path-traversal surface. Queue time is
reported separately from execution time and successful runs are never imputed as
failures. The metric functions are pure and unit-tested.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TextIO

DEFAULT_REQUIRED_CHECKS = ("verify", "sonar")
FAST_FEEDBACK_CHECK = "fast-feedback"


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    delta = (end - start).total_seconds()
    return delta if delta >= 0 else None


@dataclass(frozen=True)
class RunTiming:
    """Latency metrics derived from one workflow run and its jobs."""

    run_id: int
    head_sha: str
    conclusion: str
    queue_s: float | None
    execution_s: float | None
    time_to_first_failure_s: float | None
    final_required_completion_s: float | None


def _job_elapsed(job: Mapping[str, object], started: datetime | None) -> tuple[str, str, float] | None:
    """Return (name, conclusion, elapsed-since-start) for a timed job, else None."""

    completed = _parse_timestamp(job.get("completed_at"))
    elapsed = _seconds(started, completed)
    if elapsed is None:
        return None
    return str(job.get("name", "")), str(job.get("conclusion", "")), elapsed


def parse_run(
    run: Mapping[str, object],
    jobs: Sequence[Mapping[str, object]],
    required_checks: Iterable[str],
) -> RunTiming:
    """Derive the latency metrics for a single run from its native timestamps."""

    required = set(required_checks)
    failure_scope = required | {FAST_FEEDBACK_CHECK}
    created = _parse_timestamp(run.get("created_at"))
    started = _parse_timestamp(run.get("run_started_at")) or created

    completions: list[float] = []
    failure_times: list[float] = []
    required_completions: list[float] = []
    for job in jobs:
        timed = _job_elapsed(job, started)
        if timed is None:
            continue
        name, conclusion, elapsed = timed
        completions.append(elapsed)
        if conclusion == "failure" and name in failure_scope:
            failure_times.append(elapsed)
        if name in required and conclusion in {"success", "failure"}:
            required_completions.append(elapsed)

    run_id = run.get("id", 0)
    return RunTiming(
        run_id=run_id if isinstance(run_id, int) and not isinstance(run_id, bool) else 0,
        head_sha=str(run.get("head_sha", "")),
        conclusion=str(run.get("conclusion", "")),
        queue_s=_seconds(created, started),
        execution_s=max(completions) if completions else None,
        time_to_first_failure_s=min(failure_times) if failure_times else None,
        final_required_completion_s=max(required_completions) if required_completions else None,
    )


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Return the linear-interpolated percentile of ``values`` (empty -> None)."""

    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    rank = fraction * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _summary(values: list[float]) -> dict[str, object]:
    return {
        "count": len(values),
        "median": percentile(values, 0.5),
        "p95": percentile(values, 0.95),
    }


def summarize(timings: Sequence[RunTiming]) -> dict[str, object]:
    """Summarise a cohort: median/p95 of each metric, queue and execution split."""

    def collect(attribute: str) -> list[float]:
        return [value for value in (getattr(item, attribute) for item in timings) if value is not None]

    return {
        "runs": len(timings),
        "queue_seconds": _summary(collect("queue_s")),
        "execution_seconds": _summary(collect("execution_s")),
        "time_to_first_failure_seconds": _summary(collect("time_to_first_failure_s")),
        "final_required_completion_seconds": _summary(collect("final_required_completion_s")),
    }


def load_cohort(payload: object, required_checks: Iterable[str]) -> list[RunTiming]:
    """Parse a ``[{run, jobs}]`` cohort payload into run timings, failing closed."""

    checks = tuple(required_checks)
    if not isinstance(payload, list):
        raise ValueError("cohort payload must be a JSON array of {run, jobs} entries")
    timings: list[RunTiming] = []
    for entry in payload:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("run"), Mapping):
            raise ValueError("each cohort entry must be an object with a 'run' object")
        jobs = entry.get("jobs")
        if jobs is None:
            jobs = []
        if not isinstance(jobs, list):
            raise ValueError("cohort entry 'jobs' must be a JSON array")
        timings.append(parse_run(entry["run"], jobs, checks))
    return timings


def main(argv: Sequence[str] | None = None, *, stdin: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarise CI feedback latency from a stdin run cohort.")
    parser.add_argument("--required-check", action="append", dest="required_checks")
    args = parser.parse_args(list(argv) if argv is not None else None)
    required_checks = tuple(args.required_checks or DEFAULT_REQUIRED_CHECKS)

    payload = json.load(stdin if stdin is not None else sys.stdin)
    timings = load_cohort(payload, required_checks)
    print(json.dumps(summarize(timings), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

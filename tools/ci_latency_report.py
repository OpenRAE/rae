#!/usr/bin/env python3
"""Measure PR CI feedback latency from native GitHub run/job timestamps (#935).

This computes the two acceptance metrics for issue #935 over a cohort of workflow
runs, without adding any telemetry service, database, or credential-bearing log
scraper (per the measurement contract in
``docs/decisions/issue-935-ci-shard-fast-feedback-preflight.md``):

- time to first actionable failure: from a run's ``run_started_at`` to the
  earliest terminal failing required or fast-feedback job;
- final required-check completion: the latest terminal timestamp among the
  required checks for that run.

It reports median and p95 for each metric and separates queue time from execution
time. Baseline (before sharding) and resulting cohorts are summarised the same
way so they are directly comparable; successful runs are never imputed as
failures. The computation is pure and unit-tested; the CLI only fetches run JSON
through the ``gh`` client.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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


def parse_run(run: dict[str, Any], jobs: Sequence[dict[str, Any]], required_checks: Iterable[str]) -> RunTiming:
    """Derive the latency metrics for a single run from its native timestamps."""

    required = set(required_checks) | {FAST_FEEDBACK_CHECK}
    created = _parse_timestamp(run.get("created_at"))
    started = _parse_timestamp(run.get("run_started_at")) or created

    completions: list[float] = []
    failure_times: list[float] = []
    required_completions: list[float] = []
    for job in jobs:
        name = str(job.get("name", ""))
        completed = _parse_timestamp(job.get("completed_at"))
        elapsed = _seconds(started, completed)
        if elapsed is None:
            continue
        completions.append(elapsed)
        conclusion = str(job.get("conclusion", ""))
        if conclusion == "failure" and name in required:
            failure_times.append(elapsed)
        if name in required_checks and conclusion in {"success", "failure"}:
            required_completions.append(elapsed)

    return RunTiming(
        run_id=int(run.get("id", 0)),
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


def _summary(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "median": percentile(values, 0.5),
        "p95": percentile(values, 0.95),
    }


def summarize(timings: Sequence[RunTiming]) -> dict[str, Any]:
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


def _gh_json(args: list[str]) -> Any:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def _fetch_cohort(repo: str, branch: str, event: str, limit: int, required_checks: Sequence[str]) -> list[RunTiming]:
    runs = _gh_json(
        [
            "api",
            f"repos/{repo}/actions/workflows/ci.yml/runs?branch={branch}&event={event}&per_page={limit}",
        ]
    )
    timings: list[RunTiming] = []
    for run in runs.get("workflow_runs", [])[:limit]:
        jobs = _gh_json(
            [
                "api",
                f"repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100",
            ]
        )
        timings.append(parse_run(run, jobs.get("jobs", []), required_checks))
    return timings


def _load_offline(path: str, required_checks: Sequence[str]) -> list[RunTiming]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return [parse_run(entry["run"], entry.get("jobs", []), required_checks) for entry in payload]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="OpenRAE/rae")
    parser.add_argument("--branch", default="dev")
    parser.add_argument("--event", default="pull_request")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--required-check", action="append", dest="required_checks")
    parser.add_argument("--runs-file", help="offline JSON [{run, jobs}] cohort instead of the GitHub API")
    args = parser.parse_args(list(argv) if argv is not None else None)
    required_checks = tuple(args.required_checks or DEFAULT_REQUIRED_CHECKS)

    if args.runs_file:
        timings = _load_offline(args.runs_file, required_checks)
    else:
        timings = _fetch_cohort(args.repo, args.branch, args.event, args.limit, required_checks)

    print(json.dumps(summarize(timings), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

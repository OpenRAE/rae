#!/usr/bin/env python3
# ruff: noqa: E402
"""Check the declared branch merge policy against the repository workflows.

``implementations/tooling/branch-merge-policy.json`` declares, for each protected
branch, whether it uses the GitHub merge queue, whether it requires strict
status checks, and the producer of each required status check context (#2026).

The gate fails closed when:

- a branch does not require strict status checks and does not use the merge
  queue;
- a required context on a merge-queue branch has no workflow producer, or its
  producer workflow does not run on the ``merge_group`` event;
- a producer job condition selects events and does not name ``merge_group``;
- a declared producer workflow or job does not exist.

GitHub settings are not readable with the CI token, so the declaration is the
reviewed record that the maintainer applies to the repository settings.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError
from raes_contracts.operational_logging import run_application

from implementations.tooling.action_policy_yaml import parse_yaml_mapping
from tools.policy.common import PolicyFailure, load_bounded_json_object
from tools.tooling_artifact_policy_common import as_mapping, failure

MERGE_POLICY_PATH = "implementations/tooling/branch-merge-policy.json"
_MAX_POLICY_BYTES = 64 * 1024
_MERGE_GROUP = "merge_group"
_CHECK_KEYS = {"workflow": frozenset({"context", "workflow", "job"}), "app": frozenset({"context", "app"})}
_BRANCH_KEYS = frozenset({"merge_queue", "strict_status_checks", "required_checks"})


def _triggers(workflow: Mapping[str, Any]) -> Mapping[str, Any]:
    # PyYAML 1.1 reads an unquoted `on` key as the boolean True.
    triggers = workflow.get("on", workflow.get(True, {}))
    if isinstance(triggers, str):
        return {triggers: None}
    if isinstance(triggers, list):
        return {name: None for name in triggers if isinstance(name, str)}
    return as_mapping(triggers)


def _runs_on_merge_group(workflow: Mapping[str, Any]) -> bool:
    """Return whether every merge group requests this workflow."""

    triggers = _triggers(workflow)
    if _MERGE_GROUP not in triggers:
        return False
    config = as_mapping(triggers[_MERGE_GROUP])
    types = config.get("types", ["checks_requested"])
    return set(config) <= {"types"} and isinstance(types, list) and "checks_requested" in types


def _job_admits_merge_group(job: Mapping[str, Any]) -> bool:
    """Reject a job condition that selects events without naming the merge group event."""

    condition = str(job.get("if", ""))
    return "event_name" not in condition or _MERGE_GROUP in condition


def _check_shape(check: object) -> str | None:
    """Return the producer kind of one required check, or None when it is malformed."""

    if not isinstance(check, Mapping) or not isinstance(check.get("context"), str) or not check["context"]:
        return None
    kind = next((name for name, keys in _CHECK_KEYS.items() if set(check) == keys), None)
    if kind is None or not all(isinstance(check[key], str) and check[key] for key in _CHECK_KEYS[kind]):
        return None
    return kind


class _Workflows:
    """Load each declared producer workflow once."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._documents: dict[str, tuple[Mapping[str, Any] | None, list[PolicyFailure]]] = {}

    def get(self, path: str) -> tuple[Mapping[str, Any] | None, list[PolicyFailure]]:
        if path not in self._documents:
            if not path.startswith(".github/workflows/") or Path(path).suffix not in {".yml", ".yaml"}:
                self._documents[path] = (
                    None,
                    [failure("merge-policy-producer", "producer must be a repository workflow", MERGE_POLICY_PATH)],
                )
            else:
                self._documents[path] = parse_yaml_mapping(self._repo_root, path)
        return self._documents[path]


def _check_failures(
    branch: str,
    check: object,
    *,
    merge_queue: bool,
    workflows: _Workflows,
) -> list[PolicyFailure]:
    kind = _check_shape(check)
    if kind is None:
        return [failure("merge-policy-shape", f"{branch}: malformed required check", MERGE_POLICY_PATH)]
    check = as_mapping(check)
    context = check["context"]
    if kind == "app":
        if merge_queue:
            return [
                failure(
                    "merge-policy-merge-group",
                    f"{branch}: required context {context!r} needs a workflow producer that runs on merge groups",
                    MERGE_POLICY_PATH,
                )
            ]
        return []
    path, job = check["workflow"], check["job"]
    workflow, load_failures = workflows.get(path)
    if workflow is None:
        return load_failures
    failures: list[PolicyFailure] = []
    producer = as_mapping(workflow.get("jobs")).get(job)
    if not isinstance(producer, Mapping):
        failures.append(
            failure("merge-policy-producer", f"{branch}: producer job {job!r} of {context!r} does not exist", path)
        )
    if merge_queue and not (_runs_on_merge_group(workflow) and _job_admits_merge_group(as_mapping(producer))):
        failures.append(
            failure(
                "merge-policy-merge-group",
                f"{branch}: producer of required context {context!r} does not run on every merge group",
                path,
            )
        )
    return failures


def _branch_failures(branch: str, rules: object, workflows: _Workflows) -> list[PolicyFailure]:
    if (
        not isinstance(rules, Mapping)
        or set(rules) != _BRANCH_KEYS
        or not isinstance(rules["merge_queue"], bool)
        or not isinstance(rules["strict_status_checks"], bool)
        or not isinstance(rules["required_checks"], list)
        or not rules["required_checks"]
    ):
        return [failure("merge-policy-shape", f"{branch}: malformed branch rules", MERGE_POLICY_PATH)]
    merge_queue = rules["merge_queue"]
    failures: list[PolicyFailure] = []
    if not merge_queue and not rules["strict_status_checks"]:
        failures.append(
            failure(
                "merge-policy-strict",
                f"{branch}: strict status checks may be off only on a branch that uses the merge queue",
                MERGE_POLICY_PATH,
            )
        )
    contexts = [as_mapping(check).get("context") for check in rules["required_checks"]]
    if len(contexts) != len(set(map(str, contexts))):
        failures.append(failure("merge-policy-shape", f"{branch}: duplicate required context", MERGE_POLICY_PATH))
    for check in rules["required_checks"]:
        failures.extend(_check_failures(branch, check, merge_queue=merge_queue, workflows=workflows))
    return failures


def evaluate_merge_queue_policy(repo_root: Path = REPO_ROOT) -> list[PolicyFailure]:
    """Return deterministic failures of the declared branch merge policy."""

    try:
        policy = load_bounded_json_object(repo_root, MERGE_POLICY_PATH, max_bytes=_MAX_POLICY_BYTES)
    except (InvalidInputError, OSError) as exc:
        return [failure("merge-policy-shape", str(exc), MERGE_POLICY_PATH)]
    branches = policy.get("branches")
    if set(policy) != {"schema_version", "branches"} or policy["schema_version"] != 1 or not branches:
        return [failure("merge-policy-shape", "policy must declare schema_version 1 and branches", MERGE_POLICY_PATH)]
    if not isinstance(branches, Mapping):
        return [failure("merge-policy-shape", "branches must be a mapping", MERGE_POLICY_PATH)]
    workflows = _Workflows(repo_root)
    failures = [item for branch, rules in branches.items() for item in _branch_failures(branch, rules, workflows)]
    return sorted(set(failures), key=lambda item: (item.path or "", item.rule_id, item.message))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    failures = evaluate_merge_queue_policy(args.repo_root)
    for item in failures:
        print(item.render(), file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))

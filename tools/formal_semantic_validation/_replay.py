"""Case replay through the production SDL boundary."""

from __future__ import annotations

import dataclasses
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from tools.formal_semantic_validation._shape import (
    _diagnostic_payload,
    _digest,
    _nonempty_string,
    _sha256_file,
)
from tools.formal_semantic_validation._types import (
    _HISTORICAL_VM_REPLAY_INPUTS,
    _RENAMED_FORMAL_REPLAY_DIGESTS,
)
from tools.policy.common import safe_repo_path


def replay_case(repo_root: Path, case: Mapping[str, object]) -> dict[str, str | None]:
    """Replay one supported case through its declared production boundary."""
    fixture_value = case.get("fixture_path")
    fixture = safe_repo_path(repo_root, str(fixture_value)) if _nonempty_string(fixture_value) else None
    if fixture is None or not fixture.is_file():
        raise ValueError(f"missing or unsafe replay fixture {fixture_value!r}")

    replay_mode = case.get("replay_mode")
    if replay_mode == "parse":
        return _replay_parse_case(repo_root, case, fixture)
    if replay_mode == "compile-stability":
        first = _compiled_case_digest(repo_root, case, fixture)
        second = _compiled_case_digest(repo_root, case, fixture)
        return {
            "actual_outcome": "stable" if first == second else "drifted",
            "diagnostic_kind": None,
            "result_digest": _digest([first, second]),
        }
    if replay_mode == "compile-distinguish":
        return _replay_compile_distinguish(repo_root, case, fixture)
    raise ValueError(f"case {case.get('case_id')!r} is not replayable")


def _migration_policy_for_case(repo_root: Path, case: Mapping[str, object], path: Path) -> object:
    from raes import SDLMigrationPolicy

    relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    expected_digest = _HISTORICAL_VM_REPLAY_INPUTS.get((str(case.get("case_id")), relative))
    if expected_digest is not None and _sha256_file(path) == expected_digest:
        return SDLMigrationPolicy.ACCEPT
    return SDLMigrationPolicy.REJECT


def _replay_parse_case(
    repo_root: Path,
    case: Mapping[str, object],
    fixture: Path,
) -> dict[str, str | None]:
    from raes import SDLError, parse_sdl_file

    try:
        scenario = parse_sdl_file(
            fixture,
            migration_policy=_migration_policy_for_case(repo_root, case, fixture),
        )
    except SDLError as exc:
        return {
            "actual_outcome": "rejected",
            "diagnostic_kind": type(exc).__name__,
            "result_digest": _digest(_diagnostic_payload(exc, repo_root)),
        }
    return {
        "actual_outcome": "accepted",
        "diagnostic_kind": None,
        "result_digest": _digest(scenario.model_dump(mode="json")),
    }


def _compiled_case_digest(repo_root: Path, case: Mapping[str, object], path: Path) -> str:
    from raes import instantiate_scenario, parse_sdl_file
    from raes_processor.compiler import compile_runtime_model

    scenario = parse_sdl_file(
        path,
        migration_policy=_migration_policy_for_case(repo_root, case, path),
    )
    instantiated = instantiate_scenario(scenario, parameters={})
    compiled = dataclasses.asdict(compile_runtime_model(instantiated))
    # Additive empty runtime dimensions do not alter the historical semantic
    # replay projection. A non-empty capture demand remains digest-bearing.
    if not compiled.get("capture_demands"):
        compiled.pop("capture_demands", None)
    return _digest(compiled)


def _replay_compile_distinguish(
    repo_root: Path,
    case: Mapping[str, object],
    fixture: Path,
) -> dict[str, str | None]:
    comparison_value = case.get("comparison_fixture_path")
    comparison = safe_repo_path(repo_root, str(comparison_value)) if _nonempty_string(comparison_value) else None
    if comparison is None or not comparison.is_file():
        raise ValueError(f"missing or unsafe comparison fixture {comparison_value!r}")
    first = _compiled_case_digest(repo_root, case, fixture)
    second = _compiled_case_digest(repo_root, case, comparison)
    return {
        "actual_outcome": "distinguishable" if first != second else "indistinguishable",
        "diagnostic_kind": None,
        "result_digest": _digest([first, second]),
    }


def _replay_observation_matches(
    case_id: object,
    observation: Mapping[str, object],
    replayed: Mapping[str, object],
) -> bool:
    digest_pair = (observation.get("result_digest"), replayed.get("result_digest"))
    return (
        observation.get("actual_outcome") == replayed.get("actual_outcome")
        and observation.get("diagnostic_kind") == replayed.get("diagnostic_kind")
        and (
            observation.get("result_digest") == replayed.get("result_digest")
            or _RENAMED_FORMAL_REPLAY_DIGESTS.get(str(case_id)) == digest_pair
        )
    )


def _validate_test_ref(repo_root: Path, value: object) -> bool:
    if not _nonempty_string(value):
        return False
    path_value, separator, node_id = str(value).partition("::")
    node_id_valid = bool(separator) and bool(node_id) and "[" not in node_id and "/" not in node_id
    path = safe_repo_path(repo_root, path_value) if node_id_valid else None
    if path is None or not path.is_file() or path.suffix != ".py":
        return False
    function_name = node_id.rsplit("::", 1)[-1]
    return (
        re.search(
            rf"^def {re.escape(function_name)}\s*\(",
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        is not None
    )


def _participant_test_refs(protocol: Mapping[str, object]) -> list[str]:
    refs: list[str] = []
    for obligation in protocol.get("participant_obligations", []):
        if not isinstance(obligation, Mapping):
            continue
        for key in ("positive_test_ref", "negative_test_ref"):
            value = obligation.get(key)
            if _nonempty_string(value):
                refs.append(str(value))
    return refs


def _replay_participant_tests(repo_root: Path, test_refs: list[str]) -> tuple[bool, str]:
    """Run the declared participant fixtures without trusting snapshot labels."""
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *test_refs],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"participant fixture replay could not complete: {exc}"
    if completed.returncode != 0:
        return (
            False,
            f"participant fixture replay exited with status {completed.returncode}",
        )
    return True, ""

"""Production-evidence command and replay validation."""

from __future__ import annotations

import dataclasses
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path

from tools.formal_semantic_validation._shape import (
    _failure,
    _sha256_file,
)
from tools.formal_semantic_validation._types import (
    _CURRENT_SATISFIABILITY_PROFILE,
    _MAX_FILE_BYTES,
)
from tools.policy.common import PolicyFailure, load_bounded_json_object, safe_repo_path


@dataclasses.dataclass(frozen=True)
class _ProductionObservationContext:
    repo_root: Path
    release_artifacts_by_path: Mapping[object, Mapping[str, object]]
    replay_current: bool = True


@dataclasses.dataclass(frozen=True)
class _ProductionEvidenceReplay:
    evidence_digest_matches: bool
    direct_digest: str
    outcome: str
    profile: str
    analysis_profile: str
    configuration_digest: str
    source_digest: str


def _production_artifact_join_valid(
    fixture: Path | None,
    evidence_path: Path | None,
    fixture_pin: Mapping[str, object] | None,
    evidence_pin: Mapping[str, object] | None,
) -> bool:
    return (
        fixture is not None
        and fixture.is_file()
        and evidence_path is not None
        and evidence_path.is_file()
        and fixture_pin is not None
        and fixture_pin.get("kind") == "corpus-input"
        and evidence_pin is not None
        and evidence_pin.get("kind") == "production-evidence"
    )


def _evidence_digest_stale(
    observation: Mapping[str, object],
    evidence_path: Path,
    evidence_pin: Mapping[str, object],
) -> bool:
    recorded = observation.get("evidence_artifact_sha256")
    return recorded != _sha256_file(evidence_path) or evidence_pin.get("sha256") != recorded


def _validate_production_evidence_observation(
    context: _ProductionObservationContext,
    case: Mapping[str, object],
    observation: Mapping[str, object],
    command: object,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    repo_root = context.repo_root
    release_artifacts_by_path = context.release_artifacts_by_path
    case_id = case.get("case_id")
    fixture_value = case.get("fixture_path")
    evidence_value = observation.get("evidence_artifact_path")
    fixture = safe_repo_path(repo_root, fixture_value) if isinstance(fixture_value, str) else None
    evidence_path = safe_repo_path(repo_root, evidence_value) if isinstance(evidence_value, str) else None
    fixture_pin = release_artifacts_by_path.get(fixture_value)
    evidence_pin = release_artifacts_by_path.get(evidence_value)
    if not _production_artifact_join_valid(fixture, evidence_path, fixture_pin, evidence_pin):
        failures.append(
            _failure(
                "formal-validation-production-evidence-join",
                f"case {case_id!r} lacks an atomically selected input or evidence artifact",
                path,
            )
        )
        return
    if _evidence_digest_stale(observation, evidence_path, evidence_pin):
        failures.append(
            _failure(
                "formal-validation-production-evidence-join",
                f"case {case_id!r} evidence artifact SHA-256 is stale",
                path,
            )
        )
    expected_argv = _production_evidence_argv(str(case.get("replay_mode")), fixture_value)
    _validate_production_evidence_command(command, expected_argv, case_id, failures, path)
    try:
        replay = _replay_production_evidence(
            repo_root,
            case,
            observation,
            fixture,
            evidence_value,
            expected_argv,
            replay_current=context.replay_current,
        )
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        failures.append(
            _failure(
                "formal-validation-production-replay",
                f"case {case_id!r} production replay failed ({type(exc).__name__})",
                path,
            )
        )
        return
    if not _production_evidence_joins_match(case, observation, replay):
        failures.append(
            _failure(
                "formal-validation-production-evidence-join",
                f"case {case_id!r} source, configuration, outcome, CLI, replay, or evidence joins drifted",
                path,
            )
        )


def _replay_production_evidence(
    repo_root: Path,
    case: Mapping[str, object],
    observation: Mapping[str, object],
    fixture: Path,
    evidence_value: object,
    expected_argv: list[object],
    *,
    replay_current: bool = True,
) -> _ProductionEvidenceReplay:
    replay_mode = case.get("replay_mode")
    if replay_mode == "exploit-path":
        load_bounded_json_object(repo_root, str(case.get("fixture_path")), max_bytes=2 * 1024 * 1024)
    stored_payload = load_bounded_json_object(
        repo_root,
        str(evidence_value),
        max_bytes=_MAX_FILE_BYTES,
    )
    if replay_mode == "satisfiability":
        from raes_contracts.satisfiability import ScenarioSatisfiabilityEvidenceModel
        from raes_processor.satisfiability import analyze_scenario_file, replay_satisfiability_evidence

        stored = ScenarioSatisfiabilityEvidenceModel.model_validate(stored_payload)
    else:
        from raes_contracts.exploit_path import ExploitPathAnalysisEvidenceModel
        from raes_processor.exploit_path import analyze_exploit_path_file, replay_exploit_path_evidence

        stored = ExploitPathAnalysisEvidenceModel.model_validate(stored_payload)
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.satisfiability import canonical_contract_digest

    stored_artifact_matches = canonical_json_digest(stored_payload) == observation.get("evidence_digest")
    if not replay_current:
        # Validate the original payload's own joins, not a current replay claim.
        return _ProductionEvidenceReplay(
            evidence_digest_matches=stored_artifact_matches,
            direct_digest=canonical_json_digest(stored_payload),
            outcome=stored.outcome.value,
            profile=stored.profile,
            analysis_profile=stored.analysis_profile,
            configuration_digest=(
                stored.solver_configuration_digest
                if replay_mode == "satisfiability"
                else stored.search_configuration_digest
            ),
            source_digest=stored.source.byte_digest,
        )
    if replay_mode == "satisfiability":
        direct = analyze_scenario_file(fixture, profile=_CURRENT_SATISFIABILITY_PROFILE)
        replay_satisfiability_evidence(fixture, stored)
        configuration_digest = direct.solver_configuration_digest
    else:
        direct = analyze_exploit_path_file(fixture, profile="raes-exploit-path-analysis-v1")
        replay_exploit_path_evidence(fixture, stored)
        configuration_digest = direct.search_configuration_digest
    direct_digest = canonical_contract_digest(direct)
    stored_digest = canonical_contract_digest(stored)
    cli_payload = _run_production_evidence_cli(repo_root, expected_argv)
    cli = type(stored).model_validate(cli_payload)
    cli_digest = canonical_contract_digest(cli)
    evidence_digest_matches = (
        stored_artifact_matches
        and stored_digest == direct_digest == cli_digest
        and canonical_json_digest(cli_payload) == cli_digest
    )
    return _ProductionEvidenceReplay(
        evidence_digest_matches=evidence_digest_matches,
        direct_digest=direct_digest,
        outcome=direct.outcome.value,
        profile=direct.profile,
        analysis_profile=direct.analysis_profile,
        configuration_digest=configuration_digest,
        source_digest=direct.source.byte_digest,
    )


def _production_evidence_joins_match(
    case: Mapping[str, object],
    observation: Mapping[str, object],
    replay: _ProductionEvidenceReplay,
) -> bool:
    evidence_digest = observation.get("evidence_digest")
    joins = (
        observation.get("actual_outcome") == replay.outcome == case.get("expected_outcome"),
        observation.get("diagnostic_kind") == replay.profile,
        observation.get("result_digest") == evidence_digest,
        observation.get("evidence_profile") == replay.profile,
        observation.get("analysis_profile") == replay.analysis_profile,
        observation.get("configuration_digest") == replay.configuration_digest,
        observation.get("source_digest") == replay.source_digest,
    )
    digest_join = evidence_digest == replay.direct_digest
    return replay.evidence_digest_matches and digest_join and all(joins)


def _production_evidence_argv(replay_mode: str, fixture_value: object) -> list[object]:
    return [
        "implementations/python/.venv/bin/raes",
        "processor",
        "satisfiability" if replay_mode == "satisfiability" else "exploit-path",
        fixture_value,
        "--profile",
        (_CURRENT_SATISFIABILITY_PROFILE if replay_mode == "satisfiability" else "raes-exploit-path-analysis-v1"),
    ]


def _validate_production_evidence_command(
    command: object,
    expected_argv: list[object],
    case_id: object,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if not isinstance(command, Mapping) or command.get("argv") != expected_argv or command.get("network") != "disabled":
        failures.append(
            _failure(
                "formal-validation-production-command",
                f"case {case_id!r} must use its production CLI with fixed offline argv",
                path,
            )
        )


def _run_production_evidence_cli(repo_root: Path, argv: list[object]) -> dict[str, object]:
    if not all(isinstance(value, str) for value in argv):
        raise ValueError("production evidence argv must contain only strings")
    executable = safe_repo_path(repo_root, str(argv[0]))
    if executable is None or not executable.is_file():
        raise ValueError("production evidence executable is missing")
    completed = subprocess.run(
        [str(executable), *(str(value) for value in argv[1:])],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={},
    )
    if len(completed.stdout.encode("utf-8")) > _MAX_FILE_BYTES or len(completed.stderr.encode("utf-8")) > 16 * 1024:
        raise ValueError("production evidence command exceeded its output bound")
    if completed.returncode != 0 or completed.stderr:
        raise ValueError(f"production evidence command exited with status {completed.returncode}")
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise ValueError("production evidence command did not emit an object")
    return payload

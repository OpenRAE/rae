"""Hygiene, policy, contracts, proof, and lint lanes."""

from __future__ import annotations

from collections.abc import Sequence

import nox

from tools.nox_support.config import (
    MAX_LARGE_FILE_KB,
    PRIVATE_KEY_EXCLUDE_PREFIXES,
    PROJECT_ROOT,
)
from tools.nox_support.runner import (
    SessionReporter,
    _parse_hygiene_posargs,
    _run,
    _run_gitleaks_dir_scan,
    _run_pre_commit_hook,
    _run_project_python,
    _run_ruff,
    _split_policy_session_args,
    _suffix_paths,
    _sync_project,
    _text_paths,
)

_NO_TEXT_FILES_REASON = "no text files selected"
_STAGED_SKIP_REASON = "skipped on staged check; runs on push and verify"
_NOXFILE_PATH = "noxfile.py"
_WORKING_TREE_POLICY_STAGES: tuple[tuple[str, str], ...] = (
    ("policy / semantic coverage ADR", "tools/check_semantic_coverage.py"),
    ("policy / assurance policy ADR", "tools/check_assurance_policy.py"),
    ("policy / authority boundary ADR", "tools/check_authority_boundary.py"),
    ("policy / deprecation lifecycle records", "tools/check_deprecation_lifecycle.py"),
    ("policy / concept authority governance", "tools/check_concept_authority_governance.py"),
    ("policy / behavioral relation claims", "tools/check_behavioral_relation_claims.py"),
    ("policy / agent guidance profile", "tools/check_agent_guidance.py"),
    ("policy / example library catalog", "tools/check_example_library.py"),
    ("policy / project positioning", "tools/check_project_positioning.py"),
    ("policy / identity cutover", "tools/check_identity_cutover.py"),
)


def _run_hygiene(
    session: nox.Session,
    reporter: SessionReporter,
    *,
    posargs: Sequence[str],
    default_all_files: bool,
) -> None:
    selection = _parse_hygiene_posargs(posargs, default_all_files=default_all_files)
    paths = selection.paths
    detail = f"{len(paths)} files from {selection.source}"
    if not paths:
        reporter.skip(
            "hygiene / candidate path resolution",
            f"no files selected from {selection.source}",
        )
        return

    text_paths = _text_paths(paths)
    yaml_paths = _suffix_paths(paths, (".yaml", ".yml"))
    json_paths = _suffix_paths(paths, (".json",))
    private_key_paths = [path for path in paths if not path.startswith(PRIVATE_KEY_EXCLUDE_PREFIXES)]

    reporter.run(
        "hygiene / trailing whitespace",
        lambda: _run_pre_commit_hook(session, "trailing-whitespace-fixer", paths=text_paths),
        detail=f"{len(text_paths)} text files from {selection.source}",
    ) if text_paths else reporter.skip("hygiene / trailing whitespace", _NO_TEXT_FILES_REASON)

    reporter.run(
        "hygiene / eof newline",
        lambda: _run_pre_commit_hook(session, "end-of-file-fixer", paths=text_paths),
        detail=f"{len(text_paths)} text files from {selection.source}",
    ) if text_paths else reporter.skip("hygiene / eof newline", _NO_TEXT_FILES_REASON)

    reporter.run(
        "hygiene / yaml syntax",
        lambda: _run_pre_commit_hook(session, "check-yaml", "--unsafe", paths=yaml_paths),
        detail=f"{len(yaml_paths)} YAML files from {selection.source}",
    ) if yaml_paths else reporter.skip("hygiene / yaml syntax", "no YAML files selected")

    reporter.run(
        "hygiene / json syntax",
        lambda: _run_pre_commit_hook(session, "check-json", paths=json_paths),
        detail=f"{len(json_paths)} JSON files from {selection.source}",
    ) if json_paths else reporter.skip("hygiene / json syntax", "no JSON files selected")

    reporter.run(
        "hygiene / added large files",
        lambda: _run_pre_commit_hook(
            session,
            "check-added-large-files",
            "--maxkb",
            MAX_LARGE_FILE_KB,
            paths=paths,
        ),
        detail=detail,
    )

    reporter.run(
        "hygiene / merge conflict markers",
        lambda: _run_pre_commit_hook(session, "check-merge-conflict", paths=text_paths),
        detail=f"{len(text_paths)} text files from {selection.source}",
    ) if text_paths else reporter.skip("hygiene / merge conflict markers", _NO_TEXT_FILES_REASON)

    reporter.run(
        "hygiene / private key detection",
        lambda: _run_pre_commit_hook(session, "detect-private-key", paths=private_key_paths),
        detail=f"{len(private_key_paths)} files from {selection.source}",
    ) if private_key_paths else reporter.skip("hygiene / private key detection", "no eligible files selected")

    reporter.run(
        "hygiene / gitleaks",
        lambda: _run_gitleaks_dir_scan(session, paths),
        detail=detail,
    )


def _run_policy(session: nox.Session, reporter: SessionReporter, *args: str) -> None:
    _sync_project(session)
    reporter.run(
        "policy / development artifact lock",
        lambda: _run_project_python(session, "tools/check_tooling_artifact_policy.py"),
    )
    reporter.run(
        "policy / conftest self-verify",
        lambda: _run(
            session,
            "uv",
            "run",
            "--project",
            str(PROJECT_ROOT),
            "--frozen",
            "python",
            "-c",
            "from tools.policy.conftest_tool import verify_conftest_policy; verify_conftest_policy()",
        ),
    )
    repo_args, requirement_args, skip_requirement = _split_policy_session_args(list(args))
    arg_list = list(args)
    adr_pin_args: list[str] = []
    if "--base-rev" in arg_list:
        base_index = arg_list.index("--base-rev")
        if base_index + 1 < len(arg_list):
            adr_pin_args = ["--base-rev", arg_list[base_index + 1]]
    reporter.run(
        "policy / repo policy",
        lambda: _run_project_python(session, "tools/check_repo_policy.py", *repo_args),
    )
    if skip_requirement:
        reporter.skip("policy / requirement governance", "skipped by --skip-requirement")
    else:
        reporter.run(
            "policy / requirement governance",
            lambda: _run_project_python(session, "tools/check_requirement_governance.py", *requirement_args),
        )
    # check_semantic_coverage.py validates live files on disk, not a staged
    # snapshot, so it is meaningless (and misleading) under --staged. It runs in
    # the working-tree policy invocations (`policy`, `hook-pre-push`, `verify`).
    _run_working_tree_policies(session, reporter, staged="--staged" in args, adr_pin_args=adr_pin_args)


def _run_working_tree_policies(
    session: nox.Session,
    reporter: SessionReporter,
    *,
    staged: bool,
    adr_pin_args: list[str],
) -> None:
    if staged:
        for stage_name, _script in _WORKING_TREE_POLICY_STAGES:
            reporter.skip(stage_name, _STAGED_SKIP_REASON)
        reporter.skip("policy / ADR acceptance-content pin", _STAGED_SKIP_REASON)
        return
    for stage_name, script in _WORKING_TREE_POLICY_STAGES:
        reporter.run(stage_name, lambda script=script: _run_project_python(session, script))
    reporter.run(
        "policy / ADR acceptance-content pin",
        lambda: _run_project_python(session, "tools/check_adr_immutability.py", *adr_pin_args),
    )


def _run_contracts(session: nox.Session, reporter: SessionReporter, *args: str) -> None:
    _sync_project(session)
    arg_list = list(args)
    schema_publication_args: list[str] = []
    json_artifact_args: list[str] = []
    index = 0
    while index < len(arg_list):
        arg = arg_list[index]
        if arg == "--staged":
            json_artifact_args.append(arg)
            index += 1
            continue
        if arg == "--base-rev":
            if index + 1 < len(arg_list):
                base_rev = arg_list[index + 1]
                schema_publication_args = ["--base-rev", base_rev]
                json_artifact_args.extend(["--base-rev", base_rev])
            index += 2
            continue
        if arg == "--requirement-uid":
            index += 2
            continue
        if arg == "--skip-requirement" or arg.startswith("-"):
            index += 1
            continue
        json_artifact_args.append(arg)
        index += 1
    reporter.run(
        "contracts / schema publication manifest",
        lambda: _run_project_python(session, "tools/check_schema_publication.py", *schema_publication_args),
    )
    reporter.run(
        "contracts / generated schema drift",
        lambda: _run_project_python(session, "tools/check_generated_schemas.py"),
    )
    reporter.run(
        "contracts / SDL catalog parity",
        lambda: _run_project_python(session, "tools/check_sdl_catalog_parity.py"),
    )
    reporter.run(
        "contracts / SDL lineage provenance",
        lambda: _run_project_python(session, "tools/check_sdl_lineage.py"),
    )
    reporter.run(
        "contracts / scientific-scenario completeness",
        lambda: _run_project_python(session, "tools/check_scientific_scenario_completeness.py"),
    )
    reporter.run(
        "contracts / reproducible related-work comparison",
        lambda: _run_project_python(session, "tools/check_related_work_comparison.py"),
    )
    reporter.run(
        "contracts / DSL language-evaluation evidence",
        lambda: _run_project_python(session, "tools/check_dsl_language_evaluation.py"),
    )
    reporter.run(
        "contracts / standardized specification coverage",
        lambda: _run_project_python(session, "tools/check_specification_coverage.py"),
    )
    reporter.run(
        "contracts / formal semantic-validation evidence",
        lambda: _run_project_python(session, "tools/check_formal_semantic_validation.py"),
    )
    reporter.run(
        "contracts / json artifact validation",
        lambda: _run_project_python(session, "tools/check_json_artifacts.py", *json_artifact_args),
    )
    reporter.run(
        "contracts / ATT&CK tactic vocabulary conformance",
        lambda: _run_project_python(session, "tools/check_attack_tactic_vocabulary.py"),
    )
    reporter.run(
        "contracts / ATLAS tactic vocabulary conformance",
        lambda: _run_project_python(session, "tools/check_atlas_tactic_vocabulary.py"),
    )
    reporter.run(
        "contracts / NIST CSF defensive vocabulary conformance",
        lambda: _run_project_python(session, "tools/check_nist_csf_defensive_vocabulary.py"),
    )
    reporter.run(
        "contracts / autonomous behavior vocabulary conformance",
        lambda: _run_project_python(session, "tools/check_autonomous_behavior_vocabularies.py"),
    )


def _run_participant_opacity_proof(session: nox.Session, reporter: SessionReporter) -> None:
    reporter.run(
        "formal proof / participant opacity",
        lambda: _run_project_python(session, "tools/check_participant_opacity_proof.py"),
        detail="Isabelle2025-2 :: offline kernel replay",
    )


def _run_lint(session: nox.Session, reporter: SessionReporter) -> None:
    reporter.run(
        "lint / ruff format (project)",
        lambda: _run_ruff(session, "format", "--check", ".", project_relative=True),
    )
    reporter.run(
        "lint / ruff check (project)",
        lambda: _run_ruff(session, "check", ".", project_relative=True),
    )
    reporter.run(
        "lint / ruff format (tooling)",
        lambda: _run_ruff(session, "format", "--check", "tools", _NOXFILE_PATH),
    )
    reporter.run(
        "lint / ruff check (tooling)",
        lambda: _run_ruff(session, "check", "tools", _NOXFILE_PATH),
    )


def _run_changed_lint(session: nox.Session, reporter: SessionReporter, paths: list[str]) -> None:
    prefix = "implementations/python/"
    project_paths = []
    for path in paths:
        if path.startswith(prefix) and path.endswith(".py"):
            project_paths.append(path[len(prefix) :])
    if project_paths:
        reporter.run(
            "lint / ruff format (changed project files)",
            lambda: _run_ruff(session, "format", "--check", *project_paths, project_relative=True),
            detail=f"{len(project_paths)} files",
        )
        reporter.run(
            "lint / ruff check (changed project files)",
            lambda: _run_ruff(session, "check", *project_paths, project_relative=True),
            detail=f"{len(project_paths)} files",
        )
    else:
        reporter.skip(
            "lint / ruff format (changed project files)",
            "no changed project Python files",
        )
        reporter.skip(
            "lint / ruff check (changed project files)",
            "no changed project Python files",
        )

    tooling_paths = [
        path for path in paths if (path.startswith("tools/") or path == _NOXFILE_PATH) and path.endswith(".py")
    ]
    if tooling_paths:
        reporter.run(
            "lint / ruff format (changed tooling files)",
            lambda: _run_ruff(session, "format", "--check", *tooling_paths),
            detail=f"{len(tooling_paths)} files",
        )
        reporter.run(
            "lint / ruff check (changed tooling files)",
            lambda: _run_ruff(session, "check", *tooling_paths),
            detail=f"{len(tooling_paths)} files",
        )
    else:
        reporter.skip(
            "lint / ruff format (changed tooling files)",
            "no changed tooling Python files",
        )
        reporter.skip(
            "lint / ruff check (changed tooling files)",
            "no changed tooling Python files",
        )

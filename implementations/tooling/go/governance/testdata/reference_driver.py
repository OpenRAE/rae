"""Execute the retained Python checks for the hosted Go comparison tests.

Only this trusted checkout supplies executable code. Fixture repositories supply
data. The ADR-117 ratchet remains a separate gate outside the #1799 source set.
"""

import importlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

CHECKOUT = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(CHECKOUT), str(CHECKOUT / "implementations/python/packages")]


def findings(values):
    return [dict(rule_id=f.rule_id, message=f.message, path=f.path) for f in values]


def evaluate(request):
    tool = request["Tool"]
    root = Path(request["Root"])
    functions = {
        "adr-immutability": "evaluate_adr_immutability",
        "agent-guidance": "evaluate_agent_guidance",
        "assurance-policy": "evaluate_assurance_policy",
        "authority-boundary": "evaluate_authority_boundary",
        "concept-authority-governance": "evaluate_concept_authority_governance",
        "contract-requirement-tracing": "evaluate_contract_tracing",
        "deprecation-lifecycle": "evaluate_deprecation_records",
        "identity-cutover": "evaluate_identity_cutover",
        "project-positioning": "validate_project_positioning",
        "schema-coverage": "evaluate_schema_coverage",
    }
    if tool in functions:
        module = importlib.import_module("tools.check_" + tool.replace("-", "_"))
        return findings(getattr(module, functions[tool])(root))
    if tool.endswith("-vocabulary") or tool == "autonomous-behavior-vocabularies":
        module = importlib.import_module("tools.check_" + tool.replace("-", "_"))
        module.REPO_ROOT = root
        return [
            dict(rule_id=tool, message=m, path=None)
            for m in module._failures(SimpleNamespace(verify_remote=False))
        ]
    if tool == "schema-publication":
        from tools.check_schema_publication import validate_schema_publication_manifest

        return [
            dict(rule_id=tool, message=m, path=None)
            for m in validate_schema_publication_manifest(root)
        ]
    if tool == "public-docs":
        from tools.check_public_docs import (
            evaluate_public_boundary,
            evaluate_public_sources,
        )

        return findings(
            [*evaluate_public_sources(root), *evaluate_public_boundary(root)]
        )
    if tool == "json-artifacts":
        import subprocess
        from tools import check_json_artifacts as artifact

        def run_validator(*args):
            return subprocess.run(
                artifact.frozen_tool_command(CHECKOUT, "check-jsonschema", *args),
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

        artifact._run_check_jsonschema = run_validator
        targets = artifact.collect_validation_targets(root, paths=request["Paths"])
        failures = artifact.validate_targets(targets)
        # The CLI has no JSON report. Compare each failing batch's affected paths
        # and verdict; the two validation engines supply their own error prose.
        return [
            dict(
                rule_id="json-schema-validation",
                message=m.split(": ", 1)[0] + ": schema validation failed",
                path=None,
            )
            for m in failures
        ]
    if tool == "repo-policy":
        from tools.policy.repo_policy import evaluate_repo_policy, run_conftest_policy

        def structural(document):
            return run_conftest_policy(
                document, repo_root=CHECKOUT, policy_dir=root / "tools/policy/conftest"
            )

        return findings(
            evaluate_repo_policy(
                root,
                request["Paths"],
                check_set=request["CheckSet"],
                structural_runner=structural,
                ratchet_runner=lambda _: [],
            )
        )
    if tool == "pr-title":
        from tools.check_pr_title import validate_pr_title

        return [
            dict(rule_id=f.rule_id, message=f.message, path=None)
            for f in validate_pr_title(request["Title"], body=request.get("Body", ""))
        ]
    if tool == "pr-body":
        from tools.check_pr_body import _fixture_lookup, validate_pr_body

        return [
            dict(rule_id=f.rule_id, message=f.message, path=None)
            for f in validate_pr_body(
                request["Body"],
                _fixture_lookup(Path(request["IssuesFile"])),
                repository="OpenRAE/rae",
            )
        ]
    if tool == "requirement-governance":
        from tools.policy.requirement_governance import evaluate_requirement_governance
        from tools.policy.repository_requirements import RepositoryRequirementClient

        return findings(
            evaluate_requirement_governance(
                root,
                request["Paths"],
                client=RepositoryRequirementClient(root),
                requirement_uid=request["RequirementUID"],
            )
        )
    if tool == "requirement-context":
        from tools.requirement_context import (
            current_requirement_branch,
            resolve_requirement_context,
        )

        uid, _ = resolve_requirement_context(
            root,
            current_requirement_branch(root),
            request.get("RequirementUID") or None,
        )
        return dict(findings=[], text=(uid or "") + "\n")
    if tool == "public-docs-reads":
        import types
        from tools import public_docs_guard as guard

        observations = request["Documentation"]
        guard.DOCUMENTED_MODULE_ROOTS = frozenset(
            (root / name).resolve() for name in observations["ModuleRoots"]
        )
        for index, name in enumerate(observations["ImportedModules"]):
            sys.modules[f"reference_module_{index}"] = types.SimpleNamespace(
                __file__=str(root / name)
            )
        source_root = root / observations["SourceRoot"]
        outside = guard.files_outside(
            source_root, [row["File"] for row in observations["Reads"]]
        )
        return [
            dict(
                rule_id="public-docs-read-escape",
                message=f"page reads {name}, which is outside the documentation source directory",
                path="index",
            )
            for name in outside
        ]
    raise ValueError("unsupported reference comparison")


def main():
    job = json.load(sys.stdin)
    os.environ.update(job.get("Environment") or {})
    request = job["Request"]
    try:
        result = evaluate(request)
        if isinstance(result, list):
            if (
                request["Tool"]
                not in {
                    "pr-title",
                    "pr-body",
                    "schema-publication",
                    "json-artifacts",
                    "public-docs",
                    "public-docs-reads",
                    "requirement-context",
                }
                and not request["Tool"].endswith("-vocabulary")
                and request["Tool"] != "autonomous-behavior-vocabularies"
            ):
                from tools.policy.common import (
                    PolicyFailure,
                    apply_exceptions,
                    load_exceptions,
                )

                result = findings(
                    apply_exceptions(
                        [PolicyFailure(**row) for row in result],
                        load_exceptions(Path(request["Root"])),
                        requirement_uid=request.get("RequirementUID") or None,
                    )
                )
            result = dict(findings=result)
        json.dump(result, sys.stdout)
    except Exception as exc:
        json.dump(dict(error=type(exc).__name__), sys.stdout)


if __name__ == "__main__":
    main()

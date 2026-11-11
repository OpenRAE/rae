#!/usr/bin/env python3
"""Record native SDL transformation expectations from the unchanged reference."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))
sys.path.insert(0, str(ROOT / "implementations/python/tests"))

from raes.materialization import MaterializedScenario  # noqa: E402
from raes.parser import parse_sdl, parse_sdl_file  # noqa: E402
from raes.scenario import ExpandedScenario, Scenario  # noqa: E402
from raes.transformations import (  # noqa: E402
    ArtifactTransformationPolicy,
    RemoveSDLDeclarationRequest,
    RenameSDLDeclarationRequest,
    remove_sdl_declaration,
    rename_sdl_declaration,
)
from raes_contracts.contracts import ArtifactTransformationLossKind, ExternalConceptBindingDocumentModel  # noqa: E402
from test_artifact_transformations import _concept_binding_inputs  # noqa: E402

TransformCase = tuple[
    str,
    Scenario | ExpandedScenario | MaterializedScenario,
    str,
    dict[str, Any],
    dict[str, Any],
    tuple[ExternalConceptBindingDocumentModel, ...],
    str,
    dict[str, str],
]
RENAME_OPERATION = "rename-sdl-declaration/v1"
WEB_NODE = "nodes.web"
ROOT_FILE = "main.yaml"


def fixture_cases(rows: list[TransformCase]) -> None:
    directory = ROOT / "contracts/fixtures"
    for path in sorted((directory / "artifact-transformations-v1/cases").glob("*.json")):
        case = json.loads(path.read_bytes())
        if case["operation"] == "canonicalize-portable-contract/v1":
            continue
        source_path = directory / case["source_path"]
        source = parse_sdl_file(source_path)
        files = {file.name: file.read_text() for file in source_path.parent.glob("*.yaml")}
        if source_path.name not in files:
            files[source_path.name] = source_path.read_text()
        rows.append(
            (
                case["case_id"],
                source,
                case["operation"],
                case["request"],
                case["policy"],
                (),
                source_path.name,
                files,
            )
        )


def policy_cases(rows: list[TransformCase]) -> None:
    basic = (
        "name: transformation\nnodes: {web: {type: compute}, peer: {type: compute}}\n"
        "content: {payload: {type: file, target: web, path: /tmp/test}}\n"
    )
    for name, operation, request, policy in [
        ("alias", "rename", {"target_address": "web", "new_local_name": "front"}, {}),
        (
            "node-length",
            "rename",
            {"target_address": WEB_NODE, "new_local_name": "a" * 36},
            {},
        ),
        (
            "missing",
            "rename",
            {"target_address": "nodes.absent", "new_local_name": "front"},
            {},
        ),
        (
            "same-identity",
            "rename",
            {"target_address": WEB_NODE, "new_local_name": "web"},
            {},
        ),
        ("remove-unauthorized", "remove", {"target_address": "nodes.peer"}, {}),
        (
            "remove-alias",
            "remove",
            {"target_address": "peer"},
            {"allowed_loss_kinds": ["declaration-removed"]},
        ),
        (
            "remove-dangling",
            "remove",
            {"target_address": WEB_NODE},
            {"allowed_loss_kinds": ["declaration-removed"]},
        ),
    ]:
        rows.append(
            (
                name,
                parse_sdl(basic),
                operation + "-sdl-declaration/v1",
                request,
                policy,
                (),
                ROOT_FILE,
                {ROOT_FILE: basic},
            )
        )
    for name, policy in [
        ("augmentation-default", "augmentation_scope: {default: closed}\n"),
        (
            "augmentation-scope",
            "augmentation_scope: {default: closed, scopes: [{scope: /nodes/web, permission: open}]}\n",
        ),
        (
            "execution-default",
            "execution_policy: {default: {policy_id: p, response: terminate}}\n",
        ),
        (
            "execution-scope",
            "execution_policy: {default: {policy_id: p, response: terminate}, "
            "scopes: [{scope: /nodes/web, policy: {policy_id: q, response: terminate}}]}\n",
        ),
    ]:
        text = basic + policy
        rows.append(
            (
                name,
                parse_sdl(text),
                RENAME_OPERATION,
                {"target_address": WEB_NODE, "new_local_name": "front"},
                {},
                (),
                ROOT_FILE,
                {ROOT_FILE: text},
            )
        )


def binding_cases(rows: list[TransformCase]) -> None:
    source, binding = _concept_binding_inputs()
    text = source.model_dump_json(exclude_unset=True)
    rows.append(
        (
            "retarget-bindings",
            source,
            RENAME_OPERATION,
            {"target_address": WEB_NODE, "new_local_name": "front"},
            {},
            (binding,),
            ROOT_FILE,
            {ROOT_FILE: text},
        )
    )
    stale = binding.model_copy(deep=True)
    stale.bindings["attack-execution"].subject = stale.bindings["attack-execution"].subject.model_copy(
        update={"artifact_digest": "sha256:" + "a" * 64}
    )
    rows.append(
        (
            "stale-binding",
            source,
            RENAME_OPERATION,
            {"target_address": WEB_NODE, "new_local_name": "front"},
            {},
            (stale,),
            ROOT_FILE,
            {ROOT_FILE: text},
        )
    )
    rows.append(
        (
            "remove-bindings",
            source,
            "remove-sdl-declaration/v1",
            {"target_address": WEB_NODE},
            {"allowed_loss_kinds": ["declaration-removed"]},
            (binding,),
            ROOT_FILE,
            {ROOT_FILE: text},
        )
    )


def record_cases(rows: list[TransformCase]) -> list[dict[str, Any]]:
    cases = []
    for name, source, operation, request, policy, bindings, root, files in rows:
        if operation == RENAME_OPERATION:
            result = rename_sdl_declaration(
                source,
                RenameSDLDeclarationRequest(**request),
                binding_documents=bindings,
            )
        else:
            resolved_policy = ArtifactTransformationPolicy(
                tuple(ArtifactTransformationLossKind(value) for value in policy.get("allowed_loss_kinds", []))
            )
            result = remove_sdl_declaration(
                source,
                RemoveSDLDeclarationRequest(**request),
                policy=resolved_policy,
                binding_documents=bindings,
            )
        cases.append(
            {
                "name": name,
                "root": root,
                "files": files,
                "request": {
                    "operation_profile": operation,
                    "request": request,
                    "policy": policy,
                    "binding_documents": [value.model_dump(mode="json") for value in bindings],
                },
                "output": result.output.model_dump(mode="json", exclude_unset=True) if result.output else None,
                "result": {
                    "report": result.report.model_dump(mode="json"),
                    "binding_documents": [value.model_dump(mode="json") for value in result.binding_documents],
                },
            }
        )
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    rows: list[TransformCase] = []
    fixture_cases(rows)
    policy_cases(rows)
    binding_cases(rows)
    cases = record_cases(rows)
    encoded = json.dumps({"cases": cases}, indent=2, ensure_ascii=True) + "\n"
    target = ROOT / "implementations/go/internal/sdl/authoring/testdata/transformations.json"
    if arguments.check:
        return int(target.read_text() != encoded)
    target.write_text(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

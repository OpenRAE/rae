#!/usr/bin/env python3
"""Record reference safe-state resolution, validation and rename outcomes."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "implementations/python/packages")]

import yaml  # noqa: E402
from raes import SDLError, parse_sdl_file  # noqa: E402
from raes._transformation_rename import rename_sdl_declaration  # noqa: E402
from raes._transformation_types import RenameSDLDeclarationRequest  # noqa: E402
from raes.observation_scope import resolve_safe_states  # noqa: E402

OUTPUT = (
    ROOT
    / "implementations/go/internal/sdl/authoring/testdata/safe-state-reference.json"
)
SUBJECTS = ["nodes.first", "nodes.second", "nodes.first.services.api"]


def payload(kind: str = "safe-hold") -> dict[str, Any]:
    state: dict[str, Any] = {"kind": kind, "assertion_refs": ["safe"]}
    if kind == "continue":
        state["continuing_mode"] = "cooling"
    return {
        "name": "safe-state",
        "nodes": {
            "first": {
                "type": "compute",
                "os": "linux",
                "services": [{"name": "api", "port": 443}, {"port": 80}],
            },
            "second": {"type": "compute", "os": "linux"},
        },
        "propositions": {
            "safe": {
                "description": "The admitted safe-state condition holds.",
                "subjects": list(SUBJECTS),
                "basis": "observed_state",
                "predicate": {
                    "kind": "boolean",
                    "property": "safe",
                    "semantic_ref": "urn:example:safe",
                    "expected": True,
                },
                "evidence_requirements": ["readback"],
            }
        },
        "assertions": {"safe": {"proposition": "safe", "role": "postcondition"}},
        "evidence_requirements": {
            "readback": {
                "source_refs": list(SUBJECTS),
                "scope_refs": list(SUBJECTS),
                "window": "safe-state-verification",
                "channel": "api_response",
                "sensitivity": "plain",
                "redaction": "none",
                "integrity": "checksum",
                "retention": "run_lifetime",
                "loss_disclosure": "required",
            }
        },
        "safe_state": {"default": state},
    }


def single(value: dict[str, Any]) -> dict[str, str]:
    return {"main.yaml": yaml.safe_dump(value, sort_keys=False)}


def imported(
    module_state: dict[str, Any], root_state: dict[str, Any] | None
) -> dict[str, str]:
    module = payload()
    module["module"] = {
        "id": "example/safe",
        "version": "1.0.0",
        "exports": {"nodes": ["first", "second"]},
    }
    module["safe_state"] = module_state
    root: dict[str, Any] = {
        "name": "imported-safe-state",
        "imports": [{"source": "local:module.yaml", "namespace": "lib"}],
    }
    if root_state is not None:
        root["safe_state"] = root_state
    return {
        "main.yaml": yaml.safe_dump(root, sort_keys=False),
        "module.yaml": yaml.safe_dump(module, sort_keys=False),
    }


def cases() -> list[tuple[str, dict[str, str], dict[str, Any] | None]]:
    hold = payload()["safe_state"]["default"]
    stop = {"kind": "controlled-stop", "assertion_refs": ["safe"]}
    result: list[tuple[str, dict[str, str], dict[str, Any] | None]] = []
    for kind in ("safe-hold", "controlled-stop", "continue"):
        result.append((f"default-{kind}", single(payload(kind)), None))
    nearest = payload("continue")
    nearest["safe_state"]["scopes"] = [{"scope": "/nodes/first", "state": stop}]
    result.append(("nearest-scope", single(nearest), None))
    service = payload()
    service["safe_state"] = {
        "scopes": [{"scope": "/nodes/first/services/api", "state": stop}]
    }
    result.append(("service-scope", single(service), None))
    for change in (
        "declared",
        "precondition",
        "negative",
        "any",
        "subject",
        "evidence",
        "field-scope",
        "missing",
    ):
        value = payload()
        if change == "declared":
            value["propositions"]["safe"]["basis"] = "declared_state"
        elif change == "precondition":
            value["assertions"]["safe"]["role"] = "precondition"
        elif change == "negative":
            value["assertions"]["safe"]["polarity"] = "negative"
        elif change == "any":
            value["propositions"]["safe"]["quantifier"] = "any"
        elif change == "subject":
            value["propositions"]["safe"]["subjects"] = SUBJECTS[:2]
        elif change == "evidence":
            value["evidence_requirements"]["readback"]["source_refs"] = SUBJECTS[:2]
            value["evidence_requirements"]["readback"]["scope_refs"] = SUBJECTS[:2]
        elif change == "field-scope":
            value["safe_state"] = {
                "scopes": [{"scope": "/nodes/first/os", "state": hold}]
            }
        else:
            value["safe_state"]["default"]["assertion_refs"] = ["absent"]
        result.append((f"invalid-{change}", single(value), None))
    variable = payload()
    variable["variables"] = {"subject": {"type": "string", "default": "nodes.first"}}
    variable["propositions"]["safe"]["subjects"] = ["${subject}", *SUBJECTS[1:]]
    result.append(("deferred-variable", single(variable), None))
    result.append(("import-default", imported({"default": hold}, None), None))
    result.append(
        (
            "import-scope-and-root-default",
            imported(
                {"scopes": [{"scope": "/nodes/first", "state": stop}]},
                {"default": hold},
            ),
            None,
        )
    )
    nested = {
        "scopes": [{"namespace": [], "scope": "/nodes/second", "state": stop}],
        "default": hold,
    }
    result.append(("import-nested-namespace", imported(nested, None), None))
    result.append(
        (
            "import-field-scope",
            imported({"scopes": [{"scope": "/nodes/first/os", "state": hold}]}, None),
            None,
        )
    )
    for scopes in (False, True):
        value = payload()
        if scopes:
            value["safe_state"]["scopes"] = [
                {"scope": "/nodes/first", "state": copy.deepcopy(hold)}
            ]
        result.append(
            (
                f"rename-{'scopes' if scopes else 'default'}",
                single(value),
                {"target_address": "assertions.safe", "new_local_name": "verified"},
            )
        )
    return result


def record_case(
    name: str, files: dict[str, str], rename: dict[str, Any] | None
) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "files": files}
    with tempfile.TemporaryDirectory() as directory:
        for file, text in files.items():
            (Path(directory) / file).write_text(text, encoding="utf-8")
        try:
            scenario = parse_sdl_file(Path(directory) / "main.yaml")
        except SDLError as error:
            row.update(
                accepted=False,
                errors=list(getattr(error, "errors", None) or [str(error)]),
            )
            return row
    row["accepted"] = True
    try:
        row["safe_states"] = [
            state.model_dump(mode="json") for state in resolve_safe_states(scenario)
        ]
    except ValueError:
        # Source-time references stay deferred; instantiation refuses them before compilation.
        row["safe_states"] = None
    if rename is not None:
        result = rename_sdl_declaration(scenario, RenameSDLDeclarationRequest(**rename))
        row["rename"] = rename
        row["renamed"] = (
            result.output.model_dump(mode="json", by_alias=True, exclude_unset=True)[
                "safe_state"
            ]
            if result.succeeded
            else None
        )
    return row


def record() -> dict[str, Any]:
    return {"cases": [record_case(*case) for case in cases()]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    actual = json.dumps(record(), indent=1, sort_keys=True) + "\n"
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != actual:
            print(
                "safe-state reference differs from the reference owner", file=sys.stderr
            )
            return 1
    else:
        OUTPUT.write_text(actual, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

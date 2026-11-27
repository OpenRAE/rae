#!/usr/bin/env python3
"""Record reference safe-state resolution, validation and rename outcomes."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "implementations/python/packages")]

import yaml  # noqa: E402
from raes import SDLError, parse_sdl_file  # noqa: E402
from raes._transformation_rename import rename_sdl_declaration  # noqa: E402
from raes._transformation_types import RenameSDLDeclarationRequest  # noqa: E402
from raes.observation_scope import resolve_safe_states  # noqa: E402

OUTPUT = ROOT / "implementations/go/internal/sdl/authoring/testdata/safe-state-reference.json"
SUBJECTS = ["nodes.first", "nodes.second", "nodes.first.services.api"]
MAIN = "main.yaml"
FIRST_NODE = "/nodes/first"
DEFAULT_KINDS = ("safe-hold", "controlled-stop", "continue")


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
    return {MAIN: yaml.safe_dump(value, sort_keys=False)}


def imported(module_state: dict[str, Any], root_state: dict[str, Any] | None) -> dict[str, str]:
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
        MAIN: yaml.safe_dump(root, sort_keys=False),
        "module.yaml": yaml.safe_dump(module, sort_keys=False),
    }


Case = tuple[str, dict[str, str], dict[str, Any] | None]


def _set(path: tuple[str, ...], value: object) -> Callable[[dict[str, Any]], None]:
    def change(document: dict[str, Any]) -> None:
        target = document
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return change


def _invalid_changes(hold: dict[str, Any]) -> dict[str, list[Callable[[dict[str, Any]], None]]]:
    """Return each invalid variant of the base payload, in recorded order."""
    readback = ("evidence_requirements", "readback")
    return {
        "declared": [_set(("propositions", "safe", "basis"), "declared_state")],
        "precondition": [_set(("assertions", "safe", "role"), "precondition")],
        "negative": [_set(("assertions", "safe", "polarity"), "negative")],
        "any": [_set(("propositions", "safe", "quantifier"), "any")],
        "subject": [_set(("propositions", "safe", "subjects"), SUBJECTS[:2])],
        "evidence": [_set((*readback, "source_refs"), SUBJECTS[:2]), _set((*readback, "scope_refs"), SUBJECTS[:2])],
        "field-scope": [_set(("safe_state",), {"scopes": [{"scope": f"{FIRST_NODE}/os", "state": hold}]})],
        "missing": [_set(("safe_state", "default", "assertion_refs"), ["absent"])],
    }


def _single_cases(hold: dict[str, Any], stop: dict[str, Any]) -> list[Case]:
    result: list[Case] = [(f"default-{kind}", single(payload(kind)), None) for kind in DEFAULT_KINDS]
    nearest = payload("continue")
    nearest["safe_state"]["scopes"] = [{"scope": FIRST_NODE, "state": stop}]
    service = payload()
    service["safe_state"] = {"scopes": [{"scope": f"{FIRST_NODE}/services/api", "state": stop}]}
    result.extend([("nearest-scope", single(nearest), None), ("service-scope", single(service), None)])
    for change, steps in _invalid_changes(hold).items():
        value = payload()
        for step in steps:
            step(value)
        result.append((f"invalid-{change}", single(value), None))
    variable = payload()
    variable["variables"] = {"subject": {"type": "string", "default": "nodes.first"}}
    variable["propositions"]["safe"]["subjects"] = ["${subject}", *SUBJECTS[1:]]
    result.append(("deferred-variable", single(variable), None))
    return result


def _import_cases(hold: dict[str, Any], stop: dict[str, Any]) -> list[Case]:
    nested = {"scopes": [{"namespace": [], "scope": "/nodes/second", "state": stop}], "default": hold}
    return [
        ("import-default", imported({"default": hold}, None), None),
        (
            "import-scope-and-root-default",
            imported({"scopes": [{"scope": FIRST_NODE, "state": stop}]}, {"default": hold}),
            None,
        ),
        ("import-nested-namespace", imported(nested, None), None),
        ("import-field-scope", imported({"scopes": [{"scope": f"{FIRST_NODE}/os", "state": hold}]}, None), None),
    ]


def _rename_cases(hold: dict[str, Any]) -> list[Case]:
    rename = {"target_address": "assertions.safe", "new_local_name": "verified"}
    default, scoped = payload(), payload()
    scoped["safe_state"]["scopes"] = [{"scope": FIRST_NODE, "state": copy.deepcopy(hold)}]
    return [("rename-default", single(default), rename), ("rename-scopes", single(scoped), rename)]


def cases() -> list[Case]:
    hold = payload()["safe_state"]["default"]
    stop = {"kind": "controlled-stop", "assertion_refs": ["safe"]}
    return [*_single_cases(hold, stop), *_import_cases(hold, stop), *_rename_cases(hold)]


def record_case(name: str, files: dict[str, str], rename: dict[str, Any] | None) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "files": files}
    with tempfile.TemporaryDirectory() as directory:
        for file, text in files.items():
            (Path(directory) / file).write_text(text, encoding="utf-8")
        try:
            scenario = parse_sdl_file(Path(directory) / MAIN)
        except SDLError as error:
            row.update(
                accepted=False,
                errors=list(getattr(error, "errors", None) or [str(error)]),
            )
            return row
    row["accepted"] = True
    try:
        row["safe_states"] = [state.model_dump(mode="json") for state in resolve_safe_states(scenario)]
    except ValueError:
        # Source-time references stay deferred; instantiation refuses them before compilation.
        row["safe_states"] = None
    if rename is not None:
        result = rename_sdl_declaration(scenario, RenameSDLDeclarationRequest(**rename))
        row["rename"] = rename
        row["renamed"] = (
            result.output.model_dump(mode="json", by_alias=True, exclude_unset=True)["safe_state"]
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
            print("safe-state reference differs from the reference owner", file=sys.stderr)
            return 1
    else:
        OUTPUT.write_text(actual, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

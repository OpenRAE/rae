#!/usr/bin/env python3
"""Record simple SDL field predicates as native compatibility data."""

from __future__ import annotations

import argparse
import ast
import inspect
import json
from pathlib import Path
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from parity_sdl_constructors import Constructors  # noqa: E402
from raes._identifiers import (  # noqa: E402
    require_portable_identifier,
    require_qualified_identifier,
)
from raes.materialization import MaterializedScenario  # noqa: E402
from raes.runtime_values import absolute_path_or_var, require_non_empty, require_symbol  # noqa: E402
from raes.runtime_database import _require_object_name  # noqa: E402
from raes.scenario import Scenario  # noqa: E402
from raes.stateful_resources import _validate_relative_path, validate_mount_destination  # noqa: E402

HELPERS = {
    require_non_empty: "nonblank",
    _require_object_name: "nonblank",
    absolute_path_or_var: "absolute-path",
    require_symbol: "portable",
    require_portable_identifier: "portable",
    require_qualified_identifier: "qualified",
    _validate_relative_path: "contained-relative",
    validate_mount_destination: "contained-mount",
}


def refusal_guard(guard):
    if not isinstance(guard, ast.If) or guard.orelse or len(guard.body) != 1:
        return False
    raised = guard.body[0]
    return (
        isinstance(raised, ast.Raise)
        and raised.cause is None
        and isinstance(raised.exc, ast.Call)
        and isinstance(raised.exc.func, ast.Name)
        and raised.exc.func.id == "ValueError"
    )


def reference_list_guard(body, argument):
    if len(body) == 3 and isinstance(body[0], ast.For):
        loop = body[0]
        if (
            loop.orelse
            or not isinstance(loop.iter, ast.Name)
            or loop.iter.id != argument
            or not isinstance(loop.target, ast.Name)
            or len(loop.body) != 1
            or not refusal_guard(loop.body[0])
        ):
            return None
        guard = loop.body[0]
        test = ast.Call(
            func=ast.Name(id="any", ctx=ast.Load()),
            args=[ast.GeneratorExp(
                elt=guard.test,
                generators=[ast.comprehension(
                    target=loop.target, iter=loop.iter, ifs=[], is_async=0
                )],
            )],
            keywords=[],
        )
        body = [ast.If(test=test, body=guard.body, orelse=[]), *body[1:]]
    if (
        len(body) == 2
        and refusal_guard(body[0])
        and isinstance(body[0].test, ast.BoolOp)
        and isinstance(body[0].test.op, ast.Or)
        and len(body[0].test.values) == 2
    ):
        combined = body[0]
        body = [
            ast.If(test=test, body=combined.body, orelse=[])
            for test in combined.test.values
        ] + [body[1]]
    if len(body) != 3 or not all(refusal_guard(guard) for guard in body[:2]):
        return None
    returned = body[-1]
    if not isinstance(returned, ast.Return) or not isinstance(returned.value, ast.Name) or returned.value.id != argument:
        return None
    call = body[0].test
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != "any" or call.keywords or len(call.args) != 1:
        return None
    expression = call.args[0]
    if not isinstance(expression, ast.GeneratorExp) or len(expression.generators) != 1:
        return None
    loop = expression.generators[0]
    if not isinstance(loop.target, ast.Name) or not isinstance(loop.iter, ast.Name) or loop.iter.id != argument or loop.ifs or loop.is_async:
        return None
    item = loop.target.id
    predicates = [f"not {item}.strip()", f"not isinstance({item}, str) or not {item}.strip()"]
    if ast.dump(expression.elt) not in {ast.dump(ast.parse(text, mode="eval").body) for text in predicates}:
        return None
    comparisons = [f"len({argument}) != len(set({argument}))", f"len(set({argument})) != len({argument})"]
    if ast.dump(body[1].test) in {ast.dump(ast.parse(text, mode="eval").body) for text in comparisons}:
        return "unique-nonblank"
    return None


def nonblank_guard(body, argument):
    if operation := reference_list_guard(body, argument):
        return operation
    if len(body) != 2 or not isinstance(body[-1], ast.Return):
        return None
    if ast.dump(body[-1].value) != ast.dump(ast.Name(id=argument, ctx=ast.Load())):
        return None
    guard = body[0]
    operation = "nonblank"
    if isinstance(guard, ast.For):
        if (
            guard.orelse
            or not isinstance(guard.iter, ast.Name)
            or guard.iter.id != argument
            or not isinstance(guard.target, ast.Name)
            or len(guard.body) != 1
        ):
            return None
        argument = guard.target.id
        guard = guard.body[0]
        operation = "list-nonblank"
    if not refusal_guard(guard):
        return None
    test = ast.dump(guard.test)
    plain = ast.dump(ast.parse(f"not {argument}.strip()", mode="eval").body)
    if test == plain:
        return operation
    typed = ast.dump(ast.parse(f"not isinstance({argument}, str) or not {argument}.strip()", mode="eval").body)
    if test == typed and operation == "nonblank":
        return operation
    nullable = ast.dump(
        ast.parse(f"{argument} is not None and not {argument}.strip()", mode="eval").body
    )
    if test == nullable and operation == "nonblank":
        return "nullable-nonblank"
    return None


def direct_rule(function):
    function = getattr(function, "__func__", function)
    if function in HELPERS:
        return HELPERS[function]
    if not inspect.isfunction(function):
        return None
    source, first_line = inspect.getsourcelines(function)
    tree = ast.parse(textwrap.dedent("".join(source)))
    declaration = tree.body[0]
    if function.__name__ == "<lambda>":
        candidates = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Lambda)
            and first_line + node.lineno - 1 == function.__code__.co_firstlineno
        ]
        if len(candidates) != 1:
            return None
        declaration = candidates[0]
    if not isinstance(declaration, (ast.FunctionDef, ast.Lambda)):
        return None
    parameters = [
        arg.arg for arg in declaration.args.args if arg.arg not in {"cls", "self"}
    ]
    if not parameters:
        return None
    argument = parameters[0]
    body = [ast.Return(value=declaration.body)] if isinstance(declaration, ast.Lambda) else declaration.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
    ):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return nonblank_guard(body, argument)
    value = body[0].value
    optional = isinstance(value, ast.IfExp) and isinstance(value.test, ast.Name)
    if optional:
        if (
            value.test.id != argument
            or not isinstance(value.orelse, ast.Name)
            or value.orelse.id != argument
        ):
            return None
        value = value.body
    if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
        return None
    if (
        not value.args
        or not isinstance(value.args[0], ast.Name)
        or value.args[0].id != argument
    ):
        return None
    helper = function.__globals__.get(value.func.id)
    operation = HELPERS.get(helper)
    return ("optional-" if optional else "") + operation if operation else None


def annotated_rule(schema):
    kind = schema.get("type")
    if kind == "function-after":
        operation = direct_rule(schema["function"].get("function"))
        inner = annotated_rule(schema["schema"])
        if operation and inner and operation != inner:
            raise ValueError(f"overlapping SDL field predicates: {operation}, {inner}")
        return operation or inner
    if kind in {"default", "function-before"}:
        return annotated_rule(schema["schema"])
    if kind == "nullable":
        operation = annotated_rule(schema["schema"])
        return "nullable-" + operation if operation else None
    if kind == "list":
        operation = annotated_rule(schema.get("items_schema", {}))
        return "list-" + operation if operation else None
    return None


def annotated_fields(cls):
    core = cls.__pydantic_core_schema__
    while core.get("type") != "model-fields":
        core = core.get("schema", {})
        if not core:
            return {}
    return {
        name: operation
        for name, field in core["fields"].items()
        if (operation := annotated_rule(field["schema"]))
    }


def records():
    result = {}
    for model, contract in (
        (Scenario, "sdl-authoring-input-v1"),
        (MaterializedScenario, "materialized-scenario-v1"),
    ):
        owners = []

        def generator(*args, **kwargs):
            owner = Constructors(*args, **kwargs)
            owners.append(owner)
            return owner

        schema = model.model_json_schema(schema_generator=generator)
        published = json.loads(
            (ROOT / "contracts/schemas/sdl" / (contract + ".json")).read_bytes()
        )
        for name, definition in schema.get("$defs", {}).items():
            if "x-constructor" not in definition:
                continue
            cls = owners[0].classes[definition["x-constructor"]]
            properties = published.get("$defs", {}).get(name, {}).get("properties", {})
            for field, operation in annotated_fields(cls).items():
                info = cls.model_fields[field]
                alias = info.serialization_alias or info.alias or field
                if alias in properties:
                    result.setdefault(name, {})[alias] = operation
            for validator in cls.__pydantic_decorators__.field_validators.values():
                operation = direct_rule(validator.func)
                if operation is None:
                    continue
                for field in validator.info.fields:
                    info = cls.model_fields[field]
                    alias = info.serialization_alias or info.alias or field
                    if alias in properties:
                        previous = result.setdefault(name, {}).setdefault(
                            alias, operation
                        )
                        if previous != operation:
                            raise ValueError(f"conflicting SDL field predicates: {name}.{alias}: {previous}, {operation}")
    return result


def record():
    return json.dumps(records(), indent=2, sort_keys=True) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "implementations/go/contract/admission/sdl-field-rules.json"
    actual = record()
    if args.check:
        if path.read_text() != actual:
            print("SDL field predicates differ from the reference", file=sys.stderr)
            return 1
    else:
        path.write_text(actual)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

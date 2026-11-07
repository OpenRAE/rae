#!/usr/bin/env python3
"""Record simple SDL field predicates as native compatibility data."""

from __future__ import annotations

import argparse
import ast
import inspect
import json
import sys
import textwrap
from pathlib import Path
from types import FunctionType
from typing import Any

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from parity_sdl_constructors import model_fields_schema, reference_definitions  # noqa: E402
from raes._identifiers import (  # noqa: E402
    require_portable_identifier,
    require_qualified_identifier,
)
from raes.materialization import MaterializedScenario  # noqa: E402
from raes.runtime_database import _require_object_name  # noqa: E402
from raes.runtime_values import absolute_path_or_var, require_non_empty, require_symbol  # noqa: E402
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


def refusal_guard(guard: ast.stmt) -> bool:
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


def argument_loop(node: ast.stmt, argument: str) -> bool:
    return (
        isinstance(node, ast.For)
        and not node.orelse
        and isinstance(node.iter, ast.Name)
        and node.iter.id == argument
        and isinstance(node.target, ast.Name)
        and len(node.body) == 1
    )


def expand_list_guards(body: list[ast.stmt], argument: str) -> list[ast.stmt]:
    if len(body) == 3 and isinstance(body[0], ast.For):
        loop = body[0]
        if not argument_loop(loop, argument) or not refusal_guard(loop.body[0]):
            return []
        guard = loop.body[0]
        test = ast.Call(
            func=ast.Name(id="any", ctx=ast.Load()),
            args=[
                ast.GeneratorExp(
                    elt=guard.test,
                    generators=[ast.comprehension(target=loop.target, iter=loop.iter, ifs=[], is_async=0)],
                )
            ],
            keywords=[],
        )
        body = [ast.If(test=test, body=guard.body, orelse=[]), *body[1:]]
    if len(body) == 2 and refusal_guard(body[0]):
        combined = body[0]
        if (
            isinstance(combined.test, ast.BoolOp)
            and isinstance(combined.test.op, ast.Or)
            and len(combined.test.values) == 2
        ):
            body = [ast.If(test=test, body=combined.body, orelse=[]) for test in combined.test.values] + [body[1]]
    return body


def returns_argument(node: ast.stmt, argument: str) -> bool:
    return isinstance(node, ast.Return) and isinstance(node.value, ast.Name) and node.value.id == argument


def any_generator(call: ast.expr) -> ast.GeneratorExp | None:
    if not (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "any"
        and not call.keywords
        and len(call.args) == 1
    ):
        return None
    expression = call.args[0]
    if isinstance(expression, ast.GeneratorExp) and len(expression.generators) == 1:
        return expression
    return None


def nonblank_generator(expression: ast.GeneratorExp, argument: str) -> bool:
    loop = expression.generators[0]
    if not (
        isinstance(loop.target, ast.Name)
        and isinstance(loop.iter, ast.Name)
        and loop.iter.id == argument
        and not loop.ifs
        and not loop.is_async
    ):
        return False
    item = loop.target.id
    predicates = [f"not {item}.strip()", f"not isinstance({item}, str) or not {item}.strip()"]
    return ast.dump(expression.elt) in {ast.dump(ast.parse(text, mode="eval").body) for text in predicates}


def reference_list_guard(body: list[ast.stmt], argument: str) -> str | None:
    body = expand_list_guards(body, argument)
    if (
        len(body) != 3
        or not all(refusal_guard(guard) for guard in body[:2])
        or not returns_argument(body[-1], argument)
    ):
        return None
    expression = any_generator(body[0].test)
    if expression is None or not nonblank_generator(expression, argument):
        return None
    comparisons = [f"len({argument}) != len(set({argument}))", f"len(set({argument})) != len({argument})"]
    result = None
    if ast.dump(body[1].test) in {ast.dump(ast.parse(text, mode="eval").body) for text in comparisons}:
        result = "unique-nonblank"
    return result


def scalar_nonblank_guard(guard: ast.stmt, argument: str, operation: str) -> str | None:
    result = None
    if refusal_guard(guard):
        predicates = {f"not {argument}.strip()": operation}
        if operation == "nonblank":
            predicates[f"not isinstance({argument}, str) or not {argument}.strip()"] = operation
            predicates[f"{argument} is not None and not {argument}.strip()"] = "nullable-nonblank"
        known = {ast.dump(ast.parse(text, mode="eval").body): value for text, value in predicates.items()}
        result = known.get(ast.dump(guard.test))
    return result


def nonblank_guard(body: list[ast.stmt], argument: str) -> str | None:
    if operation := reference_list_guard(body, argument):
        return operation
    if (
        len(body) != 2
        or not returns_argument(body[-1], argument)
        or (isinstance(body[0], ast.For) and not argument_loop(body[0], argument))
    ):
        return None
    guard = body[0]
    operation = "nonblank"
    if isinstance(guard, ast.For):
        argument = guard.target.id
        guard = guard.body[0]
        operation = "list-nonblank"
    return scalar_nonblank_guard(guard, argument, operation)


def function_declaration(function: FunctionType) -> ast.FunctionDef | ast.Lambda | None:
    source, first_line = inspect.getsourcelines(function)
    tree = ast.parse(textwrap.dedent("".join(source)))
    declaration = tree.body[0]
    if function.__name__ == "<lambda>":
        candidates = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Lambda) and first_line + node.lineno - 1 == function.__code__.co_firstlineno
        ]
        if len(candidates) != 1:
            return None
        declaration = candidates[0]
    if isinstance(declaration, (ast.FunctionDef, ast.Lambda)):
        return declaration
    return None


def argument_helper(value: ast.expr | None, argument: str) -> ast.Name | None:
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.args
        and isinstance(value.args[0], ast.Name)
        and value.args[0].id == argument
    ):
        return value.func
    return None


def returned_helper(value: ast.expr | None, argument: str, namespace: dict[str, Any]) -> str | None:
    optional = isinstance(value, ast.IfExp) and isinstance(value.test, ast.Name)
    if optional:
        if value.test.id != argument or not isinstance(value.orelse, ast.Name) or value.orelse.id != argument:
            return None
        value = value.body
    if (helper := argument_helper(value, argument)) is None:
        return None
    operation = HELPERS.get(namespace.get(helper.id))
    if operation and optional:
        operation = "optional-" + operation
    return operation


def declaration_rule(declaration: ast.FunctionDef | ast.Lambda, namespace: dict[str, Any]) -> str | None:
    parameters = [arg.arg for arg in declaration.args.args if arg.arg not in {"cls", "self"}]
    if not parameters:
        return None
    argument = parameters[0]
    body = [ast.Return(value=declaration.body)] if isinstance(declaration, ast.Lambda) else declaration.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    if len(body) == 1 and isinstance(body[0], ast.Return):
        return returned_helper(body[0].value, argument, namespace)
    return nonblank_guard(body, argument)


def direct_rule(function: object) -> str | None:
    function = getattr(function, "__func__", function)
    if function in HELPERS:
        return HELPERS[function]
    result = None
    if inspect.isfunction(function) and (declaration := function_declaration(function)) is not None:
        result = declaration_rule(declaration, function.__globals__)
    return result


def annotated_rule(schema: dict[str, Any]) -> str | None:
    kind = schema.get("type")
    operation = None
    if kind == "function-after":
        operation = direct_rule(schema["function"].get("function"))
        inner = annotated_rule(schema["schema"])
        if operation and inner and operation != inner:
            raise ValueError(f"overlapping SDL field predicates: {operation}, {inner}")
        operation = operation or inner
    elif kind in {"default", "function-before"}:
        operation = annotated_rule(schema["schema"])
    elif kind in {"nullable", "list"}:
        nested = schema["schema"] if kind == "nullable" else schema.get("items_schema", {})
        if inner := annotated_rule(nested):
            operation = kind + "-" + inner
    return operation


def annotated_fields(cls: type[BaseModel]) -> dict[str, str]:
    fields = model_fields_schema(cls)
    return {name: operation for name, field in fields.items() if (operation := annotated_rule(field["schema"]))}


def field_alias(cls: type[BaseModel], field: str) -> str:
    info = cls.model_fields[field]
    return info.serialization_alias or info.alias or field


def definition_rules(cls: type[BaseModel], properties: dict[str, Any], name: str) -> dict[str, str]:
    result = {
        field_alias(cls, field): operation
        for field, operation in annotated_fields(cls).items()
        if field_alias(cls, field) in properties
    }
    for validator in cls.__pydantic_decorators__.field_validators.values():
        operation = direct_rule(validator.func)
        if operation is not None:
            merge_validator(result, cls, properties, validator.info.fields, operation, name)
    return result


def merge_validator(
    result: dict[str, str],
    cls: type[BaseModel],
    properties: dict[str, Any],
    fields: tuple[str, ...],
    operation: str,
    name: str,
) -> None:
    for field in fields:
        alias = field_alias(cls, field)
        if alias in properties:
            previous = result.setdefault(alias, operation)
            if previous != operation:
                raise ValueError(f"conflicting SDL field predicates: {name}.{alias}: {previous}, {operation}")


def records() -> dict[str, Any]:
    result = {}
    for model, contract in ((Scenario, "sdl-authoring-input-v1"), (MaterializedScenario, "materialized-scenario-v1")):
        published = json.loads((ROOT / "contracts/schemas/sdl" / (contract + ".json")).read_bytes())
        for pointer, cls in reference_definitions(model).items():
            if pointer == "#":
                continue
            name = pointer.removeprefix("#/$defs/")
            properties = published.get("$defs", {}).get(name, {}).get("properties", {})
            for alias, operation in definition_rules(cls, properties, name).items():
                previous = result.setdefault(name, {}).setdefault(alias, operation)
                if previous != operation:
                    raise ValueError(f"conflicting SDL field predicates: {name}.{alias}: {previous}, {operation}")
    return result


def record() -> str:
    return json.dumps(records(), indent=2, sort_keys=True) + "\n"


def main() -> int:
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

"""Record SDL field presentation and scalar conversion facts from the reference.

The published schema defines field identity. This file does not generate or
replace a published schema. Production Go reads only the recorded JSON.
"""

from __future__ import annotations

import argparse
import ast
import inspect
from enum import Enum
from functools import partial
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from pydantic.json_schema import GenerateJsonSchema  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from raes.materialization import MaterializedScenario  # noqa: E402
from raes.scenario import Scenario  # noqa: E402

PRIMITIVES = {
    "normalize_enum_value": "normalize",
    "parse_enum_or_var": "enum",
    "parse_runtime_enum_or_var": "vocabulary",
    "parse_int_or_var": "integer",
    "parse_float_or_var": "number",
    "parse_bool_or_var": "boolean",
    "parse_optional_bool_or_var": "boolean",
    "parse_ram": "ram",
    "parse_duration": "duration",
    "coerce_string_list": "strings",
    "normalize_architecture": "architecture",
    "normalize_os_distribution": "distribution",
    "normalize_os_version": "os-version",
    "parse_limit_value": "limit",
    "parse_account_vocabulary": "account-vocabulary",
    "normalize_capability_name": "capability",
}


def reference_function(value: object) -> bool:
    """Follow only reference functions, never library or process callbacks."""
    return inspect.isfunction(value) and value.__module__.startswith(
        ("raes.", "raes_contracts.")
    )


def function_policy(function: object, seen: set | None = None) -> set[str]:
    if isinstance(function, partial):
        function = function.func
    function = getattr(function, "__func__", function)
    if not inspect.isfunction(function):
        return set()
    if function.__name__.lstrip("_") in PRIMITIVES:
        return {PRIMITIVES[function.__name__.lstrip("_")]}
    seen = set() if seen is None else seen
    if function in seen:
        return set()
    seen.add(function)
    result: set[str] = set()
    for name in function.__code__.co_names:
        if name.lstrip("_") in PRIMITIVES:
            result.add(PRIMITIVES[name.lstrip("_")])
        elif reference_function(nested := function.__globals__.get(name)):
            result.update(function_policy(nested, seen))
    return result


def numeric_argument(node: ast.expr, namespace: dict) -> str | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        value = namespace.get(node.id) if isinstance(node, ast.Name) else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def numeric_bounds(function: object, seen: set | None = None) -> dict[str, str]:
    if isinstance(function, partial):
        function = function.func
    function = getattr(function, "__func__", function)
    if not inspect.isfunction(function):
        return {}
    seen = set() if seen is None else seen
    if function in seen:
        return {}
    seen.add(function)
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    result: dict[str, str] = {}
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            continue
        for keyword in call.keywords:
            if keyword.arg in {"minimum", "maximum"}:
                if (
                    value := numeric_argument(keyword.value, function.__globals__)
                ) is not None:
                    result[keyword.arg] = value
        if reference_function(nested := function.__globals__.get(call.func.id)):
            result.update(numeric_bounds(nested, seen))
    return result


def enum_arguments(function: object, seen: set | None = None) -> set[type[Enum]]:
    """Record primitive enum arguments as values and governed scope IDs."""
    values = []
    if isinstance(function, partial):
        values.extend(function.args)
        values.extend((function.keywords or {}).values())
        function = function.func
    function = getattr(function, "__func__", function)
    if not inspect.isfunction(function):
        return set()
    seen = set() if seen is None else seen
    if function in seen:
        return set()
    seen.add(function)
    values.extend(function.__globals__.get(name) for name in function.__code__.co_names)
    values.extend(cell.cell_contents for cell in (function.__closure__ or ()))
    direct = {
        value
        for value in values
        if inspect.isclass(value) and issubclass(value, Enum) and list(value)
    }
    if direct:
        return direct
    result = set()
    for value in values:
        if reference_function(value):
            result.update(enum_arguments(value, seen))
    return result


def scalar_shapes(schema: dict) -> list[str]:
    kind = schema.get("type")
    if kind in {
        "default",
        "function-before",
        "function-after",
        "function-wrap",
        "nullable",
    }:
        return scalar_shapes(schema["schema"]) + (
            ["null"] if kind == "nullable" else []
        )
    if kind == "union":
        return [
            shape
            for choice in schema["choices"]
            for shape in scalar_shapes(
                choice[0] if isinstance(choice, tuple) else choice
            )
        ]
    names = {
        "int": "integer",
        "float": "number",
        "str": "string",
        "bool": "boolean",
        "none": "null",
    }
    return (
        [names[kind] + ("!" if schema.get("strict") else "")] if kind in names else []
    )


def scalar_plan(schema: dict) -> dict:
    kind = schema.get("type")
    result: dict = {}
    if kind in {
        "default",
        "function-before",
        "function-after",
        "function-wrap",
        "nullable",
    }:
        result = scalar_plan(schema["schema"])
        if kind == "function-after":
            function = schema["function"].get("function")
            if "capability" in function_policy(function):
                result["convert"] = sorted(
                    set(result.get("convert", [])) | {"capability"}
                )
        if kind == "function-before":
            function = schema["function"].get("function")
            if conversions := function_policy(function):
                result["convert"] = sorted(set(result.get("convert", [])) | conversions)
                if conversions & {"enum", "vocabulary", "account-vocabulary"}:
                    enums = enum_arguments(function)
                    members = {
                        item.value
                        for cls in enums
                        for item in cls
                        if isinstance(item.value, str)
                    }
                    if members:
                        result["members"] = sorted(members)
                    if "vocabulary" in conversions:
                        result["scopes"] = sorted(
                            "sdl.definitions." + cls.__name__ for cls in enums
                        )
            result.update(numeric_bounds(function))
    elif kind in {"list", "tuple", "set", "frozenset"}:
        item = schema.get("items_schema", {})
        if isinstance(item, dict) and (nested := scalar_plan(item)):
            result["items"] = nested
    elif kind == "dict":
        if nested := scalar_plan(schema.get("values_schema", {})):
            result["values"] = nested
    elif kind == "union":
        for raw in schema["choices"]:
            child = raw[0] if isinstance(raw, tuple) else raw
            result.update(
                {
                    key: value
                    for key, value in scalar_plan(child).items()
                    if key in {"items", "values"}
                }
            )
    if shapes := scalar_shapes(schema):
        result["shapes"] = sorted(set(shapes))
    return result


def conversion_fields(schema: dict, cls: type) -> dict:
    core = schema["schema"]
    while core.get("type") != "model-fields":
        core = core.get("schema", {})
        if not core:
            return {}
    result = {}
    for name, field in core["fields"].items():
        if plan := scalar_plan(field["schema"]):
            alias = (
                cls.model_fields[name].serialization_alias
                or cls.model_fields[name].alias
                or name
            )
            result[alias] = plan
    return result


def omission_policy(field: object) -> list[str]:
    result = ["always"] if field.exclude else []
    if field.exclude_if:
        for name, value in (
            ("null", None),
            ("empty", {}),
            ("empty-sequence", []),
            ("blank", ""),
            ("false", False),
        ):
            try:
                if field.exclude_if(value):
                    result.append(name)
            except (TypeError, ValueError, AttributeError):
                continue
    return result


class Layout(GenerateJsonSchema):
    """Attach non-schema metadata while the reference resolves definition IDs."""

    def model_schema(self, schema: dict) -> dict:
        document = super().model_schema(schema)
        cls = schema["cls"]
        fields = [
            field.serialization_alias or field.alias or name
            for name, field in cls.model_fields.items()
        ]
        omit = {
            field.serialization_alias or field.alias or name: policy
            for name, field in cls.model_fields.items()
            if (policy := omission_policy(field))
        }
        document["x-layout"] = {
            "fields": fields,
            "omit": omit,
            "scalar": conversion_fields(schema, cls),
            "factory_defaults": factory_defaults(cls),
        }
        return document


def factory_defaults(cls: type) -> dict:
    result = {}
    audited = {("ExecutionPolicy", "retry"), ("TimeDomainMapping", "scale"), ("TimeProgressionPolicy", "pacing_ratio")}
    for name, field in cls.model_fields.items():
        factory = field.default_factory
        if factory is None or field.exclude:
            continue
        if factory not in (list, dict) and (cls.__name__, name) not in audited:
            raise ValueError("SDL factory default requires an explicit audit")
        value = field.get_default(call_default_factory=True)
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json", by_alias=True)
        result[field.serialization_alias or field.alias or name] = value
    return result


def compact_plan(plan: dict) -> dict:
    result = {}
    for key, value in plan.items():
        if key in {"items", "values"}:
            if child := compact_plan(value):
                result[key] = child
        elif key != "shapes" or not set(value) <= {"string", "string!", "null"}:
            result[key] = value
    return result


def record() -> bytes:
    result = {}
    for contract, cls in (
        ("sdl-authoring-input-v1", Scenario),
        ("materialized-scenario-v1", MaterializedScenario),
    ):
        schema = cls.model_json_schema(schema_generator=Layout)
        records = {"#": schema["x-layout"]}
        records.update(
            {
                "#/$defs/" + name: value["x-layout"]
                for name, value in schema.get("$defs", {}).items()
                if "x-layout" in value
            }
        )
        published = json.loads(
            (ROOT / "contracts/schemas/sdl" / (contract + ".json")).read_bytes()
        )
        for pointer, row in records.items():
            definition = published
            for token in pointer.split("/")[1:]:
                definition = definition.get(token, {})
            fields = definition.get("properties", {})
            row["fields"] = [field for field in row["fields"] if field in fields]
            for key in ("omit", "scalar", "factory_defaults"):
                row[key] = {
                    field: value for field, value in row[key].items() if field in fields
                }
            row["scalar"] = {
                field: compact
                for field, plan in row["scalar"].items()
                if (compact := compact_plan(plan))
            }
        result[contract] = records
    authored = result["sdl-authoring-input-v1"]
    materialized = result["materialized-scenario-v1"]
    common = {
        key: value
        for key, value in authored.items()
        if key != "#" and materialized.get(key) == value
    }
    for key in common:
        del authored[key]
        del materialized[key]
    result["$shared"] = common
    return (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "implementations/go/internal/sdl/authoring/layout.json"
    encoded = record()
    if args.check:
        if target.read_bytes() != encoded:
            print(
                "SDL field compatibility metadata differs from the reference",
                file=sys.stderr,
            )
            return 1
    else:
        target.write_bytes(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

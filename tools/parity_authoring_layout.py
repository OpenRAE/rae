"""Record SDL field presentation and scalar conversion facts from the reference.

The published schema defines field identity. This file does not generate or
replace a published schema. Production Go reads only the recorded JSON.
"""

from __future__ import annotations

import argparse
import ast
import inspect
import json
import sys
import textwrap
from enum import Enum
from functools import partial
from pathlib import Path
from types import FunctionType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from pydantic import BaseModel  # noqa: E402
from pydantic.json_schema import GenerateJsonSchema  # noqa: E402
from pydantic_core import SchemaValidator, ValidationError  # noqa: E402
from raes.materialization import MaterializedScenario  # noqa: E402
from raes.scenario import ExpandedScenario, InstantiatedScenario, Scenario  # noqa: E402

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
    "normalize_http_method": "http-method",
}


def reference_function(value: object) -> bool:
    """Follow only reference functions, never library or process callbacks."""
    return inspect.isfunction(value) and value.__module__.startswith(("raes.", "raes_contracts."))


def function_policy(function: object, seen: set[object] | None = None) -> set[str]:
    if isinstance(function, partial):
        function = function.func
    function = getattr(function, "__func__", function)
    if not inspect.isfunction(function):
        return set()
    if function.__name__.lstrip("_") in PRIMITIVES:
        return {PRIMITIVES[function.__name__.lstrip("_")]}
    seen = set() if seen is None else seen
    return nested_policies(function, seen)


def nested_policies(function: FunctionType, seen: set[object]) -> set[str]:
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


def numeric_argument(node: ast.expr, namespace: dict[str, Any]) -> str | None:
    try:
        value = ast.literal_eval(node)
    except ValueError, TypeError:
        value = namespace.get(node.id) if isinstance(node, ast.Name) else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def numeric_bounds(function: object, seen: set[object] | None = None) -> dict[str, str]:
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
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
            result.update(call_bounds(call, function.__globals__, seen))
    return result


def call_bounds(call: ast.Call, namespace: dict[str, Any], seen: set[object]) -> dict[str, str]:
    result = {}
    for keyword in call.keywords:
        if keyword.arg in {"minimum", "maximum"}:
            if (value := numeric_argument(keyword.value, namespace)) is not None:
                result[keyword.arg] = value
    if reference_function(nested := namespace.get(call.func.id)):
        result.update(numeric_bounds(nested, seen))
    return result


def direct_enums(values: list[Any]) -> set[type[Enum]]:
    result = set()
    for value in values:
        if inspect.isclass(value) and issubclass(value, Enum) and list(value):
            result.add(value)
    return result


def enum_arguments(function: object, seen: set[object] | None = None) -> set[type[Enum]]:
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
    direct = direct_enums(values)
    if not direct:
        for value in values:
            if reference_function(value):
                direct.update(enum_arguments(value, seen))
    return direct


def scalar_shapes(schema: dict[str, Any]) -> list[str]:
    kind = schema.get("type")
    if kind in {
        "default",
        "function-before",
        "function-after",
        "function-wrap",
        "nullable",
    }:
        return scalar_shapes(schema["schema"]) + (["null"] if kind == "nullable" else [])
    if kind == "union":
        return [
            shape
            for choice in schema["choices"]
            for shape in scalar_shapes(choice[0] if isinstance(choice, tuple) else choice)
        ]
    names = {
        "int": "integer",
        "float": "number",
        "str": "string",
        "bool": "boolean",
        "none": "null",
    }
    result = []
    if kind in names:
        result = [names[kind] + ("!" if schema.get("strict") else "")]
    return result


def conversion_plan(function: object, result: dict[str, Any]) -> None:
    conversions = function_policy(function)
    if conversions:
        result["convert"] = sorted(set(result.get("convert", [])) | conversions)
        if conversions & {"enum", "vocabulary", "account-vocabulary"}:
            enum_plan(function, conversions, result)
    result.update(numeric_bounds(function))


def enum_plan(function: object, conversions: set[str], result: dict[str, Any]) -> None:
    enums = enum_arguments(function)
    members = {item.value for cls in enums for item in cls if isinstance(item.value, str)}
    if members:
        result["members"] = sorted(members)
    if "vocabulary" in conversions:
        result["scopes"] = sorted("sdl.definitions." + cls.__name__ for cls in enums)


def wrapper_plan(schema: dict[str, Any]) -> dict[str, Any]:
    result = scalar_plan(schema["schema"])
    kind = schema["type"]
    if kind == "function-after":
        function = schema["function"].get("function")
        conversions = function_policy(function) & {"capability", "http-method"}
        if conversions:
            result["convert"] = sorted(set(result.get("convert", [])) | conversions)
        if "http-method" in conversions:
            result["members"] = sorted(function.__globals__["_HTTP_METHODS"])
    if kind == "function-before":
        conversion_plan(schema["function"].get("function"), result)
    return result


def container_plan(schema: dict[str, Any]) -> dict[str, Any]:
    result = {}
    kind = schema["type"]
    if kind in {"list", "tuple", "set", "frozenset"}:
        item = schema.get("items_schema", {})
        if isinstance(item, dict) and (nested := scalar_plan(item)):
            result["items"] = nested
    elif kind == "dict":
        if nested := scalar_plan(schema.get("values_schema", {})):
            result["values"] = nested
    elif kind == "union":
        for raw in schema["choices"]:
            child = raw[0] if isinstance(raw, tuple) else raw
            result.update({key: value for key, value in scalar_plan(child).items() if key in {"items", "values"}})
    return result


def scalar_plan(schema: dict[str, Any]) -> dict[str, Any]:
    kind = schema.get("type")
    result: dict[str, Any] = {}
    if kind in {
        "default",
        "function-before",
        "function-after",
        "function-wrap",
        "nullable",
    }:
        result = wrapper_plan(schema)
    else:
        result = container_plan(schema)
    if shapes := scalar_shapes(schema):
        result["shapes"] = sorted(set(shapes))
    return result


def visitor_plan(schema: dict[str, Any]) -> dict[str, Any]:
    """Record reference visitor distinctions that JSON alone does not retain."""
    definitions = {
        item["ref"]: item
        for model in (Scenario, MaterializedScenario)
        for item in model.__pydantic_core_schema__.get("definitions", [])
    }
    validator = SchemaValidator(
        {
            "type": "definitions",
            "schema": schema,
            "definitions": list(definitions.values()),
        }
    )
    sentinels = []
    for token in ("unknown", "other"):
        try:
            value = validator.validate_python(token)
        except ValidationError, ValueError, TypeError:
            continue
        if isinstance(value, Enum):
            sentinels.append(token)
    result = {"explicitness_enums": sentinels} if sentinels else {}
    while schema.get("type") in {
        "default",
        "nullable",
        "function-before",
        "function-after",
        "function-wrap",
    }:
        schema = schema["schema"]
    kind = schema.get("type")
    if kind in {"tuple", "set", "frozenset"}:
        result["explicitness_atomic"] = True
    elif kind == "list" and (child := visitor_plan(schema.get("items_schema", {"type": "any"}))):
        result["items"] = child
    elif kind == "dict" and (child := visitor_plan(schema.get("values_schema", {"type": "any"}))):
        result["values"] = child
    return result


def merge_plan(target: dict[str, Any], extra: dict[str, Any]) -> None:
    for name, value in extra.items():
        if name in {"items", "values"}:
            merge_plan(target.setdefault(name, {}), value)
        else:
            target[name] = value


def conversion_fields(schema: dict[str, Any], cls: type[BaseModel]) -> dict[str, Any]:
    core = schema["schema"]
    while core.get("type") != "model-fields":
        core = core.get("schema", {})
        if not core:
            return {}
    result = {}
    for name, field in core["fields"].items():
        plan = scalar_plan(field["schema"])
        merge_plan(plan, visitor_plan(field["schema"]))
        if plan:
            alias = cls.model_fields[name].serialization_alias or cls.model_fields[name].alias or name
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
            except TypeError, ValueError, AttributeError:
                continue
    return result


class Layout(GenerateJsonSchema):
    """Attach non-schema metadata while the reference resolves definition IDs."""

    def model_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        document = super().model_schema(schema)
        cls = schema["cls"]
        fields = [field.serialization_alias or field.alias or name for name, field in cls.model_fields.items()]
        omit = {
            field.serialization_alias or field.alias or name: policy
            for name, field in cls.model_fields.items()
            if (policy := omission_policy(field))
        }
        document["x-layout"] = {
            "model_type": cls.__name__,
            "native_sdl": cls.__module__.startswith("raes."),
            "fields": fields,
            "omit": omit,
            "scalar": conversion_fields(schema, cls),
            "factory_defaults": factory_defaults(cls),
        }
        model_names = {
            field.serialization_alias or field.alias or name: name
            for name, field in cls.model_fields.items()
            if (field.serialization_alias or field.alias or name) != name
        }
        if model_names:
            document["x-layout"]["model_names"] = model_names
        if any(name.endswith(("classification", "sensitivity")) for name in cls.model_fields):
            document["x-layout"]["capability_classified"] = True
        public = sorted(getattr(cls, "realization_public_parameter_fields", ()))
        if public:
            document["x-layout"]["capability_public"] = public
        return document


def factory_defaults(cls: type[BaseModel]) -> dict[str, Any]:
    result = {}
    audited = {
        ("ExecutionPolicy", "retry"),
        ("TimeDomainMapping", "scale"),
        ("TimeProgressionPolicy", "pacing_ratio"),
        ("ExpandedScenario", "expansion_provenance"),
    }
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


def compact_plan(plan: dict[str, Any]) -> dict[str, Any]:
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
        ("sdl-expanded-authoring-object-v1", ExpandedScenario),
        ("instantiated-scenario-v1", InstantiatedScenario),
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
        if cls is InstantiatedScenario:
            # The phase owner's wrap serializer omits absent trial provenance.
            records["#/$defs/InstantiationProvenance"]["omit"]["trial"] = ["null"]
        published = (
            schema
            if cls is ExpandedScenario
            else json.loads((ROOT / "contracts/schemas/sdl" / (contract + ".json")).read_bytes())
        )
        filter_records(records, published)
        result[contract] = records
    authored = result["sdl-authoring-input-v1"]
    materialized = result["materialized-scenario-v1"]
    common = {key: value for key, value in authored.items() if key != "#" and materialized.get(key) == value}
    for key in common:
        del authored[key]
        del materialized[key]
    result["$shared"] = common
    expanded = result["sdl-expanded-authoring-object-v1"]
    result["sdl-expanded-authoring-object-v1"] = {
        key: value for key, value in expanded.items() if key == "#" or value != authored.get(key, common.get(key))
    }
    instantiated = result["instantiated-scenario-v1"]
    result["instantiated-scenario-v1"] = {
        key: value for key, value in instantiated.items() if key == "#" or value != authored.get(key, common.get(key))
    }
    return (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()


def filter_records(records: dict[str, Any], published: dict[str, Any]) -> None:
    for pointer, row in records.items():
        definition = published
        for token in pointer.split("/")[1:]:
            definition = definition.get(token, {})
        fields = definition.get("properties", {})
        row["fields"] = [field for field in row["fields"] if field in fields]
        for key in ("omit", "scalar", "factory_defaults"):
            row[key] = {field: value for field, value in row[key].items() if field in fields}
        if "model_names" in row:
            row["model_names"] = {field: name for field, name in row["model_names"].items() if field in fields}
        row["scalar"] = {field: compact for field, plan in row["scalar"].items() if (compact := compact_plan(plan))}


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

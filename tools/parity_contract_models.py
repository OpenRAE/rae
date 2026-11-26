"""Resolve each published contract to the reference root model that contributes its schema."""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path
from types import ModuleType

from pydantic import BaseModel, TypeAdapter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

import raes  # noqa: E402
import raes_contracts  # noqa: E402
import raes_processor  # noqa: E402
from raes_contracts.published_schemas import published_contract_ids, published_schema  # noqa: E402


def _modules() -> list[ModuleType]:
    modules = []
    for package in (raes_contracts, raes, raes_processor):
        for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            modules.append(importlib.import_module(info.name))
    return modules


def _model(module: ModuleType, value: ast.expr) -> type[BaseModel] | None:
    """Resolve ``Model`` or ``Model.model_json_schema()`` in a module namespace."""
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == "model_json_schema":
        value = value.func.value
    if isinstance(value, ast.Name):
        model = getattr(module, value.id, None)
        if isinstance(model, type) and issubclass(model, BaseModel):
            return model
    return None


def _contributions(
    module: ModuleType,
) -> tuple[dict[str, type[BaseModel]], dict[str, type[BaseModel]]]:
    """Return the contract ids that a module maps to a model, and to an event stream of a model."""
    try:
        tree = ast.parse(inspect.getsource(module))
    except OSError, TypeError:
        return {}, {}
    models: dict[str, type[BaseModel]] = {}
    streams: dict[str, type[BaseModel]] = {}
    for key, value in _string_keyed_entries(tree):
        if _is_event_stream(value):
            target, item = streams, _model(module, value.args[1])
        else:
            target, item = models, _model(module, value)
        if item is not None:
            target.setdefault(key, item)
    return models, streams


def _string_keyed_entries(tree: ast.AST) -> list[tuple[str, ast.expr]]:
    """Return every string-keyed entry of every dictionary display in a module."""
    return [
        (key.value, value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values, strict=True)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    ]


def _is_event_stream(value: ast.expr) -> bool:
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "event_stream_schema"
        and len(value.args) == 2
    )


@cache
def contract_validators() -> dict[str, Callable[[object], object]]:
    """Return the reference validation of each published contract.

    A contract whose schema title names one reference model uses it. Otherwise the
    schema contribution that maps the contract id to a model, or to an event stream
    of a model, decides.
    """
    by_name: dict[str, set[type[BaseModel]]] = {}
    models: dict[str, type[BaseModel]] = {}
    streams: dict[str, type[BaseModel]] = {}
    for module in _modules():
        for value in vars(module).values():
            if inspect.isclass(value) and issubclass(value, BaseModel):
                by_name.setdefault(value.__name__, set()).add(value)
        named, streamed = _contributions(module)
        for contract_id, model in named.items():
            models.setdefault(contract_id, model)
        for contract_id, model in streamed.items():
            streams.setdefault(contract_id, model)
    validators: dict[str, Callable[[object], object]] = {}
    for contract_id in sorted(published_contract_ids()):
        validator = _validator(contract_id, by_name, models.get(contract_id), streams.get(contract_id))
        if validator is not None:
            validators[contract_id] = validator
    return validators


def _validator(
    contract_id: str,
    by_name: dict[str, set[type[BaseModel]]],
    contributed: type[BaseModel] | None,
    stream: type[BaseModel] | None,
) -> Callable[[object], object] | None:
    """Select the event stream, the titled contribution, the one titled model, or the contribution."""
    title = published_schema(contract_id).get("title")
    candidates = by_name.get(title, set()) if isinstance(title, str) else set()
    if stream is not None:
        return TypeAdapter(list[stream]).validate_python  # type: ignore[valid-type]
    if contributed is not None and contributed.__name__ != title and len(candidates) == 1:
        contributed = None
    if contributed is None and len(candidates) == 1:
        contributed = next(iter(candidates))
    return contributed.model_validate if contributed is not None else None


def contract_validator(contract_id: str) -> Callable[[object], object]:
    validator = contract_validators().get(contract_id)
    if validator is None:
        raise ValueError(f"{contract_id} has no reference root model")
    return validator


def contract_model(contract_id: str) -> type[BaseModel]:
    """Return the root model of an object contract."""
    validator = contract_validator(contract_id)
    model = getattr(validator, "__self__", None)
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise ValueError(f"{contract_id} has no reference root model")
    return model

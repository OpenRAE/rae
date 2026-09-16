"""Audit coverage follows the real runtime graph; it is not semantic approval."""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import get_args

import pytest
from pydantic import BaseModel
from raes._runtime_service_family_registry import RUNTIME_SERVICE_FAMILIES
from raes.runtime_configuration import RuntimeConfiguration
from raes.runtime_service_units import ServiceManagerUnit

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "docs/research/language-extensibility/product-semantics-fields.md"
CATEGORIES = frozenset("PCKBANROD")


def _types(annotation):
    yield annotation
    for child in get_args(annotation):
        yield from _types(child)


def _models():
    pending = [ServiceManagerUnit]
    for family in RUNTIME_SERVICE_FAMILIES:
        pending.extend(_types(RuntimeConfiguration.model_fields[family.collection_name].annotation))
    found = {}
    while pending:
        model = pending.pop()
        if not isinstance(model, type) or not issubclass(model, BaseModel):
            continue
        if model.__name__ in found:
            assert found[model.__name__] is model, "ambiguous audit model name"
            continue
        found[model.__name__] = model
        for field in model.model_fields.values():
            pending.extend(_types(field.annotation))
    return found


def _rows(text):
    rows = {}
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        _, name, source, assignments, _ = line.split("|")
        name = name.strip().strip("`")
        assert name not in rows, f"duplicate audit model: {name}"
        link = re.fullmatch(r"\[[^]]+\]\(([^)]+)\)", source.strip())
        assert link is not None, f"missing model source: {name}"
        fields = {}
        for group in assignments.strip().split("; "):
            category, names = group.split(": ", 1)
            assert category in CATEGORIES, f"unknown audit category: {category}"
            for token in names.split(", "):
                assert re.fullmatch(r"`[a-z_][a-z_0-9]*`", token), token
                field = token.strip("`")
                assert field not in fields, f"duplicate audit field: {name}.{field}"
                fields[field] = category
        rows[name] = (link.group(1), fields)
    return rows


def _check_coverage(rows, models):
    assert rows.keys() == models.keys(), "runtime audit model coverage drift"
    for name, model in models.items():
        source, fields = rows[name]
        assert fields.keys() == model.model_fields.keys(), f"runtime audit field coverage drift: {name}"
        assert (LEDGER.parent / source).resolve() == Path(inspect.getfile(model)), name


def test_audit_classifies_every_reachable_runtime_field_once():
    assert LEDGER.is_file(), "runtime semantic audit field ledger is missing"
    _check_coverage(_rows(LEDGER.read_text(encoding="utf-8")), _models())


@pytest.mark.parametrize("mutation", ["missing_model", "missing_field", "extra_field", "wrong_source"])
def test_audit_coverage_rejects_incomplete_or_stale_records(mutation):
    rows = _rows(LEDGER.read_text(encoding="utf-8"))
    model = "RuntimePlatformApplication"
    source, fields = rows[model]
    if mutation == "missing_model":
        del rows[model]
    elif mutation == "missing_field":
        del fields["capabilities"]
    elif mutation == "extra_field":
        fields["unreviewed_field"] = "C"
    else:
        rows[model] = ("../../../specs/sdl/runtime-inventory.md", fields)
    with pytest.raises(AssertionError):
        _check_coverage(rows, _models())


@pytest.mark.parametrize(
    "assignment",
    ["P: `field`; C: `field`", "X: `field`", "P: field"],
)
def test_audit_rows_reject_ambiguous_classification(assignment):
    with pytest.raises(AssertionError):
        _rows(f"| `Model` | [source](source.py) | {assignment} |")

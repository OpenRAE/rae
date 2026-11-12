"""Generic compiler primitives: serialization, address rendering, dedup helpers."""

from typing import Any

from raes_contracts.addressing import render_compiled_address


def _dump(model: object) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json", by_alias=True)
    if isinstance(model, dict):
        return dict(model)
    return {}


def _address(*parts: str) -> str:
    return render_compiled_address(*parts)


def _dedupe(items: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _dedupe_by_value(items: list[Any]) -> tuple[Any, ...]:
    ordered: dict[str, Any] = {}
    for item in items:
        key = getattr(item, "value", repr(item))
        ordered.setdefault(key, item)
    return tuple(item for _, item in sorted(ordered.items()))

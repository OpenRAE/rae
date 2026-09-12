"""Compatibility facade for the GitHub Actions tooling policy authority."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import product
from typing import Any

from implementations.tooling.action_policy_main import action_failures
from implementations.tooling.action_policy_matrix import matrix_rows, runner_profiles


def _matrix_rows(job: Mapping[str, Any]) -> tuple[list[dict[str, object]], bool]:
    """Retain the private test seam while the implementation lives under implementations/."""

    return matrix_rows(job, product_values=product)


def _runner_profiles(
    job: Mapping[str, Any],
) -> tuple[str, list[tuple[str, dict[str, object]]], bool]:
    """Retain the private runner-expansion test seam."""

    return runner_profiles(job, product_values=product)


__all__ = ("action_failures",)

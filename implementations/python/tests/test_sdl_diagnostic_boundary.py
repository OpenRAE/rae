"""Executable drift guard for the SDL error-vs-advisory diagnostic boundary.

``specs/sdl/diagnostics.md`` §5 states the normative classification criterion:
an **error** is a condition that affects SDL *meaning* (structural/semantic
invariants), while an **advisory** is a non-fatal deployability or quality
heuristic that leaves SDL meaning intact. The reference ``SemanticValidator``
keeps the two diagnostic channels structurally separate:

- error passes are ``_verify_*`` methods that call ``self._err(...)``;
- advisory passes are ``_warn_*`` methods that call ``self._warn(...)``,
  registered exactly once each in ``_collect_advisories()``, which
  ``validate()`` invokes after the error passes.

This lint makes that convention executable so a new pass cannot silently emit an
advisory from an error pass (or an error from the advisory seam) -- the
inconsistency review IMP-3 (issue #505) set out to prevent. It mirrors the
AST-introspection style of ``test_runtime_family_invariants.py`` and keeps its
negative path executable via a synthetic violating fixture, rather than
inventing a new validator framework or diagnostic registry for one advisory
pass.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest
import raes.validator as validator_module


def _all_class_methods(source: str) -> dict[str, ast.AST]:
    """Collect every method from every class in ``source``.

    The reference ``SemanticValidator`` is composed from per-seam mixin classes
    split across the ``raes.validator`` package (issue #42), so the boundary
    lint aggregates methods across all classes in the source rather than a single
    ``SemanticValidator`` ClassDef. Method names are unique across the mixins, so
    a flat name->node map faithfully reconstructs the composed method set.
    """
    tree = ast.parse(source)
    methods: dict[str, ast.AST] = {}
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for node in cls.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods[node.name] = node
    return methods


def _calls_self_method(func: ast.AST, name: str) -> bool:
    """True when ``func`` contains a ``self.<name>(...)`` call."""

    for sub in ast.walk(func):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == name
            and isinstance(sub.func.value, ast.Name)
            and sub.func.value.id == "self"
        ):
            return True
    return False


def _self_methods_called(func: ast.AST) -> set[str]:
    """Names of every ``self.<method>(...)`` call made inside ``func``."""

    called: set[str] = set()
    for sub in ast.walk(func):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and isinstance(sub.func.value, ast.Name)
            and sub.func.value.id == "self"
        ):
            called.add(sub.func.attr)
    return called


def find_advisory_boundary_violations(source: str) -> set[str]:
    """Return the advisory/error channel-separation violations in ``source``.

    Pure over ``source`` so the negative path is executable against synthetic
    input (see ``test_lint_detects_synthetic_violations``). Each violation is a
    short ``<kind>:<method>`` key so a failure names the offending site.
    """

    methods = _all_class_methods(source)
    violations: set[str] = set()

    for name, func in methods.items():
        is_advisory_pass = name == "_collect_advisories" or name.startswith("_warn_")
        emits_advisory = _calls_self_method(func, "_warn")
        emits_error = _calls_self_method(func, "_err")

        # Rule 1: advisories may only be emitted from a ``_warn_*`` advisory pass.
        if emits_advisory and not name.startswith("_warn_"):
            violations.add(f"warn-outside-advisory-pass:{name}")
        # Rule 2: advisory passes never emit errors.
        if is_advisory_pass and emits_error:
            violations.add(f"err-in-advisory-pass:{name}")

    # Rule 3: every ``_warn_*`` pass is registered in ``_collect_advisories()``.
    collect = methods.get("_collect_advisories")
    if collect is None:
        violations.add("missing-collect-advisories")
    else:
        registered = _self_methods_called(collect)
        for name in methods:
            if name.startswith("_warn_") and name not in registered:
                violations.add(f"unregistered-advisory-pass:{name}")

    # Rule 4: ``validate()`` invokes ``_collect_advisories()`` after the passes.
    validate = methods.get("validate")
    if validate is None or not _calls_self_method(validate, "_collect_advisories"):
        violations.add("collect-advisories-not-invoked-in-validate")

    # Rule 5: a ``_warn_*`` advisory pass may only be *invoked* from
    # ``_collect_advisories()``. An error pass that calls a ``_warn_*`` method
    # emits an advisory indirectly -- Rule 1 only sees a direct ``self._warn``
    # call, so without this rule a ``_verify_*`` pass could route an advisory
    # through a helper and slip past the guard.
    for name, func in methods.items():
        if name == "_collect_advisories":
            continue
        if any(called.startswith("_warn_") for called in _self_methods_called(func)):
            violations.add(f"advisory-pass-invoked-outside-collect:{name}")

    return violations


def test_validator_advisory_error_channels_are_separated() -> None:
    """The live ``SemanticValidator`` honours the diagnostics.md boundary.

    ``raes.validator`` is a package (issue #42), so concatenate every
    module's source and let the lint aggregate methods across the mixin classes
    that compose ``SemanticValidator``.
    """

    package_dir = Path(validator_module.__file__).parent
    source = "\n".join(path.read_text() for path in sorted(package_dir.glob("*.py")))
    assert find_advisory_boundary_violations(source) == set()


# A synthetic class that violates every rule, so the negative path of the lint
# stays executable (cf. ``GuardlessProfileKind`` in test_runtime_family_invariants).
_SYNTHETIC_VIOLATING_SOURCE = """
class SemanticValidator:
    def validate(self):
        self._verify_nodes()
        self._verify_indirect()
        # _collect_advisories() intentionally not invoked here.

    def _verify_nodes(self):
        self._warn("advisory emitted directly from an error pass")

    def _verify_indirect(self):
        self._warn_registered()  # advisory pass invoked outside _collect_advisories

    def _collect_advisories(self):
        self._warn_registered()
        self._err("error emitted from the advisory seam")

    def _warn_registered(self):
        self._warn("registered advisory, but also reached from an error pass")

    def _warn_orphan(self):
        self._warn("never registered in _collect_advisories")
"""


def test_lint_detects_synthetic_violations() -> None:
    """Each rule fires on a known-bad fixture (the lint has teeth)."""

    violations = find_advisory_boundary_violations(_SYNTHETIC_VIOLATING_SOURCE)
    assert "warn-outside-advisory-pass:_verify_nodes" in violations
    assert "err-in-advisory-pass:_collect_advisories" in violations
    assert "unregistered-advisory-pass:_warn_orphan" in violations
    assert "collect-advisories-not-invoked-in-validate" in violations
    assert "advisory-pass-invoked-outside-collect:_verify_indirect" in violations


def test_load_scenario_returns_advisories_without_logging_their_content(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Advisories reach the caller on the scenario; the log keeps only counts (ADR-116 rules E8, L3, L6)."""

    from raes.scenarios import load_scenario

    path = tmp_path / "scenario.yaml"
    path.write_text(
        "name: advisory-scenario\nnodes:\n  secret-node-name: {type: compute, os: linux}\n", encoding="utf-8"
    )
    with caplog.at_level(logging.DEBUG, logger="raes.scenarios"):
        scenario = load_scenario(path)

    assert len(scenario.advisories) == 1
    records = [record for record in caplog.records if record.name == "raes.scenarios"]
    assert [record.levelno for record in records] == [logging.INFO]
    assert "secret-node-name" not in records[0].getMessage()
    assert "with 1 advisories and 0 source diagnostics" in records[0].getMessage()

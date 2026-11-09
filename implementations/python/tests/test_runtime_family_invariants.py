"""Executable cross-family structural invariant lint for runtime service families.

Enforces the single structural invariant set required by DSL-139 (consistency
epic Brad-Edwards/raes#439 and children #442 / #443 / #444): every registered
runtime service family must use a ``Runtime<Noun>`` model class, a
``singular(collection_name) + "_id"`` primary identifier field, and a plural
typed-child container registered through ``_runtime_service_families``.

The remaining pre-existing violations are tracked explicitly in
``KNOWN_VIOLATIONS`` and driven to empty as the existing families are
reconciled. The point of this lint is the *drift* guarantee: any **new**
family that violates an invariant, or any reconciliation that resolves a
violation without updating this allowlist, fails the suite immediately. When
``KNOWN_VIOLATIONS`` is empty the invariant set is fully enforced for the whole
surface, old and new.
"""

from __future__ import annotations

import ast
import enum
import importlib
import inspect
import pkgutil
import types
import typing
from pathlib import Path

import raes
from pydantic import Field
from raes import _runtime_service_families as rsf
from raes.runtime_configuration import RuntimeConfiguration
from raes.runtime_directory_identity import RuntimeIdentityRelationshipKind
from raes_contracts.runtime_values import parse_runtime_enum_or_var
from raes_contracts.sdl_model import SDLModel
from raes_contracts.variable_references import parse_enum_or_var


def _singularize(plural: str) -> str:
    """Mechanical singular of a runtime container collection name."""

    if plural.endswith("ies"):
        return plural[:-3] + "y"
    if plural.endswith("s"):
        return plural[:-1]
    return plural


def _element_model(collection_name: str) -> type | None:
    """Return the element model class for a ``list[X]`` runtime container field."""

    field = RuntimeConfiguration.model_fields.get(collection_name)
    if field is None:
        return None
    args = typing.get_args(field.annotation)
    return args[0] if args else None


def _current_violations() -> set[str]:
    """Compute the live set of structural-invariant violations across families."""

    violations: set[str] = set()
    for family in rsf.RUNTIME_SERVICE_FAMILIES:
        model = _element_model(family.collection_name)
        if model is None or not model.__name__.startswith("Runtime"):
            violations.add(f"class-name:{family.key}")
        expected_id = _singularize(family.collection_name) + "_id"
        if family.id_field != expected_id:
            violations.add(f"primary-id:{family.key}")
    config_fields = set(RuntimeConfiguration.model_fields)
    if "process" in config_fields and "processes" in config_fields:
        violations.add("scalar-twin:runtime_configuration.process")
    return violations


# Pre-existing violations as of the start of the DSL-139 reconciliation. Each
# entry is removed in the same commit that resolves it; an empty set means the
# whole surface satisfies the invariant set.
KNOWN_VIOLATIONS: set[str] = set()

KNOWN_PROFILE_GUARD_VIOLATIONS: set[str] = set()


class GuardlessProfileKind(str, enum.Enum):
    """Open discriminator for the synthetic required-profile lint target.

    The ``example_kind`` discriminator selects a required profile; the class is
    intentionally missing the matching guard so the lint's negative path stays
    executable.
    """

    CONCRETE = "concrete"
    UNKNOWN = "unknown"
    OTHER = "other"


class GuardlessProfileChild(SDLModel):
    """Synthetic profile-bearing child for the guardless lint target."""

    child_id: str


class GuardlessDiscriminatedRuntimeSpine(SDLModel):
    """Synthetic discriminated runtime spine with no required-profile guard.

    The ``example_kind`` discriminator selects a required profile from
    ``profile_children``.
    """

    example_id: str
    example_kind: GuardlessProfileKind | str = GuardlessProfileKind.UNKNOWN
    profile_children: list[GuardlessProfileChild] = Field(default_factory=list)


def _union_args(annotation: object) -> tuple[object, ...]:
    """Return union members, or the annotation itself for non-unions."""

    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return typing.get_args(annotation)
    return (annotation,)


def _enum_or_str(annotation: object) -> type[enum.Enum] | None:
    """Return the enum from an ``Enum | str`` annotation, if present."""

    args = _union_args(annotation)
    enum_args = [arg for arg in args if isinstance(arg, type) and issubclass(arg, enum.Enum)]
    if len(enum_args) == 1 and str in args:
        return enum_args[0]
    return None


def _is_open_runtime_enum(enum_cls: type[enum.Enum]) -> bool:
    """Return whether the enum carries the runtime open-taxonomy sentinels."""

    values = {member.value for member in enum_cls}
    return {"unknown", "other"} <= values


def _sdl_model_types(annotation: object) -> tuple[type[SDLModel], ...]:
    """Return SDLModel types nested under list/optional annotations."""

    origin = typing.get_origin(annotation)
    if origin is list:
        args = typing.get_args(annotation)
        return _sdl_model_types(args[0]) if args else ()
    if origin in (typing.Union, types.UnionType):
        found: list[type[SDLModel]] = []
        for arg in typing.get_args(annotation):
            if arg is type(None):
                continue
            found.extend(_sdl_model_types(arg))
        return tuple(found)
    if isinstance(annotation, type) and issubclass(annotation, SDLModel):
        return (annotation,)
    return ()


def _runtime_configuration_models() -> tuple[type[SDLModel], ...]:
    """Return the runtime models discovered from ``RuntimeConfiguration``."""

    models: list[type[SDLModel]] = []
    seen: set[type[SDLModel]] = set()
    for field in RuntimeConfiguration.model_fields.values():
        for model in _sdl_model_types(field.annotation):
            if model in seen:
                continue
            seen.add(model)
            models.append(model)
    return tuple(models)


def _has_profile_bearing_sibling(model: type[SDLModel], discriminator_field: str) -> bool:
    """A profile discriminator must select between sibling structured fields."""

    for field_name, field in model.model_fields.items():
        if field_name == discriminator_field:
            continue
        if _sdl_model_types(field.annotation):
            return True
    return False


def _required_profile_signal(model: type[SDLModel], enum_cls: type[enum.Enum], field_name: str) -> bool:
    """Return whether docs declare that ``field_name`` selects a profile.

    The detector is intentionally structural plus documented-signal based:
    many runtime enum-or-string fields are product taxonomies, not profile
    selectors. A required-profile discriminator is one whose model/enum/module
    documentation calls it a discriminator and ties it to a required profile.
    """

    module = importlib.import_module(model.__module__)
    docs = "\n".join(
        text
        for text in (
            inspect.getdoc(module),
            inspect.getdoc(enum_cls),
            inspect.getdoc(model),
        )
        if text
    ).lower()
    guard_name = f"require_profile_for_{field_name}"
    discriminator_terms = (
        f"{field_name} discriminator",
        f"`{field_name}` discriminator",
        f"``{field_name}`` discriminator",
    )
    return (guard_name in docs or any(term in docs for term in discriminator_terms)) and (
        "required profile" in docs or guard_name in docs
    )


def _required_profile_discriminators(
    models: typing.Iterable[type[SDLModel]],
) -> tuple[tuple[type[SDLModel], str], ...]:
    """Return runtime models whose discriminator is documented as profile-selecting."""

    found: list[tuple[type[SDLModel], str]] = []
    for model in models:
        for field_name, field in model.model_fields.items():
            enum_cls = _enum_or_str(field.annotation)
            if enum_cls is None:
                continue
            if not _is_open_runtime_enum(enum_cls):
                continue
            if not _has_profile_bearing_sibling(model, field_name):
                continue
            if not _required_profile_signal(model, enum_cls, field_name):
                continue
            found.append((model, field_name))
    return tuple(found)


def _registered_after_model_validator_calls(model: type[SDLModel], guard_name: str) -> bool:
    """Return whether Pydantic registered an after-validator invoking ``guard_name``."""

    decorators = getattr(model, "__pydantic_decorators__", None)
    model_validators = getattr(decorators, "model_validators", {})
    for validator in model_validators.values():
        info = getattr(validator, "info", None)
        if getattr(info, "mode", None) != "after":
            continue
        if getattr(validator, "cls_var_name", "") == guard_name:
            return True
        func = getattr(validator, "func", None)
        code = getattr(func, "__code__", None)
        if code is not None and guard_name in code.co_names:
            return True
    return False


def _required_profile_guard_violations(models: typing.Iterable[type[SDLModel]]) -> set[str]:
    """Compute missing or unregistered required-profile guard violations."""

    violations: set[str] = set()
    for model, field_name in _required_profile_discriminators(models):
        guard_name = f"require_profile_for_{field_name}"
        label = f"{model.__module__}.{model.__name__}.{field_name}"
        if not callable(getattr(model, guard_name, None)):
            violations.add(f"{label}: missing {guard_name}")
            continue
        if not _registered_after_model_validator_calls(model, guard_name):
            violations.add(f"{label}: {guard_name} is not called by a registered after model-validator")
    return violations


_SHARED_HELPER_DEFINITION_NAMES = frozenset(
    {
        "_absolute_refs",
        "_coerce_refs",
        "_normalize_enum",
        "_reject_duplicates",
        "_require_non_empty",
        "coerce_string_list",
        "parse_runtime_enum_or_var",
        "reject_duplicates",
        "require_non_empty",
        "validate_absolute_paths",
    }
)


def test_runtime_family_invariants_no_new_drift() -> None:
    """Live violations must exactly match the tracked allowlist (no drift)."""

    current = _current_violations()
    new = sorted(current - KNOWN_VIOLATIONS)
    resolved = sorted(KNOWN_VIOLATIONS - current)
    assert current == KNOWN_VIOLATIONS, (
        "Runtime service-family structural-invariant drift detected.\n"
        f"  NEW violations (fix the family, or this change is wrong): {new}\n"
        f"  RESOLVED but still allow-listed (remove from KNOWN_VIOLATIONS): {resolved}"
    )


def test_discriminated_runtime_spines_register_required_profile_guards() -> None:
    """Required-profile discriminators must be wired through model validators."""

    current = _required_profile_guard_violations(_runtime_configuration_models())
    new = sorted(current - KNOWN_PROFILE_GUARD_VIOLATIONS)
    resolved = sorted(KNOWN_PROFILE_GUARD_VIOLATIONS - current)
    assert current == KNOWN_PROFILE_GUARD_VIOLATIONS, (
        "Runtime required-profile guard drift detected.\n"
        f"  NEW violations (register a require_profile_for_* model validator): {new}\n"
        f"  RESOLVED but still allow-listed (remove from KNOWN_PROFILE_GUARD_VIOLATIONS): {resolved}"
    )


def test_required_profile_lint_rejects_guardless_discriminated_family() -> None:
    """A test-local discriminated spine without a guard must trip the lint."""

    violations = _required_profile_guard_violations([GuardlessDiscriminatedRuntimeSpine])

    assert any(
        "GuardlessDiscriminatedRuntimeSpine.example_kind" in violation
        and "require_profile_for_example_kind" in violation
        for violation in violations
    ), violations


def test_runtime_modules_do_not_redeclare_shared_validation_helpers() -> None:
    """Runtime families import shared helper policy instead of shadowing it."""

    package_dir = Path(raes.__file__).resolve().parent
    # Discover both flat ``runtime_*.py`` modules and the submodules of
    # ``runtime_*`` packages (a runtime family may be split into a package
    # behind an API-stable re-export ``__init__``), so the no-shadowing
    # invariant keeps enforcing after a modularity split.
    runtime_module_paths = [
        *package_dir.glob("runtime_*.py"),
        *package_dir.glob("runtime_*/**/*.py"),
    ]
    offenders: list[str] = []
    for path in sorted(runtime_module_paths):
        if path.name == "runtime_values.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in _SHARED_HELPER_DEFINITION_NAMES:
                offenders.append(f"{path.relative_to(package_dir)}:{node.lineno}:{node.name}")

    assert not offenders, "Runtime modules must not redeclare shared validation helpers:\n  " + "\n  ".join(offenders)


def test_enum_or_var_helpers_share_hyphen_alias_normalization() -> None:
    """Runtime and base enum parsing share one author-facing normalization rule."""

    assert (
        parse_runtime_enum_or_var("member-of", RuntimeIdentityRelationshipKind, field_name="relationship_type")
        is RuntimeIdentityRelationshipKind.MEMBER_OF
    )
    assert (
        parse_enum_or_var("member-of", RuntimeIdentityRelationshipKind, field_name="relationship_type")
        is RuntimeIdentityRelationshipKind.MEMBER_OF
    )


def test_primary_id_field_exists_on_model() -> None:
    """Every registry primary id field must be a real field on its model."""

    for family in rsf.RUNTIME_SERVICE_FAMILIES:
        model = _element_model(family.collection_name)
        assert model is not None, f"{family.key}: no element model for {family.collection_name}"
        assert family.id_field in model.model_fields, (
            f"{family.key}: registry id_field '{family.id_field}' is not a field on {model.__name__}"
        )


def _runtime_family_modules() -> dict[str, list[str]]:
    """Map each top-level ``runtime_*`` family to the modules that define it.

    A runtime-family is any ``raes`` submodule whose name starts with
    ``runtime_`` (this includes the ``*_vocab`` and ``*_definitions`` modules).
    When a modularity split turns such a module into a *package* behind an
    API-stable re-export ``__init__``, its concrete declarations live in private
    submodules; the value list therefore carries the package ``__init__`` plus
    every submodule, discovered by walking the real package files rather than
    trusting what ``__init__`` happens to re-export.
    """

    families: dict[str, list[str]] = {}
    for module_info in pkgutil.iter_modules(raes.__path__):
        name = module_info.name
        if not name.startswith("runtime_"):
            continue
        qualified = f"raes.{name}"
        module_names = [qualified]
        if module_info.ispkg:
            package = importlib.import_module(qualified)
            module_names.extend(info.name for info in pkgutil.walk_packages(package.__path__, prefix=f"{qualified}."))
        families[name] = module_names
    return families


def _runtime_family_enums() -> dict[str, type[enum.Enum]]:
    """Collect every Enum subclass *defined in* a runtime-family module.

    Discovery walks each family's real modules (a flat ``runtime_*.py`` or every
    submodule of a ``runtime_*`` package — see :func:`_runtime_family_modules`)
    and keeps enums whose ``__module__`` is the module being inspected. Reading
    each concrete submodule directly — instead of ``vars`` of a re-exporting
    ``__init__`` — means an enum defined in a private submodule but never
    re-exported is still seen, so it cannot silently opt out of the
    open/closed-sentinel lint; enums merely re-exported or imported from another
    module are counted once, against their defining module.
    """

    found: dict[str, type[enum.Enum]] = {}
    for name, module_names in _runtime_family_modules().items():
        for module_name in module_names:
            module = importlib.import_module(module_name)
            for value in vars(module).values():
                if (
                    isinstance(value, type)
                    and issubclass(value, enum.Enum)
                    and value is not enum.Enum
                    and value.__module__ == module_name
                ):
                    found[f"{name}.{value.__name__}"] = value
    return found


def test_runtime_enums_open_or_closed_not_single_sentinel() -> None:
    """Runtime-family enums must be open (both sentinels) or closed (neither).

    The enum-sentinel convention (DSL-139, Brad-Edwards/raes#443) is: an OPEN
    observed-value taxonomy carries BOTH ``unknown`` and ``other``; a CLOSED
    structural/protocol/redaction-lattice vocabulary carries NEITHER. The
    single-sentinel state -- exactly one of ``{unknown, other}`` -- is the
    inconsistency this lint forbids. Any future runtime enum introduced in a
    single-sentinel state fails here, which is the drift guard.
    """

    enums = _runtime_family_enums()
    assert enums, "no runtime-family enums discovered; module iteration is broken"

    offenders: list[str] = []
    for qualified_name, enum_cls in sorted(enums.items()):
        values = {member.value for member in enum_cls}
        has_unknown = "unknown" in values
        has_other = "other" in values
        if has_unknown != has_other:
            present = "unknown" if has_unknown else "other"
            offenders.append(f"{qualified_name} (single-sentinel: only '{present}')")

    assert not offenders, (
        "Runtime-family enums must carry BOTH 'unknown' and 'other' (open) or "
        "NEITHER (closed), never exactly one. Single-sentinel enums:\n  " + "\n  ".join(offenders)
    )


def test_registered_child_refs_exist_on_models() -> None:
    """Every registered child collection/id must exist on its parent model."""

    def _check(model: type, children: tuple[rsf.RuntimeReferenceChild, ...]) -> None:
        for child in children:
            assert child.collection_name in model.model_fields, (
                f"{model.__name__}: child collection '{child.collection_name}' is not a field"
            )
            child_model = typing.get_args(model.model_fields[child.collection_name].annotation)
            element = child_model[0] if child_model else None
            assert element is not None, f"{model.__name__}.{child.collection_name} is not a typed list"
            assert child.id_field in element.model_fields, (
                f"{element.__name__}: child id_field '{child.id_field}' is not a field"
            )
            _check(element, child.children)

    for family in rsf.RUNTIME_SERVICE_FAMILIES:
        model = _element_model(family.collection_name)
        assert model is not None
        _check(model, family.child_refs)

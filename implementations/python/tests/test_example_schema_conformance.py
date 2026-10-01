"""Issue #501 (review CT-4) — worked examples conform to the *published* JSON Schema.

Every example loads through its production loader; SDL examples must also have a name
and no advisories. Pydantic acceptance is not published-schema conformance, so this
suite also serializes each example with the canonical, contract-shaped publication
serialization (``model_dump(mode="json", by_alias=True)`` — the same flags ``raes_processor/compiler.py``
uses) and validates the result against the *checked-in* published schema
``contracts/schemas/sdl/sdl-authoring-input-v1.json`` with ``Draft202012Validator``.

Validating the shipped schema artifact rather than ``schema_bundle()`` is deliberate: per
ADR-009 the published ``contracts/schemas/`` JSON is the normative authority, while
``schema_bundle()`` remains the drift/compatibility proof used by other gates.

A non-vacuity guard and a deliberate negative control keep the suite from passing
vacuously — a stale corpus path that collects zero cases, or a validator that accepts
everything, both fail loudly.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Protocol

import pytest
from jsonschema import Draft202012Validator
from paths import EXAMPLES_DIR, EXPERIMENTS_DIR
from raes import load_sdl_fragment
from raes.scenarios import load_scenario
from raes_contracts.corpus import corpus_family_root
from raes_contracts.experiment_spec import load_experiment_spec


class SupportsModelDump(Protocol):
    """Any loaded contract model that can be serialized for publication comparison.

    The corpus spans more than one loaded model type (``Scenario`` for SDL,
    ``ExperimentSpecModel`` for authored experiments), so the loader is typed by
    the one capability the suite uses — ``model_dump`` — rather than a single
    concrete model class.
    """

    def model_dump(self, **kwargs: Any) -> dict: ...


# ``by_alias=True`` is load-bearing for intentional language keywords such as
# ``class``, ``type``, ``then``, and ``else``. Ordinary structural wire fields
# use canonical snake_case. ``mode="json"`` yields JSON-native enum values.
_PUBLICATION_DUMP_KWARGS = {"mode": "json", "by_alias": True}


@dataclass(frozen=True)
class CorpusEntry:
    """One validation-corpus leg: a glob of example files checked against one published schema.

    The extension seam (issue #501 preflight): a future instantiated-example corpus adds a
    row to ``VALIDATION_CORPUS`` — root, glob, loader, contract id, schema file, and
    serialization kwargs — rather than a new loader, path convention, or validator wrapper.
    """

    contract_id: str
    root: Path
    glob: str
    loader: Callable[[Path], SupportsModelDump]
    schema_path: Path
    dump_kwargs: dict = field(default_factory=lambda: dict(_PUBLICATION_DUMP_KWARGS))

    def examples(self) -> list[Path]:
        return sorted(self.root.glob(self.glob))

    def validator(self) -> Draft202012Validator:
        return _validator_for(self.schema_path)


@cache
def _validator_for(schema_path: Path) -> Draft202012Validator:
    """Load the *checked-in* published schema artifact and build its validator once."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


_SDL_SCHEMA_DIR = corpus_family_root("schemas") / "sdl"
_EXP_SCHEMA_DIR = corpus_family_root("schemas") / "experiment-core"

# The experiment authoring-input reference models (task / capture-spec) forbid
# ``ref_digest``/``ref_path`` in their published sub-schemas, so an id-only
# reference publishes without those keys. ``exclude_none`` yields exactly that
# schema-conformant publication shape (unset optionals are omitted, not null).
_EXPERIMENT_DUMP_KWARGS = {"mode": "json", "by_alias": True, "exclude_none": True}

# Today the table has exactly one leg: the authoring example corpus against the published
# authoring-input contract. No instantiated-scenario *example* artifacts exist under
# ``examples/`` — the instantiated schema's fixtures under ``contracts/fixtures/sdl/`` are
# covered by ``test_instantiated_scenario_schema.py`` — so a future instantiated corpus adds
# a row here for ``instantiated-scenario-v1``.
VALIDATION_CORPUS = [
    CorpusEntry(
        contract_id="sdl-authoring-input-v1",
        root=EXAMPLES_DIR,
        glob="*.sdl.yaml",
        loader=load_scenario,
        schema_path=_SDL_SCHEMA_DIR / "sdl-authoring-input-v1.json",
    ),
    CorpusEntry(
        contract_id="experiment-authoring-input-v1",
        root=EXPERIMENTS_DIR,
        glob="*.exp.yaml",
        loader=load_experiment_spec,
        schema_path=_EXP_SCHEMA_DIR / "experiment-authoring-input-v1.json",
        dump_kwargs=dict(_EXPERIMENT_DUMP_KWARGS),
    ),
]


def _example_cases() -> list[tuple[CorpusEntry, Path]]:
    return [(entry, path) for entry in VALIDATION_CORPUS for path in entry.examples()]


def _case_id(value: object) -> str:
    if isinstance(value, Path):
        return value.name
    if isinstance(value, CorpusEntry):
        return value.contract_id
    return str(value)


@pytest.mark.parametrize(("entry", "path"), _example_cases(), ids=_case_id)
def test_example_conforms_to_published_schema(entry: CorpusEntry, path: Path) -> None:
    """Every shipped example provably conforms to the published contract surface in CI.

    The serialization mirrors the runtime compiler's publication serialization, so the JSON
    validated here is the shape a downstream consumer reads — not an internal Pydantic-only
    projection.
    """
    scenario = entry.loader(path)
    if entry.contract_id == "sdl-authoring-input-v1":
        assert scenario.name, path.name
        assert scenario.advisories == [], path.name
    payload = scenario.model_dump(**entry.dump_kwargs)

    errors = sorted(entry.validator().iter_errors(payload), key=lambda error: error.json_path)

    assert not errors, f"{path.name} violates {entry.contract_id}:\n" + "\n".join(
        f"  {error.json_path}: {error.message}" for error in errors
    )


@pytest.mark.parametrize("path", sorted(EXAMPLES_DIR.glob("*.sdl.yaml")), ids=lambda path: path.name)
def test_sdl_example_is_canonical_source_and_direct_normalized_schema_input(path: Path) -> None:
    """Canonical examples pass strict source decoding and the advertised schema directly."""
    payload = load_sdl_fragment(path.read_text(encoding="utf-8"))
    errors = sorted(_AUTHORING_ENTRY.validator().iter_errors(payload), key=lambda error: error.json_path)

    assert not errors, f"{path.name} is not direct normalized authoring-schema input:\n" + "\n".join(
        f"  {error.json_path}: {error.message}" for error in errors
    )


@pytest.mark.parametrize("entry", VALIDATION_CORPUS, ids=_case_id)
def test_corpus_leg_is_nonempty(entry: CorpusEntry) -> None:
    """Non-vacuity guard: a stale/relocated corpus root must fail loudly, not collect zero cases."""
    assert entry.examples(), f"No examples for {entry.contract_id} under {entry.root} (glob {entry.glob!r})"


# --- Negative control: the validator must be engaged (the suite cannot pass vacuously) ---

_AUTHORING_ENTRY = VALIDATION_CORPUS[0]

_MINIMAL_VALID_PAYLOAD = {"name": "negative-control-baseline"}

# Each payload violates exactly one published-schema rule: ``required: ["name"]``,
# ``name`` typed ``string``, and top-level ``additionalProperties: false``. Kept inline,
# never as a file under ``examples/scenarios/``, so an invalid control never leaks into the
# reusable positive example corpus.
_INVALID_PAYLOADS = {
    "missing-required-name": {"description": "no name field"},
    "wrong-type-name": {"name": 123},
    "additional-top-level-property": {"name": "neg-control", "not_a_real_section": True},
}


def test_negative_control_baseline_is_accepted() -> None:
    """A minimal valid document validates, so the rejections below indicate the injected defect,
    not a validator that rejects everything."""
    _AUTHORING_ENTRY.validator().validate(_MINIMAL_VALID_PAYLOAD)


@pytest.mark.parametrize("payload", _INVALID_PAYLOADS.values(), ids=list(_INVALID_PAYLOADS))
def test_negative_control_invalid_payload_is_rejected(payload: dict) -> None:
    """A known-invalid payload must fail published-schema validation, proving the validator is engaged."""
    assert not _AUTHORING_ENTRY.validator().is_valid(payload)

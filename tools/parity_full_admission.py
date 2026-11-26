#!/usr/bin/env python3
"""Re-record the full admission verdicts of every contract fixture.

Each row keeps the original structural golden result from the parity corpus.
The recorder seals each fixture as the reference fixture loader does, then
records the published-schema result and the full model verdict. Rows with a
contextual owner keep their recorded owner verdict; their owners are fixed
independent inputs.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from jsonschema import Draft202012Validator  # noqa: E402
from parity_contract_models import contract_validators  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from raes_conformance.conformance.validators import _SEMANTIC_CONTEXT_REQUIRED_CONTRACTS  # noqa: E402
from raes_contracts.contract_seals import (  # noqa: E402
    SEALED_FIXTURE_KINDS,
    seal_contract_fixture,
    sealed_contract_ids,
)
from raes_contracts.errors import RaesError  # noqa: E402
from raes_contracts.published_schemas import published_schema  # noqa: E402

JSON_FILES = "*.json"
CONTRACTS = ROOT / "contracts"
TESTDATA = ROOT / "implementations/go/contract/admission/testdata"
CORPUS = ROOT / "implementations/go/internal/parity/testdata"
VERDICTS = TESTDATA / "full-admission-verdicts.json"
PHASES = TESTDATA / "sdl-phase-verdicts.json"
# The native SDL phase owner admits these contracts; its records name each exact source.
SDL_PHASE_CONTRACTS = frozenset(
    {
        "sdl-authoring-input-v1",
        "instantiated-scenario-v1",
        "instantiated-scenario-snapshot-v1",
        "materialized-scenario-v1",
    }
)
PHASE_SHARD_BYTES = 512 * 1024
SHARDS = 2
SKIPPED_FAMILY = "fixtures/sdl/semantic-vectors-v1"


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _published_ids() -> set[str]:
    return {path.stem for path in (CONTRACTS / "schema-publication/entries").glob(JSON_FILES)}


def _version_index(ids: set[str]) -> dict[str, str]:
    candidates: dict[str, list[str]] = {}
    for contract_id in sorted(ids):
        entry = json.loads((CONTRACTS / "schema-publication/entries" / f"{contract_id}.json").read_text("utf-8"))
        schema = json.loads((ROOT / entry["schema_path"]).read_text("utf-8"))
        version = schema.get("properties", {}).get("schema_version", {}).get("const")
        if isinstance(version, str):
            candidates.setdefault(version, []).append(entry["contract_id"])
    return {version: names[0] for version, names in candidates.items() if len(names) == 1}


def _fixtures() -> Iterator[Path]:
    # The inventory orders repository-relative paths by their bytes, as the Go walk does.
    for path in sorted(
        (CONTRACTS / "fixtures").rglob(JSON_FILES), key=lambda item: item.relative_to(CONTRACTS).as_posix()
    ):
        relative = path.relative_to(CONTRACTS).as_posix()
        if not relative.startswith(SKIPPED_FAMILY + "/"):
            yield path


def inventory() -> tuple[list[tuple[str, str]], list[str]]:
    """Return each contract fixture with its contract, and every other fixture."""
    ids = _published_ids()
    versions = _version_index(ids)
    contracts: list[tuple[str, str]] = []
    other: list[str] = []
    for path in _fixtures():
        relative = path.relative_to(CONTRACTS).as_posix()
        contract = next((part for part in relative.split("/") if part in ids), None)
        if contract is None:
            try:
                version = json.loads(path.read_bytes()).get("schema_version")
            except ValueError, AttributeError:
                version = None
            contract = versions.get(version) if isinstance(version, str) else None
        if contract is None:
            other.append(relative)
        else:
            contracts.append((relative, contract))
    return contracts, other


def _structural_records() -> dict[str, dict[str, object]]:
    """Index the original admission CLI and schema results by fixture name and by input digest."""
    records: dict[str, dict[str, object]] = {}
    for path in sorted((CORPUS / "cases/cli/semantic-validate").glob(JSON_FILES)):
        record = json.loads(path.read_text("utf-8"))
        if record["name"].startswith("contracts/fixtures/"):
            records.setdefault("cli:" + record["name"], {**record, "_path": path.relative_to(CORPUS).as_posix()})
    for path in sorted((CORPUS / "cases/schema/validate").glob(JSON_FILES)):
        record = json.loads(path.read_text("utf-8"))
        key = "schema:" + record["args"][0] + ":" + record["files"]["payload.json"]
        records.setdefault(key, {**record, "_path": path.relative_to(CORPUS).as_posix()})
    return records


def _structural(records: dict[str, dict[str, object]], name: str, contract: str, digest: str) -> dict[str, object]:
    record = records.get("cli:" + name)
    if record is not None and record["files"].get("input.json") == digest:
        payload = (record["result"].get("stdout") or {}).get("payload") or {}
        return {
            "structural_admitted": bool(payload.get("admitted", False)),
            "structural_surface": "contract-admission CLI",
            "structural_source": record["_path"],
            "input_name": "input.json",
        }
    record = records.get(f"schema:{contract}:{digest}")
    if record is None:
        raise ValueError(f"{name} has no original structural result in the parity corpus")
    return {
        "structural_admitted": bool(record["result"]["valid"]),
        "structural_surface": "schema validate",
        "structural_source": record["_path"],
        "input_name": "payload.json",
    }


def _kind(relative: str) -> str:
    parts = relative.split("/")
    return next((part for part in reversed(parts[:-1]) if part in {"valid", "invalid", *SEALED_FIXTURE_KINDS}), "")


def _sealed(contract: str, relative: str, payload: object) -> object:
    kind = _kind(relative)
    if contract in sealed_contract_ids() and kind in SEALED_FIXTURE_KINDS and isinstance(payload, dict):
        return seal_contract_fixture(contract, payload, kind=kind)
    return payload


def _model_verdict(contract: str, payload: object, validators: dict[str, object]) -> dict[str, object]:
    validator = validators[contract]
    check = f"published-schema gate + {getattr(validator, '__self__', validator)}"
    if not Draft202012Validator(published_schema(contract)).is_valid(payload):
        return {"full_admitted": False, "reference_check": check, "failure_class": "ValidationError"}
    try:
        validator(payload)
    except (ValidationError, ValueError, RaesError) as exc:
        return {"full_admitted": False, "reference_check": check, "failure_class": type(exc).__name__}
    return {"full_admitted": True, "reference_check": check, "failure_class": ""}


def _model_owners(rows: object) -> dict[str, str]:
    """Return the owner that every retained model row of a contract shares."""
    seen: dict[str, set[str]] = {}
    for row in rows:
        if row.get("reference_kind") == "model-reference":
            seen.setdefault(row["contract_id"], set()).add(row["owner"])
    return {contract: next(iter(names)) for contract, names in seen.items() if len(names) == 1}


def _bytes(sealed: object, raw: bytes) -> bytes:
    """Return the bytes the Go owner seals: the original bytes when nothing was added."""
    return raw if sealed == json.loads(raw) else json.dumps(sealed, separators=(",", ":"), ensure_ascii=False).encode()


def _phase_record(contract: str, payload: object, source: str, validators: dict[str, object]) -> dict[str, object]:
    published = Draft202012Validator(published_schema(contract)).is_valid(payload)
    try:
        model = validators[contract](payload)
    except ValidationError, ValueError, RaesError:
        model = None
    result: dict[str, object] = {
        "contract_id": contract,
        "source_sha256": source,
        "published_schema_admitted": published,
        "python_model_admitted": model is not None,
    }
    if model is not None:
        result["document"] = model.model_dump(mode="json", exclude_unset=True)
    return result


def _phase_records(
    sources: dict[str, tuple[str, object]], validators: dict[str, object]
) -> tuple[dict[str, object], dict[str, list[dict[str, object]]]]:
    """Add the native phase record of each new SDL phase source to the retained records."""
    header = json.loads(PHASES.read_text("utf-8"))
    shards = {name: json.loads((TESTDATA / name).read_text("utf-8")) for name in sorted(header["case_files"])}
    known = {row["source_sha256"] for rows in shards.values() for row in rows}
    names = sorted(shards)
    for source, (contract, payload) in sorted(sources.items()):
        if source in known:
            continue
        row = _phase_record(contract, payload, source, validators)
        last = names[-1]
        if len(json.dumps([*shards[last], row], separators=(",", ":"))) + 1 > PHASE_SHARD_BYTES:
            last = f"sdl-phase-verdicts-{len(names) + 1:02d}.json"
            names.append(last)
            shards[last] = []
        shards[last].append(row)
    header["case_count"] = sum(len(rows) for rows in shards.values())
    header["case_files"] = {
        name: _digest((json.dumps(rows, separators=(",", ":"), ensure_ascii=False) + "\n").encode())
        for name, rows in shards.items()
    }
    return header, shards


def _record_native_fixture(relative: str, fixture: dict[str, object], validators: dict[str, object]) -> None:
    raw = (CONTRACTS / relative).read_bytes()
    payload = json.loads(raw)
    sealed = _sealed(fixture["contract_id"], relative, payload)
    verdict = _model_verdict(fixture["contract_id"], sealed, validators)
    fixture.update(
        input_sha256=_digest(raw),
        published_schema_admitted=Draft202012Validator(published_schema(fixture["contract_id"])).is_valid(payload),
        full_admitted=verdict["full_admitted"],
        failure_class=verdict["failure_class"],
    )


class _FixtureRecorder:
    """Record the verdict row of each contract fixture, collecting the SDL phase sources."""

    _KEYS = ("full_admitted", "owner", "reference_check", "failure_class", "reference_kind")

    def __init__(self, retained: dict[str, dict[str, object]], validators: dict[str, object]) -> None:
        self.retained = retained
        self.validators = validators
        self.structural = _structural_records()
        self.owners = _model_owners(retained.values())
        self.phase_sources: dict[str, tuple[str, object]] = {}

    def row(self, relative: str, contract: str) -> dict[str, object]:
        raw = (CONTRACTS / relative).read_bytes()
        name = "contracts/" + relative.removesuffix(".json")
        payload = json.loads(raw)
        previous = self.retained.get(relative, {})
        row: dict[str, object] = {"name": name, "contract_id": previous.get("contract_id", contract)}
        row.update(input_path=relative, input_sha256=_digest(raw))
        row.update(_structural(self.structural, name, row["contract_id"], row["input_sha256"]))
        published = Draft202012Validator(published_schema(row["contract_id"])).is_valid(payload)
        if previous.get("reference_kind") == "contextual-reference" or (
            previous and row["contract_id"] in _SEMANTIC_CONTEXT_REQUIRED_CONTRACTS
        ):
            # A trusted context owner decides these verdicts; the owners are fixed recorded inputs.
            row.update({key: previous[key] for key in self._KEYS})
        else:
            self._model_row(row, relative, payload, raw, previous)
        row["published_schema_admitted"] = published
        return row

    def _model_row(
        self, row: dict[str, object], relative: str, payload: object, raw: bytes, previous: dict[str, object]
    ) -> None:
        sealed = _sealed(row["contract_id"], relative, payload)
        row.update(_model_verdict(row["contract_id"], sealed, self.validators))
        row["owner"] = previous.get("owner") or self.owners.get(row["contract_id"], "none")
        if not previous and row["contract_id"] in SDL_PHASE_CONTRACTS:
            row["owner"] = "sdl-phase"
        if row["owner"] == "sdl-phase":
            self.phase_sources[_digest(_bytes(sealed, raw))] = (row["contract_id"], sealed)
        row["reference_check"] = previous.get("reference_check", row["reference_check"])
        row["reference_kind"] = "model-reference"


def record(verdicts: dict[str, object]) -> tuple[dict[str, object], list[list[dict[str, object]]]]:
    retained: dict[str, dict[str, object]] = {}
    selectors: list[dict[str, object]] = []
    for name in verdicts["case_files"]:
        for row in json.loads((TESTDATA / name).read_text("utf-8")):
            if row.get("reference_kind") == "selector-refusal":
                selectors.append(row)
            else:
                retained[row["input_path"]] = row
    validators = contract_validators()
    contracts, other = inventory()
    # A native SDL owner covers these fixtures in its own Go package; record their reference verdicts by name.
    native = verdicts.get("native_owner_fixtures", {})
    contracts = [(relative, contract) for relative, contract in contracts if relative not in native]
    for relative, fixture in native.items():
        _record_native_fixture(relative, fixture, validators)
    recorder = _FixtureRecorder(retained, validators)
    rows = [recorder.row(relative, contract) for relative, contract in contracts]
    phase_sources = recorder.phase_sources
    rows.extend(selectors)
    noncontract = verdicts["noncontract_fixtures"]
    unclassified = [path for path in other if path not in noncontract]
    if unclassified:
        raise ValueError(f"unclassified fixtures: {unclassified}")
    result = {
        **verdicts,
        "fixture_inventory": [relative for relative, _ in contracts],
        "noncontract_fixtures": {path: noncontract[path] for path in other},
    }
    phases = _phase_records(phase_sources, validators)
    result["owner_sources"] = {
        **result["owner_sources"],
        PHASES.name: _digest((json.dumps(phases[0], indent=2) + "\n").encode()),
    }
    size = -(-len(rows) // SHARDS)
    shards = [rows[index * size : (index + 1) * size] for index in range(SHARDS)]
    result["case_files"] = [f"full-admission-cases-{index + 1:02d}.json" for index in range(SHARDS)]
    return result, shards, phases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    before = json.loads(VERDICTS.read_text("utf-8"))
    after, shards, (phase_header, phase_shards) = record(copy.deepcopy(before))
    outputs = {VERDICTS: after} | {
        TESTDATA / name: shard for name, shard in zip(after["case_files"], shards, strict=True)
    }
    outputs |= {PHASES: phase_header} | {TESTDATA / name: rows for name, rows in phase_shards.items()}
    failed = False
    for path, value in outputs.items():
        indent = {VERDICTS: 2, PHASES: 2}.get(path)
        compact = json.dumps(value, separators=(",", ":"), ensure_ascii=not path.name.startswith("sdl-phase"))
        text = (json.dumps(value, indent=indent) if indent else compact) + "\n"
        if args.check:
            if not path.exists() or json.loads(path.read_text("utf-8")) != value:
                print(f"{path.name} differs from the reference admission", file=sys.stderr)
                failed = True
        elif not path.exists() or path.read_text("utf-8") != text:
            path.write_text(text, encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

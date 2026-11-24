#!/usr/bin/env python3
"""Re-record the retained model-stage references against the published reference root models.

Each case names a retained input by digest and may change it at fixed paths. The
recorded result is whether the published root model of the contract accepts the
changed input. Inputs of a contract that is no longer published are dropped.
Retained plans and batch receipts lose the scheduler isolation fields that the
trial-parallelism contract replaced; a changed input is stored under its new
digest, and a case that changes a replaced field is dropped.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from parity_contract_models import contract_validator, contract_validators  # noqa: E402
from parity_trial_references import reseal_plan  # noqa: E402

from tools.parity_storage import INLINE_BYTES, read_blob  # noqa: E402
from tools.parity_support import encode  # noqa: E402

TESTDATA = ROOT / "implementations/go/contract/admission/testdata"
RETAINED = TESTDATA / "retained-model-inputs"
CASES = Path("cases/schema/validate")
INLINE = ("local-model-inputs.json", "expanded-model-inputs.json")
SHARDED = (
    "diverse-model-inputs",
    "local-model-boundaries",
    "expanded-model-boundaries",
    "enum-model-boundaries",
    "focused-model-boundaries",
)
REPLACED_FIELDS = {
    "admitted-trial-plan-v1": ("isolation_proof", "isolation_profile"),
    "batch-execution-receipt-v1": ("isolation_proof_ref", "lease_evidence_refs"),
}


class Retained:
    """Read retained inputs and stage new ones."""

    def __init__(self) -> None:
        self.inputs: dict[str, bytes] = {}
        self.migrated: dict[tuple[str, str], str] = {}
        self.contracts: dict[str, str] = {}

    def payload(self, identity: str) -> bytes:
        return self.inputs.get(identity) or read_blob(RETAINED, identity)

    def migrate(self, contract: str, identity: str) -> str:
        key = (contract, identity)
        if key not in self.migrated:
            self.migrated[key] = self._migrate(contract, identity)
        return self.migrated[key]

    def _migrate(self, contract: str, identity: str) -> str:
        fields = REPLACED_FIELDS.get(contract)
        if fields is None:
            return identity
        document = json.loads(self.payload(identity))
        if contract == "admitted-trial-plan-v1":
            if "isolation_proof" not in document and "isolation_profile" not in document.get("profiles", {}):
                return identity
            changed = reseal_plan(document)
        else:
            changed = {key: value for key, value in document.items() if key not in fields}
        if changed == document:
            return identity
        content = encode(changed)
        new_identity = hashlib.sha256(content).hexdigest()
        self.inputs[new_identity] = content
        return new_identity


def _changed(document: Any, changes: list[dict[str, Any]]) -> Any:
    result = copy.deepcopy(document)
    for change in changes:
        parent = result
        for token in change["path"][:-1]:
            parent = parent[int(token)] if isinstance(parent, list) else parent[token]
        key = change["path"][-1]
        if isinstance(parent, list):
            parent[int(key)] = change["value"]
        else:
            parent[key] = change["value"]
    return result


def _admitted(contract: str, document: Any) -> bool:
    try:
        contract_validator(contract)(document)
    except ValidationError, ValueError, TypeError:
        return False
    return True


def record_case(case: dict[str, Any], retained: Retained) -> dict[str, Any] | None:
    contract = case["contract"]
    if contract not in contract_validators():
        return None
    replaced = REPLACED_FIELDS.get(contract, ())
    if any(token in replaced for change in case.get("changes", []) for token in change["path"]):
        return None
    result = dict(case)
    identity = retained.migrate(contract, case["input_sha256"])
    if identity != case["input_sha256"]:
        result["input_sha256"] = identity
        result["case_file"] = (CASES / f"{identity}.json").as_posix()
    retained.contracts[identity] = contract
    document = json.loads(retained.payload(identity))
    result["admitted"] = _admitted(contract, _changed(document, case.get("changes", [])))
    return result


def _case_document(contract: str, identity: str, valid: bool) -> bytes:
    return encode(
        {
            "args": [contract],
            "command": "validate",
            "files": {"payload.json": f"sha256:{identity}"},
            "name": f"retained/{identity}",
            "result": {"valid": valid},
            "surface": "schema",
        }
    )


def _stored(identity: str, content: bytes) -> Iterator[tuple[Path, bytes]]:
    compressed = gzip.compress(content, mtime=0)
    if len(compressed) <= INLINE_BYTES:
        yield Path("inputs", identity), compressed
        return
    pieces = [compressed[index : index + INLINE_BYTES] for index in range(0, len(compressed), INLINE_BYTES)]
    yield Path("inputs", identity), encode({"parts": len(pieces)})
    for index, piece in enumerate(pieces):
        yield Path("pieces", identity, str(index)), b"\x00" + piece


def records() -> tuple[dict[str, Any], dict[Path, bytes]]:
    retained = Retained()
    documents: dict[str, Any] = {}
    for name in INLINE:
        document = json.loads((TESTDATA / name).read_text(encoding="utf-8"))
        document["cases"] = [row for case in document["cases"] if (row := record_case(case, retained)) is not None]
        documents[name] = document
    for prefix in SHARDED:
        header = json.loads((TESTDATA / f"{prefix}.json").read_text(encoding="utf-8"))
        total = 0
        for shard in header["case_files"]:
            cases = json.loads((TESTDATA / shard).read_text(encoding="utf-8"))
            documents[shard] = [row for case in cases if (row := record_case(case, retained)) is not None]
            total += len(documents[shard])
        header["case_count"] = total
        documents[f"{prefix}.json"] = header
    files: dict[Path, bytes] = {}
    for identity, content in sorted(retained.inputs.items()):
        if identity not in retained.contracts:
            continue
        contract = retained.contracts[identity]
        files[CASES / f"{identity}.json"] = _case_document(contract, identity, _admitted(contract, json.loads(content)))
        files.update(_stored(identity, content))
    return documents, files


def _referenced(documents: dict[str, Any]) -> tuple[set[str], set[str]]:
    identities: set[str] = set()
    case_files: set[str] = set()
    for document in documents.values():
        cases = document.get("cases", []) if isinstance(document, dict) else document
        for case in cases:
            identities.add(case["input_sha256"])
            case_files.add(case["case_file"])
    return identities, case_files


def _orphans(documents: dict[str, Any]) -> list[Path]:
    """Return retained files that no reference case names."""
    identities, case_files = _referenced(documents)
    orphans = [path for path in (RETAINED / "inputs").iterdir() if path.name not in identities]
    pieces = RETAINED / "pieces"
    if pieces.is_dir():
        orphans += [path for path in pieces.iterdir() if path.name not in identities]
    orphans += [path for path in (RETAINED / CASES).iterdir() if (CASES / path.name).as_posix() not in case_files]
    return sorted(orphans)


def _manifest() -> dict[str, Any]:
    """Describe the retained tree; ``files_sha256`` digests the ``sha256sum`` listing of every other file."""
    manifest = json.loads((RETAINED / "manifest.json").read_text(encoding="utf-8"))
    files = sorted(path for path in RETAINED.rglob("*") if path.is_file() and path.name != "manifest.json")
    listing = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(RETAINED).as_posix()}\n" for path in files
    )
    manifest["case_count"] = len(list((RETAINED / CASES).iterdir()))
    manifest["file_count"] = len(files)
    manifest["files_sha256"] = hashlib.sha256(listing.encode()).hexdigest()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    documents, files = records()
    failed = False
    for name, document in documents.items():
        path = TESTDATA / name
        actual = json.dumps(document, indent=2) + "\n"
        if args.check:
            if json.loads(path.read_text(encoding="utf-8")) != document:
                print(f"{name} differs from the reference models", file=sys.stderr)
                failed = True
        else:
            path.write_text(actual, encoding="utf-8")
    for relative, content in files.items():
        path = RETAINED / relative
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                print(f"{relative} differs from the reference models", file=sys.stderr)
                failed = True
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    orphans = _orphans(documents)
    if args.check and orphans:
        print("retained inputs contain files that no case names", file=sys.stderr)
        failed = True
    for path in [] if args.check else orphans:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    manifest = json.dumps(_manifest(), indent=2) + "\n"
    if args.check:
        if (RETAINED / "manifest.json").read_text(encoding="utf-8") != manifest:
            print("retained input manifest differs", file=sys.stderr)
            failed = True
    else:
        (RETAINED / "manifest.json").write_text(manifest, encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

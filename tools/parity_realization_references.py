#!/usr/bin/env python3
"""Re-record the realization relation references against the reference processor.

Each reference case keeps its recorded inputs: provisioning plans, runtime
snapshots, backend manifests, realization envelopes and compiled requirements.
The recorder evaluates each case again with the reference relation and records
its diagnostics and provenance. It changes no input.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from pydantic import TypeAdapter  # noqa: E402
from raes_backend_protocols.manifest import (  # noqa: E402
    backend_manifest_from_v2_model,
    backend_manifest_from_v2_model_with_envelope,
)
from raes_contracts.contracts import ProvisioningPlanModel  # noqa: E402
from raes_contracts.contracts.participant_manifests import BackendManifestV2Model  # noqa: E402
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel  # noqa: E402
from raes_contracts.realization_structure import (  # noqa: E402
    RealizationConstraintDocument,
    RealizationConstraintLimits,
    evaluate_realization_constraint,
)
from raes_processor.planner.realization_authority import (  # noqa: E402
    realization_authority_diagnostics,
    realization_authority_disclosure,
)
from raes_processor.planner.realization_cleanup import realization_cleanup_diagnostics  # noqa: E402
from raes_processor.semantics.realization import (  # noqa: E402
    realization_disclosure,
    realization_envelope_diagnostics,
)
from raes_processor.semantics.realization_requirement import (  # noqa: E402
    CompiledRealizationRequirement,
)
from raes_processor.semantics.realization_support import realization_support_diagnostics  # noqa: E402
from raes_runtime.control_plane_api_models import _provisioning_plan  # noqa: E402
from raes_runtime.snapshot_contract import (  # noqa: E402
    RuntimeSnapshotEnvelopeModel,
    runtime_snapshot_from_contract,
)

TESTDATA = ROOT / "implementations/go/processor/realization/testdata"
FAMILIES = {
    "portable": [
        "portable-realization-reference.json",
        "portable-realization-reference-2.json",
    ],
    "relations": [f"relations-reference{suffix}.json" for suffix in ("", *(f"-{n}" for n in range(2, 10)))],
}
LIBRARY = ("plans", "snapshots", "manifests", "envelopes", "requirements")


def _requirement_adapter() -> TypeAdapter[tuple[CompiledRealizationRequirement, ...]]:
    """Resolve the field types that the requirement dataclass names only for type checking."""
    from raes.artifact_requirements import ArtifactRequirement
    from raes_contracts.bounded_domains import DomainDescriptor
    from raes_processor.semantics import realization_requirement
    from raes_processor.semantics.realization_process_limits import (
        ProcessResourceLimitDemand,
        RealizationValueConstraint,
    )

    adapter = TypeAdapter(tuple[CompiledRealizationRequirement, ...])
    namespace = {
        **vars(realization_requirement),
        "ArtifactRequirement": ArtifactRequirement,
        "DomainDescriptor": DomainDescriptor,
        "ProcessResourceLimitDemand": ProcessResourceLimitDemand,
        "RealizationValueConstraint": RealizationValueConstraint,
    }
    adapter.rebuild(_types_namespace=namespace)
    return adapter


REQUIREMENTS = _requirement_adapter()


def load_family(
    names: list[str],
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    library: dict[str, dict[str, Any]] = {key: {} for key in LIBRARY}
    parts = []
    for name in names:
        part = json.loads((TESTDATA / name).read_text(encoding="utf-8"))
        for key in LIBRARY:
            library[key].update(part.get(key, {}))
        parts.append((name, part))
    return library, parts


class Inputs:
    """Typed reference objects built from the recorded portable inputs."""

    def __init__(self, library: dict[str, Any]) -> None:
        self.library = library

    def plan(self, key: str) -> object:
        return _provisioning_plan(ProvisioningPlanModel.model_validate(self.library["plans"][key]))

    def snapshot(self, key: str) -> object:
        envelope = {
            "schema_version": "runtime-snapshot/v1",
            **self.library["snapshots"][key],
        }
        return runtime_snapshot_from_contract(RuntimeSnapshotEnvelopeModel.model_validate(envelope))

    def manifest(self, key: str, envelope_key: str) -> object | None:
        if not key:
            return None
        model = BackendManifestV2Model.model_validate(self.library["manifests"][key])
        envelope = self.library["envelopes"].get(envelope_key) if envelope_key else None
        if envelope is None:
            return backend_manifest_from_v2_model(model)
        return backend_manifest_from_v2_model_with_envelope(
            model, BackendRealizationEnvelopeModel.model_validate(envelope)
        )

    def requirements(self, key: str) -> tuple[CompiledRealizationRequirement, ...]:
        return REQUIREMENTS.validate_python(self.library["requirements"].get(key, []) if key else [])


def diagnostics(items: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "code": item.code,
            "domain": item.domain,
            "address": item.address,
            "message": item.message,
            "severity": str(getattr(item.severity, "value", item.severity)),
        }
        for item in items
    ]


def provenance(items: tuple[Any, ...]) -> list[dict[str, str]]:
    def text(value: object) -> str:
        return "" if value is None else str(getattr(value, "value", value))

    return [
        {
            "Address": item.address,
            "FieldPath": item.field_path,
            "Domain": item.domain,
            "Kind": item.requirement_kind,
            "Posture": text(item.explicitness),
            "Provenance": text(item.provenance),
            "GoverningScope": text(item.governing_scope),
        }
        for item in items
    ]


Recorded = tuple[list[dict[str, str]], list[dict[str, str]]]


def _support(case: dict[str, Any], inputs: Inputs, manifest: object) -> Recorded:
    requirements = inputs.requirements(case["requirements"])
    found = [
        *realization_support_diagnostics(requirements, manifest),
        *realization_envelope_diagnostics(requirements, manifest),
    ]
    return diagnostics(found), case.get("provenance", [])


def _evaluate(case: dict[str, Any], inputs: Inputs, manifest: object) -> Recorded:
    found, entries = realization_disclosure(
        inputs.requirements(case["requirements"]),
        inputs.plan(case["plan"]),
        inputs.snapshot(case["snapshot"]),
        manifest=manifest,
    )
    return diagnostics(found), provenance(entries)


def _planned_evaluate(case: dict[str, Any], inputs: Inputs, manifest: object) -> Recorded:
    found, entries = realization_authority_disclosure(
        inputs.plan(case["plan"]), inputs.snapshot(case["snapshot"]), manifest=manifest
    )
    return diagnostics(found), provenance(entries)


def _planned_diagnostics(case: dict[str, Any], inputs: Inputs, manifest: object) -> Recorded:
    found = realization_authority_diagnostics(inputs.plan(case["plan"]), manifest)
    return diagnostics(found), case.get("provenance", [])


def _planned_cleanup(case: dict[str, Any], inputs: Inputs, manifest: object) -> Recorded:
    found = realization_cleanup_diagnostics(
        inputs.plan(case["plan"]),
        inputs.snapshot(case["snapshot"]),
        manifest=manifest,
        requirements=inputs.requirements(case.get("requirements", "")),
    )
    return diagnostics(found), case.get("provenance", [])


RELATIONS = {
    "support": _support,
    "evaluate": _evaluate,
    "planned-evaluate": _planned_evaluate,
    "planned-diagnostics": _planned_diagnostics,
    "planned-cleanup": _planned_cleanup,
}


def evaluate(case: dict[str, Any], inputs: Inputs) -> Recorded | None:
    relation = RELATIONS.get(case["relation"])
    if relation is None:
        return None
    return relation(case, inputs, inputs.manifest(case.get("manifest", ""), case.get("envelope", "")))


def patch_cases(name: str, updated: dict[str, dict[str, Any]]) -> None:
    """Rewrite only the changed case lines; each case occupies one line."""
    path = TESTDATA / name
    lines = path.read_text(encoding="utf-8").split("\n")
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith('{"name":'):
            continue
        case_name = json.loads(stripped.rstrip(","))["name"]
        if case_name in updated:
            comma = "," if stripped.endswith(",") else ""
            lines[index] = (
                line[: len(line) - len(stripped)] + json.dumps(updated.pop(case_name), separators=(",", ":")) + comma
            )
    if updated:
        raise ValueError(f"{name}: changed cases are not one line each: {sorted(updated)}")
    path.write_text("\n".join(lines), encoding="utf-8")


def _updated_cases(name: str, part: dict[str, Any], inputs: Inputs) -> dict[str, dict[str, Any]]:
    """Evaluate the cases of one reference part; return each case whose recording changed."""
    updated: dict[str, dict[str, Any]] = {}
    for case in part.get("cases", []):
        result = evaluate(case, inputs)
        if result is None or (case.get("diagnostics"), case.get("provenance")) == result:
            continue
        print(f"{name}: {case['name']} differs", file=sys.stderr)
        case["diagnostics"], case["provenance"] = result
        updated[case["name"]] = case
    return updated


def record(check: bool) -> bool:
    changed = False
    for names in FAMILIES.values():
        library, parts = load_family(names)
        inputs = Inputs(library)
        for name, part in parts:
            updated = _updated_cases(name, part, inputs)
            changed = changed or bool(updated)
            if updated and not check:
                patch_cases(name, updated)
    return changed


def patch_fields(name: str, updated: dict[str, dict[str, Any]]) -> None:
    """Rewrite the changed field lines of multi-line cases; each field occupies one line."""
    path = TESTDATA / name
    lines = path.read_text(encoding="utf-8").split("\n")
    current = None
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith('"name":'):
            current = json.loads("{" + stripped.rstrip(",") + "}")["name"]
            continue
        case = updated.get(current) if current is not None else None
        for field in ("status", "diagnostics"):
            if case is not None and stripped.startswith(f'"{field}":'):
                comma = "," if stripped.endswith(",") else ""
                encoded = json.dumps(case[field], separators=(",", ":"))
                lines[index] = line[: len(line) - len(stripped)] + f'"{field}":{encoded}{comma}'
    path.write_text("\n".join(lines), encoding="utf-8")


def record_constraints(check: bool) -> bool:
    """Re-record each constraint evaluation from its recorded document, value and limits."""
    name = "constraint-reference.json"
    cases = json.loads((TESTDATA / name).read_text(encoding="utf-8"))
    updated: dict[str, dict[str, Any]] = {}
    for case in cases:
        result = evaluate_realization_constraint(
            RealizationConstraintDocument.model_validate(case["constraint"]),
            case["actual"],
            limits=RealizationConstraintLimits(**(case.get("limits") or {})),
        )
        status = str(getattr(result.status, "value", result.status))
        found = diagnostics(list(result.diagnostics))
        if case["status"] != status or case["diagnostics"] != found:
            print(f"{name}: {case['name']} differs", file=sys.stderr)
            case["status"], case["diagnostics"] = status, found
            updated[case["name"]] = case
    if updated and not check:
        patch_fields(name, updated)
    return bool(updated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changed = record(args.check)
    changed = record_constraints(args.check) or changed
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())

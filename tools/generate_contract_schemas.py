#!/usr/bin/env python3
"""Generate checked-in JSON Schema bundles for RAES external contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_EXACT_SCHEMA_DIRECTORIES = (
    {
        "raes-semantic-invariants-v1": "profiles",
        "reusable-asset-trust-policy-v1": "asset-trust",
        "sdl-lineage-ledger-v1": "provenance",
        "associated-artifact-manifest-v1": "associated-artifacts",
        "runtime-snapshot-v1": "snapshots",
        "recursive-realization-constraint-v1": "realization-constraints",
        "backend-realization-preparation-v1": "plans",
        "plan-realization-profiles-v1": "plans",
    }
    | dict.fromkeys(
        {
            "sdl-authoring-input-v1",
            "instantiated-scenario-v1",
            "instantiated-scenario-snapshot-v1",
            "scenario-instantiation-request-v1",
        },
        "sdl",
    )
    | dict.fromkeys(
        {
            "concept-families-v1",
            "behavioral-relations-v1",
            "reference-models-v1",
            "uco-alignment-v1",
            "controlled-vocabularies-v1",
            "external-concept-bindings-v1",
            "semantic-projection-report-v1",
            "attack-enterprise-tactics-source-v1",
            "atlas-tactics-source-v1",
            "fipa-communicative-acts-source-v1",
            "nist-csf-defensive-categories-source-v1",
            "w3c-activitystreams-activity-types-source-v1",
        },
        "concept-authority",
    )
    | dict.fromkeys(
        {
            "participant-lifecycle-event-v1",
            "participant-observation-envelope-v1",
            "participant-information-state-record-v1",
            "participant-shared-state-record-v1",
            "participant-joint-action-record-v1",
            "participant-time-management-context-v1",
            "participant-control-occurrence-v1",
            "participant-crossing-occurrence-v1",
            "participant-flow-control-relation-v1",
            "participant-execution-binding-v1",
            "participant-execution-control-v1",
            "participant-execution-service-state-v1",
            "participant-resource-budget-policy-v1",
            "participant-resource-pool-capacity-v1",
            "participant-resource-budget-state-v1",
            "participant-resource-budget-event-v1",
            "participant-outcome-report-v1",
            "runtime-fact-binding-plane-v1",
        },
        "participant-runtime",
    )
    | dict.fromkeys(
        {
            "participant-status-view-v1",
            "participant-history-view-v1",
            "participant-context-view-v1",
        },
        "control-plane",
    )
    | dict.fromkeys(
        {"time-model-v1", "time-runtime-state-v1", "realized-time-model-v1"},
        "time",
    )
)

_PREFIX_SCHEMA_DIRECTORIES = (
    ("scenario-satisfiability-evidence-v", "satisfiability"),
    ("artifact-requirement-v", "artifact-requirements"),
    ("artifact-transformation-report-v", "artifact-transformations"),
    ("exploit-path-analysis-evidence-v", "exploit-path-analysis"),
    ("backend-manifest-v", "backend-manifest"),
    ("realization-envelope-v", "realization-envelope"),
    ("processor-manifest-v", "processor-manifest"),
    ("participant-implementation-manifest-v", "participant-implementation-manifest"),
    (
        "participant-implementation-provenance-v",
        "participant-implementation-provenance",
    ),
    ("participant-configuration-result-v", "participant-implementation-configuration"),
    ("semantic-profile-v", "profiles"),
    ("domain-profile-", "profiles"),
    ("backend-profile-v", "profiles"),
    ("random-stream-profile-v", "profiles"),
    ("participant-information-reconstruction-profile-v", "profiles"),
    ("participant-boundary-flow-policy-v", "profiles"),
    ("random-stream-vector-v", "profiles"),
    ("behavioral-relation-profile-v", "profiles"),
    ("participant-opacity-", "formal-analysis"),
    ("scientific-completeness-", "profiles"),
    ("validation-profile-", "profiles"),
    ("validation-basis-disclosure-", "profiles"),
    ("experiment-", "experiment-core"),
    ("semantic-comparison-", "semantic-comparison"),
    ("sdl-candidate-synthesis-", "candidate-synthesis"),
)


def _prefix_schema_directory(name: str) -> str | None:
    for prefix, directory in _PREFIX_SCHEMA_DIRECTORIES:
        if name.startswith(prefix):
            return directory
    return None


def _schema_output_path(schemas_dir: Path, name: str) -> Path:
    directory = _EXACT_SCHEMA_DIRECTORIES.get(name)
    if directory is None:
        directory = _prefix_schema_directory(name)
    if directory is None and name.endswith("-plan-v1"):
        directory = "plans"
    if directory is None:
        directory = "control-plane"
    return schemas_dir / directory / f"{name}.json"


def write_schema_bundle(schemas_dir: Path) -> None:
    """Write the reference implementation's schema bundle into ``schemas_dir``.

    The published schemas under ``contracts/schemas/`` are the hand-governed
    normative authority (ADR-009 §7); the Python ``schema_bundle()`` is the
    reference implementation's output, kept identical to that authority as a
    compatibility proof. ``check_generated_schemas.py`` calls this with a
    throwaway directory so it can compare the reference output against the
    published normative schemas without overwriting them.
    """
    from raes_contracts.contracts import schema_bundle

    bundle = schema_bundle()
    for name, schema in bundle.items():
        output_path = _schema_output_path(schemas_dir, name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    python_root = repo_root / "implementations" / "python"
    sys.path.insert(0, str(python_root / "src"))
    sys.path.insert(0, str(python_root / "packages"))

    write_schema_bundle(repo_root / "contracts" / "schemas")


if __name__ == "__main__":
    main()

"""Reproduce the issue-1198 static census and bounded behavioral probes.

Run from the repository root with implementations/python/.venv/bin/python.
This is research evidence, not a language validator or conformance suite.
The census lists candidates; an enum or Literal is not itself a defect.
"""

from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path


def census() -> dict:
    root = Path("implementations/python/packages")
    files = sorted(root.rglob("*.py"))
    enums = []
    literals = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                ast.unparse(base).endswith("Enum") for base in node.bases
            ):
                values = [
                    child.value.value
                    for child in node.body
                    if isinstance(child, (ast.Assign, ast.AnnAssign))
                    and isinstance(child.value, ast.Constant)
                ]
                enums.append(
                    {
                        "path": str(path),
                        "line": node.lineno,
                        "name": node.name,
                        "values": values,
                    }
                )
            if isinstance(node, ast.Subscript) and ast.unparse(node.value) in {
                "Literal",
                "typing.Literal",
            }:
                literals.append(
                    {
                        "path": str(path),
                        "line": node.lineno,
                        "annotation": ast.unparse(node),
                    }
                )

    schema_files = sorted(Path("contracts/schemas").rglob("*.json"))
    schema_counts = Counter()

    def walk_schema(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"enum", "const", "required", "discriminator"}:
                    schema_counts[key] += 1
                if key == "additionalProperties" and child is False:
                    schema_counts["additionalProperties:false"] += 1
                walk_schema(child)
        elif isinstance(value, list):
            for child in value:
                walk_schema(child)

    for path in schema_files:
        walk_schema(json.loads(path.read_text(encoding="utf-8")))
    sdl_enums = [row for row in enums if "/raes/" in row["path"]]
    sentinels = [
        row
        for row in sdl_enums
        if "other" in row["values"] or "unknown" in row["values"]
    ]
    catalog = json.loads(
        Path("contracts/concept-authority/controlled-vocabularies-v1.json").read_text(
            encoding="utf-8"
        )
    )
    vocabularies = {
        name: {
            "policy": value["extension_policy"],
            "pattern": value.get("extension_pattern"),
            "terms": len(value["terms"]),
        }
        for name, value in catalog["vocabularies"].items()
    }
    return {
        "summary": {
            "python_files": len(files),
            "enum_definitions": len(enums),
            "sdl_enum_definitions": len(sdl_enums),
            "sdl_enums_with_other_or_unknown": len(sentinels),
            "literal_annotations": len(literals),
            "schema_files": len(schema_files),
            "schema_keyword_occurrences_not_unique_concepts": dict(schema_counts),
        },
        "vocabularies": vocabularies,
        "enums": enums,
        "literals": literals,
    }


def probes() -> dict:
    from dataclasses import replace

    from pydantic import ValidationError
    from raes import parse_sdl
    from raes.explicitness import ExplicitnessClass, classify_model_explicitness
    from raes.nodes import Node
    from raes.realization_designation import (
        RealizationDesignation,
        designation_records,
        resolve_realization_designation,
    )
    from raes.runtime_database_vocab import DatabaseEngine
    from raes.runtime_datastore import RuntimeDatastoreService
    from raes.runtime_forwarding_agent import RuntimeForwardingAgent
    from raes.runtime_packages import RuntimePackage
    from raes_backend_protocols.capabilities import (
        BackendManifest,
        ProvisionerCapabilities,
    )
    from raes_contracts.apparatus import (
        ConceptBinding,
        RealizationObservationCapability,
        RealizationSupportDeclaration,
    )
    from raes_contracts.planning import (
        ChangeAction,
        ProvisioningPlan,
        ProvisionOp,
        RuntimeDomain,
    )
    from raes_contracts.realization_observation import RealizationObservationDisclosure
    from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
    from raes_contracts.vocabulary import (
        ObservationStrength,
        RealizationSupportMode,
        RealizationVerificationScope,
    )
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.compiler.realization_concern_explicitness import (
        semantic_explicitness_record,
    )
    from raes_processor.semantics.realization_runtime_evaluation import (
        evaluate_registered_realization,
    )

    results = {}

    def attempt(name, model, value):
        try:
            result = model.model_validate(value)
            results[name] = {"accepted": True, "value": result.model_dump(mode="json")}
        except ValidationError as exc:
            results[name] = {
                "accepted": False,
                "errors": [
                    {"path": list(error["loc"]), "type": error["type"]}
                    for error in exc.errors()
                ],
            }

    attempt("package-name-only", RuntimePackage, {"name": "wazuh-agent"})
    attempt(
        "package-private-manager-no-repository",
        RuntimePackage,
        {
            "manager": "private-manager",
            "name": "sensor",
            "version": "1",
        },
    )
    attempt(
        "package-private-repository",
        RuntimePackage,
        {
            "manager": "private-manager",
            "name": "sensor",
            "version": "1",
            "repository": {
                "repository_profile": "x-lab:private",
                "profile_version": "1",
            },
        },
    )
    attempt(
        "private-distribution",
        Node,
        {
            "type": "compute",
            "os_distribution": "x-lab:private-os",
        },
    )
    try:
        DatabaseEngine("x-lab:private-db")
        results["private-database-engine"] = {"accepted": True}
    except ValueError:
        results["private-database-engine"] = {"accepted": False}

    node = Node.model_validate(
        {
            "type": "compute",
            "runtime": {
                "database_services": [{"database_service_id": "db", "engine": "other"}],
            },
        }
    )
    explicitness = classify_model_explicitness(node, variables={})
    record = semantic_explicitness_record(
        explicitness.records,
        field_path="runtime.database_services",
        excluded_fields=frozenset({"description", "evidence_refs", "readiness"}),
    )
    results["mixed-known-id-and-other-engine"] = {
        "leaves": {
            key: value.classification.value
            for key, value in explicitness.records.items()
            if key.startswith("runtime.database_services")
        },
        "aggregate": record.classification.value,
    }
    db_scenario = parse_sdl("""name: database-audit
nodes:
  host:
    type: compute
    runtime:
      database_services:
        - database_service_id: db
          engine: other
""")
    db_compiled = compile_runtime_model(db_scenario)
    db_requirement = next(
        item
        for item in db_compiled.realization_requirements
        if item.requirement_kind == "runtime-database-services"
    )

    def db_payload(identity):
        return {
            "spec": {
                "node": {
                    "runtime": {
                        "database_services": [
                            {"database_service_id": identity, "engine": "other"},
                        ]
                    }
                }
            }
        }

    declared_plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=db_requirement.address,
                resource_type="node",
                payload=db_payload("db"),
            )
        ]
    )
    observation = RealizationObservationDisclosure(
        address=db_requirement.address,
        field_path=db_requirement.field_path,
        domain=db_requirement.domain,
        requirement_kind=db_requirement.requirement_kind,
        verification_scope=RealizationVerificationScope.CONFIGURATION,
        observation_strength=ObservationStrength.GUEST_OBSERVED,
    )
    manifest = BackendManifest(
        name="audit",
        version="1",
        supported_contract_versions=frozenset({"backend-manifest-v2"}),
        compatible_processors=frozenset({"audit"}),
        concept_bindings=(
            ConceptBinding(
                scope="capabilities.provisioner.supported_node_types", family="assets"
            ),
        ),
        provisioner=ProvisionerCapabilities(
            name="audit",
            supported_node_types=frozenset({"compute"}),
            supported_os_families=frozenset({"linux"}),
        ),
        realization_support=(
            RealizationSupportDeclaration(
                domain="runtime-realization",
                support_mode=RealizationSupportMode.OPEN_REALIZATION,
                supported_exact_requirement_kinds=frozenset(
                    {"declared-capability-match"}
                ),
                disclosure_kinds=frozenset({"runtime-snapshot-v1"}),
                observation_capabilities={
                    "runtime-database-services": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    )
                },
            ),
        ),
    )
    snapshot = RuntimeSnapshot(
        entries={
            db_requirement.address: SnapshotEntry(
                address=db_requirement.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload=db_payload("different-db"),
            )
        },
        realization_observations=(observation,),
    )
    diagnostic, _ = evaluate_registered_realization(
        db_requirement,
        declared_plan,
        snapshot,
        manifest=manifest,
    )
    exact_diagnostic, _ = evaluate_registered_realization(
        replace(db_requirement, explicitness=ExplicitnessClass.EXACT),
        declared_plan,
        snapshot,
        manifest=manifest,
    )
    results["changed-exact-id-at-runtime-evaluator"] = {
        "compiled_mode": db_requirement.explicitness.value,
        "diagnostic": diagnostic.code if diagnostic else None,
        "exact-mode-negative-control": exact_diagnostic.code
        if exact_diagnostic
        else None,
        "scope": "single registered-concern evaluator; not full backend execution",
    }
    attempt(
        "partial-key-value-store",
        RuntimeDatastoreService,
        {
            "datastore_service_id": "cache",
            "data_model": "key_value",
        },
    )
    attempt(
        "partial-log-forwarder",
        RuntimeForwardingAgent,
        {
            "forwarding_agent_id": "agent",
            "agent_kind": "log_forwarder",
        },
    )

    source = """name: audit
nodes:
  host:
    type: compute
    runtime:
      packages:
        - manager: apt
          name: sensor
          version: '1'
realization:
  default: closed
  scopes:
    - field_pointer: /nodes/host/runtime/packages/0/repository
      posture: open
"""
    compiled = compile_runtime_model(parse_sdl(source))
    results["nested-repository-open-scope"] = {
        "authority": [
            {"field_path": item.field_path, "mode": item.mode.value}
            for item in compiled.realization_authority
            if item.requirement_kind == "runtime-packages"
        ],
    }
    designation = RealizationDesignation.model_validate(
        {
            "default": "closed",
            "scopes": [{"field_pointer": "/nodes/host", "posture": "unspecified"}],
        }
    )
    resolved = resolve_realization_designation(
        designation_records(designation),
        field_pointer="/nodes/host/os",
    )
    results["inner-unspecified-under-outer-closed"] = {
        "closure": resolved.closure.value,
        "source": resolved.source,
        "delegated": resolved.delegated,
    }
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("census", "probes"))
    args = parser.parse_args()
    print(json.dumps(census() if args.mode == "census" else probes(), indent=2))

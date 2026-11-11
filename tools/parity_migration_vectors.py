#!/usr/bin/env python3
"""Record source-bound semantic migration results from the Python owner."""

from __future__ import annotations

import argparse
import base64
import copy
import gzip
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))
sys.path.insert(0, str(ROOT / "implementations/python/tests"))

import test_issue_1678_sweep_s as refusal_sources  # noqa: E402
import yaml  # noqa: E402
from mixed_control_rev1_scenarios import rev1_scenario  # noqa: E402
from raes import parse_sdl  # noqa: E402
from raes.classification_migration import migrate_sdl_classifications  # noqa: E402
from raes.external_concept_subjects import external_concept_subjects  # noqa: E402
from raes.mixed_control_migration import migrate_mixed_control_to_finite_script  # noqa: E402
from raes.participant_migration import (  # noqa: E402
    ParticipantIdentityMigrationContext,
    migrate_participant_identity,
)
from raes.semantic_migration import SDLSemanticMigrationContext, migrate_sdl_semantics  # noqa: E402
from raes.semantic_revisions import PROGRESSIVE_SDL_REVISION  # noqa: E402
from raes.transformations import ArtifactTransformationPolicy  # noqa: E402
from raes_contracts.contracts import (  # noqa: E402
    ArtifactTransformationLossKind,
    ExternalConceptBindingDocumentModel,
)
from raes_contracts.external_concept_bindings import ExternalConceptSchemeSnapshotModel  # noqa: E402
from test_classification_migration import (  # noqa: E402
    LEGACY_SOURCE,
    NATIVE_MIGRATION_SOURCE,
    _migration_inputs,
)
from test_issue_847_runtime_package_repositories import _package  # noqa: E402
from test_issue_1210_semantic_migration import context  # noqa: E402
from test_issue_1338_identity_migration import _legacy  # noqa: E402
from test_issue_1363_mixed_control_migration import (  # noqa: E402
    CANCEL_CHAIN,
    DECISION_CHAIN,
    HANDOFF_CHAIN,
    REFUSALS,
    _state,
)
from test_issue_1363_mixed_control_migration import (  # noqa: E402
    _legacy as _legacy_control,
)

CaseRows = list[dict[str, Any]]
ClassificationRecorder = Callable[..., None]
OLD_SOURCE = "name: old\n"
GOAL_POINTER = "/objectives/goal"
DIGEST_PREFIX = "sha256:"
PROGRESSIVE_OPERATION = "adopt-progressive-sdl-semantics/v1"


def progressive_cases(rows: CaseRows) -> None:
    def add(name: str, source: str, author: SDLSemanticMigrationContext | None = None) -> None:
        result = migrate_sdl_semantics(source, context=author)
        rows.append(
            {
                "name": name,
                "source": source,
                "context": author.model_dump(mode="json") if author else None,
                "output": result.output.model_dump(mode="json", exclude_unset=True) if result.output else None,
                "result": {
                    "report": result.report.model_dump(mode="json"),
                    "binding_documents": [value.model_dump(mode="json") for value in result.binding_documents],
                },
            }
        )

    add("context-required", OLD_SOURCE)
    add("minimal-adoption", OLD_SOURCE, context(OLD_SOURCE))
    add("stale-source", "name: changed\n", context("name: original\n"))
    package = yaml.safe_dump(
        {
            "name": "old",
            "nodes": {"host": {"type": "compute", "runtime": {"packages": [_package()]}}},
        }
    )
    add("exact-repository", package, context(package))
    source = (
        "name: old\nnodes: {host: {type: compute, runtime: "
        "{database_services: [{database_service_id: db, engine: other}]}}}\n"
    )
    pointer = "/nodes/host/runtime/database_services/0/engine"
    add("missing-sentinel", source, context(source))
    for interpretation, identity in (
        ("knowledge", None),
        ("exact-identity", "x-owner:private-db"),
        ("delegated", None),
    ):
        decision = {
            "pointer": pointer,
            "interpretation": interpretation,
            "identity": identity,
            "rationale": "Author reviewed the source.",
        }
        add("sentinel-" + interpretation, source, context(source, (decision,)))
        if interpretation == "delegated":
            opened = source + "realization: {default: open}\n"
            add("open-delegation", opened, context(opened, (decision,)))
    progressive_list_cases(add)
    for name, source in [
        (
            "arbitrary-strings",
            "name: old\ndescription: other\nnodes: {host: {type: compute, runtime: "
            "{environment: [{name: MODE, value: unknown}]}}}\n",
        ),
        ("imports", "name: old\nimports: [{path: module.yaml, namespace: module}]\n"),
        ("unsupported-revision", "name: old\nsemantic_revision: unsupported\n"),
        ("invalid-source", "[broken"),
        ("non-mapping", "[]\n"),
    ]:
        add(name, source, context(source))
    current = "name: current\nsemantic_revision: " + PROGRESSIVE_SDL_REVISION + "\n"
    add("current-noop", current)
    add("current-with-context", current, context(current))


def progressive_list_cases(record: Callable[[str, str, SDLSemanticMigrationContext], None]) -> None:
    for reverse in (False, True):
        for index, (protocols, actions) in enumerate(
            [
                (["other"], [(0, "http")]),
                (["other"], [(0, None)]),
                (["other", "tls", "unknown"], [(0, None), (2, None)]),
                (["other", "tls", "unknown"], [(0, None), (2, "http")]),
            ]
        ):
            source = yaml.safe_dump(
                {
                    "name": "old",
                    "realization": {"default": "open"},
                    "nodes": {
                        "host": {
                            "type": "compute",
                            "runtime": {
                                "network_detection_engines": [
                                    {
                                        "network_detection_engine_id": "ids",
                                        "app_layer_protocols": protocols,
                                    }
                                ],
                            },
                        },
                    },
                }
            )
            decisions = [
                {
                    "pointer": f"/nodes/host/runtime/network_detection_engines/0/app_layer_protocols/{position}",
                    "interpretation": "exact-identity" if identity else "delegated",
                    "identity": identity,
                    "rationale": "Author reviewed the original collection.",
                }
                for position, identity in actions
            ]
            if reverse:
                decisions.reverse()
            record(f"list-decisions-{index}-{reverse}", source, context(source, decisions))


def participant_cases(rows: CaseRows) -> None:
    def participant(
        name: str,
        payload: dict[str, Any] | list[Any],
        decisions: dict[str, str | None] | None = None,
        digest: str | None = None,
    ) -> None:
        source = yaml.safe_dump(payload, sort_keys=False)
        author = (
            None
            if decisions is None
            else ParticipantIdentityMigrationContext(
                source_digest=digest or context(source).source_digest,
                entity_objectives=decisions,
            )
        )
        result = migrate_participant_identity(source, context=author)
        rows.append(
            {
                "name": "participant-" + name,
                "source": source,
                "context": {
                    "operation_profile": "adopt-participant-identity/v1",
                    "context": author.model_dump(mode="json") if author else None,
                },
                "output": result.output.model_dump(mode="json", exclude_unset=True) if result.output else None,
                "result": {"report": result.report.model_dump(mode="json"), "binding_documents": []},
            }
        )

    participant("assignment", _legacy(organizational=False))
    participant("owner-only", _legacy(), {GOAL_POINTER: None})
    participant("owner-and-participant", _legacy(), {GOAL_POINTER: "one"})
    participant("decision-required", _legacy())
    participant("empty-decisions", _legacy(), {})
    participant("stale-source", _legacy(), {GOAL_POINTER: None}, DIGEST_PREFIX + "0" * 64)
    participant(
        "extra-decision",
        _legacy(),
        {GOAL_POINTER: None, "/objectives/extra": None},
    )
    for change in (
        "conflict",
        "unknown",
        "action",
        "assignment",
        "both-legacy",
        "import",
    ):
        payload = _legacy()
        if change == "conflict":
            payload["agents"]["one"]["affiliations"] = ["team"]
        elif change == "unknown":
            payload["agents"]["one"]["hidden_field"] = "private-value-do-not-echo"
        elif change == "action":
            payload["objectives"]["goal"]["actions"] = ["private-value-do-not-echo"]
        elif change == "assignment":
            payload["objectives"]["goal"]["actions"] = ["observe"]
        elif change == "both-legacy":
            payload["objectives"]["goal"]["agent"] = "one"
        else:
            payload["imports"] = [{"path": "external.yaml", "namespace": "other"}]
        participant(
            change,
            payload,
            {GOAL_POINTER: "two" if change == "assignment" else None},
        )
    aliased = _legacy()
    aliased["objectives"]["second"] = aliased["objectives"]["goal"]
    participant(
        "alias-decisions",
        aliased,
        {GOAL_POINTER: "one", "/objectives/second": "two"},
    )
    for section in ("agents", "objectives", "variation_points"):
        payload = _legacy()
        payload[section] = []
        participant("invalid-" + section, payload)
    participant("non-mapping", [])
    participant("materialized", {"materialization_provenance": {}})
    participant("minimal-current", {"name": "current"})
    earliest = _legacy()
    earliest["objectives"]["earlier"] = copy.deepcopy(earliest["objectives"]["goal"])
    participant("sorted-decision", earliest)
    unresolved = _legacy(organizational=False)
    unresolved["variables"] = {"team": {"type": "string", "default": "team"}}
    unresolved["agents"]["one"]["entity"] = "${team}"
    participant("unresolved-affiliation", unresolved)


def mixed_cases(rows: CaseRows) -> None:
    def mixed(name: str, payload: dict[str, Any]) -> None:
        source = yaml.safe_dump(payload, sort_keys=False)
        result = migrate_mixed_control_to_finite_script(source)
        rows.append(
            {
                "name": "mixed-" + name,
                "source": source,
                "context": {"operation_profile": "convert-mixed-control-finite-script/v1"},
                "output": result.output.model_dump(mode="json", exclude_unset=True) if result.output else None,
                "result": {"report": result.report.model_dump(mode="json"), "binding_documents": []},
            }
        )

    for name, payload in (
        ("handoff", HANDOFF_CHAIN),
        ("decisions", DECISION_CHAIN),
        ("cancel", CANCEL_CHAIN),
        ("current", rev1_scenario()),
        ("minimal", {"name": "current"}),
        ("nonmapping", []),
    ):
        mixed(name, payload)
    for name, build, _ in REFUSALS:
        mixed(name, build())
    invalid = copy.deepcopy(HANDOFF_CHAIN)
    invalid["behavior_specifications"]["controlled-red"]["mixed_control"]["transitions"]["return"].update(
        expected_state_revision=7, resulting_state_revision=8
    )
    mixed("invalid-revision", invalid)
    same_controller = _legacy_control(
        {"autonomous": _state("self"), "supervised": _state("self")},
        [("take", "handoff", "autonomous", "supervised", 0, 10, None)],
    )
    mixed("issue-1678-handoff-pointer", same_controller)
    renamed = copy.deepcopy(same_controller)
    specs = renamed["behavior_specifications"]
    specs["transition-red"] = specs.pop("controlled-red")
    mixed("issue-1678-owner-name", renamed)
    imitated = copy.deepcopy(HANDOFF_CHAIN)
    imitated["behavior_specifications"]["controlled-red"]["mixed_control"]["controller_states"]["autonomous"][
        "evidence_refs"
    ] = ["Behavior specification 'controlled-red' mixed_control transition 'take'"]
    mixed("issue-1678-imitated-label", imitated)
    revoked = rev1_scenario()
    revoked["behavior_specifications"]["controlled-red"]["mixed_control"]["controller_states"]["supervised"][
        "authority_status"
    ] = "revoked"
    mixed("issue-1678-rev1-pointer", revoked)


def classification_cases(rows: CaseRows) -> None:
    def classification(
        name: str,
        source: str,
        bindings: ExternalConceptBindingDocumentModel | None = None,
        snapshots: tuple[ExternalConceptSchemeSnapshotModel, ...] = (),
        existing: tuple[ExternalConceptBindingDocumentModel, ...] = (),
        losses: tuple[str, ...] = (),
    ) -> None:
        policy = ArtifactTransformationPolicy(
            allowed_loss_kinds=tuple(ArtifactTransformationLossKind(value) for value in losses)
        )
        result = migrate_sdl_classifications(
            source,
            bindings=bindings,
            scheme_snapshots=snapshots,
            existing_binding_documents=existing,
            policy=policy,
        )
        author = {
            "bindings": bindings.model_dump(mode="json") if bindings else None,
            "snapshots": [value.model_dump(mode="json") for value in snapshots],
            "existing": [value.model_dump(mode="json") for value in existing],
            "policy": {"allowed_loss_kinds": list(losses)},
        }
        rows.append(
            {
                "name": "classification-" + name,
                "source": source,
                "context": {
                    "operation_profile": "externalize-sdl-classifications/v1",
                    "context": author,
                },
                "output": result.output.model_dump(mode="json", exclude_unset=True) if result.output else None,
                "result": {
                    "report": result.report.model_dump(mode="json"),
                    "binding_documents": [value.model_dump(mode="json") for value in result.binding_documents],
                },
            }
        )

    document, snapshot = _migration_inputs()
    classification(
        "complete",
        LEGACY_SOURCE,
        document,
        (snapshot,),
        losses=("declaration-removed",),
    )
    classification("context-required", LEGACY_SOURCE)
    classification_mutations(classification, document, snapshot)
    classification_source_variants(classification)
    classification_surfaces(classification)
    classification_existing(classification, document, snapshot)


def classification_mutations(
    classification: ClassificationRecorder,
    document: ExternalConceptBindingDocumentModel,
    snapshot: ExternalConceptSchemeSnapshotModel,
) -> None:
    for mutation in (
        "unavailable",
        "stale-snapshot",
        "unknown-concept",
        "duplicate-snapshot",
        "stale-subject",
        "wrong-subject",
        "missing-pointer",
        "unauthorized-loss",
    ):
        payload = document.model_dump(mode="json")
        binding = payload["bindings"]["attack-execution"]
        snapshots, losses = (snapshot,), ("declaration-removed",)
        if mutation == "unavailable":
            snapshots = ()
        elif mutation == "stale-snapshot":
            snapshots = (snapshot.model_copy(update={"revision": "2"}),)
        elif mutation == "unknown-concept":
            snapshots = (
                snapshot.model_copy(
                    update={"concepts": [snapshot.concepts[0].model_copy(update={"concept_id": "another-concept"})]}
                ),
            )
        elif mutation == "duplicate-snapshot":
            snapshots = (snapshot, snapshot)
        elif mutation == "stale-subject":
            binding["subject"]["artifact_digest"] = DIGEST_PREFIX + "f" * 64
        elif mutation == "wrong-subject":
            binding["subject"]["canonical_ref"] = "nodes.other"
        elif mutation == "missing-pointer":
            binding["provenance"]["source_refs"][0]["ref_path"] = "/nodes/other/vulnerabilities/0"
        else:
            losses = ()
        classification(
            mutation,
            LEGACY_SOURCE,
            ExternalConceptBindingDocumentModel.model_validate(payload),
            snapshots,
            losses=losses,
        )


def classification_source_variants(classification: ClassificationRecorder) -> None:
    for name, suffix in (
        ("dangling", "infrastructure: {web: {count: 1, links: [injection]}}\n"),
        ("normalization", ""),
    ):
        source = (
            LEGACY_SOURCE + suffix
            if suffix
            else LEGACY_SOURCE.replace("type: compute", "type: compute\n    resources: {ram: 1 GiB, cpu: 1}")
        )
        binding, scheme = _migration_inputs(source)
        classification(name, source, binding, (scheme,), losses=("declaration-removed",))
    classification("native", "name: native\nnodes: {web: {type: compute}}\n")
    for index, losses in enumerate(((), ("declaration-removed",), ("declaration-removed", "semantic-omission"))):
        classification(
            "unreferenced-" + str(index),
            LEGACY_SOURCE.replace("vulnerabilities: [injection]", "vulnerabilities: []"),
            losses=losses,
        )
    for index, source in enumerate(
        (
            "name: invalid\nname: duplicate\n",
            "name: invalid\nvulnerabilities: {v: {class: CWE-89, technical: 'true'}}\n",
            "name: invalid\nnodes: {web: {type: compute, vulnerabilities: ['${label}']}}\n",
            "name: invalid\nnodes: {web: {type: compute, vulnerabilities: [missing]}}\n",
            "name: invalid\ninstantiation_provenance: {}\n",
            "name: invalid\nvulnerabilities: []\n",
            "name: invalid\nimports: [{path: other.yaml, namespace: other}]\n",
        )
    ):
        classification("malformed-" + str(index), source)


def classification_surfaces(classification: ClassificationRecorder) -> None:
    native = parse_sdl(NATIVE_MIGRATION_SOURCE)
    surfaces = [
        (("nodes", "web"), "vulnerabilities", "nodes.web"),
        (("features", "service"), "vulnerabilities", "features.service"),
        (("entities", "team"), "vulnerabilities", "entities.team"),
        (
            ("entities", "team", "entities", "member"),
            "vulnerabilities",
            "entities.team.member",
        ),
        (
            ("entities", "team", "entities", "member"),
            "categories",
            "entities.team.member",
        ),
        *(
            (
                ("behavior_specifications", "behavior"),
                field,
                "behavior_specifications.behavior",
            )
            for field in (
                "offensive_behavior_refs",
                "ai_offensive_behavior_refs",
                "defensive_behavior_refs",
            )
        ),
        (
            ("action_contracts", "inspect"),
            "external_mappings",
            "action_contracts.inspect",
        ),
        (
            ("nodes", "web", "runtime", "applications", 0, "routes", 0),
            "vulnerability_refs",
            "nodes.web.runtime.applications.portal.routes.upload",
        ),
    ]
    for index, (path, field, subject) in enumerate(surfaces):
        payload = native.model_dump(mode="json", by_alias=True, exclude_unset=True)
        cursor = payload
        for part in path:
            cursor = cursor[part]
        if field in ("vulnerabilities", "vulnerability_refs"):
            payload["vulnerabilities"] = {
                "injection": {
                    "name": "Injection",
                    "description": "Authored weakness label",
                    "class": "CWE-89",
                },
            }
            cursor[field] = ["injection"]
        elif field == "external_mappings":
            cursor[field] = [
                {
                    "system": "custom-scheme",
                    "identifier": "old-label",
                    "loss_label": "lossy",
                    "rationale": "Historical authored rationale",
                }
            ]
        else:
            cursor[field] = ["old-label"]
        source = yaml.safe_dump(payload, sort_keys=False)
        binding, scheme = _migration_inputs(source)
        context_payload = binding.model_dump(mode="json")
        assertion = context_payload["bindings"]["attack-execution"]
        identity = assertion["subject"]["artifact_digest"]
        assertion["subject"] = next(
            s for s in external_concept_subjects(native) if s.canonical_ref == subject
        ).model_dump(mode="json")
        assertion["subject"]["artifact_digest"] = identity
        assertion["provenance"]["source_refs"][0]["ref_path"] = "/" + "/".join(map(str, (*path, field, 0)))
        classification(
            "surface-" + str(index),
            source,
            ExternalConceptBindingDocumentModel.model_validate(context_payload),
            (scheme,),
            losses=("declaration-removed",),
        )


def classification_existing(
    classification: ClassificationRecorder,
    document: ExternalConceptBindingDocumentModel,
    snapshot: ExternalConceptSchemeSnapshotModel,
) -> None:
    existing = document.model_dump(mode="json")
    existing["binding_set_id"] = "existing-interpretation"
    existing["bindings"]["attack-execution"]["provenance"]["source_refs"][0]["ref_path"] = "/nodes/web"
    classification(
        "existing",
        LEGACY_SOURCE,
        document,
        (snapshot,),
        (ExternalConceptBindingDocumentModel.model_validate(existing),),
        ("declaration-removed",),
    )


def linked_cases(rows: CaseRows) -> None:
    document, snapshot = _migration_inputs()
    classified = migrate_sdl_classifications(
        LEGACY_SOURCE,
        bindings=document,
        scheme_snapshots=(snapshot,),
        policy=ArtifactTransformationPolicy(allowed_loss_kinds=(ArtifactTransformationLossKind.DECLARATION_REMOVED,)),
    )
    source = yaml.safe_dump(classified.output.model_dump(mode="json", exclude_unset=True), sort_keys=False)
    for name in ("complete", "missing-snapshot", "stale-subject", "current-noop"):
        bindings = classified.binding_documents
        snapshots = () if name == "missing-snapshot" else (snapshot,)
        if name == "stale-subject":
            payload = bindings[0].model_dump(mode="json")
            payload["bindings"]["attack-execution"]["subject"]["artifact_digest"] = DIGEST_PREFIX + "f" * 64
            bindings = (ExternalConceptBindingDocumentModel.model_validate(payload),)
        author, linked_source = context(source), source
        if name == "current-noop":
            first = migrate_sdl_semantics(
                source,
                context=author,
                binding_documents=bindings,
                scheme_snapshots=snapshots,
            )
            linked_source = yaml.safe_dump(
                first.output.model_dump(mode="json", exclude_unset=True),
                sort_keys=False,
            )
            author, bindings = None, first.binding_documents
        result = migrate_sdl_semantics(
            linked_source,
            context=author,
            binding_documents=bindings,
            scheme_snapshots=snapshots,
        )
        author_payload = {
            "author": author.model_dump(mode="json") if author else None,
            "bindings": [value.model_dump(mode="json") for value in bindings],
            "snapshots": [value.model_dump(mode="json") for value in snapshots],
        }
        rows.append(
            {
                "name": "progressive-linked-" + name,
                "source": linked_source,
                "context": {
                    "operation_profile": PROGRESSIVE_OPERATION,
                    "context": author_payload,
                },
                "output": result.output.model_dump(mode="json", exclude_unset=True) if result.output else None,
                "result": {
                    "report": result.report.model_dump(mode="json"),
                    "binding_documents": [value.model_dump(mode="json") for value in result.binding_documents],
                },
            }
        )


def boundary_cases(rows: CaseRows) -> None:
    boundary_sources = [
        (name.removeprefix("_").lower(), getattr(refusal_sources, name))
        for name in (
            "_FEATURE_LIST",
            "_ROLE_LIST",
            "_STEP_TYPE",
            "_SURROGATE_VALUE",
            "_SURROGATE_KEY",
            "_DEEP_FLOW",
            "_DEEP_BLOCK",
            "_HUGE_RAM",
            "_HUGE_SPEED",
            "_NON_CANONICAL_TARGET",
        )
    ]
    boundary_sources += [
        (
            "oversized-decimal",
            refusal_sources._integer_source(refusal_sources._DECIMAL),
        ),
        ("oversized-hex", refusal_sources._integer_source(refusal_sources._HEX)),
        ("unpaired-utf8", "name: legacy\ud800\n"),
        ("unicode-index", refusal_sources._realization_source("²")),
        ("noncanonical-asset", refusal_sources._oversized_asset_source()),
        ("unhashable-revision", "name: old\nsemantic_revision: []\n"),
    ]
    for name, source in boundary_sources:
        for operation, migrate in (
            (PROGRESSIVE_OPERATION, migrate_sdl_semantics),
            ("adopt-participant-identity/v1", migrate_participant_identity),
            (
                "convert-mixed-control-finite-script/v1",
                migrate_mixed_control_to_finite_script,
            ),
            ("externalize-sdl-classifications/v1", migrate_sdl_classifications),
        ):
            author = context(source) if operation == PROGRESSIVE_OPERATION else None
            result = migrate(source, context=author) if author else migrate(source)
            author_payload = author.model_dump(mode="json") if author else None
            rows.append(
                {
                    "name": "issue-1678-" + operation.split("/")[0] + "-" + name,
                    "source": "",
                    "source_bytes": base64.b64encode(source.encode("utf-8", errors="surrogatepass")).decode("ascii"),
                    "context": author_payload if author else {"operation_profile": operation},
                    "output": result.output.model_dump(mode="json", exclude_unset=True) if result.output else None,
                    "result": {
                        "report": result.report.model_dump(mode="json"),
                        "binding_documents": [],
                    },
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    rows: CaseRows = []
    progressive_cases(rows)
    participant_cases(rows)
    mixed_cases(rows)
    classification_cases(rows)
    linked_cases(rows)
    boundary_cases(rows)
    encoded = json.dumps({"cases": rows}, indent=2, ensure_ascii=True) + "\n"
    target = ROOT / "implementations/go/internal/sdl/authoring/testdata/migrations.json.gz"
    if arguments.check:
        return int(gzip.decompress(target.read_bytes()).decode() != encoded)
    target.write_bytes(gzip.compress(encoded.encode(), mtime=0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

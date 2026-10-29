"""Revision-pinned multi-operation construction, reusing inert export plumbing."""

import ast
from dataclasses import asdict, fields
from pathlib import Path

from raes_contracts._participant_crossing_multi_profile import MultiParticipantCrossingParametersModel
from raes_contracts.behavioral_relation_profiles import BehavioralRelationProfileModel
from raes_contracts.behavioral_relations import load_behavioral_relation_catalog_revision
from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest
from raes_contracts.json_ingress import parse_bounded_json_object

from . import multi_abstract, multi_concrete
from .aut import parse_aut, render_aut
from .export import SOURCE_PATHS as LEGACY_SOURCE_PATHS
from .export import _check_expected, _validate_graph, digest, publish_bundle
from .ingress import read_bytes

PROFILE_PATH = "contracts/profiles/behavioral-relation/participant-crossing-multi-operation-dpbb-finite-v1.json"
OUTPUT_PATH = "specs/formal/participant-semantics/crossing-models/multi-rev1"
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
_PACKAGE = "implementations/python/packages/"
SOURCE_PATHS = tuple(
    sorted(
        set(LEGACY_SOURCE_PATHS)
        | {
            "implementations/formal/participant_crossing/multi_abstract.py",
            "implementations/formal/participant_crossing/multi_concrete.py",
            "implementations/formal/participant_crossing/multi_export.py",
            "specs/formal/participant-semantics/participant-crossing-multi-operation-models.md",
            "contracts/schemas/profiles/behavioral-relation-profile-v1.json",
            "contracts/schemas/participant-runtime/participant-crossing-occurrence-v1.json",
            _PACKAGE + "raes_contracts/_participant_crossing_multi_profile.py",
            _PACKAGE + "raes_contracts/_participant_opacity_common.py",
            _PACKAGE + "raes_contracts/behavioral_relations.py",
            _PACKAGE + "raes_contracts/contracts/base.py",
            _PACKAGE + "raes_contracts/operation_lifecycle.py",
            _PACKAGE + "raes_contracts/corpus.py",
            _PACKAGE + "raes_contracts/participant_crossing_history.py",
            _PACKAGE + "raes_runtime/control_plane_operation_context.py",
            _PACKAGE + "raes_runtime/control_plane_admission.py",
            _PACKAGE + "raes_runtime/control_plane_recovery.py",
            _PACKAGE + "raes_runtime/control_plane_durability.py",
            _PACKAGE + "raes_runtime/control_plane_store_records.py",
            _PACKAGE + "raes_runtime/control_plane.py",
            _PACKAGE + "raes_runtime/participant_crossing_action.py",
            _PACKAGE + "raes_runtime/participant_action_validation.py",
            _PACKAGE + "raes_runtime/participant_crossing_projection.py",
            _PACKAGE + "raes_runtime/participant_submission_options.py",
            _PACKAGE + "raes_runtime/participant_flow_sink.py",
            _PACKAGE + "raes_runtime/participant_opacity_enforcement.py",
            _PACKAGE + "raes_runtime/participant_control_orchestration.py",
        }
    )
)
_ROOT = Path(__file__).resolve().parents[3]
_EXECUTING_SOURCE_DIGESTS = {path: digest(read_bytes(_ROOT, path)) for path in SOURCE_PATHS if path.endswith(".py")}


def _json(value) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _independence(sources) -> None:
    allowed = {"collections", "dataclasses", "raes_contracts._participant_crossing_multi_profile", "graph"}
    for module in (multi_abstract, multi_concrete):
        if module.successors.__module__ != module.__name__:
            raise ValueError("models must use independent transition authorities")
        path = "implementations/formal/participant_crossing/" + module.__name__.rsplit(".", 1)[1] + ".py"
        for node in ast.walk(ast.parse(sources[path])):
            if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom) and node.module not in allowed:
                raise ValueError("models must use independent transition dependencies")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"eval", "exec", "__import__"}
            ):
                raise ValueError("models must use independent static dependencies")
    if multi_abstract.successors is multi_concrete.successors or multi_abstract.build is multi_concrete.build:
        raise ValueError("models must use independent transition authorities")


def _domains(graph, name, parameters) -> None:
    domains = parameters.domains.model_dump(mode="json")
    for state in graph.states:
        if (
            state.phase not in domains[name + "_phase"]
            or state.cut not in domains["policy_cut"]
            or type(state.head) is not int
            or not 0 <= state.head <= 2
            or type(state.effects) is not int
            or not 0 <= state.effects <= 2
            or type(state.known) is not int
            or not 0 <= state.known < (1 << len(state.ledger))
            or len(state.ledger) > 2
            or state.decision not in domains["decision"]
        ):
            raise ValueError("model state outside complete declared domain")
        if name == "concrete" and (
            state.gate not in domains["gate"]
            or state.capability not in domains["capability"]
            or type(state.changed) is not bool
        ):
            raise ValueError("model gate outside declared domain")
        if state.intent is not None:
            slot, item, body, mode = state.intent
            if (
                type(slot) is not int
                or slot not in (0, 1)
                or item not in domains["input_class"]
                or body not in domains["request_body"]
                or mode not in domains["replay"]
            ):
                raise ValueError("model intent outside declared domain")
        for item, body, policy, before, after, outcome in state.ledger:
            if (
                item not in domains["input_class"]
                or body != "original"
                or policy not in (None, "p0", "p1")
                or outcome not in domains["decision"][1:]
                or type(before) is not int
                or type(after) is not int
                or not 0 <= before <= after <= 2
                or after - before != (outcome != "unresolved")
                or (policy is None) != (outcome == "unresolved")
            ):
                raise ValueError("model ledger outside declared domain")


def _state_maps(result, name, graph) -> list[str]:
    # Inert dictionary encoding avoids copying the same retained ledger into
    # tens of thousands of preparation states. Rows retain original values.
    ledger_ids = {}
    ledgers = []
    columns = [field.name for field in fields(graph.states[0])]
    names = []
    for first in range(0, len(graph.states), 2000):
        rows = []
        for state in graph.states[first : first + 2000]:
            if state.ledger not in ledger_ids:
                ledger_ids[state.ledger] = len(ledgers)
                ledgers.append(state.ledger)
            rows.append(
                [ledger_ids[state.ledger] if column == "ledger" else getattr(state, column) for column in columns]
            )
        path = f"{name}.states-{first // 2000:03d}.json"
        result[path] = _json({"first_ordinal": first, "columns": columns, "states": rows})
        names.append(path)
    result[f"{name}.ledgers.json"] = _json({"entries": ledgers})
    return names


def build_bundle(root: Path) -> dict[str, bytes]:
    profile_bytes = read_bytes(root, PROFILE_PATH)
    profile = BehavioralRelationProfileModel.model_validate(
        parse_bounded_json_object(profile_bytes, max_bytes=256 * 1024, max_depth=32)
    )
    if not isinstance(profile.parameters, MultiParticipantCrossingParametersModel):
        raise ValueError("expected exact multi-operation profile")
    sources = {path: read_bytes(root, path) for path in SOURCE_PATHS}
    identities = {path: digest(content) for path, content in sources.items()}
    for carrier in (profile.parameters.left, profile.parameters.right):
        if identities[carrier.source_path] != carrier.source_digest:
            raise ValueError("model source digest drift")
    for ref in profile.source_refs:
        if identities.get(ref.source_ref) != ref.source_digest:
            raise ValueError("profile source digest drift")
    if any(identities[path] != expected for path, expected in _EXECUTING_SOURCE_DIGESTS.items()):
        raise ValueError("executing source identity drift")
    _independence(sources)
    result = {}
    counts = {}
    for name, module in (("abstract", multi_abstract), ("concrete", multi_concrete)):
        graph = module.build()
        _validate_graph(graph, module)
        _domains(graph, name, profile.parameters)
        aut = render_aut(
            graph,
            visible_labels=profile.parameters.visible_labels,
            hidden_labels=profile.parameters.hidden_labels,
            max_states=100000,
            max_bytes=MAX_ARTIFACT_BYTES,
        )
        initial, count, projected = parse_aut(
            aut, visible_labels=profile.parameters.visible_labels, max_states=100000, max_bytes=MAX_ARTIFACT_BYTES
        )
        aut_parts = []
        lines = aut.splitlines(keepends=True)
        for first in range(0, len(lines), 5000):
            path = f"{name}.aut-{first // 5000:03d}.part"
            result[path] = b"".join(lines[first : first + 5000])
            aut_parts.append(path)
        edge_maps = []
        for first in range(0, len(graph.edges), 5000):
            path = f"{name}.edges-{first // 5000:03d}.json"
            result[path] = _json({"first_edge": first, "semantic_edges": graph.edges[first : first + 5000]})
            edge_maps.append(path)
        maps = _state_maps(result, name, graph)
        counts[name] = {
            "states": count,
            "transitions": len(graph.edges),
            "projected_transitions": len(projected),
            "initial_states": 1,
            "initial_ordinal": initial,
            "initial_state": asdict(graph.states[initial]),
            "state_maps": maps,
            "ledger_map": f"{name}.ledgers.json",
            "aut_parts": aut_parts,
            "aut_digest": digest(aut),
            "aut_bytes": len(aut),
            "edge_maps": edge_maps,
        }
    catalog = load_behavioral_relation_catalog_revision(profile.taxonomy_revision)
    manifest = {
        "schema": "participant-crossing-model-bundle/v1",
        "profile_id": profile.profile_id,
        "profile_revision": profile.profile_revision,
        "profile_digest": profile.canonical_digest,
        "profile_file_digest": digest(profile_bytes),
        "projection": profile.observation_projection_ref + "@" + profile.observation_projection_revision,
        "catalog_revision": profile.taxonomy_revision,
        "catalog_digest": canonical_json_digest(catalog.model_dump(mode="json")),
        "source_revision": canonical_json_digest(identities),
        "source_digests": identities,
        "domain_counts": {key: len(values) for key, values in profile.parameters.domains.model_dump().items()},
        "identity_map": {
            key: {"operation": f"operation-{key}", "receipt": f"receipt-{key}", "key": f"key-{key}"} for key in "ab"
        },
        "models": counts,
        "complete_reachable_fixed_point": True,
        "fresh_operation_budget": 2,
        "artifact_digests": {path: digest(content) for path, content in result.items()},
        "equivalence_result": "not-established",
        "runtime_realization": "not-established",
        "limitations": list(profile.limitations),
        "explicit_non_claims": list(profile.explicit_non_claims),
    }
    result["manifest.json"] = _json(manifest)
    if (
        any(len(content) > MAX_ARTIFACT_BYTES for content in result.values())
        or sum(map(len, result.values())) > MAX_BUNDLE_BYTES
    ):
        raise ValueError("model bundle exceeds resource limit")
    return result


def check(root: Path) -> None:
    _check_expected(root, build_bundle(root), OUTPUT_PATH, max_bytes=MAX_ARTIFACT_BYTES)


def publish(root: Path) -> None:
    publish_bundle(root, build_bundle(root), OUTPUT_PATH, max_bytes=MAX_ARTIFACT_BYTES)

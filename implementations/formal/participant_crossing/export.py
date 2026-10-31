"""Offline, reproducible model bundles; no equivalence result is produced."""

import ast
import hashlib
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from pydantic import ValidationError
from raes_contracts.behavioral_authority_errors import BehavioralAuthorityUnsupportedError
from raes_contracts.behavioral_relation_profiles import (
    BehavioralRelationProfileModel,
    ParticipantCrossingParametersModel,
)
from raes_contracts.behavioral_relations import (
    load_behavioral_relation_catalog_revision,
)
from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest
from raes_contracts.errors import EvidenceIntegrityError, InvalidInputError
from raes_contracts.json_ingress import parse_bounded_json_object

from . import abstract, concrete
from .aut import parse_aut as parse_aut
from .aut import render_aut
from .ingress import MAX_BYTES, read_bytes, safe_path

PROFILE_PATH = "contracts/profiles/behavioral-relation/participant-crossing-dpbb-finite-v1.json"
OUTPUT_PATH = "specs/formal/participant-semantics/crossing-models/rev2"
_PACKAGE = "implementations/python/packages/"
SOURCE_PATHS = (
    "implementations/formal/participant_crossing/__init__.py",
    "implementations/formal/participant_crossing/__main__.py",
    "implementations/formal/participant_crossing/abstract.py",
    "implementations/formal/participant_crossing/concrete.py",
    "implementations/formal/participant_crossing/graph.py",
    "implementations/formal/participant_crossing/aut.py",
    "implementations/formal/participant_crossing/ingress.py",
    "implementations/formal/participant_crossing/export.py",
    _PACKAGE + "raes_contracts/_participant_crossing_profile.py",
    _PACKAGE + "raes_contracts/behavioral_relation_profiles.py",
    _PACKAGE + "raes_contracts/_behavioral_profile_loader.py",
    _PACKAGE + "raes_contracts/canonical.py",
    _PACKAGE + "raes_contracts/_canonical.py",
    _PACKAGE + "raes_contracts/json_ingress.py",
    _PACKAGE + "raes_contracts/contracts/participant_crossing.py",
    _PACKAGE + "raes_contracts/contracts/participant_crossing_validation.py",
    _PACKAGE + "raes_runtime/participant_crossing_policy.py",
    _PACKAGE + "raes_runtime/participant_crossing_mediation.py",
    _PACKAGE + "raes_runtime/participant_crossing_records.py",
    _PACKAGE + "raes_runtime/participant_crossing_commit.py",
    _PACKAGE + "raes_runtime/participant_crossing_boundary.py",
    _PACKAGE + "raes_runtime/participant_crossing_egress.py",
    _PACKAGE + "raes_runtime/participant_crossing_state_cut.py",
    _PACKAGE + "raes_runtime/control_plane_store.py",
    "specs/formal/participant-semantics/participant-crossing-models.md",
    "specs/formal/participant-semantics/information-flow-control.md",
    "implementations/python/uv.lock",
)


def digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


# The CLI starts a fresh interpreter in this checkout. A caller may export a
# copied tree only when its Python sources match that executing checkout.
_EXECUTING_SOURCE_DIGESTS = {
    path: digest(read_bytes(Path(__file__).resolve().parents[3], path)) for path in SOURCE_PATHS if path.endswith(".py")
}


def _independence(sources: dict[str, bytes]) -> None:
    allowed = {
        "collections",
        "dataclasses",
        "raes_contracts.behavioral_relation_profiles",
        "graph",
    }
    for module in (abstract, concrete):
        if module.successors.__module__ != module.__name__:
            raise InvalidInputError("models must use independent transition authorities")
        path = f"implementations/formal/participant_crossing/{module.__name__.rsplit('.', 1)[1]}.py"
        tree = ast.parse(sources[path])
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom) and node.module not in allowed:
                raise InvalidInputError("models must use independent transition dependencies")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"eval", "exec", "__import__"}
            ):
                raise InvalidInputError("models must use independent static transition dependencies")
    if abstract.successors is concrete.successors or abstract.build is concrete.build:
        raise InvalidInputError("models must use independent transition authorities")


def _validate_graph(graph, module) -> None:
    if not graph.states or graph.states[graph.initial] != module.INITIAL:
        raise InvalidInputError("invalid model initial state")
    index = {state: ordinal for ordinal, state in enumerate(graph.states)}
    if len(index) != len(graph.states):
        raise InvalidInputError("duplicate model states")
    expected = set()
    for ordinal, state in enumerate(graph.states):
        for label, target in module.successors(state):
            if target not in index:
                raise InvalidInputError("incomplete model transition closure")
            expected.add((ordinal, label, index[target]))
    if expected != set(graph.edges) or len(graph.edges) != len(expected):
        raise InvalidInputError("incomplete model transition closure")
    reachable = {graph.initial}
    while True:
        expanded = reachable | {target for source, _, target in graph.edges if source in reachable}
        if expanded == reachable:
            break
        reachable = expanded
    if len(reachable) != len(graph.states):
        raise InvalidInputError("unreachable model states")


def _profile_catalog(taxonomy_revision: str):
    """Resolve the catalog revision that a crossing profile names."""
    try:
        return load_behavioral_relation_catalog_revision(taxonomy_revision)
    except BehavioralAuthorityUnsupportedError as exc:
        # A damaged packaged catalog is an OperationalError and propagates unchanged.
        raise InvalidInputError("crossing profile catalog revision does not resolve") from exc


def build_bundle(root: Path) -> dict[str, bytes]:
    payload = parse_bounded_json_object(read_bytes(root, PROFILE_PATH), max_bytes=256 * 1024, max_depth=32)
    try:
        profile = BehavioralRelationProfileModel.model_validate(payload)
    except ValidationError as exc:
        raise InvalidInputError("crossing profile does not satisfy its contract") from exc
    if not isinstance(profile.parameters, ParticipantCrossingParametersModel):
        raise InvalidInputError("expected crossing profile")
    sources = {path: read_bytes(root, path) for path in SOURCE_PATHS}
    identities = {path: digest(content) for path, content in sources.items()}
    for carrier in (profile.parameters.left, profile.parameters.right):
        if identities[carrier.source_path] != carrier.source_digest:
            raise EvidenceIntegrityError("model source digest drift")
    for source in profile.source_refs:
        if identities.get(source.source_ref) != source.source_digest:
            raise EvidenceIntegrityError("profile source digest drift")
    if any(identities[path] != value for path, value in _EXECUTING_SOURCE_DIGESTS.items()):
        raise EvidenceIntegrityError("executing source identity drift")
    _independence(sources)
    result = {}
    counts = {}
    for name, module in (("abstract", abstract), ("concrete", concrete)):
        graph = module.build()
        _validate_graph(graph, module)
        result[f"{name}.aut"] = render_aut(graph)
        result[f"{name}.json"] = (
            canonical_json_bytes(
                {
                    "initial": graph.initial,
                    "states": [asdict(state) for state in graph.states],
                    "semantic_edges": [list(edge) for edge in graph.edges],
                }
            )
            + b"\n"
        )
        counts[name] = {
            "states": len(graph.states),
            "transitions": len(graph.edges),
            "initial_states": 1,
            "initial_state": asdict(graph.states[graph.initial]),
            "reachable_phases": sorted({state.phase for state in graph.states}),
        }
    catalog = _profile_catalog(profile.taxonomy_revision)
    manifest = {
        "schema": "participant-crossing-model-bundle/v1",
        "profile_id": profile.profile_id,
        "profile_revision": profile.profile_revision,
        "profile_digest": profile.canonical_digest,
        "profile_file_digest": digest(read_bytes(root, PROFILE_PATH)),
        "projection": "participant-crossing-projection@rev1",
        "catalog_revision": profile.taxonomy_revision,
        "catalog_digest": canonical_json_digest(catalog.model_dump(mode="json")),
        "source_revision": canonical_json_digest(identities),
        "source_digests": identities,
        "domain_counts": {key: len(values) for key, values in profile.parameters.domains.model_dump().items()},
        "models": counts,
        "complete_reachable_fixed_point": True,
        "artifact_digests": {key: digest(value) for key, value in result.items()},
        "equivalence_result": "not-established",
        "runtime_realization": "not-established",
        "limitations": list(profile.limitations),
        "explicit_non_claims": list(profile.explicit_non_claims),
    }
    result["manifest.json"] = canonical_json_bytes(manifest) + b"\n"
    if any(len(content) > MAX_BYTES for content in result.values()):
        raise InvalidInputError("model bundle exceeds resource limit")
    return result


def _check_expected(
    root: Path, expected: dict[str, bytes], output_path: str = OUTPUT_PATH, *, max_bytes=MAX_BYTES
) -> None:
    target = safe_path(root, output_path)
    if not target.is_dir() or {path.name for path in target.iterdir()} != set(expected):
        raise EvidenceIntegrityError("model bundle artifact drift")
    for name, content in expected.items():
        if read_bytes(root, output_path + "/" + name, max_bytes=max_bytes) != content:
            raise EvidenceIntegrityError("model bundle digest or count drift")


def check(root: Path) -> None:
    _check_expected(root, build_bundle(root))


def publish(root: Path) -> None:
    """Publish a new complete directory atomically; never overwrite drift."""
    publish_bundle(root, build_bundle(root), OUTPUT_PATH)


def publish_bundle(root: Path, expected: dict[str, bytes], output_path: str, *, max_bytes=MAX_BYTES) -> None:
    """Nonsemantic fixed-repository publication; trusted parent, exclusive writer."""
    target = safe_path(root, output_path)
    if target.exists():
        _check_expected(root, expected, output_path, max_bytes=max_bytes)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".crossing-stage-", dir=target.parent) as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir()
        for name, content in expected.items():
            with (stage / name).open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        safe_path(root, output_path)
        os.rename(stage, target)

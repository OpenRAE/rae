"""Source-bound mapping artifacts, separate from retained construction evidence."""

from collections import Counter
from pathlib import Path

from raes_contracts.canonical import canonical_json_bytes
from raes_contracts.json_ingress import parse_bounded_json_object

from . import export
from .ingress import read_bytes, safe_path

OUTPUT_PATH = "specs/formal/participant-semantics/runtime-mapping/rev1"
SOURCE_ROOTS = (
    "implementations/python/packages",
    "implementations/python/tests",
    "implementations/formal/participant_crossing",
    "contracts",
    "tools",
)
EXTRA_SOURCES = (
    "implementations/python/pyproject.toml",
    "implementations/python/uv.lock",
    "specs/formal/participant-semantics/participant-crossing-runtime-mapping.md",
    ".ground-control.yaml",
    "tools/policy/adr_policy.yaml",
    "tools/policy/requirement_order.yaml",
    "docs/governance/requirement-scopes/972.json",
)
ROOT = Path(__file__).resolve().parents[3]
HISTORICAL_TOMBSTONES = "contracts/schema-publication/tombstones"


def source_pins(root: Path) -> dict[str, str]:
    paths = set(EXTRA_SOURCES)
    for relative in SOURCE_ROOTS:
        directory = safe_path(root, relative)
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ValueError("unsafe mapping source directory or file")
            if path.is_relative_to(root / HISTORICAL_TOMBSTONES):
                continue
            if path.suffix in {".py", ".json", ".yaml"}:
                paths.add(path.relative_to(root).as_posix())
    if not 1 <= len(paths) <= 10000:
        raise ValueError("mapping source inventory exceeds limit")
    pins = {}
    total = 0
    for relative in sorted(paths):
        data = read_bytes(root, relative, max_bytes=16 * 1024 * 1024)
        total += len(data)
        if total > 128 * 1024 * 1024:
            raise ValueError("mapping source bytes exceed limit")
        pins[relative] = export.digest(data)
    return pins


_EXECUTING_PINS = source_pins(ROOT)


def build_bundle(root: Path, reports: dict[str, dict[str, object]]) -> dict[str, bytes]:
    pins = source_pins(root)
    if pins != _EXECUTING_PINS:
        raise ValueError("mapping executing source identity drift")
    if not 1 <= len(reports) <= 64 or any(
        item.get("classification")
        not in {"match", "incompatible", "observation-gap", "invalid-evidence"}
        for item in reports.values()
    ):
        raise ValueError("invalid mapping case inventory")
    current = export.build_bundle(root)
    identity = parse_bounded_json_object(
        current["manifest.json"], max_bytes=2 * 1024 * 1024, max_depth=32
    )
    if (
        identity["profile_id"],
        identity["profile_revision"],
        identity["projection"],
        identity["catalog_revision"],
    ) != (
        "participant-crossing-dpbb-finite-v1",
        "rev2",
        "participant-crossing-projection@rev1",
        "rev8",
    ):
        raise ValueError("mapping profile identity drift")
    retained_manifest_bytes = read_bytes(root, export.OUTPUT_PATH + "/manifest.json")
    retained = parse_bounded_json_object(
        retained_manifest_bytes, max_bytes=2 * 1024 * 1024, max_depth=32
    )
    model_pins = {}
    for name, expected in retained["artifact_digests"].items():
        relative = export.OUTPUT_PATH + "/" + name
        data = read_bytes(root, relative)
        model_pins[relative] = export.digest(data)
        if model_pins[relative] != expected or current[name] != data:
            raise ValueError("retained model artifact drift")
    model_pins[export.OUTPUT_PATH + "/manifest.json"] = export.digest(
        retained_manifest_bytes
    )
    cases = canonical_json_bytes(reports) + b"\n"
    counts = dict(
        sorted(Counter(item["classification"] for item in reports.values()).items())
    )
    manifest = {
        "schema": "participant-crossing-runtime-mapping/v1",
        "profile": "participant-crossing-dpbb-finite-v1@rev2",
        "model": "api-423-run-319-crossing-kernel@rev2",
        "projection": "participant-crossing-projection@rev1",
        "taxonomy": "raes-behavioral-relations@rev8",
        "source_digests": pins,
        "source_exclusions": {
            HISTORICAL_TOMBSTONES: "Historical schema removals are not live runtime-mapping inputs."
        },
        "model_artifact_digests": model_pins,
        "artifact_digests": {"cases.json": export.digest(cases)},
        "case_counts": counts,
        "case_count": len(reports),
        "historical_source_drift": sorted(
            name
            for name, digest in retained["source_digests"].items()
            if export.digest(read_bytes(root, name)) != digest
        ),
        "equivalence_result": "not-established",
        "runtime_realization": "not-established",
        "backend_conformance": "not-established",
        "limitations": [
            "Selected public Python calls with synthetic local policy/providers and a stub backend.",
            "A case match compares witnessed states and transitions; it proves no enabled-choice completeness.",
            "Legacy API-423 cases explicitly disable the final sink; egress cases explicitly enable it.",
            "Unprofiled fixtures claim no P0/P1/P2/P3 conformance, HTTP authentication or process-loss recovery.",
            "No bisimulation, independent reproduction, whole-runtime, timing, probability or concurrency claim.",
            "Additional operations, transformed ingress revalidation, errors and absent observations remain explicit.",
        ],
    }
    result = {
        "cases.json": cases,
        "manifest.json": canonical_json_bytes(manifest) + b"\n",
    }
    if any(len(value) > 2 * 1024 * 1024 for value in result.values()):
        raise ValueError("mapping artifact exceeds limit")
    return result


def check(root: Path, reports: dict[str, dict[str, object]]) -> None:
    export._check_expected(root, build_bundle(root, reports), OUTPUT_PATH)


def publish(root: Path, reports: dict[str, dict[str, object]]) -> None:
    export.publish_bundle(root, build_bundle(root, reports), OUTPUT_PATH)

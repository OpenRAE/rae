#!/usr/bin/env python3
"""Record immutable branch captures and number them only during integration."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from tools.evidence_bundle_index import load_index_records, revision_key
from tools.policy.common import load_bounded_json_object, safe_repo_path
from tools.research_evidence import (
    capture_identity,
    current_release_path,
    is_capture,
    validate_inventory,
)

FAMILIES = {
    "formal-semantic-validation": "formal-semantic-validation-bundle-index/v2",
    "specification-coverage": "specification-coverage-bundle-index/v1",
}


def _records(root: Path, family: str) -> list[tuple[str, dict[str, object]]]:
    records = load_index_records(
        root,
        index_path=f"docs/research/{family}/bundle-manifest.json",
        schema_version=FAMILIES[family],
        directory_key="bundles_directory",
        max_bytes=2 * 1024 * 1024,
    )
    validate_inventory(root, family, records)
    return records


def _pinned_capture_documents(root, manifest):
    documents = {}
    for label in ("protocol", "corpus", "snapshot", "analysis"):
        if f"{label}_path" not in manifest:
            continue
        path = safe_repo_path(root, manifest[f"{label}_path"])
        if path is None or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("capture document path is unsafe or oversized")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != manifest[f"{label}_sha256"]:
            raise ValueError("capture document pin is stale")
        documents[label] = content
    return documents


def _prepare_capture_documents(root, manifest, documents, snapshot_path, analysis_path):
    overrides = {"snapshot": snapshot_path, "analysis": analysis_path}
    if (snapshot_path is None) != (analysis_path is None):
        raise ValueError("a fresh capture requires snapshot and analysis together")
    for label, relative in overrides.items():
        if relative is None:
            continue
        load_bounded_json_object(root, relative, max_bytes=2 * 1024 * 1024)
        path = safe_repo_path(root, relative)
        documents[label] = path.read_bytes()
        manifest[f"{label}_sha256"] = hashlib.sha256(documents[label]).hexdigest()
    if snapshot_path is not None:
        _normalize_snapshot_reference(manifest, documents, snapshot_path)


def _normalize_snapshot_reference(manifest, documents, snapshot_path):
    analysis = json.loads(documents["analysis"])
    claim = analysis.get("claim")
    if isinstance(claim, dict) and isinstance(claim.get("evidence_artifacts"), list):
        claim["evidence_artifacts"] = [
            "@snapshot" if reference == snapshot_path else reference for reference in claim["evidence_artifacts"]
        ]
        documents["analysis"] = (json.dumps(analysis, indent=2, sort_keys=True) + "\n").encode()
        manifest["analysis_sha256"] = hashlib.sha256(documents["analysis"]).hexdigest()


def _write_capture_documents(root, prefix, documents):
    folder = root / prefix
    if folder.exists():
        if any((folder / f"{label}.json").read_bytes() != content for label, content in documents.items()):
            raise ValueError("an immutable capture identity already contains different bytes")
    else:
        folder.mkdir(parents=True)
        for label, content in documents.items():
            (folder / f"{label}.json").write_bytes(content)


def _write_retention_record(root, family, identity, prefix, documents):
    receipt = {
        "capture_path": prefix + "/manifest.json",
        "capture_sha256": hashlib.sha256(documents["manifest"]).hexdigest(),
    }
    receipt_folder = root / "docs/research" / family / "capture-records"
    receipt_folder.mkdir(exist_ok=True)
    receipt_path = receipt_folder / f"{identity}.json"
    expected = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if receipt_path.exists():
        if receipt_path.read_text() != expected:
            raise ValueError("capture retention record differs from its immutable manifest")
    else:
        with receipt_path.open("x") as stream:
            stream.write(expected)


def record_capture(
    root: Path,
    family: str,
    template_path: str,
    *,
    snapshot_path: str | None = None,
    analysis_path: str | None = None,
) -> str:
    """Copy a digest-pinned capture without relabeling its immutable observations."""
    records = _records(root, family)
    if template_path not in dict(records):
        raise ValueError("capture template must be an indexed, admitted evidence manifest")
    manifest = dict(dict(records)[template_path])
    documents = _pinned_capture_documents(root, manifest)
    _prepare_capture_documents(root, manifest, documents, snapshot_path, analysis_path)
    identity = capture_identity(manifest)
    prefix = f"docs/research/{family}/captures/{identity}"
    manifest.update(
        revision=identity,
        snapshot_path=f"{prefix}/snapshot.json",
        analysis_path=f"{prefix}/analysis.json",
    )
    documents = {
        "snapshot": documents["snapshot"],
        "analysis": documents["analysis"],
        "manifest": (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
    }
    _write_capture_documents(root, prefix, documents)
    _write_retention_record(root, family, identity, prefix, documents)
    return prefix + "/manifest.json"


def _validate_publication_receipt(root, receipt_path, receipt, records, revisions, capture_paths):
    if set(receipt) != {"revision", "capture_path", "capture_sha256"}:
        raise ValueError("invalid evidence publication receipt")
    number = revision_key(receipt["revision"])
    if receipt_path.name != f"v{number[0]}.json" or number[1:] != (0, 0):
        raise ValueError("publication receipt filename must match its major release number")
    if receipt["revision"] in revisions or receipt["capture_path"] in capture_paths:
        raise ValueError("publication receipts must have unique revisions and captures")
    revisions.add(receipt["revision"])
    capture_paths.add(receipt["capture_path"])
    capture = safe_repo_path(root, receipt["capture_path"])
    if (
        capture is None
        or receipt["capture_path"] not in dict(records)
        or hashlib.sha256(capture.read_bytes()).hexdigest() != receipt["capture_sha256"]
    ):
        raise ValueError("publication receipt has a stale capture pin")


def _publication_receipts(root, folder, records, selected):
    prior = []
    existing = None
    revisions = set()
    capture_paths = set()
    for receipt_path in sorted(folder.glob("*.json")):
        receipt = load_bounded_json_object(root, receipt_path.relative_to(root).as_posix(), max_bytes=4096)
        _validate_publication_receipt(root, receipt_path, receipt, records, revisions, capture_paths)
        if receipt["capture_path"] == selected:
            existing = receipt_path.relative_to(root).as_posix()
        prior.append(receipt)
    return prior, existing


def publish_capture(root: Path, family: str) -> str:
    """Create a numbered publication receipt on dev; leave the capture unchanged."""
    branch = subprocess.check_output(["git", "-C", str(root), "branch", "--show-current"], text=True).strip()
    if branch != "dev":
        raise ValueError("numbered evidence publication is allowed only on the dev integration branch")
    if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True).strip():
        raise ValueError("publication requires a clean integrated checkout")
    records = _records(root, family)
    selected = current_release_path(records, root)
    manifest = dict(records)[selected]
    if not is_capture(manifest.get("revision")):
        raise ValueError("integration publication requires a content-addressed capture")
    path = safe_repo_path(root, selected)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    folder = root / "docs/research" / family / "publications"
    prior, existing = _publication_receipts(root, folder, records, selected)
    if existing is not None:
        return existing
    numbers = [revision_key(record["revision"]) for _, record in records if not is_capture(record["revision"])]
    numbers.extend(revision_key(receipt["revision"]) for receipt in prior)
    major = max(numbers)[0] + 1
    folder.mkdir(exist_ok=True)
    receipt_path = folder / f"v{major}.json"
    receipt = {
        "revision": f"{major}.0.0",
        "capture_path": selected,
        "capture_sha256": digest,
    }
    with receipt_path.open("x") as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt_path.relative_to(root).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["record", "publish"])
    parser.add_argument("family", choices=sorted(FAMILIES))
    parser.add_argument("--template")
    parser.add_argument("--snapshot")
    parser.add_argument("--analysis")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if args.action == "record":
            if args.template is None:
                parser.error("record requires --template")
            path = record_capture(
                root,
                args.family,
                args.template,
                snapshot_path=args.snapshot,
                analysis_path=args.analysis,
            )
        else:
            path = publish_capture(root, args.family)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

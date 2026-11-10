#!/usr/bin/env python3
"""Record the unchanged publisher's tar and gzip byte profiles."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from raes.module_registry import publish_module_to_oci_layout  # noqa: E402
from raes.module_registry.publishing import _build_module_bundle  # noqa: E402


def signed_graph() -> str:
    entry = "module:root.yaml"
    files = {
        entry: 'name: shared\nmodule: {id: example/shared, version: 1.0.0, exports: {nodes: [host]}}\nnodes: {host: {type: compute}}\nimports: [{path: "children:files/child.yaml", namespace: child}]\n',
        "children:files/child.yaml": "name: child\nmodule: {id: example/child, version: 1.0.0, exports: {nodes: [worker]}}\nnodes: {worker: {type: compute}}\n",
    }
    key = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"public-module-graph-fixture").digest())
    with tempfile.TemporaryDirectory(prefix="module-graph-profile-") as directory:
        source = Path(directory) / "source"
        for name, content in files.items():
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        key_path = Path(directory) / "public-fixture-key.pem"
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        result = publish_module_to_oci_layout(
            source / entry,
            output_dir=Path(directory) / "output",
            signer_id="test-signer",
            private_key_path=key_path,
        )
        layout = Path(result["layout_dir"])

        def blob(identity):
            return (layout / "blobs/sha256" / identity.removeprefix("sha256:")).read_bytes()

        manifest = blob(result["manifest_digest"])
        descriptor = json.loads(manifest)
        artifact = dict(
            manifest=base64.b64encode(manifest).decode(),
            config=base64.b64encode(blob(descriptor["config"]["digest"])).decode(),
            bundle=base64.b64encode(blob(descriptor["layers"][0]["digest"])).decode(),
        )
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return (
        json.dumps(
            dict(
                root=entry,
                public_key=base64.b64encode(public).decode(),
                sources={name: base64.b64encode(content.encode()).decode() for name, content in files.items()},
                artifact=artifact,
            ),
            indent=2,
            ensure_ascii=True,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    cases = []
    for name, child in [
        ("short", "child.yaml"),
        ("long-name", "a" * 101 + ".yaml"),
        ("split-path", "a" * 75 + "/" + "b" * 75 + ".yaml"),
        ("unicode", "模块.yaml"),
        ("window-sliding", "large.yaml"),
    ]:
        files = {
            "module.yaml": "name: root\nmodule: {id: example/root, version: 1.0.0}\nimports: [{namespace: child, path: "
            + json.dumps(child)
            + "}]\n",
            child: "name: child\nmodule: {id: example/child, version: 1.0.0}\n",
        }
        if name == "window-sliding":
            files[child] += "description: '" + "abcdefghijk-0123456789 " * 20000 + "'\n"
        with tempfile.TemporaryDirectory(prefix="module-byte-profile-") as directory:
            for path, content in files.items():
                target = Path(directory) / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            bundle = _build_module_bundle(Path(directory) / "module.yaml")
        cases.append(
            dict(
                name=name,
                files={path: base64.b64encode(content.encode()).decode() for path, content in files.items()},
                bundle=base64.b64encode(bundle).decode(),
            )
        )
    encoded = json.dumps(dict(cases=cases), indent=2, ensure_ascii=True) + "\n"
    target = ROOT / "implementations/go/sdl/module/testdata/python-bundles.json.gz"
    graph_target = ROOT / "implementations/go/sdl/module/testdata/python-signed-graph.json"
    graph = signed_graph()
    if arguments.check:
        return int(gzip.decompress(target.read_bytes()).decode() != encoded or graph_target.read_text() != graph)
    target.write_bytes(gzip.compress(encoded.encode(), mtime=0))
    graph_target.write_text(graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

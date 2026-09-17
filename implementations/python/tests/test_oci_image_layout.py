"""GOV-913 (#1223): offline admission of an exported OCI image layout.

The layout is an untrusted carrier. Nothing in it may be believed because a
client reported success: every object is re-hashed against the reviewed lock
before any import or execution, and the reviewed *index* identity is what binds
the selected platform manifests, configs and layers together.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest
from tools.oci_image_layout import LayoutRejected, LockedPlatformGraph, OciDescriptor, verify_layout

_MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
_INDEX_MEDIA_TYPE = "application/vnd.oci.image.index.v1+json"
_CONFIG_MEDIA_TYPE = "application/vnd.oci.image.config.v1+json"
_LAYER_MEDIA_TYPE = "application/vnd.oci.image.layer.v1.tar+gzip"


class _LayoutBuilder:
    """Build a real OCI image layout the way `skopeo copy --all` would."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.blobs = root / "blobs" / "sha256"
        self.blobs.mkdir(parents=True)
        (root / "oci-layout").write_text(json.dumps({"imageLayoutVersion": "1.0.0"}), encoding="utf-8")

    def put(self, payload: bytes) -> OciDescriptor:
        digest = hashlib.sha256(payload).hexdigest()
        (self.blobs / digest).write_bytes(payload)
        return OciDescriptor(digest=f"sha256:{digest}", size=len(payload))

    def put_json(self, document: dict) -> OciDescriptor:
        return self.put(json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8"))

    def platform(self, architecture: str, *, layer_body: bytes) -> tuple[dict, dict]:
        layer_payload = gzip.compress(layer_body, mtime=0)
        diff_id = f"sha256:{hashlib.sha256(layer_body).hexdigest()}"
        layer = self.put(layer_payload)
        config = self.put_json(
            {
                "architecture": architecture,
                "os": "linux",
                "rootfs": {"type": "layers", "diff_ids": [diff_id]},
            }
        )
        manifest = self.put_json(
            {
                "schemaVersion": 2,
                "mediaType": _MANIFEST_MEDIA_TYPE,
                "config": {"mediaType": _CONFIG_MEDIA_TYPE, "digest": config.digest, "size": config.size},
                "layers": [{"mediaType": _LAYER_MEDIA_TYPE, "digest": layer.digest, "size": layer.size}],
            }
        )
        descriptor = {
            "mediaType": _MANIFEST_MEDIA_TYPE,
            "digest": manifest.digest,
            "size": manifest.size,
            "platform": {"architecture": architecture, "os": "linux"},
        }
        graph_parts = {
            "manifest": manifest,
            "config": config,
            "layers": (layer,),
            "diff_ids": (diff_id,),
            "architecture": architecture,
        }
        return descriptor, graph_parts

    def seal(self, descriptors: list[dict]) -> OciDescriptor:
        index = self.put_json({"schemaVersion": 2, "mediaType": _INDEX_MEDIA_TYPE, "manifests": descriptors})
        # skopeo writes a wrapper index that points at the copied image's index.
        (self.root / "index.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 2,
                    "manifests": [
                        {"mediaType": _INDEX_MEDIA_TYPE, "digest": index.digest, "size": index.size},
                    ],
                }
            ),
            encoding="utf-8",
        )
        return index


def _build(root: Path) -> tuple[Path, list[LockedPlatformGraph]]:
    builder = _LayoutBuilder(root)
    amd64_descriptor, amd64 = builder.platform("amd64", layer_body=b"amd64 root filesystem")
    arm64_descriptor, arm64 = builder.platform("arm64", layer_body=b"arm64 root filesystem")
    index = builder.seal([amd64_descriptor, arm64_descriptor])
    graphs = [
        LockedPlatformGraph(
            platform_id=platform_id,
            index=index,
            manifest=parts["manifest"],
            config=parts["config"],
            layers=parts["layers"],
            diff_ids=parts["diff_ids"],
            architecture=parts["architecture"],
            os="linux",
            variant=None,
        )
        for platform_id, parts in (("linux-x86_64", amd64), ("linux-arm64", arm64))
    ]
    return root, graphs


def test_exact_multiarch_export_is_admitted_for_every_required_platform(tmp_path: Path) -> None:
    layout, graphs = _build(tmp_path / "layout")

    verify_layout(layout, graphs)


def test_export_missing_a_required_platform_is_rejected(tmp_path: Path) -> None:
    layout, graphs = _build(tmp_path / "layout")
    (layout / "blobs" / "sha256" / graphs[1].manifest.digest.removeprefix("sha256:")).unlink()

    with pytest.raises(LayoutRejected) as excinfo:
        verify_layout(layout, graphs)
    assert excinfo.value.reason == "blob-missing"


def test_mutated_layer_byte_is_rejected_even_at_the_locked_size(tmp_path: Path) -> None:
    layout, graphs = _build(tmp_path / "layout")
    layer = layout / "blobs" / "sha256" / graphs[0].layers[0].digest.removeprefix("sha256:")
    payload = bytearray(layer.read_bytes())
    payload[-1] ^= 0xFF
    layer.write_bytes(bytes(payload))

    with pytest.raises(LayoutRejected) as excinfo:
        verify_layout(layout, graphs)
    assert excinfo.value.reason == "blob-corrupt"


def test_layout_whose_index_is_not_the_reviewed_index_is_rejected(tmp_path: Path) -> None:
    layout, graphs = _build(tmp_path / "layout")
    substitute = [
        LockedPlatformGraph(
            **{
                **graph.__dict__,
                "index": OciDescriptor(digest="sha256:" + "9" * 64, size=graph.index.size),
            }
        )
        for graph in graphs
    ]

    with pytest.raises(LayoutRejected) as excinfo:
        verify_layout(layout, substitute)
    assert excinfo.value.reason == "index-identity"


def test_wrong_platform_object_under_a_required_platform_is_rejected(tmp_path: Path) -> None:
    layout, graphs = _build(tmp_path / "layout")
    # Claim the arm64 selection carries the amd64 manifest: the digest is real
    # and present, but it is not this platform's object.
    swapped = [
        graphs[0],
        LockedPlatformGraph(**{**graphs[1].__dict__, "manifest": graphs[0].manifest}),
    ]

    with pytest.raises(LayoutRejected) as excinfo:
        verify_layout(layout, swapped)
    assert excinfo.value.reason == "graph-mismatch"


def test_extra_blob_outside_the_reviewed_index_closure_is_rejected(tmp_path: Path) -> None:
    layout, graphs = _build(tmp_path / "layout")
    stray = b"payload the reviewed index never referenced"
    (layout / "blobs" / "sha256" / hashlib.sha256(stray).hexdigest()).write_bytes(stray)

    with pytest.raises(LayoutRejected) as excinfo:
        verify_layout(layout, graphs)
    assert excinfo.value.reason == "blob-unexpected"


def test_symlinked_blob_is_rejected_without_being_read(tmp_path: Path) -> None:
    layout, graphs = _build(tmp_path / "layout")
    secret = tmp_path / "outside"
    secret.write_bytes(b"not a blob")
    target = layout / "blobs" / "sha256" / graphs[0].config.digest.removeprefix("sha256:")
    target.unlink()
    target.symlink_to(secret)

    with pytest.raises(LayoutRejected) as excinfo:
        verify_layout(layout, graphs)
    assert excinfo.value.reason == "unsafe-path"


def test_layout_without_a_version_marker_is_rejected(tmp_path: Path) -> None:
    layout, graphs = _build(tmp_path / "layout")
    (layout / "oci-layout").unlink()

    with pytest.raises(LayoutRejected) as excinfo:
        verify_layout(layout, graphs)
    assert excinfo.value.reason == "layout-shape"


def test_rejection_never_echoes_layout_content(tmp_path: Path) -> None:
    layout, graphs = _build(tmp_path / "layout")
    (layout / "index.json").write_text(json.dumps({"manifests": [{"digest": "sha256:" + "0" * 64}]}), encoding="utf-8")

    with pytest.raises(LayoutRejected) as excinfo:
        verify_layout(layout, graphs)
    message = str(excinfo.value)
    assert "0" * 64 not in message
    assert str(layout) not in message


def test_layout_whose_entry_file_is_itself_the_reviewed_index_is_admitted(tmp_path: Path) -> None:
    """Both admissible spellings of the entry point resolve to one identity."""

    layout, graphs = _build(tmp_path / "layout")
    index_blob = layout / "blobs" / "sha256" / graphs[0].index.digest.removeprefix("sha256:")
    payload = index_blob.read_bytes()
    # Write the reviewed index as the entry file rather than as a wrapped blob.
    (layout / "index.json").write_bytes(payload)
    index_blob.unlink()

    verify_layout(layout, graphs)


def test_entry_file_that_merely_claims_the_reviewed_digest_is_rejected(tmp_path: Path) -> None:
    layout, graphs = _build(tmp_path / "layout")
    (layout / "index.json").write_text(
        json.dumps({"schemaVersion": 2, "manifests": [{"digest": graphs[0].index.digest, "size": 1}]}),
        encoding="utf-8",
    )

    with pytest.raises(LayoutRejected) as excinfo:
        verify_layout(layout, graphs)
    assert excinfo.value.reason == "index-identity"

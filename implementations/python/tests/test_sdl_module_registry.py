"""Registry-aware SDL composition and packaging tests."""

from __future__ import annotations

import base64
import dataclasses
import gzip
import io
import json
import os
import shutil
import stat
import sys
import tarfile
import textwrap
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.error import URLError

import pytest
import raes.composition._expand as composition_expand
import raes.module_registry as module_registry
import raes.module_registry._archive as module_registry_archive
import raes.module_registry._cache as module_registry_cache
import raes.module_registry._extraction as module_registry_extraction
import raes.module_registry._filesystem as module_registry_filesystem
import raes.module_registry.publishing as module_registry_publishing
import raes.module_registry.resolution as module_registry_resolution
import raes.parser as sdl_parser
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from raes._errors import SDLParseError, SDLValidationError
from raes._source_profile import DEFAULT_SOURCE_PARSE_OPTIONS
from raes.module_registry import (
    LOCKFILE_NAME,
    load_lockfile,
    publish_module_to_oci_layout,
)
from raes.parser import parse_sdl_file
from raes_cli.main import app
from raes_processor.compiler import compile_runtime_model
from typer.testing import CliRunner


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return path


def _local_module(path: Path, *, version: str = "1.2.3", exports: str = "nodes: [vm]\ninfrastructure: [vm]") -> Path:
    exports_block = "\n".join(f"    {line}" for line in textwrap.dedent(exports).strip().splitlines())
    return _write(
        path,
        "\n".join(
            [
                "name: shared",
                f"version: {version}",
                "module:",
                "  id: acme/shared",
                f"  version: {version}",
                "  exports:",
                exports_block,
                "nodes:",
                "  vm:",
                "    type: compute",
                "    os: linux",
                "    resources: {ram: 1 gib, cpu: 1}",
                "infrastructure:",
                "  vm: 1",
            ]
        ),
    )


def _root_import(path: Path, import_body: str) -> Path:
    lines = textwrap.dedent(import_body).strip().splitlines()
    import_lines = [f"  - {lines[0].strip()}"]
    import_lines.extend(f"    {line.strip()}" for line in lines[1:])
    import_block = "\n".join(import_lines)
    return _write(
        path,
        "\n".join(
            [
                "name: root",
                "imports:",
                import_block,
            ]
        ),
    )


class _OCIHandler(BaseHTTPRequestHandler):
    repo = ""
    tag = ""
    manifest_digest = ""
    manifest_bytes = b""
    blobs: dict[str, bytes] = {}

    def do_GET(self) -> None:  # noqa: N802
        if self.path == f"/v2/{self.repo}/tags/list":
            payload = json.dumps({"name": self.repo, "tags": [self.tag]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path in {
            f"/v2/{self.repo}/manifests/{self.tag}",
            f"/v2/{self.repo}/manifests/{self.manifest_digest}",
        }:
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.oci.image.manifest.v1+json")
            self.send_header("Content-Length", str(len(self.manifest_bytes)))
            self.end_headers()
            self.wfile.write(self.manifest_bytes)
            return
        blob_prefix = f"/v2/{self.repo}/blobs/"
        if self.path.startswith(blob_prefix):
            digest = self.path.removeprefix(blob_prefix)
            blob = self.blobs.get(digest)
            if blob is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)
            return
        self.send_error(404)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        del format, args


class _OCIRegistry:
    def __init__(self, layout_dir: Path, repo: str) -> None:
        index_payload = json.loads((layout_dir / "index.json").read_text(encoding="utf-8"))
        manifest_digest = index_payload["manifests"][0]["digest"]
        tag = index_payload["manifests"][0]["annotations"]["org.opencontainers.image.ref.name"]
        manifest_bytes = (layout_dir / "blobs" / "sha256" / manifest_digest.removeprefix("sha256:")).read_bytes()
        blobs = {f"sha256:{blob.name}": blob.read_bytes() for blob in (layout_dir / "blobs" / "sha256").iterdir()}
        handler = type(
            "Handler",
            (_OCIHandler,),
            {
                "repo": repo,
                "tag": tag,
                "manifest_digest": manifest_digest,
                "manifest_bytes": manifest_bytes,
                "blobs": blobs,
            },
        )
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.host, self.port = self._server.server_address
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> _OCIRegistry:
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def test_local_path_source_and_locked_imports_compile_equivalently(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    root_path = _root_import(
        tmp_path / "root-path.yaml",
        "path: shared.yaml\n            namespace: shared",
    )
    root_source = _root_import(
        tmp_path / "root-source.yaml",
        "source: local:shared.yaml\n            namespace: shared\n            version: 1.2.3",
    )

    runner = CliRunner()
    resolve_result = runner.invoke(app, ["sdl", "resolve", str(root_source)])
    assert resolve_result.exit_code == 0, resolve_result.output
    lockfile = load_lockfile(tmp_path)
    assert lockfile is not None
    record = lockfile.imports[0]

    root_locked = _root_import(
        tmp_path / "root-locked.yaml",
        f"source: locked:{record.resolved_source}\n            namespace: shared",
    )

    path_model = compile_runtime_model(parse_sdl_file(root_path))
    source_model = compile_runtime_model(parse_sdl_file(root_source))
    locked_model = compile_runtime_model(parse_sdl_file(root_locked))

    assert (
        path_model.node_deployments.keys()
        == source_model.node_deployments.keys()
        == locked_model.node_deployments.keys()
        == {"provision.node.shared.vm"}
    )
    assert path_model.networks.keys() == source_model.networks.keys() == locked_model.networks.keys() == set()
    assert module_path.exists()


def test_local_import_digest_mismatch_fails_closed(tmp_path: Path):
    _local_module(tmp_path / "shared.yaml")
    root = _root_import(
        tmp_path / "root.yaml",
        "source: local:shared.yaml\n            namespace: shared\n            digest: sha256:deadbeef",
    )

    with pytest.raises(SDLParseError, match="Digest mismatch"):
        parse_sdl_file(root)


def test_local_import_composes_the_exact_document_verified_by_resolution(tmp_path: Path, monkeypatch) -> None:
    module_path = _local_module(tmp_path / "shared.yaml")
    root = _root_import(
        tmp_path / "root.yaml",
        "source: local:shared.yaml\n            namespace: shared",
    )
    original_read = sdl_parser.read_sdl_source
    module_reads = 0

    def swap_after_verified_read(path: Path, **kwargs):
        nonlocal module_reads
        document = original_read(path, **kwargs)
        if path.resolve() == module_path.resolve():
            module_reads += 1
            if module_reads == 1:
                module_path.write_bytes(document.raw_bytes.replace(b"os: linux", b"os: windows"))
        return document

    monkeypatch.setattr(sdl_parser, "read_sdl_source", swap_after_verified_read)

    scenario = parse_sdl_file(root)

    assert module_reads == 1
    assert scenario.nodes["shared.vm"].os.value == "linux"


def test_module_exports_are_enforced_for_importers(tmp_path: Path):
    _write(
        tmp_path / "shared.yaml",
        """
        name: shared
        version: 1.2.3
        module:
          id: acme/shared
          version: 1.2.3
          exports:
            nodes: [vm]
            infrastructure: [vm]
        nodes:
          vm:
            type: compute
            os: linux
            resources: {ram: 1 gib, cpu: 1}
            conditions: {health: ops}
            roles: {ops: operator}
        infrastructure:
          vm: 1
        conditions:
          health: {command: /bin/true, interval: 15}
        """,
    )
    root = _write(
        tmp_path / "root.yaml",
        """
        name: root
        imports:
          - source: local:shared.yaml
            namespace: shared
        entities:
          blue: {role: blue}
        objectives:
          check:
            owner: blue
            success:
              assertions: [shared.health]
        """,
    )

    with pytest.raises(
        SDLValidationError,
        match=r"Objective 'check' references undefined assertion 'shared\.health' in success criteria",
    ):
        parse_sdl_file(root)


@pytest.mark.parametrize("exported", [True, False])
def test_scenario_forwarding_agents_compose_by_stable_list_identity(tmp_path: Path, exported: bool):
    exports = "    forwarding_agents: [shipper]\n" if exported else ""
    _write(
        tmp_path / "shared.yaml",
        f"""
        name: shared
        version: 1.0.0
        module:
          id: raes/shared-forwarder
          version: 1.0.0
          exports:
            nodes: [source, sink]
            relationships: [shipping]
        {exports.rstrip()}
        nodes:
          source: {{type: switch}}
          sink: {{type: switch}}
        forwarding_agents:
          - forwarding_agent_id: shipper
        relationships:
          shipping:
            type: connects_to
            source: source
            target: sink
            forwarding_edge:
              forwarder_ref: shipper
        """,
    )
    root = _root_import(
        tmp_path / "root.yaml",
        "source: local:shared.yaml\n            namespace: shared",
    )

    scenario = parse_sdl_file(root)

    expected = "shared.shipper" if exported else "shared.__private.shipper"
    assert isinstance(scenario.forwarding_agents, list)
    assert [agent.forwarding_agent_id for agent in scenario.forwarding_agents] == [expected]
    assert scenario.relationships["shared.shipping"].forwarding_edge.forwarder_ref == expected


def test_import_cycles_and_namespace_collisions_are_rejected(tmp_path: Path):
    a = _write(
        tmp_path / "a.yaml",
        """
        name: a
        version: 1.0.0
        module:
          id: raes/a
          version: 1.0.0
        imports:
          - source: local:b.yaml
            namespace: other
        """,
    )
    _write(
        tmp_path / "b.yaml",
        """
        name: b
        version: 1.0.0
        module:
          id: raes/b
          version: 1.0.0
        imports:
          - source: local:a.yaml
            namespace: other
        """,
    )
    with pytest.raises(SDLParseError, match="Import cycle detected"):
        parse_sdl_file(a)

    _local_module(tmp_path / "one.yaml")
    _local_module(tmp_path / "two.yaml")
    root = _write(
        tmp_path / "collision.yaml",
        """
        name: collision
        imports:
          - source: local:one.yaml
            namespace: shared
          - source: local:two.yaml
            namespace: shared
        """,
    )
    with pytest.raises(SDLParseError, match="collides on nodes"):
        parse_sdl_file(root)


def test_sdl_resolve_and_verify_detect_lockfile_drift(tmp_path: Path):
    _local_module(tmp_path / "shared.yaml")
    root = _root_import(
        tmp_path / "root.yaml",
        "source: local:shared.yaml\n            namespace: shared",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["sdl", "resolve", str(root)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / LOCKFILE_NAME).exists()

    verify = runner.invoke(app, ["sdl", "verify-imports", str(root)])
    assert verify.exit_code == 0, verify.output

    _local_module(tmp_path / "shared.yaml", version="1.2.4")
    stale = runner.invoke(app, ["sdl", "verify-imports", str(root)])
    assert stale.exit_code != 0
    assert "stale" in stale.output.lower()


def test_local_import_lockfile_is_checkout_independent(tmp_path: Path):
    # Author the scenario under one absolute checkout path, with the imported
    # module in a subdirectory so the persisted identity is a multi-segment
    # relative path rather than a bare filename.
    checkout_a = tmp_path / "checkout_a"
    _local_module(checkout_a / "nodes" / "shared.yaml")
    root_a = _root_import(
        checkout_a / "root.yaml",
        "source: local:nodes/shared.yaml\n            namespace: shared",
    )
    runner = CliRunner()

    resolve_result = runner.invoke(app, ["sdl", "resolve", str(root_a)])
    assert resolve_result.exit_code == 0, resolve_result.output

    # Acceptance: `resolve` writes no absolute machine paths for local: imports.
    lock_text = (checkout_a / LOCKFILE_NAME).read_text(encoding="utf-8")
    assert str(checkout_a) not in lock_text
    lockfile = load_lockfile(checkout_a)
    assert lockfile is not None
    record = lockfile.imports[0]
    assert not Path(record.resolved_source).is_absolute()
    assert record.resolved_source == "nodes/shared.yaml"

    # Acceptance: `verify-imports` passes on a checkout at a different absolute
    # path than the one that generated the lock.
    checkout_b = tmp_path / "checkout_b"
    shutil.copytree(checkout_a, checkout_b)
    verify = runner.invoke(app, ["sdl", "verify-imports", str(checkout_b / "root.yaml")])
    assert verify.exit_code == 0, verify.output

    # ...and still fails when the imported content actually changes.
    _local_module(checkout_b / "nodes" / "shared.yaml", version="1.2.4")
    stale = runner.invoke(app, ["sdl", "verify-imports", str(checkout_b / "root.yaml")])
    assert stale.exit_code != 0
    assert "stale" in stale.output.lower()


def test_local_imports_cannot_escape_base_dir(tmp_path: Path):
    _local_module(tmp_path / "shared.yaml")
    root = _root_import(
        tmp_path / "scenario" / "root.yaml",
        "source: local:../shared.yaml\n            namespace: shared",
    )

    with pytest.raises(SDLParseError, match="escapes base directory"):
        parse_sdl_file(root)


def test_publishing_local_bundle_rejects_import_escape(tmp_path: Path):
    _local_module(tmp_path / "shared.yaml")
    root = _write(
        tmp_path / "scenario" / "root.yaml",
        """
        name: root
        version: 1.0.0
        module:
          id: acme/root
          version: 1.0.0
          exports:
            nodes: [vm]
            infrastructure: [vm]
        imports:
          - source: local:../shared.yaml
            namespace: shared
        nodes:
          vm:
            type: compute
            os: linux
            resources: {ram: 1 gib, cpu: 1}
        infrastructure:
          vm: 1
        """,
    )

    with pytest.raises(SDLParseError, match="escapes base directory"):
        publish_module_to_oci_layout(root, output_dir=tmp_path / "dist")


def _published_blob(layout_dir: Path, digest: str) -> bytes:
    return (layout_dir / "blobs" / "sha256" / digest.removeprefix("sha256:")).read_bytes()


def _version_slot(version: Path) -> Path:
    assert version.parent.name == "versions"
    return version.parent.parent


def _current_version(slot: Path) -> Path:
    version_name = (slot / ".raes-current").read_text(encoding="ascii").removesuffix("\n")
    return slot / "versions" / version_name


def _published_config(layout_dir: Path) -> dict[str, object]:
    index = json.loads((layout_dir / "index.json").read_text(encoding="utf-8"))
    manifest = json.loads(_published_blob(layout_dir, index["manifests"][0]["digest"]))
    return json.loads(_published_blob(layout_dir, manifest["config"]["digest"]))


def test_published_bundle_is_byte_reproducible_and_normalized(tmp_path: Path):
    module_path = _local_module(tmp_path / "source" / "shared.yaml")
    first = publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist-a")
    os.chmod(module_path, 0o600)
    os.utime(module_path, (2_000_000_000, 2_000_000_000))
    second = publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist-b")

    assert first["content_digest"] == second["content_digest"]
    assert first["manifest_digest"] == second["manifest_digest"]
    first_bundle = _published_blob(Path(first["layout_dir"]), str(first["content_digest"]))
    second_bundle = _published_blob(Path(second["layout_dir"]), str(second["content_digest"]))
    assert first_bundle == second_bundle
    assert int.from_bytes(first_bundle[4:8], "little") == 0  # gzip MTIME
    with tarfile.open(fileobj=io.BytesIO(first_bundle), mode="r:gz") as archive:
        members = archive.getmembers()
    assert [member.name for member in members] == ["shared.yaml"]
    assert {(member.uid, member.gid, member.uname, member.gname, member.mode, member.mtime) for member in members} == {
        (0, 0, "", "", 0o644, 0)
    }


def test_published_bundle_collects_nested_local_graph_against_one_root(tmp_path: Path):
    _write(
        tmp_path / "common.yaml",
        """
        name: common
        module: {id: acme/common, version: 1.0.0}
        """,
    )
    _write(
        tmp_path / "nested" / "child.yaml",
        """
        name: child
        module: {id: acme/child, version: 1.0.0}
        imports:
          - source: local:../common.yaml
            namespace: common
        """,
    )
    root = _write(
        tmp_path / "root.yaml",
        """
        name: root
        module: {id: acme/root, version: 1.0.0}
        imports:
          - source: local:nested/child.yaml
            namespace: child
        """,
    )

    bundle = module_registry_publishing._build_module_bundle(root)

    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as archive:
        assert [member.name for member in archive] == ["common.yaml", "nested/child.yaml", "root.yaml"]


def test_published_bundle_rejects_remote_import_graph(tmp_path: Path):
    root = _write(
        tmp_path / "root.yaml",
        """
        name: root
        module: {id: acme/root, version: 1.0.0}
        imports:
          - source: oci:registry.example/acme/child
            namespace: child
        """,
    )

    with pytest.raises(SDLParseError, match="self-contained local module graph"):
        module_registry_publishing._build_module_bundle(root)


def test_bundle_collector_rejects_invalid_roots_cycles_and_escape(tmp_path: Path):
    root = _write(tmp_path / "root.yaml", "name: root\nmodule: {id: acme/root, version: 1.0.0}")
    with pytest.raises(SDLParseError, match="Unable to resolve"):
        module_registry_publishing._collect_local_bundle_files(tmp_path / "missing.yaml")
    with pytest.raises(SDLParseError, match="regular file"):
        module_registry_publishing._collect_local_bundle_files(tmp_path)
    with pytest.raises(SDLParseError, match="canonical publishing root"):
        module_registry_publishing._collect_local_bundle_files(root, bundle_root=tmp_path / "other")
    seen = {root.resolve()}
    with pytest.raises(SDLParseError, match="Import cycle"):
        module_registry_publishing._collect_local_bundle_files(root, seen=seen)

    _write(tmp_path / "outside.yaml", "name: outside\nmodule: {id: acme/outside, version: 1.0.0}")
    nested = _write(
        tmp_path / "nested" / "root.yaml",
        """
        name: nested
        module: {id: acme/nested, version: 1.0.0}
        imports:
          - source: local:../outside.yaml
            namespace: outside
        """,
    )
    bundle_root = nested.parent.resolve()
    with pytest.raises(SDLParseError, match="escapes base directory"):
        module_registry_publishing._collect_local_bundle_files(nested, bundle_root=bundle_root)


def test_relative_and_symlink_publish_roots_have_one_canonical_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module_path = _local_module(tmp_path / "source" / "shared.yaml")
    alias = tmp_path / "alias.yaml"
    try:
        alias.symlink_to(module_path)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    monkeypatch.chdir(tmp_path)

    relative = publish_module_to_oci_layout(Path("source/shared.yaml"), output_dir=tmp_path / "dist-relative")
    linked = publish_module_to_oci_layout(Path("alias.yaml"), output_dir=tmp_path / "dist-linked")

    assert relative["content_digest"] == linked["content_digest"]
    assert relative["manifest_digest"] == linked["manifest_digest"]
    assert _published_config(Path(relative["layout_dir"]))["root_file"] == "shared.yaml"
    assert _published_config(Path(linked["layout_dir"]))["root_file"] == "shared.yaml"


@pytest.mark.parametrize(
    ("signer_id", "private_key"),
    [("configured-signer", None), ("", Path("configured-key.pem"))],
)
def test_publish_rejects_partially_configured_signing(tmp_path: Path, signer_id: str, private_key: Path | None):
    module_path = _local_module(tmp_path / "shared.yaml")

    with pytest.raises(SDLParseError, match="requires both"):
        publish_module_to_oci_layout(
            module_path,
            output_dir=tmp_path / "dist",
            signer_id=signer_id,
            private_key_path=private_key,
        )


def test_publish_rejects_invalid_key_with_stable_error(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    invalid_key = tmp_path / "invalid.pem"
    invalid_key.write_text("not a private key\nSECRET-NATIVE-DETAIL", encoding="utf-8")

    with pytest.raises(SDLParseError) as exc_info:
        publish_module_to_oci_layout(
            module_path,
            output_dir=tmp_path / "dist",
            signer_id="configured-signer",
            private_key_path=invalid_key,
        )

    assert str(exc_info.value) == "Publishing private key is not a valid PEM private key"
    assert "SECRET-NATIVE-DETAIL" not in str(exc_info.value)


def test_publish_rejects_whitespace_signer_id(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    key = Ed25519PrivateKey.generate()
    key_path = tmp_path / "signing-key.pem"
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    with pytest.raises(SDLParseError, match="leading or trailing whitespace"):
        publish_module_to_oci_layout(
            module_path,
            output_dir=tmp_path / "dist",
            signer_id=" signer ",
            private_key_path=key_path,
        )


def test_publish_with_complete_signing_configuration_emits_signature(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    key = Ed25519PrivateKey.generate()
    key_path = tmp_path / "signing-key.pem"
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    published = publish_module_to_oci_layout(
        module_path,
        output_dir=tmp_path / "dist",
        signer_id="signer",
        private_key_path=key_path,
    )

    config = _published_config(Path(published["layout_dir"]))
    assert config["signatures"][0]["signer_id"] == "signer"
    assert config["signatures"][0]["signature"]


def test_publish_rejects_unreadable_or_non_ed25519_key(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    with pytest.raises(SDLParseError, match="Unable to read"):
        publish_module_to_oci_layout(
            module_path,
            output_dir=tmp_path / "dist-a",
            signer_id="signer",
            private_key_path=tmp_path / "missing.pem",
        )

    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_path = tmp_path / "rsa.pem"
    rsa_path.write_bytes(
        rsa_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    with pytest.raises(SDLParseError, match="must be an Ed25519"):
        publish_module_to_oci_layout(
            module_path,
            output_dir=tmp_path / "dist-b",
            signer_id="signer",
            private_key_path=rsa_path,
        )


def test_publish_missing_entrypoint_and_unwritable_layout_fail_stably(tmp_path: Path):
    with pytest.raises(SDLParseError, match="Unable to resolve"):
        publish_module_to_oci_layout(tmp_path / "missing.yaml", output_dir=tmp_path / "dist")

    module_path = _local_module(tmp_path / "shared.yaml")
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("occupied\n", encoding="utf-8")
    with pytest.raises(SDLParseError, match="Unable to build the OCI layout"):
        publish_module_to_oci_layout(module_path, output_dir=output_file)


def test_publish_rejects_linked_layout_lock_parent_without_writing_target(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    output_dir = tmp_path / "dist"
    output_dir.mkdir()
    outside = tmp_path / "outside-locks"
    outside.mkdir()
    try:
        (output_dir / ".raes-layout-locks").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(SDLParseError, match="Unable to open the OCI module cache lock"):
        publish_module_to_oci_layout(module_path, output_dir=output_dir)

    assert not list(outside.iterdir())


def test_republishing_layout_removes_stale_inventory(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    first = publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")
    layout = Path(first["layout_dir"])
    (layout / "stale.txt").write_text("stale\n", encoding="utf-8")
    (layout / "blobs" / "sha256" / ("f" * 64)).write_bytes(b"stale")

    second = publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")

    layout = Path(second["layout_dir"])
    assert layout != Path(first["layout_dir"])
    assert (Path(first["layout_dir"]) / "stale.txt").read_text(encoding="utf-8") == "stale\n"
    assert _current_version(_version_slot(layout)) == layout
    actual_files = {path.relative_to(layout).as_posix() for path in layout.rglob("*") if path.is_file()}
    expected_blobs = {
        f"blobs/sha256/{str(second[key]).removeprefix('sha256:')}" for key in ("content_digest", "manifest_digest")
    }
    manifest = json.loads(_published_blob(layout, str(second["manifest_digest"])))
    expected_blobs.add(f"blobs/sha256/{manifest['config']['digest'].removeprefix('sha256:')}")
    assert actual_files == {"index.json", "oci-layout", *expected_blobs}


def test_failed_layout_commit_restores_prior_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module_path = _local_module(tmp_path / "shared.yaml")
    published = publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")
    layout = Path(published["layout_dir"])
    slot = _version_slot(layout)
    before = {path.relative_to(layout).as_posix(): path.read_bytes() for path in layout.rglob("*") if path.is_file()}
    module_path.write_text(module_path.read_text(encoding="utf-8") + "# changed bytes\n", encoding="utf-8")
    real_replace = module_registry_filesystem.os.replace

    def fail_staged_install(source, destination):
        if Path(source).name.startswith(".raes-current.staged-") and Path(destination) == slot / ".raes-current":
            raise OSError("simulated atomic install failure")
        return real_replace(source, destination)

    monkeypatch.setattr(module_registry_filesystem.os, "replace", fail_staged_install)

    with pytest.raises(SDLParseError, match="atomically"):
        publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")

    after = {path.relative_to(layout).as_posix(): path.read_bytes() for path in layout.rglob("*") if path.is_file()}
    assert after == before
    assert _current_version(slot) == layout
    assert len(list((slot / "versions").iterdir())) == 2
    assert not list(slot.glob(".raes-current.staged-*"))

    monkeypatch.undo()
    repaired = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])
    assert repaired != layout
    assert _current_version(slot) == repaired


def test_layout_prune_failure_cannot_advance_pointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module_path = _local_module(tmp_path / "shared.yaml")
    first = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])
    slot = _version_slot(first)
    module_path.write_text(module_path.read_text(encoding="utf-8") + "# next publication\n", encoding="utf-8")

    def fail_prune(**kwargs):
        del kwargs
        raise SDLParseError("simulated prune failure")

    monkeypatch.setattr(module_registry_publishing, "_prune_version_directories", fail_prune)

    with pytest.raises(SDLParseError, match="simulated prune failure"):
        publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")

    assert _current_version(slot) == first
    assert (first / "index.json").is_file()


def test_layout_rejects_non_directory_target(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    layout = tmp_path / "dist" / "acme_shared-1.2.3.oci"
    layout.parent.mkdir()
    layout.write_text("occupied\n", encoding="utf-8")

    with pytest.raises(SDLParseError, match="atomically"):
        publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")

    assert layout.read_text(encoding="utf-8") == "occupied\n"


def test_layout_build_failure_removes_staging_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module_path = _local_module(tmp_path / "shared.yaml")
    real_write_bytes = Path.write_bytes

    def fail_blob_write(path: Path, payload: bytes):
        if ".staged-" in path.as_posix() and "/blobs/sha256/" in path.as_posix():
            raise OSError("simulated blob write failure")
        return real_write_bytes(path, payload)

    monkeypatch.setattr(Path, "write_bytes", fail_blob_write)

    with pytest.raises(SDLParseError, match="Unable to build the OCI layout"):
        publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")

    versions = tmp_path / "dist" / "acme_shared-1.2.3.oci" / "versions"
    assert not list(versions.glob(".staged-*"))


def test_layout_repairs_missing_pointer_and_abandoned_stages(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    first = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])
    slot = _version_slot(first)
    (slot / ".raes-current").unlink()
    (slot / "versions" / ".staged-abandoned").mkdir()
    (slot / ".raes-current.staged-abandoned").write_text("partial\n", encoding="utf-8")

    repaired = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])

    assert repaired == first
    assert _current_version(slot) == first
    assert not list((slot / "versions").glob(".staged-*"))
    assert not list(slot.glob(".raes-current.staged-*"))


def test_layout_prior_reader_survives_new_publication(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    first_result = publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")
    first = Path(first_result["layout_dir"])
    first_index = (first / "index.json").read_bytes()
    module_path.write_text(module_path.read_text(encoding="utf-8") + "# next publication\n", encoding="utf-8")

    second = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])

    assert second != first
    assert (first / "index.json").read_bytes() == first_index
    assert first.is_dir()
    assert _current_version(_version_slot(second)) == second


def test_layout_validation_rejects_symlink_without_touching_target(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    first = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])
    outside = tmp_path / "outside-layout"
    outside.write_text("outside\n", encoding="utf-8")
    layout_metadata = first / "oci-layout"
    layout_metadata.unlink()
    try:
        layout_metadata.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    repaired = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])

    assert repaired != first
    assert (repaired / "oci-layout").read_bytes() == b'{"imageLayoutVersion":"1.0.0"}\n'
    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_layout_validation_rejects_modified_bytes_and_special_files(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    first = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])
    index = first / "index.json"
    payload = index.read_bytes()
    index.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])

    second = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])
    assert second != first

    if not hasattr(os, "mkfifo"):
        return
    os.mkfifo(second / "unexpected-pipe")
    third = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])
    assert third != second


def test_layout_rejects_invalid_staged_and_installed_versions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module_path = _local_module(tmp_path / "shared.yaml")
    real_rglob = Path.rglob

    def hide_staged_inventory(path: Path, pattern: str):
        if path.name.startswith(".staged-"):
            return iter(())
        return real_rglob(path, pattern)

    monkeypatch.setattr(Path, "rglob", hide_staged_inventory)
    with pytest.raises(SDLParseError, match="Staged OCI layout failed validation"):
        publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist-a")

    monkeypatch.undo()
    real_install = module_registry_publishing._install_version_directory

    def corrupt_installed(**kwargs):
        installed = real_install(**kwargs)
        (installed / "unexpected").write_text("corrupt\n", encoding="utf-8")
        return installed

    monkeypatch.setattr(module_registry_publishing, "_install_version_directory", corrupt_installed)
    with pytest.raises(SDLParseError, match="Published OCI layout failed validation"):
        publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist-b")


def test_layout_healthy_republish_reuses_current_immutable_version(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    first = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])

    second = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])

    assert second == first
    assert _current_version(_version_slot(first)) == first


def test_layout_validation_io_failure_rebuilds_without_exposing_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module_path = _local_module(tmp_path / "shared.yaml")
    first = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])
    failed_path = first / "index.json"
    real_lstat = Path.lstat
    failed = False

    def fail_once(path: Path):
        nonlocal failed
        if path == failed_path and not failed:
            failed = True
            raise OSError("SECRET-LSTAT-DETAIL")
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fail_once)

    repaired = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"])
    assert repaired != first


def test_layout_result_and_cli_identify_usable_immutable_version(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    publish = CliRunner().invoke(
        app,
        ["sdl", "publish", str(module_path), "--output-dir", str(tmp_path / "dist")],
    )

    assert publish.exit_code == 0, publish.output
    result = json.loads(publish.stdout)
    layout = Path(result["layout_dir"])
    slot = _version_slot(layout)
    assert layout.is_dir()
    assert (layout / "oci-layout").is_file()
    assert (layout / "index.json").is_file()
    assert slot.name == "acme_shared-1.2.3.oci"
    assert not (slot / "oci-layout").exists()
    assert _current_version(slot) == layout


def test_layout_fails_closed_on_pre_versioned_root_inventory(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    seed = Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "seed")["layout_dir"])
    legacy_slot = tmp_path / "dist" / "acme_shared-1.2.3.oci"
    legacy_slot.parent.mkdir()
    shutil.copytree(seed, legacy_slot)
    before = {
        path.relative_to(legacy_slot).as_posix(): path.read_bytes() for path in legacy_slot.rglob("*") if path.is_file()
    }
    module_path.write_text(module_path.read_text(encoding="utf-8") + "# changed publication\n", encoding="utf-8")

    with pytest.raises(SDLParseError, match="legacy root-layout format"):
        publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")

    after = {
        path.relative_to(legacy_slot).as_posix(): path.read_bytes() for path in legacy_slot.rglob("*") if path.is_file()
    }
    assert after == before
    assert not (legacy_slot / "versions").exists()
    assert not (legacy_slot / ".raes-current").exists()


def test_layout_version_retention_is_bounded_and_preserves_immediate_prior_reader(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    published: list[Path] = []
    for revision in range(module_registry_filesystem._MAX_RETAINED_VERSIONS + 3):
        module_path.write_text(
            module_path.read_text(encoding="utf-8") + f"# revision {revision}\n",
            encoding="utf-8",
        )
        published.append(Path(publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")["layout_dir"]))

    current = published[-1]
    prior = published[-2]
    versions = _version_slot(current) / "versions"
    assert len(list(versions.iterdir())) == module_registry_filesystem._MAX_RETAINED_VERSIONS
    assert current.is_dir()
    assert prior.is_dir()
    assert _current_version(_version_slot(current)) == current


def test_transaction_cleanup_does_not_follow_symlink(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep\n", encoding="utf-8")
    link = tmp_path / "transaction-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    module_registry_filesystem._remove_path(link)

    assert not link.exists()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep\n"


def test_version_install_failure_preserves_current_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slot = tmp_path / "slot"
    versions = module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    prior = versions / "prior"
    prior.mkdir()
    (prior / "prior.txt").write_text("prior\n", encoding="utf-8")
    module_registry_filesystem._write_version_pointer(
        slot=slot,
        version_name="prior",
        error_message="transaction failed",
    )
    staged = module_registry_filesystem._new_version_stage(versions=versions, error_message="transaction failed")
    real_replace = module_registry_filesystem.os.replace

    def fail_install(source, destination):
        if Path(source) == staged:
            raise OSError("simulated rename failure")
        return real_replace(source, destination)

    monkeypatch.setattr(module_registry_filesystem.os, "replace", fail_install)

    with pytest.raises(SDLParseError, match="transaction failed"):
        module_registry_filesystem._install_version_directory(
            staged=staged,
            versions=versions,
            version_name="next",
            error_message="transaction failed",
        )

    assert _current_version(slot) == prior
    assert (prior / "prior.txt").read_text(encoding="utf-8") == "prior\n"
    assert not staged.exists()


def test_pointer_failure_never_removes_prior_pointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slot = tmp_path / "slot"
    versions = module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    for name in ("prior", "next"):
        (versions / name).mkdir()
    module_registry_filesystem._write_version_pointer(
        slot=slot,
        version_name="prior",
        error_message="transaction failed",
    )
    real_replace = module_registry_filesystem.os.replace

    def fail_pointer(source, destination):
        if Path(destination) == slot / ".raes-current":
            raise OSError("simulated pointer failure")
        return real_replace(source, destination)

    monkeypatch.setattr(module_registry_filesystem.os, "replace", fail_pointer)

    with pytest.raises(SDLParseError, match="transaction failed"):
        module_registry_filesystem._write_version_pointer(
            slot=slot,
            version_name="next",
            error_message="transaction failed",
        )

    assert _current_version(slot) == versions / "prior"
    assert not list(slot.glob(".raes-current.staged-*"))


def test_version_install_and_pointer_sync_before_and_after_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    slot = tmp_path / "slot"
    versions = module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    staged = module_registry_filesystem._new_version_stage(versions=versions, error_message="transaction failed")
    (staged / "payload").write_text("complete\n", encoding="utf-8")
    events: list[str] = []
    real_replace = module_registry_filesystem.os.replace

    monkeypatch.setattr(
        module_registry_filesystem,
        "_fsync_tree",
        lambda path, *, error_message: events.append("tree-fsync"),
    )
    monkeypatch.setattr(
        module_registry_filesystem,
        "_fsync_directory",
        lambda path, *, error_message: events.append("directory-fsync"),
    )

    def record_replace(source, destination):
        events.append("replace")
        return real_replace(source, destination)

    monkeypatch.setattr(module_registry_filesystem.os, "replace", record_replace)
    module_registry_filesystem._install_version_directory(
        staged=staged,
        versions=versions,
        version_name="version",
        error_message="transaction failed",
    )
    assert events == ["tree-fsync", "replace", "directory-fsync"]

    events.clear()
    monkeypatch.setattr(module_registry_filesystem.os, "fsync", lambda descriptor: events.append("file-fsync"))
    module_registry_filesystem._write_version_pointer(
        slot=slot,
        version_name="version",
        error_message="transaction failed",
    )
    assert events == ["file-fsync", "replace", "directory-fsync"]


def test_version_fsync_failures_and_unsafe_tree_nodes_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(module_registry_filesystem, "_DIRECTORY_FSYNC_SUPPORTED", False)
    monkeypatch.setattr(
        module_registry_filesystem.os,
        "open",
        lambda *args, **kwargs: pytest.fail("unsupported directory fsync must not open a directory"),
    )
    module_registry_filesystem._fsync_directory(tmp_path, error_message="sync failed")

    monkeypatch.undo()
    if module_registry_filesystem._DIRECTORY_FSYNC_SUPPORTED:
        real_open = module_registry_filesystem.os.open

        def fail_directory_open(path, *args, **kwargs):
            if Path(path) == tmp_path:
                raise OSError("SECRET-DIRECTORY-OPEN")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(module_registry_filesystem.os, "open", fail_directory_open)
        with pytest.raises(SDLParseError, match="sync failed"):
            module_registry_filesystem._fsync_directory(tmp_path, error_message="sync failed")

        monkeypatch.undo()
        monkeypatch.setattr(
            module_registry_filesystem.os,
            "fsync",
            lambda descriptor: (_ for _ in ()).throw(OSError("SECRET-FSYNC")),
        )
        with pytest.raises(SDLParseError, match="sync failed"):
            module_registry_filesystem._fsync_directory(tmp_path, error_message="sync failed")

        monkeypatch.undo()
        monkeypatch.setattr(
            module_registry_filesystem.os,
            "fsync",
            lambda descriptor: (_ for _ in ()).throw(OSError(module_registry_filesystem.errno.EINVAL, "unsupported")),
        )
        module_registry_filesystem._fsync_directory(tmp_path, error_message="sync failed")

    monkeypatch.undo()
    outside = tmp_path / "outside"
    outside.write_text("outside\n", encoding="utf-8")
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(SDLParseError, match="sync failed"):
        module_registry_filesystem._fsync_tree(linked, error_message="sync failed")

    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "fifo"
        os.mkfifo(fifo)
        with pytest.raises(SDLParseError, match="sync failed"):
            module_registry_filesystem._fsync_tree(fifo, error_message="sync failed")

    regular = tmp_path / "regular"
    regular.write_text("regular\n", encoding="utf-8")
    directory_stat = tmp_path.stat()
    monkeypatch.setattr(module_registry_filesystem.os, "fstat", lambda descriptor: directory_stat)
    with pytest.raises(SDLParseError, match="sync failed"):
        module_registry_filesystem._fsync_tree(regular, error_message="sync failed")

    monkeypatch.undo()
    with pytest.raises(SDLParseError, match="sync failed"):
        module_registry_filesystem._fsync_tree(tmp_path / "missing", error_message="sync failed")

    original = tmp_path.stat()
    changed_values = list(original)
    changed_values[2] = original.st_dev + 1
    assert not module_registry_filesystem._same_file_identity(original, os.stat_result(changed_values))


@pytest.mark.parametrize("access_mode", [os.O_RDONLY, os.O_RDWR])
def test_tree_fsync_uses_platform_compatible_file_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    access_mode: int,
):
    regular = tmp_path / "regular"
    regular.write_text("regular\n", encoding="utf-8")
    real_open = module_registry_filesystem.os.open
    opened_flags: dict[int, int] = {}
    synced: list[int] = []

    def tracked_open(path, flags):
        descriptor = real_open(path, flags)
        opened_flags[descriptor] = flags
        return descriptor

    def windows_compatible_fsync(descriptor):
        flags = opened_flags[descriptor]
        if access_mode == os.O_RDWR and flags & os.O_RDWR != os.O_RDWR:
            raise OSError(module_registry_filesystem.errno.EBADF, "Windows requires a writable descriptor")
        synced.append(descriptor)

    monkeypatch.setattr(module_registry_filesystem, "_REGULAR_FILE_FSYNC_ACCESS_MODE", access_mode)
    monkeypatch.setattr(module_registry_filesystem.os, "open", tracked_open)
    monkeypatch.setattr(module_registry_filesystem.os, "fsync", windows_compatible_fsync)

    module_registry_filesystem._fsync_tree(regular, error_message="sync failed")

    assert len(opened_flags) == 1
    assert next(iter(opened_flags.values())) & (os.O_WRONLY | os.O_RDWR) == access_mode
    assert len(synced) == 1


def test_generated_version_names_bound_internal_path_growth() -> None:
    digest = "sha256:" + "a" * 64

    version_name = module_registry_filesystem._new_digest_version_name(digest)

    assert module_registry_filesystem._version_digest_prefix(digest) == "a" * 20
    assert version_name.startswith("a" * 20 + "-")
    assert len(version_name) == 41
    assert module_registry_filesystem._valid_version_name(version_name)


def test_version_install_cleans_stage_when_tree_sync_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slot = tmp_path / "slot"
    versions = module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    staged = module_registry_filesystem._new_version_stage(versions=versions, error_message="transaction failed")

    def fail_sync(*args, **kwargs):
        del args, kwargs
        raise SDLParseError("tree sync failed")

    monkeypatch.setattr(module_registry_filesystem, "_fsync_tree", fail_sync)
    with pytest.raises(SDLParseError, match="tree sync failed"):
        module_registry_filesystem._install_version_directory(
            staged=staged,
            versions=versions,
            version_name="version",
            error_message="transaction failed",
        )
    assert not staged.exists()


@pytest.mark.parametrize(
    "payload",
    [b"", b"version", b"\xff\n", b"../escape\n", b"a" * 257],
)
def test_invalid_version_pointer_is_never_followed(tmp_path: Path, payload: bytes):
    slot = tmp_path / "slot"
    versions = module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    (versions / "version").mkdir()
    (slot / ".raes-current").write_bytes(payload)

    assert module_registry_filesystem._read_version_pointer(slot=slot) is None


def test_version_pointer_rejects_symlink_and_missing_version(tmp_path: Path):
    slot = tmp_path / "slot"
    module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    outside = tmp_path / "outside"
    outside.write_text("missing\n", encoding="utf-8")
    pointer = slot / ".raes-current"
    try:
        pointer.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    assert module_registry_filesystem._read_version_pointer(slot=slot) is None
    assert outside.read_text(encoding="utf-8") == "missing\n"

    pointer.unlink()
    pointer.write_text("missing\n", encoding="ascii")
    assert module_registry_filesystem._read_version_pointer(slot=slot) is None


def test_version_store_rejects_links_files_collisions_and_invalid_names(tmp_path: Path):
    slot = tmp_path / "slot"
    versions = module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    valid = versions / "valid"
    valid.mkdir()
    (versions / "file").write_text("not a version\n", encoding="utf-8")
    try:
        (versions / "link").symlink_to(valid, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    assert list(module_registry_filesystem._iter_version_directories(versions)) == [valid]
    for version_name in ("../escape", "valid"):
        staged = module_registry_filesystem._new_version_stage(versions=versions, error_message="transaction failed")
        with pytest.raises(SDLParseError, match="transaction failed"):
            module_registry_filesystem._install_version_directory(
                staged=staged,
                versions=versions,
                version_name=version_name,
                error_message="transaction failed",
            )
        assert not staged.exists()

    with pytest.raises(SDLParseError, match="transaction failed"):
        module_registry_filesystem._write_version_pointer(
            slot=slot,
            version_name="../escape",
            error_message="transaction failed",
        )
    with pytest.raises(SDLParseError, match="transaction failed"):
        module_registry_filesystem._write_version_pointer(
            slot=slot,
            version_name="missing",
            error_message="transaction failed",
        )


def test_version_slot_rejects_symlink_without_following_it(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("keep\n", encoding="utf-8")
    slot = tmp_path / "slot"
    try:
        slot.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(SDLParseError, match="transaction failed"):
        module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")

    assert (outside / "keep").read_text(encoding="utf-8") == "keep\n"


def test_version_store_translates_directory_and_stage_creation_failures(tmp_path: Path):
    with pytest.raises(SDLParseError, match="transaction failed"):
        module_registry_filesystem._prepare_versioned_slot(
            slot=tmp_path / "missing-parent" / "slot",
            error_message="transaction failed",
        )
    with pytest.raises(SDLParseError, match="Unable to inspect immutable version directories"):
        list(module_registry_filesystem._iter_version_directories(tmp_path / "missing-versions"))
    with pytest.raises(SDLParseError, match="transaction failed"):
        module_registry_filesystem._new_version_stage(
            versions=tmp_path / "missing-versions",
            error_message="transaction failed",
        )


def test_version_pointer_translates_temporary_file_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slot = tmp_path / "slot"
    versions = module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    (versions / "version").mkdir()

    def fail_mkstemp(*args, **kwargs):
        del args, kwargs
        raise OSError("SECRET-TEMP-DETAIL")

    monkeypatch.setattr(module_registry_filesystem.tempfile, "mkstemp", fail_mkstemp)

    with pytest.raises(SDLParseError) as exc_info:
        module_registry_filesystem._write_version_pointer(
            slot=slot,
            version_name="version",
            error_message="transaction failed",
        )
    assert str(exc_info.value) == "transaction failed"


def test_version_store_detects_post_create_replacement_and_cleanup_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "target"
    real_is_dir = Path.is_dir

    def hide_created_directory(path: Path) -> bool:
        if path == target:
            return False
        return real_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", hide_created_directory)
    with pytest.raises(SDLParseError, match="transaction failed"):
        module_registry_filesystem._require_directory(target, error_message="transaction failed")

    monkeypatch.undo()
    slot = tmp_path / "slot"
    versions = module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    real_iterdir = Path.iterdir

    def fail_cleanup_scan(path: Path):
        if path == versions:
            raise OSError("SECRET-SCAN-DETAIL")
        return real_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fail_cleanup_scan)
    with pytest.raises(SDLParseError) as exc_info:
        module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    assert str(exc_info.value) == "transaction failed"


def test_version_pointer_rejects_identity_swap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slot = tmp_path / "slot"
    versions = module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    (versions / "version").mkdir()
    (slot / ".raes-current").write_text("version\n", encoding="ascii")
    directory_stat = slot.stat()
    monkeypatch.setattr(module_registry_filesystem.os, "fstat", lambda descriptor: directory_stat)

    assert module_registry_filesystem._read_version_pointer(slot=slot) is None


def test_version_pointer_closes_descriptor_when_fdopen_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slot = tmp_path / "slot"
    versions = module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    (versions / "version").mkdir()

    def fail_fdopen(*args, **kwargs):
        del args, kwargs
        raise OSError("SECRET-FDOPEN-DETAIL")

    monkeypatch.setattr(module_registry_filesystem.os, "fdopen", fail_fdopen)
    with pytest.raises(SDLParseError) as exc_info:
        module_registry_filesystem._write_version_pointer(
            slot=slot,
            version_name="version",
            error_message="transaction failed",
        )
    assert str(exc_info.value) == "transaction failed"
    assert not list(slot.glob(".raes-current.staged-*"))


def test_version_pointer_read_closes_descriptor_when_fdopen_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    slot = tmp_path / "slot"
    versions = module_registry_filesystem._prepare_versioned_slot(slot=slot, error_message="transaction failed")
    (versions / "version").mkdir()
    (slot / ".raes-current").write_text("version\n", encoding="ascii")

    def fail_fdopen(*args, **kwargs):
        del args, kwargs
        raise OSError("SECRET-FDOPEN-DETAIL")

    monkeypatch.setattr(module_registry_filesystem.os, "fdopen", fail_fdopen)
    assert module_registry_filesystem._read_version_pointer(slot=slot) is None


def test_version_pruning_rejects_invalid_bound_and_translates_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    versions = tmp_path / "versions"
    versions.mkdir()
    version = versions / "version"
    version.mkdir()
    with pytest.raises(SDLParseError, match="prune failed"):
        module_registry_filesystem._prune_version_directories(
            versions=versions,
            retain_names={"version"},
            max_versions=1,
            error_message="prune failed",
        )

    real_stat = Path.stat

    def fail_version_stat(path: Path, *args, **kwargs):
        if path == version:
            raise OSError("SECRET-STAT-DETAIL")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fail_version_stat)
    with pytest.raises(SDLParseError) as exc_info:
        module_registry_filesystem._prune_version_directories(
            versions=versions,
            retain_names={"version"},
            error_message="prune failed",
        )
    assert str(exc_info.value) == "prune failed"


def test_oci_registry_requests_use_bounded_timeouts(monkeypatch: pytest.MonkeyPatch):
    responses = [b'{"ok": true}', b"bundle-bytes"]
    timeouts: list[float | None] = []

    class _Response:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

        def read(self, amt: int = -1) -> bytes:
            if amt is None or amt < 0:
                return self._payload
            return self._payload[:amt]

    def fake_urlopen(request, *, timeout=None):
        del request
        timeouts.append(timeout)
        return _Response(responses.pop(0))

    monkeypatch.setattr(module_registry, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        module_registry, "_OCI_LIMITS", dataclasses.replace(module_registry._OCI_LIMITS, timeout_seconds=7)
    )

    assert module_registry._json_request("https://registry.example/v2/acme/tags/list") == {"ok": True}
    assert module_registry._bytes_request("https://registry.example/v2/acme/blobs/sha256:abc") == b"bundle-bytes"
    assert timeouts == [7, 7]


@pytest.mark.parametrize("request_name", ["_json_request", "_bytes_request"])
def test_oci_registry_transport_errors_are_stable(monkeypatch: pytest.MonkeyPatch, request_name: str):
    def fail_urlopen(*args, **kwargs):
        raise URLError("SECRET-TRANSPORT-DETAIL")

    monkeypatch.setattr(module_registry, "urlopen", fail_urlopen)
    request = getattr(module_registry, request_name)

    with pytest.raises(SDLParseError) as exc_info:
        request("https://registry.example/v2/acme/resource")

    assert "SECRET-TRANSPORT-DETAIL" not in str(exc_info.value)


def test_oci_manifest_rejects_malformed_tag_shape(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(module_registry, "_json_request", lambda *args, **kwargs: {"tags": "1.0.0"})
    import_decl = module_registry.ImportDecl(source="oci:registry.example/acme/shared", namespace="shared")

    with pytest.raises(SDLParseError, match="invalid tags list"):
        module_registry_resolution._resolve_oci_manifest(
            base_url="https://registry.example",
            repository="acme/shared",
            import_decl=import_decl,
            locked=None,
            source="oci:registry.example/acme/shared",
        )


def test_oci_config_rejects_malformed_descriptor_shape():
    with pytest.raises(SDLParseError, match="malformed config or layer descriptors"):
        module_registry_resolution._resolve_oci_config(
            base_url="https://registry.example",
            repository="acme/shared",
            manifest={"config": [], "layers": ["not-an-object"]},
            source="oci:registry.example/acme/shared",
        )


def test_oci_module_descriptor_validation_is_normalized_to_sdl_parse_error() -> None:
    import_decl = module_registry.ImportDecl(
        source="oci:registry.example/acme/shared",
        namespace="shared",
    )

    with pytest.raises(SDLParseError, match="invalid module descriptor"):
        module_registry_resolution._build_oci_descriptor(
            config_payload={"module": {"id": [], "version": "1.0.0"}},
            layer_digest="sha256:" + "0" * 64,
            import_decl=import_decl,
            locked=None,
            source=import_decl.source,
        )


def test_signed_oci_import_rejects_non_object_signature_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "oci:registry.example/acme/shared"
    import_decl = module_registry.ImportDecl(source=source, namespace="shared")
    trust_policy = module_registry.TrustPolicy(
        registries={
            "registry.example": module_registry.RegistryTrustPolicy(
                require_signatures=True,
            )
        }
    )
    digest = "sha256:" + "0" * 64
    monkeypatch.setattr(
        module_registry_resolution,
        "_resolve_oci_manifest",
        lambda **_kwargs: (digest, {}),
    )
    monkeypatch.setattr(
        module_registry_resolution,
        "_resolve_oci_config",
        lambda **_kwargs: (
            {
                "module": {"id": "acme/shared", "version": "1.0.0"},
                "signatures": ["not-an-object"],
            },
            digest,
        ),
    )
    monkeypatch.setattr(
        module_registry_resolution,
        "_fetch_oci_bundle",
        lambda **_kwargs: b"unused-bundle",
    )

    with pytest.raises(SDLParseError, match="malformed signature metadata"):
        module_registry_resolution._resolve_oci_import(
            import_decl,
            source,
            base_dir=tmp_path,
            lockfile=None,
            trust_policy=trust_policy,
            source_options=DEFAULT_SOURCE_PARSE_OPTIONS,
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b'{"unterminated":', "is not valid UTF-8 JSON"),
        (b'\xff{"valid": false}', "is not valid UTF-8 JSON"),
        (b'["not", "an", "object"]', "must be a JSON object"),
        pytest.param(b'{"integer":' + b"9" * 10_000 + b"}", "is not valid UTF-8 JSON", id="integer"),
    ],
)
def test_oci_metadata_malformed_json_has_stable_error(monkeypatch: pytest.MonkeyPatch, payload: bytes, message: str):
    monkeypatch.setattr(module_registry, "urlopen", _fake_urlopen_returning(_FakeResponse(payload)))

    with pytest.raises(SDLParseError) as exc_info:
        module_registry._json_request("https://registry.example/v2/acme/tags/list")

    assert str(exc_info.value) == f"OCI metadata from https://registry.example/v2/acme/tags/list {message}"
    assert "line 1 column" not in str(exc_info.value)


@pytest.mark.parametrize("decoder_error", [RecursionError("too deep"), ValueError("integer limit")])
def test_oci_metadata_decoder_limit_errors_are_stable(
    monkeypatch: pytest.MonkeyPatch,
    decoder_error: Exception,
) -> None:
    def fail_decode(_payload: str) -> object:
        raise decoder_error

    monkeypatch.setattr(module_registry.json, "loads", fail_decode)
    with pytest.raises(SDLParseError) as exc_info:
        module_registry._decode_json_object(b"{}", context="OCI metadata")

    assert str(exc_info.value) == "OCI metadata is not valid UTF-8 JSON"


def test_oci_manifest_malformed_json_has_stable_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(module_registry, "_bytes_request", lambda *args, **kwargs: b'{"broken":')
    monkeypatch.setattr(module_registry, "_json_request", lambda *args, **kwargs: {"tags": ["1.0.0"]})
    import_decl = module_registry.ImportDecl(source="oci:registry.example/acme/shared", namespace="shared")

    with pytest.raises(SDLParseError) as exc_info:
        module_registry_resolution._resolve_oci_manifest(
            base_url="https://registry.example",
            repository="acme/shared",
            import_decl=import_decl,
            locked=None,
            source="oci:registry.example/acme/shared",
        )

    assert str(exc_info.value) == "OCI manifest for 'oci:registry.example/acme/shared' is not valid UTF-8 JSON"


def test_oci_config_malformed_json_has_stable_error(monkeypatch: pytest.MonkeyPatch):
    malformed = b'{"broken":'
    digest = f"sha256:{module_registry._sha256_digest(malformed)}"
    monkeypatch.setattr(module_registry, "_bytes_request", lambda *args, **kwargs: malformed)
    manifest = {
        "config": {"digest": digest},
        "layers": [{"mediaType": module_registry.OCI_BUNDLE_MEDIA_TYPE, "digest": "sha256:" + "a" * 64}],
    }

    with pytest.raises(SDLParseError) as exc_info:
        module_registry_resolution._resolve_oci_config(
            base_url="https://registry.example",
            repository="acme/shared",
            manifest=manifest,
            source="oci:registry.example/acme/shared",
        )

    assert str(exc_info.value) == "OCI config for 'oci:registry.example/acme/shared' is not valid UTF-8 JSON"


@pytest.mark.parametrize(
    "root_file",
    ["../module.yaml", "a//module.yaml", "a/module.yaml/", "./module.yaml", ".", "C:/module.yaml"],
)
def test_oci_bundle_rejects_root_file_escape(tmp_path: Path, root_file: str):
    with pytest.raises(SDLParseError, match="Invalid OCI root_file path"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=b"",
            manifest_digest="abc123",
            root_file=root_file,
            base_dir=tmp_path,
        )


def test_oci_bundle_rejects_unsafe_tar_members(tmp_path: Path):
    bundle_buffer = io.BytesIO()
    with tarfile.open(fileobj=bundle_buffer, mode="w:gz") as tar:
        payload = b"name: unsafe\n"
        member = tarfile.TarInfo(name="../escape.yaml")
        member.size = len(payload)
        tar.addfile(member, io.BytesIO(payload))
    bundle_buffer.seek(0)

    with (
        tarfile.open(fileobj=bundle_buffer, mode="r:gz") as tar,
        pytest.raises(SDLParseError, match="Path traversal detected"),
    ):
        module_registry._safe_tar_members(tar, tmp_path / "cache")


def test_oci_bundle_rejects_nul_in_pax_member_path(tmp_path: Path):
    raw_bundle = io.BytesIO()
    with tarfile.open(fileobj=raw_bundle, mode="w", format=tarfile.PAX_FORMAT) as tar:
        payload = b"name: unsafe\n"
        member = tarfile.TarInfo(name="safe.yaml")
        member.pax_headers = {"path": "unsafe\x00name.yaml"}
        member.size = len(payload)
        tar.addfile(member, io.BytesIO(payload))

    bundle = gzip.compress(raw_bundle.getvalue(), mtime=0)
    with pytest.raises(SDLParseError, match="Path traversal detected"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="nul-pax-path",
            root_file="safe.yaml",
            base_dir=tmp_path,
        )


def test_oci_bundle_rejects_special_member_types(tmp_path: Path):
    bundle_buffer = io.BytesIO()
    with tarfile.open(fileobj=bundle_buffer, mode="w:gz") as tar:
        fifo = tarfile.TarInfo(name="pipe")
        fifo.type = tarfile.FIFOTYPE
        tar.addfile(fifo)
    bundle_buffer.seek(0)

    with (
        tarfile.open(fileobj=bundle_buffer, mode="r:gz") as tar,
        pytest.raises(SDLParseError, match="Unsupported tar member"),
    ):
        module_registry._safe_tar_members(tar, tmp_path / "cache")


def test_oci_bundle_rejects_reserved_cache_manifest_member(tmp_path: Path):
    bundle = _gzip_tar([(".raes-cache-tree.json", b"attacker controlled\n")])
    with (
        tarfile.open(fileobj=bundle, mode="r:gz") as archive,
        pytest.raises(SDLParseError, match="reserved cache metadata"),
    ):
        module_registry._safe_tar_members(archive, tmp_path / "cache")


def test_oci_bundle_rejects_symlink_members(tmp_path: Path):
    # A symlink whose own name passes the traversal check (e.g. name='module.yaml')
    # but whose linkname escapes the cache is a distinct attack vector and must be
    # rejected before extraction.
    bundle_buffer = io.BytesIO()
    with tarfile.open(fileobj=bundle_buffer, mode="w:gz") as tar:
        member = tarfile.TarInfo(name="module.yaml")
        member.type = tarfile.SYMTYPE
        member.linkname = "../outside.yaml"
        tar.addfile(member)
    bundle_buffer.seek(0)

    with (
        tarfile.open(fileobj=bundle_buffer, mode="r:gz") as tar,
        pytest.raises(SDLParseError, match="Links are not allowed"),
    ):
        module_registry._safe_tar_members(tar, tmp_path / "cache")


def test_oci_bundle_rejects_hardlink_members(tmp_path: Path):
    bundle_buffer = io.BytesIO()
    with tarfile.open(fileobj=bundle_buffer, mode="w:gz") as tar:
        target = tarfile.TarInfo(name="module.yaml")
        target.size = 0
        tar.addfile(target, io.BytesIO(b""))
        link = tarfile.TarInfo(name="link.yaml")
        link.type = tarfile.LNKTYPE
        link.linkname = "module.yaml"
        tar.addfile(link)
    bundle_buffer.seek(0)

    with (
        tarfile.open(fileobj=bundle_buffer, mode="r:gz") as tar,
        pytest.raises(SDLParseError, match="Links are not allowed"),
    ):
        module_registry._safe_tar_members(tar, tmp_path / "cache")


def test_oci_bundle_strips_dangerous_mode_bits(tmp_path: Path):
    payload = b"name: m\n"
    bundle_buffer = io.BytesIO()
    with tarfile.open(fileobj=bundle_buffer, mode="w:gz") as tar:
        member = tarfile.TarInfo(name="module.yaml")
        member.size = len(payload)
        member.mode = 0o4755  # setuid bit set by an attacker-controlled bundle
        tar.addfile(member, io.BytesIO(payload))
    bundle_buffer.seek(0)

    with tarfile.open(fileobj=bundle_buffer, mode="r:gz") as tar:
        safe = module_registry._safe_tar_members(tar, tmp_path / "cache")

    assert safe[0].mode & 0o7000 == 0
    assert safe[0].mode == 0o755


@pytest.mark.parametrize(
    "member_name",
    ["", "./module.yaml", "nested/../module.yaml", "nested//module.yaml", "C:/module.yaml", "nested\\module.yaml"],
)
def test_oci_bundle_rejects_noncanonical_cross_platform_member_paths(tmp_path: Path, member_name: str):
    member = tarfile.TarInfo(name=member_name)
    member.size = 0
    destination = tmp_path / "cache"
    resolved_destination = destination.resolve()

    with pytest.raises(SDLParseError, match="Path traversal detected"):
        module_registry._validate_tar_member_shape(
            member,
            dest=destination,
            resolved_dest=resolved_destination,
            seen_paths=set(),
            limits=module_registry._OCI_LIMITS,
        )


def test_oci_bundle_member_must_remain_below_validated_destination(tmp_path: Path):
    member = tarfile.TarInfo(name="module.yaml")
    member.size = 0
    destination = tmp_path / "cache"
    resolved_destination = (tmp_path / "different-cache").resolve()

    with pytest.raises(SDLParseError, match="Path traversal detected"):
        module_registry._validate_tar_member_shape(
            member,
            dest=destination,
            resolved_dest=resolved_destination,
            seen_paths=set(),
            limits=module_registry._OCI_LIMITS,
        )


def test_oci_bundle_inventory_is_streamed_with_filtered_modes_and_implicit_directories(tmp_path: Path):
    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode="w:gz") as archive:
        member = tarfile.TarInfo(name="nested/module.yaml")
        member.mode = 0o111
        payload = b"name: executable\n"
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    bundle.seek(0)

    with tarfile.open(fileobj=bundle, mode="r:gz") as archive:
        members = module_registry._safe_tar_members(archive, tmp_path / "inventory")
        manifest = module_registry._expected_cache_tree_manifest(
            tar=archive,
            members=members,
            content_digest="sha256:" + "0" * 64,
            root_file="nested/module.yaml",
        )

    directory_mode = 0o777 if os.name == "nt" else 0o700
    file_mode = 0o666 if os.name == "nt" else 0o711
    assert manifest["entries"] == [
        {"mode": directory_mode, "path": ".", "type": "directory"},
        {"mode": directory_mode, "path": "nested", "type": "directory"},
        {
            "digest": f"sha256:{module_registry._sha256_digest(payload)}",
            "mode": file_mode,
            "path": "nested/module.yaml",
            "size": len(payload),
            "type": "file",
        },
    ]
    assert not (tmp_path / "inventory").exists()


def test_oci_bundle_inventory_uses_windows_representable_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module_registry_archive.os, "name", "nt")
    bundle = _gzip_tar([("nested/module.yaml", b"name: windows\n")])
    with tarfile.open(fileobj=bundle, mode="r:gz") as archive:
        members = module_registry._safe_tar_members(archive, tmp_path / "inventory")
        manifest = module_registry._expected_cache_tree_manifest(
            tar=archive,
            members=members,
            content_digest="sha256:" + "0" * 64,
            root_file="nested/module.yaml",
        )

    entries = {entry["path"]: entry for entry in manifest["entries"]}
    assert entries["."]["mode"] == 0o777
    assert entries["nested"]["mode"] == 0o777
    assert entries["nested/module.yaml"]["mode"] == 0o666


def test_oci_directory_mode_normalization_does_not_use_windows_chmod(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mode = stat.S_IMODE(tmp_path.stat().st_mode)
    monkeypatch.setattr(module_registry_extraction.os, "name", "nt")
    monkeypatch.setattr(
        module_registry_extraction.os,
        "chmod",
        lambda *args, **kwargs: pytest.fail("Windows directory mode admission must not call chmod"),
    )

    module_registry_extraction._normalize_extracted_directory_modes(
        tmp_path,
        [{"mode": mode, "path": ".", "type": "directory"}],
    )


def test_oci_directory_mode_normalization_rejects_invalid_and_unstable_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    not_directory = tmp_path / "file"
    not_directory.write_text("payload", encoding="utf-8")
    with pytest.raises(SDLParseError, match="non-directory entry"):
        module_registry_extraction._normalize_extracted_directory_modes(
            tmp_path,
            [{"mode": 0o700, "path": "file", "type": "directory"}],
        )

    expected_mode = stat.S_IMODE(tmp_path.stat().st_mode) ^ 0o100
    monkeypatch.setattr(module_registry_extraction.os, "chmod", lambda *args, **kwargs: None)
    with pytest.raises(SDLParseError, match="changed during normalization"):
        module_registry_extraction._normalize_extracted_directory_modes(
            tmp_path,
            [{"mode": expected_mode, "path": ".", "type": "directory"}],
        )


def test_oci_directory_mode_normalization_wraps_platform_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_chmod(*args, **kwargs):
        raise OSError("injected mode failure")

    monkeypatch.setattr(module_registry_extraction.os, "name", "posix")
    monkeypatch.setattr(module_registry_extraction.os, "chmod", fail_chmod)
    with pytest.raises(SDLParseError, match="Unable to normalize"):
        module_registry_extraction._normalize_extracted_directory_modes(
            tmp_path,
            [{"mode": 0o700, "path": ".", "type": "directory"}],
        )


@pytest.mark.parametrize(
    "members",
    [
        [("parent", b"file\n"), ("parent/module.yaml", b"name: nested\n")],
        [("parent/module.yaml", b"name: nested\n"), ("parent", b"file\n")],
    ],
)
def test_oci_bundle_inventory_rejects_file_directory_conflicts(
    tmp_path: Path,
    members: list[tuple[str, bytes]],
):
    bundle_bytes = _gzip_tar(members).getvalue()
    member_identity = repr(members).encode()
    manifest_digest = "conflict-" + module_registry._sha256_digest(member_identity)
    with pytest.raises(SDLParseError, match="conflicting file and directory paths"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle_bytes,
            manifest_digest=manifest_digest,
            root_file="parent/module.yaml",
            base_dir=tmp_path,
        )


def test_oci_bundle_inventory_rejects_file_at_tree_root(tmp_path: Path):
    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode="w:gz") as archive:
        member = tarfile.TarInfo(name=".")
        member.size = 0
        archive.addfile(member, io.BytesIO())

    bundle_bytes = bundle.getvalue()
    with pytest.raises(SDLParseError, match="cannot replace the cache tree root"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle_bytes,
            manifest_digest="root-file",
            root_file="module.yaml",
            base_dir=tmp_path,
        )


def test_oci_bundle_inventory_defensive_stream_failures(monkeypatch: pytest.MonkeyPatch):
    class StubTar:
        def __init__(self, payload: bytes | None) -> None:
            self.payload = payload

        def extractfile(self, member):
            del member
            return None if self.payload is None else io.BytesIO(self.payload)

    root_directory = tarfile.TarInfo(name=".")
    root_directory.type = tarfile.DIRTYPE
    manifest = module_registry._expected_cache_tree_manifest(
        tar=StubTar(None),
        members=[root_directory],
        content_digest="sha256:" + "0" * 64,
        root_file="module.yaml",
    )
    directory_mode = 0o777 if os.name == "nt" else 0o700
    assert manifest["entries"] == [{"mode": directory_mode, "path": ".", "type": "directory"}]

    file_member = tarfile.TarInfo(name="entry")
    file_member.size = 1
    missing_payload_tar = StubTar(None)
    with pytest.raises(SDLParseError, match="Unable to read"):
        module_registry._expected_cache_tree_manifest(
            tar=missing_payload_tar,
            members=[file_member],
            content_digest="sha256:" + "0" * 64,
            root_file="entry",
        )
    oversized_payload_tar = StubTar(b"xx")
    with pytest.raises(SDLParseError, match="exceeds its declared size"):
        module_registry._expected_cache_tree_manifest(
            tar=oversized_payload_tar,
            members=[file_member],
            content_digest="sha256:" + "0" * 64,
            root_file="entry",
        )
    file_member.size = 2
    short_payload_tar = StubTar(b"x")
    with pytest.raises(SDLParseError, match="shorter than its declared size"):
        module_registry._expected_cache_tree_manifest(
            tar=short_payload_tar,
            members=[file_member],
            content_digest="sha256:" + "0" * 64,
            root_file="entry",
        )

    file_member.size = 0
    directory_member = tarfile.TarInfo(name="entry")
    directory_member.type = tarfile.DIRTYPE
    conflicting_entry_tar = StubTar(b"")
    with pytest.raises(SDLParseError, match="conflicting file and directory paths"):
        module_registry._expected_cache_tree_manifest(
            tar=conflicting_entry_tar,
            members=[file_member, directory_member],
            content_digest="sha256:" + "0" * 64,
            root_file="entry",
        )

    limits = module_registry._OCI_LIMITS
    monkeypatch.setattr(module_registry, "_OCI_LIMITS", dataclasses.replace(limits, max_bundle_members=0))
    entry_limit_tar = StubTar(b"")
    with pytest.raises(SDLParseError, match="tree entry limit"):
        module_registry._expected_cache_tree_manifest(
            tar=entry_limit_tar,
            members=[file_member],
            content_digest="sha256:" + "0" * 64,
            root_file="entry",
        )
    monkeypatch.setattr(module_registry, "_OCI_LIMITS", dataclasses.replace(limits, max_metadata_bytes=1))
    metadata_limit_tar = StubTar(None)
    with pytest.raises(SDLParseError, match="metadata limit"):
        module_registry._expected_cache_tree_manifest(
            tar=metadata_limit_tar,
            members=[],
            content_digest="sha256:" + "0" * 64,
            root_file="entry",
        )


def test_oci_bundle_extracts_safe_members(tmp_path: Path):
    payload = b"name: ok\n"
    bundle_buffer = io.BytesIO()
    with tarfile.open(fileobj=bundle_buffer, mode="w:gz") as tar:
        member = tarfile.TarInfo(name="module.yaml")
        member.size = len(payload)
        tar.addfile(member, io.BytesIO(payload))
    bundle_buffer.seek(0)

    root_path = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle_buffer.getvalue(),
        manifest_digest="deadbeef",
        root_file="module.yaml",
        base_dir=tmp_path,
    )

    assert root_path.is_file()
    assert root_path.read_bytes() == payload
    cache = module_registry._oci_cache_dir(tmp_path) / "deadbeef"
    assert root_path.resolve().is_relative_to(cache.resolve())


def test_oci_bundle_without_data_filter_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Simulate Python 3.11.0–3.11.3, where TarFile.extractall lacks the PEP 706
    # `filter` keyword (backported in 3.11.4). There is deliberately no unsafe
    # compatibility fallback at this filesystem-write boundary.

    def no_filter_extractall(self, path=None, members=None, **kwargs):
        del self, path, members
        if "filter" in kwargs:
            raise TypeError("extractall() got an unexpected keyword argument 'filter'")
        pytest.fail("unfiltered extraction must never be attempted")

    monkeypatch.setattr(tarfile.TarFile, "extractall", no_filter_extractall)

    payload = b"name: ok\n"
    bundle_buffer = io.BytesIO()
    with tarfile.open(fileobj=bundle_buffer, mode="w:gz") as tar:
        member = tarfile.TarInfo(name="module.yaml")
        member.size = len(payload)
        tar.addfile(member, io.BytesIO(payload))
    bundle_buffer.seek(0)
    bundle_bytes = bundle_buffer.getvalue()

    with pytest.raises(SDLParseError, match="Python 3.11.4 or newer"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle_bytes,
            manifest_digest="cafef00d",
            root_file="module.yaml",
            base_dir=tmp_path,
        )
    versions = module_registry._oci_cache_dir(tmp_path) / "cafef00d" / "versions"
    assert not list(versions.iterdir())


def test_oci_bundle_fallback_rejects_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # The fallback path used on Python 3.11.0–3.11.3 must still reject traversal.
    real_extractall = tarfile.TarFile.extractall

    def no_filter_extractall(self, path=None, members=None, **kwargs):
        if "filter" in kwargs:
            raise TypeError("extractall() got an unexpected keyword argument 'filter'")
        return real_extractall(self, path, members=members)

    monkeypatch.setattr(tarfile.TarFile, "extractall", no_filter_extractall)

    payload = b"owned\n"
    bundle_buffer = io.BytesIO()
    with tarfile.open(fileobj=bundle_buffer, mode="w:gz") as tar:
        member = tarfile.TarInfo(name="../escape.yaml")
        member.size = len(payload)
        tar.addfile(member, io.BytesIO(payload))
    bundle_buffer.seek(0)

    with pytest.raises(SDLParseError, match="Path traversal detected"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle_buffer.getvalue(),
            manifest_digest="badbad",
            root_file="module.yaml",
            base_dir=tmp_path,
        )
    assert not (tmp_path / "escape.yaml").exists()


def test_oci_bundle_rejects_root_file_directory(tmp_path: Path):
    bundle_buffer = io.BytesIO()
    with tarfile.open(fileobj=bundle_buffer, mode="w:gz") as tar:
        directory = tarfile.TarInfo(name="module.yaml")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        tar.addfile(directory)
    bundle_buffer.seek(0)

    with pytest.raises(SDLParseError, match="root file"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle_buffer.getvalue(),
            manifest_digest="d1rd1r",
            root_file="module.yaml",
            base_dir=tmp_path,
        )


def test_oci_bundle_rechecks_declared_root_after_extraction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(tarfile.TarFile, "extractall", lambda *args, **kwargs: None)
    bundle_bytes = _cache_test_bundle(b"name: absent\n")

    with pytest.raises(SDLParseError, match="missing declared root file"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle_bytes,
            manifest_digest="missing-after-extraction",
            root_file="module.yaml",
            base_dir=tmp_path,
        )


def test_oci_bundle_cache_hit_enforces_root_file_containment(tmp_path: Path):
    # Simulate a cache populated by an earlier unsafe extractor: a symlink at the
    # root_file location resolving outside the digest cache. The cache-hit fast path
    # must still fail closed rather than returning the escaping path.
    bundle = _cache_test_bundle(b"name: safe\n")
    root = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="stale",
        root_file="module.yaml",
        base_dir=tmp_path,
    )
    outside = tmp_path / "outside.yaml"
    outside.write_text("name: evil\n", encoding="utf-8")
    root.unlink()
    root.symlink_to(outside)

    repaired = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="stale",
        root_file="module.yaml",
        base_dir=tmp_path,
    )

    assert repaired.parent != root.parent
    assert repaired.read_bytes() == b"name: safe\n"
    assert root.is_symlink()


def _cache_test_bundle(payload: bytes) -> bytes:
    return _gzip_tar([("module.yaml", payload)]).getvalue()


def _cache_graph_bundle() -> bytes:
    return _gzip_tar(
        [
            (
                "module.yaml",
                b"name: root\nimports:\n  - source: local:nested/child.yaml\n    namespace: child\n",
            ),
            ("nested/child.yaml", b"name: child\n"),
        ]
    ).getvalue()


def test_verified_oci_cache_source_graph_is_captured_on_miss_and_hit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _cache_graph_bundle()
    first = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="verified-source-graph",
        root_file="module.yaml",
        base_dir=tmp_path,
        source_options=DEFAULT_SOURCE_PARSE_OPTIONS,
    )

    assert isinstance(first, module_registry._VerifiedSourceBundle)
    assert list(first.documents) == ["module.yaml", "nested/child.yaml"]
    assert first.resolve_local(base_dir=first.cache_root, relative="module.yaml")[1].raw_bytes.startswith(b"name: root")

    monkeypatch.setattr(
        tarfile.TarFile,
        "extractall",
        lambda *_args, **_kwargs: pytest.fail("a verified cache hit must not extract"),
    )
    second = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="verified-source-graph",
        root_file="module.yaml",
        base_dir=tmp_path,
        source_options=DEFAULT_SOURCE_PARSE_OPTIONS,
    )

    assert isinstance(second, module_registry._VerifiedSourceBundle)
    assert second.cache_root == first.cache_root
    assert second.documents == first.documents


@pytest.mark.parametrize("relative", ["module.yaml", "nested/child.yaml"])
def test_verified_oci_cache_source_graph_rejects_replacement_after_tree_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    bundle = _cache_graph_bundle()
    module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="verified-source-race",
        root_file="module.yaml",
        base_dir=tmp_path,
    )
    real_validate = module_registry_cache._validated_cache_root
    replaced = False

    def replace_after_validation(**kwargs):
        nonlocal replaced
        root = real_validate(**kwargs)
        if root is not None and not replaced:
            target = root.parent.joinpath(*PurePosixPath(relative).parts)
            payload = target.read_bytes()
            replacement = target.with_name(f".{target.name}.replacement")
            replacement.write_bytes(payload.replace(b"root", b"evil").replace(b"child", b"other"))
            replacement.chmod(stat.S_IMODE(target.stat().st_mode))
            os.replace(replacement, target)
            replaced = True
        return root

    monkeypatch.setattr(module_registry_cache, "_validated_cache_root", replace_after_validation)

    with pytest.raises(SDLParseError, match="cache tree failed integrity validation"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="verified-source-race",
            root_file="module.yaml",
            base_dir=tmp_path,
            source_options=DEFAULT_SOURCE_PARSE_OPTIONS,
        )

    assert replaced is True


def test_oci_cache_entry_is_bound_to_bundle_digest(tmp_path: Path):
    first_bundle = _cache_test_bundle(b"name: first\n")
    second_bundle = _cache_test_bundle(b"name: second\n")
    first_digest = f"sha256:{module_registry._sha256_digest(first_bundle)}"
    second_digest = f"sha256:{module_registry._sha256_digest(second_bundle)}"

    first = module_registry._extract_bundle_to_cache(
        bundle_bytes=first_bundle,
        manifest_digest="shared-manifest",
        content_digest=first_digest,
        root_file="module.yaml",
        base_dir=tmp_path,
    )
    assert first.read_bytes() == b"name: first\n"
    second = module_registry._extract_bundle_to_cache(
        bundle_bytes=second_bundle,
        manifest_digest="shared-manifest",
        content_digest=second_digest,
        root_file="module.yaml",
        base_dir=tmp_path,
    )

    assert second.read_bytes() == b"name: second\n"
    manifest = json.loads((second.parent / ".raes-cache-tree.json").read_text(encoding="utf-8"))
    assert manifest["content_digest"] == second_digest
    assert _current_version(_version_slot(second.parent)) == second.parent


def test_oci_cache_hit_hashes_bundle_without_extraction_or_version_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bundle = _cache_graph_bundle()
    first = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="streaming-hit",
        root_file="module.yaml",
        base_dir=tmp_path,
    )

    def forbidden(*args, **kwargs):
        del args, kwargs
        pytest.fail("a valid cache hit must not extract or stage a version")

    monkeypatch.setattr(tarfile.TarFile, "extractall", forbidden)
    monkeypatch.setattr(module_registry, "_new_version_stage", forbidden)
    monkeypatch.setattr(module_registry, "_install_version_directory", forbidden)

    second = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="streaming-hit",
        root_file="module.yaml",
        base_dir=tmp_path,
    )

    assert second == first
    assert len(list(first.parent.parent.iterdir())) == 1


def test_oci_cache_rejects_bundle_bytes_that_do_not_match_expected_digest(tmp_path: Path):
    bundle = _cache_test_bundle(b"name: mismatch\n")

    with pytest.raises(SDLParseError, match="expected content digest"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="mismatch",
            content_digest="sha256:" + "0" * 64,
            root_file="module.yaml",
            base_dir=tmp_path,
        )

    assert not (module_registry._oci_cache_dir(tmp_path) / "mismatch").exists()


def test_oci_cache_concurrent_writers_extract_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bundle = _cache_test_bundle(b"name: concurrent\n")
    digest = f"sha256:{module_registry._sha256_digest(bundle)}"
    barrier = threading.Barrier(2)
    commits = 0
    real_commit = module_registry._install_version_directory

    def counted_commit(**kwargs):
        nonlocal commits
        commits += 1
        return real_commit(**kwargs)

    monkeypatch.setattr(module_registry, "_install_version_directory", counted_commit)

    def resolve() -> bytes:
        barrier.wait(timeout=5)
        return module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="concurrent",
            content_digest=digest,
            root_file="module.yaml",
            base_dir=tmp_path,
        ).read_bytes()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: resolve(), range(2)))

    assert results == [b"name: concurrent\n", b"name: concurrent\n"]
    assert commits == 1
    versions = module_registry._oci_cache_dir(tmp_path) / "concurrent" / "versions"
    assert not list(versions.glob(".staged-*"))


def test_oci_cache_failed_pointer_preserves_prior_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    first_bundle = _cache_test_bundle(b"name: first\n")
    second_bundle = _cache_test_bundle(b"name: second\n")
    first_digest = f"sha256:{module_registry._sha256_digest(first_bundle)}"
    second_digest = f"sha256:{module_registry._sha256_digest(second_bundle)}"
    first = module_registry._extract_bundle_to_cache(
        bundle_bytes=first_bundle,
        manifest_digest="transaction",
        content_digest=first_digest,
        root_file="module.yaml",
        base_dir=tmp_path,
    )

    slot = _version_slot(first.parent)

    def fail_commit(**kwargs):
        raise SDLParseError("simulated cache transaction failure")

    monkeypatch.setattr(module_registry, "_write_version_pointer", fail_commit)
    with pytest.raises(SDLParseError, match="simulated cache transaction failure"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=second_bundle,
            manifest_digest="transaction",
            content_digest=second_digest,
            root_file="module.yaml",
            base_dir=tmp_path,
        )

    assert first.read_bytes() == b"name: first\n"
    assert (
        json.loads((first.parent / ".raes-cache-tree.json").read_text(encoding="utf-8"))["content_digest"]
        == first_digest
    )
    assert _current_version(slot) == first.parent
    assert not list((slot / "versions").glob(".staged-*"))


def test_oci_cache_prune_failure_cannot_advance_pointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    first_bundle = _cache_test_bundle(b"name: first\n")
    second_bundle = _cache_test_bundle(b"name: second\n")
    first = module_registry._extract_bundle_to_cache(
        bundle_bytes=first_bundle,
        manifest_digest="prune-order",
        root_file="module.yaml",
        base_dir=tmp_path,
    )
    slot = _version_slot(first.parent)

    def fail_prune(**kwargs):
        del kwargs
        raise SDLParseError("simulated cache prune failure")

    monkeypatch.setattr(module_registry, "_prune_version_directories", fail_prune)
    with pytest.raises(SDLParseError, match="simulated cache prune failure"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=second_bundle,
            manifest_digest="prune-order",
            root_file="module.yaml",
            base_dir=tmp_path,
        )

    assert _current_version(slot) == first.parent
    assert first.read_bytes() == b"name: first\n"


def test_oci_cache_invalid_archive_leaves_no_partial_entry(tmp_path: Path):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        good = tarfile.TarInfo(name="module.yaml")
        good_payload = b"name: partial\n"
        good.size = len(good_payload)
        archive.addfile(good, io.BytesIO(good_payload))
        bad = tarfile.TarInfo(name="../escape.yaml")
        bad_payload = b"escaped\n"
        bad.size = len(bad_payload)
        archive.addfile(bad, io.BytesIO(bad_payload))
    bundle = buffer.getvalue()
    content_digest = f"sha256:{module_registry._sha256_digest(bundle)}"

    with pytest.raises(SDLParseError, match="Path traversal"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="partial",
            content_digest=content_digest,
            root_file="module.yaml",
            base_dir=tmp_path,
        )

    cache_root = module_registry._oci_cache_dir(tmp_path)
    slot = cache_root / "partial"
    assert not (slot / ".raes-current").exists()
    assert not list((slot / "versions").iterdir())
    assert not (tmp_path / "escape.yaml").exists()


def test_oci_cache_rejects_invalid_manifest_cache_key(tmp_path: Path):
    bundle = _cache_test_bundle(b"name: invalid-key\n")
    with pytest.raises(SDLParseError, match="cache key"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="../escape",
            root_file="module.yaml",
            base_dir=tmp_path,
        )


def test_oci_cache_repairs_unreadable_tree_manifest(tmp_path: Path):
    bundle = _cache_test_bundle(b"name: marker\n")
    digest = f"sha256:{module_registry._sha256_digest(bundle)}"
    root = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="marker",
        content_digest=digest,
        root_file="module.yaml",
        base_dir=tmp_path,
    )
    (root.parent / ".raes-cache-tree.json").write_bytes(b"\xff")

    repaired = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="marker",
        content_digest=digest,
        root_file="module.yaml",
        base_dir=tmp_path,
    )

    assert repaired.read_bytes() == b"name: marker\n"
    assert repaired.parent != root.parent
    manifest = json.loads((repaired.parent / ".raes-cache-tree.json").read_text(encoding="utf-8"))
    assert manifest["content_digest"] == digest


def test_oci_cache_rejects_invalid_gzip_without_partial_entry(tmp_path: Path):
    payload = b"not a gzip tar"
    content_digest = f"sha256:{module_registry._sha256_digest(payload)}"
    with pytest.raises(SDLParseError, match="not a valid gzip-compressed tar archive"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=payload,
            manifest_digest="invalid-archive",
            content_digest=content_digest,
            root_file="module.yaml",
            base_dir=tmp_path,
        )

    slot = module_registry._oci_cache_dir(tmp_path) / "invalid-archive"
    assert not (slot / ".raes-current").exists()
    assert not list((slot / "versions").iterdir())


def test_oci_cache_detects_noncommitting_transaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bundle = _cache_test_bundle(b"name: no-commit\n")
    digest = f"sha256:{module_registry._sha256_digest(bundle)}"
    monkeypatch.setattr(
        module_registry,
        "_install_version_directory",
        lambda *, versions, **kwargs: versions / "missing",
    )

    with pytest.raises(SDLParseError, match="failed validation"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="no-commit",
            content_digest=digest,
            root_file="module.yaml",
            base_dir=tmp_path,
        )

    versions = module_registry._oci_cache_dir(tmp_path) / "no-commit" / "versions"
    assert not list(versions.glob(".staged-*"))


@pytest.mark.parametrize("tamper", ["content", "mode", "type", "missing", "extra", "symlink"])
def test_oci_cache_hit_revalidates_complete_extracted_tree(tmp_path: Path, tamper: str):
    bundle = _cache_graph_bundle()
    digest = f"sha256:{module_registry._sha256_digest(bundle)}"
    root = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest=f"tree-{tamper}",
        content_digest=digest,
        root_file="module.yaml",
        base_dir=tmp_path,
    )
    version = root.parent
    child = version / "nested" / "child.yaml"
    completion = version / ".raes-cache-tree.json"
    retained_completion = completion.read_bytes()

    if tamper == "content":
        child.write_bytes(b"name: modified\n")
    elif tamper == "mode":
        if os.name == "nt":
            os.chmod(child, stat.S_IREAD)
        else:
            os.chmod(child, stat.S_IMODE(child.stat().st_mode) ^ 0o100)
    elif tamper == "type":
        child.unlink()
        child.mkdir()
    elif tamper == "missing":
        child.unlink()
    elif tamper == "extra":
        (version / "extra.yaml").write_text("name: extra\n", encoding="utf-8")
    else:
        outside = tmp_path / "outside.yaml"
        outside.write_text("name: outside\n", encoding="utf-8")
        child.unlink()
        try:
            child.symlink_to(outside)
        except OSError:
            pytest.skip("symlink creation is unavailable")

    assert completion.read_bytes() == retained_completion
    repaired = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest=f"tree-{tamper}",
        content_digest=digest,
        root_file="module.yaml",
        base_dir=tmp_path,
    )

    assert repaired.parent != version
    assert (repaired.parent / "nested" / "child.yaml").read_bytes() == b"name: child\n"
    manifest = json.loads((repaired.parent / ".raes-cache-tree.json").read_text(encoding="utf-8"))
    entries = {entry["path"]: entry for entry in manifest["entries"]}
    assert entries["nested"]["type"] == "directory"
    assert entries["nested/child.yaml"]["digest"].startswith("sha256:")
    assert entries["nested/child.yaml"]["mode"] == (repaired.parent / "nested" / "child.yaml").stat().st_mode & 0o777


@pytest.mark.parametrize("forgery", ["content", "directory-mode"])
def test_oci_cache_rejects_tree_and_manifest_forged_together(tmp_path: Path, forgery: str):
    bundle = _cache_graph_bundle() if forgery == "directory-mode" else _cache_test_bundle(b"name: authentic\n")
    digest = f"sha256:{module_registry._sha256_digest(bundle)}"
    root = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="coordinated-forgery",
        content_digest=digest,
        root_file="module.yaml",
        base_dir=tmp_path,
    )
    forged_version = root.parent
    authentic_root = root.read_bytes()
    if forgery == "content":
        root.write_bytes(b"name: forged\n")
    else:
        if os.name == "nt":
            pytest.skip("Windows does not expose mutable directory permission bits")
        directory = forged_version / "nested"
        directory.chmod(stat.S_IMODE(directory.stat().st_mode) ^ 0o020)
    forged_manifest = module_registry._cache_tree_manifest(
        root=forged_version,
        content_digest=digest,
        root_file="module.yaml",
    )
    (forged_version / ".raes-cache-tree.json").write_bytes(module_registry._canonical_json_bytes(forged_manifest))

    repaired = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="coordinated-forgery",
        content_digest=digest,
        root_file="module.yaml",
        base_dir=tmp_path,
    )

    assert repaired.parent != forged_version
    assert repaired.read_bytes() == authentic_root


@pytest.mark.parametrize(
    "corruption",
    ["malformed", "deep", "integer", "shape", "noncanonical", "tree-digest", "entry-mode"],
)
def test_oci_cache_rebuilds_for_invalid_completion_manifest(tmp_path: Path, corruption: str):
    bundle = _cache_graph_bundle()
    root = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest=f"completion-{corruption}",
        root_file="module.yaml",
        base_dir=tmp_path,
    )
    completion = root.parent / ".raes-cache-tree.json"
    manifest = json.loads(completion.read_text(encoding="utf-8"))
    if corruption == "malformed":
        completion.write_bytes(b"{")
    elif corruption == "deep":
        completion.write_bytes(b'{"entries":' + b"[" * 10_000 + b"]" * 10_000 + b"}")
    elif corruption == "integer":
        completion.write_bytes(b'{"integer":' + b"9" * 10_000 + b"}")
    elif corruption == "shape":
        completion.write_bytes(module_registry._canonical_json_bytes({"schema": "wrong"}))
    elif corruption == "noncanonical":
        completion.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    elif corruption == "tree-digest":
        manifest["tree_digest"] = "sha256:" + "0" * 64
        completion.write_bytes(module_registry._canonical_json_bytes(manifest))
    else:
        manifest["entries"][0]["mode"] ^= 0o100
        manifest["tree_digest"] = (
            f"sha256:{module_registry._sha256_digest(module_registry._canonical_json_bytes(manifest['entries']))}"
        )
        completion.write_bytes(module_registry._canonical_json_bytes(manifest))

    repaired = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest=f"completion-{corruption}",
        root_file="module.yaml",
        base_dir=tmp_path,
    )

    assert repaired.parent != root.parent
    assert repaired.read_bytes().startswith(b"name: root")


def test_oci_cache_repairs_missing_pointer_and_crash_residue(tmp_path: Path):
    bundle = _cache_test_bundle(b"name: recoverable\n")
    root = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="recover-pointer",
        root_file="module.yaml",
        base_dir=tmp_path,
    )
    slot = _version_slot(root.parent)
    (slot / ".raes-current").unlink()
    abandoned_version_stage = slot / "versions" / ".staged-abandoned"
    abandoned_version_stage.mkdir()
    (abandoned_version_stage / "partial").write_text("partial\n", encoding="utf-8")
    (slot / ".raes-current.staged-abandoned").write_text("partial\n", encoding="utf-8")

    repaired = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="recover-pointer",
        root_file="module.yaml",
        base_dir=tmp_path,
    )

    assert repaired == root
    assert _current_version(slot) == root.parent
    assert not abandoned_version_stage.exists()
    assert not list(slot.glob(".raes-current.staged-*"))


def test_oci_cache_old_reader_remains_valid_while_pointer_advances(tmp_path: Path):
    first_bundle = _cache_test_bundle(b"name: first\n")
    second_bundle = _cache_test_bundle(b"name: second\n")
    first = module_registry._extract_bundle_to_cache(
        bundle_bytes=first_bundle,
        manifest_digest="reader-writer",
        root_file="module.yaml",
        base_dir=tmp_path,
    )
    barrier = threading.Barrier(2)

    def read_prior() -> bytes:
        barrier.wait(timeout=5)
        return first.read_bytes()

    def publish_next() -> Path:
        barrier.wait(timeout=5)
        return module_registry._extract_bundle_to_cache(
            bundle_bytes=second_bundle,
            manifest_digest="reader-writer",
            root_file="module.yaml",
            base_dir=tmp_path,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        prior_future = executor.submit(read_prior)
        next_future = executor.submit(publish_next)
        assert prior_future.result(timeout=5) == b"name: first\n"
        second = next_future.result(timeout=5)

    assert first.read_bytes() == b"name: first\n"
    assert second.read_bytes() == b"name: second\n"
    assert _current_version(_version_slot(second.parent)) == second.parent


def test_oci_cache_version_retention_is_bounded_and_preserves_immediate_prior_reader(tmp_path: Path):
    resolved: list[Path] = []
    for revision in range(module_registry_filesystem._MAX_RETAINED_VERSIONS + 3):
        bundle = _cache_test_bundle(f"name: revision-{revision}\n".encode())
        resolved.append(
            module_registry._extract_bundle_to_cache(
                bundle_bytes=bundle,
                manifest_digest="bounded-retention",
                root_file="module.yaml",
                base_dir=tmp_path,
            )
        )

    current = resolved[-1]
    prior = resolved[-2]
    versions = _version_slot(current.parent) / "versions"
    assert len(list(versions.iterdir())) == module_registry_filesystem._MAX_RETAINED_VERSIONS
    assert current.read_text(encoding="utf-8") == (
        f"name: revision-{module_registry_filesystem._MAX_RETAINED_VERSIONS + 2}\n"
    )
    assert prior.read_text(encoding="utf-8") == (
        f"name: revision-{module_registry_filesystem._MAX_RETAINED_VERSIONS + 1}\n"
    )
    assert _current_version(_version_slot(current.parent)) == current.parent


def test_oci_cache_tree_inventory_enforces_limits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    limits = module_registry._OCI_LIMITS
    root = tmp_path / "tree"
    root.mkdir()
    (root / "first").write_bytes(b"1234")
    (root / "second").write_bytes(b"5678")
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(limits, max_member_bytes=4, max_total_bytes=7),
    )
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._cache_tree_entries(root)

    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(limits, max_bundle_members=-1),
    )
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._cache_tree_entries(root)

    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(limits, max_member_bytes=3, max_total_bytes=100),
    )
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._cache_tree_entries(root)

    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(
            limits,
            max_member_bytes=100,
            max_total_bytes=100,
            max_bundle_members=1,
        ),
    )
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._cache_tree_entries(root)


@pytest.mark.parametrize("last_entry", ["file", "directory"])
def test_oci_cache_tree_inventory_counts_nested_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    last_entry: str,
):
    root = tmp_path / "tree"
    (root / "a").mkdir(parents=True)
    (root / "a" / "child").write_bytes(b"x")
    if last_entry == "file":
        (root / "z").write_bytes(b"z")
    else:
        (root / "z").mkdir()
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(module_registry._OCI_LIMITS, max_bundle_members=2),
    )

    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._cache_tree_entries(root)


def test_oci_cache_tree_inventory_rejects_special_file(tmp_path: Path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is unavailable")
    root = tmp_path / "tree"
    root.mkdir()
    os.mkfifo(root / "pipe")

    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._cache_tree_entries(root)


def test_oci_cache_manifest_size_and_reserved_path_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "tree"
    root.mkdir()
    (root / "module.yaml").write_text("name: module\n", encoding="utf-8")
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(module_registry._OCI_LIMITS, max_metadata_bytes=1),
    )
    with pytest.raises(SDLParseError, match="metadata limit"):
        module_registry._write_cache_tree_manifest(
            root=root,
            content_digest="sha256:" + "0" * 64,
            root_file="module.yaml",
        )

    (root / ".raes-cache-tree.json").write_text("occupied\n", encoding="utf-8")
    with pytest.raises(SDLParseError, match="reserved cache metadata"):
        module_registry._write_cache_tree_manifest(
            root=root,
            content_digest="sha256:" + "0" * 64,
            root_file="module.yaml",
        )


def test_oci_cache_manifest_io_failures_are_bounded_and_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manifest = tmp_path / "manifest"
    manifest.mkdir()
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._read_cache_manifest_bytes(manifest)

    manifest.rmdir()
    manifest.write_bytes(b"xx")
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(module_registry._OCI_LIMITS, max_metadata_bytes=1),
    )
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._read_cache_manifest_bytes(manifest)

    root = tmp_path / "tree"
    root.mkdir()
    (root / "module.yaml").write_text("name: module\n", encoding="utf-8")
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(module_registry._OCI_LIMITS, max_metadata_bytes=1024),
    )
    real_write_bytes = Path.write_bytes

    def fail_manifest_write(path: Path, payload: bytes):
        if path.name == ".raes-cache-tree.json":
            raise OSError("SECRET-WRITE-DETAIL")
        return real_write_bytes(path, payload)

    monkeypatch.setattr(Path, "write_bytes", fail_manifest_write)
    with pytest.raises(SDLParseError) as exc_info:
        module_registry._write_cache_tree_manifest(
            root=root,
            content_digest="sha256:" + "0" * 64,
            root_file="module.yaml",
        )
    assert str(exc_info.value) == "Unable to write the OCI module cache integrity manifest"


def test_oci_cache_manifest_rejects_open_and_identity_races(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manifest = tmp_path / "manifest"
    manifest.write_text("{}\n", encoding="utf-8")
    real_open = module_registry.os.open

    def fail_open(path, flags):
        if Path(path) == manifest:
            raise OSError("SECRET-OPEN-DETAIL")
        return real_open(path, flags)

    monkeypatch.setattr(module_registry.os, "open", fail_open)
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._read_cache_manifest_bytes(manifest)

    monkeypatch.undo()
    directory_stat = tmp_path.stat()
    monkeypatch.setattr(module_registry.os, "fstat", lambda descriptor: directory_stat)
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._read_cache_manifest_bytes(manifest)

    monkeypatch.undo()

    def fail_fdopen(*args, **kwargs):
        del args, kwargs
        raise OSError("SECRET-FDOPEN-DETAIL")

    monkeypatch.setattr(module_registry.os, "fdopen", fail_fdopen)
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._read_cache_manifest_bytes(manifest)


def test_oci_cache_tree_translates_missing_and_scan_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._cache_tree_entries(tmp_path / "missing")

    root = tmp_path / "tree"
    root.mkdir()
    real_scandir = module_registry.os.scandir

    def fail_scandir(path):
        if Path(path) == root:
            raise OSError("SECRET-SCAN-DETAIL")
        return real_scandir(path)

    monkeypatch.setattr(module_registry.os, "scandir", fail_scandir)
    with pytest.raises(SDLParseError) as exc_info:
        module_registry._cache_tree_entries(root)
    assert str(exc_info.value) == "OCI module cache tree failed integrity validation"


@pytest.mark.parametrize("race", ["missing", "mode"])
def test_oci_cache_tree_detects_directory_race(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, race: str):
    root = tmp_path / "tree"
    root.mkdir()
    original = root.lstat()
    calls = 0
    real_lstat = Path.lstat

    def race_lstat(path: Path):
        nonlocal calls
        if path != root:
            return real_lstat(path)
        calls += 1
        if calls == 1:
            return original
        if race == "missing":
            raise OSError("SECRET-RACE-DETAIL")
        changed = list(original)
        changed[0] ^= 0o100
        return os.stat_result(changed)

    monkeypatch.setattr(Path, "lstat", race_lstat)
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._cache_tree_entries(root)


def test_oci_cache_file_open_and_identity_failures_are_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    existing = tmp_path / "existing"
    existing.write_text("data\n", encoding="utf-8")
    expected = existing.lstat()
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._hash_cache_file(tmp_path / "missing", expected)

    different_values = list(expected)
    different_values[2] = expected.st_dev + 1
    different = os.stat_result(different_values)
    assert not module_registry._same_file_identity(expected, different)


def test_oci_cache_file_hash_detects_fstat_read_and_size_races(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "file"
    path.write_bytes(b"1234")
    expected = path.lstat()
    directory_stat = tmp_path.stat()
    monkeypatch.setattr(module_registry.os, "fstat", lambda descriptor: directory_stat)
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._hash_cache_file(path, expected)

    monkeypatch.undo()
    real_fstat = module_registry.os.fstat

    def fail_fstat(descriptor: int):
        del descriptor
        raise OSError("SECRET-FSTAT-DETAIL")

    monkeypatch.setattr(module_registry.os, "fstat", fail_fstat)
    with pytest.raises(SDLParseError) as exc_info:
        module_registry._hash_cache_file(path, expected)
    assert str(exc_info.value) == "OCI module cache tree failed integrity validation"

    monkeypatch.undo()
    truncated = False

    def truncate_after_stat(descriptor: int):
        nonlocal truncated
        result = real_fstat(descriptor)
        if not truncated:
            truncated = True
            path.write_bytes(b"")
        return result

    monkeypatch.setattr(module_registry.os, "fstat", truncate_after_stat)
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._hash_cache_file(path, expected)

    monkeypatch.undo()

    def fail_fdopen(*args, **kwargs):
        del args, kwargs
        raise OSError("SECRET-FDOPEN-DETAIL")

    monkeypatch.setattr(module_registry.os, "fdopen", fail_fdopen)
    expected = path.lstat()
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._hash_cache_file(path, expected)


def test_oci_cache_file_hash_detects_growth_after_fstat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "file"
    path.write_bytes(b"1234")
    expected = path.lstat()
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(module_registry._OCI_LIMITS, max_member_bytes=4),
    )
    real_fstat = module_registry.os.fstat
    grown = False

    def grow_after_stat(descriptor: int):
        nonlocal grown
        result = real_fstat(descriptor)
        if not grown:
            grown = True
            with path.open("ab") as handle:
                handle.write(b"5")
        return result

    monkeypatch.setattr(module_registry.os, "fstat", grow_after_stat)
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._hash_cache_file(path, expected)


def test_oci_cache_rejects_valid_manifest_without_declared_root(tmp_path: Path):
    version = tmp_path / "version"
    version.mkdir()
    (version / "different.yaml").write_text("name: different\n", encoding="utf-8")
    expected_manifest = module_registry._cache_tree_manifest(
        root=version,
        content_digest="sha256:" + "0" * 64,
        root_file="module.yaml",
    )
    module_registry._write_cache_tree_manifest(
        root=version,
        content_digest="sha256:" + "0" * 64,
        root_file="module.yaml",
    )

    assert (
        module_registry._validated_cache_root(
            version=version,
            expected_manifest=expected_manifest,
            root_relative=module_registry.PurePosixPath("module.yaml"),
        )
        is None
    )


def test_oci_cache_rejects_invalid_trusted_manifest_shape_and_tree_digest(tmp_path: Path):
    version = tmp_path / "version"
    version.mkdir()
    (version / "module.yaml").write_text("name: module\n", encoding="utf-8")
    valid = module_registry._cache_tree_manifest(
        root=version,
        content_digest="sha256:" + "0" * 64,
        root_file="module.yaml",
    )
    manifest_path = version / ".raes-cache-tree.json"

    assert (
        module_registry._validated_cache_root(
            version=version,
            expected_manifest={},
            root_relative=module_registry.PurePosixPath("module.yaml"),
        )
        is None
    )

    invalid_schema = {**valid, "schema": "wrong"}
    manifest_path.write_bytes(module_registry._canonical_json_bytes(invalid_schema))
    assert (
        module_registry._validated_cache_root(
            version=version,
            expected_manifest=invalid_schema,
            root_relative=module_registry.PurePosixPath("module.yaml"),
        )
        is None
    )

    manifest_path.write_bytes(module_registry._canonical_json_bytes(invalid_schema))
    assert (
        module_registry._validated_cache_root(
            version=version,
            expected_manifest=valid,
            root_relative=module_registry.PurePosixPath("module.yaml"),
        )
        is None
    )

    invalid_digest = {**valid, "tree_digest": "sha256:" + "f" * 64}
    manifest_path.write_bytes(module_registry._canonical_json_bytes(invalid_digest))
    assert (
        module_registry._validated_cache_root(
            version=version,
            expected_manifest=invalid_digest,
            root_relative=module_registry.PurePosixPath("module.yaml"),
        )
        is None
    )


@pytest.mark.parametrize(
    "entries",
    [
        [None],
        [{"path": "entry", "type": "special"}],
        [{"path": "entry", "type": "file", "digest": "sha256:0", "mode": 0}],
    ],
)
def test_oci_cache_trusted_inventory_projection_rejects_invalid_entries(entries: list[object]):
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._trusted_entry_projection(entries)


def test_oci_cache_staging_validation_failure_cleans_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bundle = _cache_test_bundle(b"name: invalid-stage\n")
    monkeypatch.setattr(module_registry, "_validated_cache_root", lambda **kwargs: None)

    with pytest.raises(SDLParseError, match="Staged OCI module cache entry failed validation"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="invalid-stage",
            root_file="module.yaml",
            base_dir=tmp_path,
        )

    versions = module_registry._oci_cache_dir(tmp_path) / "invalid-stage" / "versions"
    assert not list(versions.iterdir())


def test_oci_cache_creation_failure_is_stable(tmp_path: Path):
    occupied = tmp_path / "occupied"
    occupied.write_text("not a directory\n", encoding="utf-8")
    bundle = _cache_test_bundle(b"name: blocked\n")

    with pytest.raises(SDLParseError, match="Unable to create the OCI module cache"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="blocked",
            root_file="module.yaml",
            base_dir=occupied,
        )


def test_oci_cache_lock_open_failure_is_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    lock_path = tmp_path / "locks" / "entry.lock"
    real_open = os.open

    def fail_lock_open(path, *args, **kwargs):
        if Path(path) in {lock_path, Path(lock_path.name)}:
            raise OSError("SECRET-LOCK-DETAIL")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", fail_lock_open)

    with pytest.raises(SDLParseError) as exc_info, module_registry._cache_entry_lock(lock_path):
        pass

    assert str(exc_info.value) == "Unable to open the OCI module cache lock"


def test_oci_cache_lock_rejects_identity_and_fdopen_races(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    lock_parent = tmp_path / "locks"
    lock_parent.mkdir()
    lock_path = lock_parent / "entry.lock"
    lock_path.write_bytes(b"")
    directory_stat = lock_parent.stat()
    monkeypatch.setattr(module_registry.os, "fstat", lambda descriptor: directory_stat)
    with pytest.raises(SDLParseError, match="Unable to open the OCI module cache lock"):
        module_registry._open_cache_lock(lock_path)

    monkeypatch.undo()

    def fail_fdopen(*args, **kwargs):
        del args, kwargs
        raise OSError("SECRET-FDOPEN-DETAIL")

    monkeypatch.setattr(module_registry.os, "fdopen", fail_fdopen)
    with pytest.raises(SDLParseError) as exc_info:
        module_registry._open_cache_lock(lock_path)
    assert str(exc_info.value) == "Unable to open the OCI module cache lock"


def test_oci_cache_lock_rechecks_parent_type_and_descriptor_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    occupied_parent = tmp_path / "occupied"
    occupied_parent.write_bytes(b"")
    monkeypatch.setattr(module_registry_cache, "_require_directory", lambda *args, **kwargs: None)
    with pytest.raises(SDLParseError, match="Unable to open the OCI module cache lock"):
        module_registry_cache._open_cache_lock(occupied_parent / "entry.lock")

    monkeypatch.undo()
    if not module_registry_cache._LOCK_DIR_FD_SUPPORTED:
        pytest.skip("parent descriptor identity is unavailable")
    lock_parent = tmp_path / "locks"
    lock_parent.mkdir()
    monkeypatch.setattr(module_registry_cache.os, "fstat", lambda descriptor: tmp_path.stat())
    with pytest.raises(SDLParseError, match="Unable to open the OCI module cache lock"):
        module_registry_cache._open_cache_lock(lock_parent / "entry.lock")


@pytest.mark.parametrize("linked_component", ["metadata", "cache"])
def test_oci_cache_rejects_linked_cache_root_without_writing_target(tmp_path: Path, linked_component: str):
    outside = tmp_path / "outside-cache"
    outside.mkdir()
    metadata = tmp_path / ".raes"
    try:
        if linked_component == "metadata":
            metadata.symlink_to(outside, target_is_directory=True)
        else:
            metadata.mkdir()
            (metadata / "module-cache").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    bundle = _cache_test_bundle(b"name: blocked\n")
    with pytest.raises(SDLParseError, match="Unable to create the OCI module cache"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="linked-root",
            root_file="module.yaml",
            base_dir=tmp_path,
        )

    assert not list(outside.iterdir())


def test_oci_cache_rejects_linked_real_lock_parent_without_writing_target(tmp_path: Path):
    cache_root = module_registry._oci_cache_dir(tmp_path)
    cache_root.mkdir(parents=True)
    outside = tmp_path / "outside-locks"
    outside.mkdir()
    try:
        (cache_root / ".locks").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    bundle = _cache_test_bundle(b"name: blocked\n")
    with pytest.raises(SDLParseError, match="Unable to open the OCI module cache lock"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="linked-lock-parent",
            root_file="module.yaml",
            base_dir=tmp_path,
        )

    assert not list(outside.iterdir())


def test_oci_cache_lock_rejects_linked_parent_and_file(tmp_path: Path):
    outside = tmp_path / "outside-locks"
    outside.mkdir()
    linked_parent = tmp_path / "linked-locks"
    try:
        linked_parent.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with (
        pytest.raises(SDLParseError, match="Unable to open the OCI module cache lock"),
        module_registry._cache_entry_lock(linked_parent / "entry.lock"),
    ):
        pytest.fail("a linked lock parent must not be entered")
    assert not (outside / "entry.lock").exists()

    real_parent = tmp_path / "real-locks"
    real_parent.mkdir()
    outside_file = tmp_path / "outside-file"
    outside_file.write_bytes(b"")
    (real_parent / "entry.lock").symlink_to(outside_file)
    with (
        pytest.raises(SDLParseError, match="Unable to open the OCI module cache lock"),
        module_registry._cache_entry_lock(real_parent / "entry.lock"),
    ):
        pytest.fail("a linked lock file must not be entered")
    assert outside_file.read_bytes() == b""


def test_oci_cache_lock_parent_swap_cannot_escape_anchored_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    if not module_registry_cache._LOCK_DIR_FD_SUPPORTED:
        pytest.skip("anchored openat is unavailable")
    lock_parent = tmp_path / "locks"
    lock_parent.mkdir()
    moved_parent = tmp_path / "moved-locks"
    outside = tmp_path / "outside-locks"
    outside.mkdir()
    lock_path = lock_parent / "entry.lock"
    real_open = module_registry_cache.os.open
    swapped = False

    def swap_parent_before_lock_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if Path(path) == Path(lock_path.name) and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            lock_parent.rename(moved_parent)
            lock_parent.symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module_registry_cache.os, "open", swap_parent_before_lock_open)
    with (
        pytest.raises(SDLParseError, match="Unable to open the OCI module cache lock"),
        module_registry._cache_entry_lock(lock_path),
    ):
        pytest.fail("a replaced lock parent must not be entered")

    assert swapped
    assert not (outside / "entry.lock").exists()
    assert (moved_parent / "entry.lock").is_file()


def test_oci_cache_lock_parent_identity_fallback_is_rechecked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    lock_path = tmp_path / "locks" / "entry.lock"
    monkeypatch.setattr(module_registry_cache, "_LOCK_DIR_FD_SUPPORTED", False)

    handle = module_registry_cache._open_cache_lock(lock_path)
    handle.close()

    assert lock_path.is_file()


@pytest.mark.parametrize("anchored_parent", [True, False])
def test_oci_cache_lock_reopens_peer_created_regular_file_after_exclusive_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    anchored_parent: bool,
):
    lock_parent = tmp_path / "locks"
    lock_parent.mkdir()
    lock_path = lock_parent / "entry.lock"
    real_open = module_registry_cache.os.open
    collided = False
    if not anchored_parent:
        monkeypatch.setattr(module_registry_cache, "_LOCK_DIR_FD_SUPPORTED", False)

    def create_as_peer_then_report_collision(path, flags, *args, **kwargs):
        nonlocal collided
        if flags & os.O_EXCL and not collided:
            collided = True
            descriptor = real_open(path, flags, *args, **kwargs)
            os.close(descriptor)
            raise FileExistsError("simulated concurrent lock creation")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module_registry_cache.os, "open", create_as_peer_then_report_collision)

    handle = module_registry_cache._open_cache_lock(lock_path)
    handle.close()

    assert collided is True
    assert lock_path.is_file()


def test_oci_cache_lock_rejects_peer_created_link_after_exclusive_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    lock_parent = tmp_path / "locks"
    lock_parent.mkdir()
    lock_path = lock_parent / "entry.lock"
    outside = tmp_path / "outside.lock"
    outside.write_bytes(b"")
    real_open = module_registry_cache.os.open
    collided = False
    monkeypatch.setattr(module_registry_cache, "_LOCK_DIR_FD_SUPPORTED", False)

    def create_link_as_peer_then_report_collision(path, flags, *args, **kwargs):
        nonlocal collided
        if flags & os.O_EXCL and not collided:
            collided = True
            Path(path).symlink_to(outside)
            raise FileExistsError("simulated concurrent linked lock creation")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module_registry_cache.os, "open", create_link_as_peer_then_report_collision)

    with pytest.raises(SDLParseError, match="Unable to open the OCI module cache lock"):
        module_registry_cache._open_cache_lock(lock_path)

    assert collided is True
    assert lock_path.is_symlink()
    assert outside.read_bytes() == b""


def test_oci_cache_lock_rejects_fifo_without_blocking(tmp_path: Path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is unavailable")
    lock_parent = tmp_path / "locks"
    lock_parent.mkdir()
    lock_path = lock_parent / "entry.lock"
    os.mkfifo(lock_path)

    with (
        pytest.raises(SDLParseError, match="Unable to open the OCI module cache lock"),
        module_registry._cache_entry_lock(lock_path),
    ):
        pytest.fail("a FIFO lock must not be entered")


def test_oci_cache_lock_closes_handle_when_acquisition_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    lock_path = tmp_path / "locks" / "entry.lock"

    def fail_acquire(handle):
        assert not handle.closed
        raise SDLParseError("simulated acquisition failure")

    monkeypatch.setattr(module_registry, "_acquire_file_lock", fail_acquire)

    with (
        pytest.raises(SDLParseError, match="simulated acquisition failure"),
        module_registry._cache_entry_lock(lock_path),
    ):
        pytest.fail("an unacquired lock must not yield")

    assert lock_path.is_file()


def test_oci_cache_windows_lock_backend_is_exercised_without_platform_exclusion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[int] = []

    class FakeMSVCRT:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @staticmethod
        def locking(descriptor: int, operation: int, length: int) -> None:
            assert descriptor >= 0
            assert length == 1
            calls.append(operation)

    lock_path = tmp_path / "windows.lock"
    lock_path.write_bytes(b"")
    monkeypatch.setitem(sys.modules, "msvcrt", FakeMSVCRT)
    monkeypatch.setattr(module_registry_cache, "_WINDOWS_LOCKING", True)

    with lock_path.open("r+b") as handle:
        module_registry_cache._acquire_file_lock(handle)
        module_registry_cache._release_file_lock(handle)
        module_registry_cache._acquire_file_lock(handle)
        module_registry_cache._release_file_lock(handle)

    assert lock_path.read_bytes() == b"\0"
    assert calls == [FakeMSVCRT.LK_NBLCK, FakeMSVCRT.LK_UNLCK, FakeMSVCRT.LK_NBLCK, FakeMSVCRT.LK_UNLCK]


def test_oci_cache_lock_timeout_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    if os.name == "nt":
        pytest.skip("POSIX lock contention seam")
    import fcntl

    times = iter((0.0, 0.5, 2.0))
    sleeps: list[float] = []
    monkeypatch.setattr(module_registry.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(module_registry.time, "sleep", sleeps.append)
    monkeypatch.setattr(
        module_registry, "_OCI_LIMITS", dataclasses.replace(module_registry._OCI_LIMITS, timeout_seconds=1)
    )
    monkeypatch.setattr(fcntl, "flock", lambda *args, **kwargs: (_ for _ in ()).throw(BlockingIOError()))

    with (tmp_path / "lock").open("a+b") as handle, pytest.raises(SDLParseError, match="Timed out"):
        module_registry._acquire_file_lock(handle)

    assert sleeps == [0.01]


def test_oci_import_composes_verified_root_and_nested_sources_after_cache_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_bytes = b"""name: remote-root
version: 1.0.0
module: {id: acme/shared, version: 1.0.0, exports: {nodes: [child.vm], infrastructure: [child.vm]}}
imports:
  - {source: local:nested/child.yaml, namespace: child}
"""
    child_bytes = b"""name: child
version: 1.0.0
module: {id: acme/child, version: 1.0.0, exports: {nodes: [vm], infrastructure: [vm]}}
nodes: {vm: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}}
infrastructure: {vm: 1}
"""
    bundle = _gzip_tar([("module.yaml", root_bytes), ("nested/child.yaml", child_bytes)]).getvalue()
    content_digest = f"sha256:{module_registry._sha256_digest(bundle)}"
    manifest_digest = "sha256:" + "a" * 64
    descriptor = {
        "id": "acme/shared",
        "version": "1.0.0",
        "exports": {"nodes": ["child.vm"], "infrastructure": ["child.vm"]},
    }
    monkeypatch.setattr(
        module_registry_resolution,
        "_resolve_oci_manifest",
        lambda **_kwargs: (manifest_digest, {}),
    )
    monkeypatch.setattr(
        module_registry_resolution,
        "_resolve_oci_config",
        lambda **_kwargs: ({"module": descriptor, "root_file": "module.yaml"}, content_digest),
    )
    monkeypatch.setattr(module_registry_resolution, "_fetch_oci_bundle", lambda **_kwargs: bundle)
    real_extract = module_registry._extract_bundle_to_cache
    tampered_roots: list[Path] = []

    def replace_after_capture(**kwargs):
        sources = real_extract(**kwargs)
        assert isinstance(sources, module_registry._VerifiedSourceBundle)
        tampered_roots.append(sources.cache_root)
        (sources.cache_root / "module.yaml").write_text("name: replaced-root\n", encoding="utf-8")
        (sources.cache_root / "nested" / "child.yaml").write_text("name: replaced-child\n", encoding="utf-8")
        for directory in (sources.cache_root, sources.cache_root / "nested"):
            (directory / module_registry.TRUST_POLICY_NAME).write_text("not: [valid\n", encoding="utf-8")
            (directory / module_registry.LOCKFILE_NAME).write_text("{not-json", encoding="utf-8")
        return sources

    monkeypatch.setattr(module_registry, "_extract_bundle_to_cache", replace_after_capture)
    _write(
        tmp_path / module_registry.TRUST_POLICY_NAME,
        """
        schema_version: raes-trust/v1
        registries:
          registry.example: {require_signatures: false}
        """,
    )
    root = _root_import(
        tmp_path / "root.yaml",
        "source: oci:registry.example/acme/shared\n            namespace: remote",
    )

    scenario = parse_sdl_file(root)

    assert set(scenario.nodes) == {"remote.child.vm"}
    assert tampered_roots
    tampered_child = tampered_roots[0] / "nested" / "child.yaml"
    assert tampered_child.read_text(encoding="utf-8") == "name: replaced-child\n"
    provenance = {entry.namespace: entry for entry in scenario.expansion_provenance.imports}
    assert provenance[("remote",)].content_digest == content_digest
    assert provenance[("remote",)].manifest_digest == manifest_digest
    assert provenance[("remote", "child")].content_digest == (f"sha256:{module_registry._sha256_digest(child_bytes)}")


@pytest.mark.integration
def test_signed_oci_import_resolution_and_publish_cli(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    runner = CliRunner()

    private_key = Ed25519PrivateKey.generate()
    private_key_path = tmp_path / "signing-key.pem"
    private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    publish = runner.invoke(
        app,
        [
            "sdl",
            "publish",
            str(module_path),
            "--output-dir",
            str(tmp_path / "dist"),
            "--signer-id",
            "test-signer",
            "--private-key",
            str(private_key_path),
        ],
    )
    assert publish.exit_code == 0, publish.output
    publish_payload = json.loads(publish.stdout)
    layout_dir = Path(publish_payload["layout_dir"])

    with _OCIRegistry(layout_dir, repo="acme/shared") as registry:
        _write(
            tmp_path / "raes-trust.yaml",
            f"""
            schema_version: raes-trust/v1
            registries:
              "127.0.0.1:{registry.port}":
                require_signatures: true
                allow_insecure_http: true
                trusted_signers:
                  test-signer: "{base64.b64encode(public_key).decode("utf-8")}"
            """,
        )
        root = _root_import(
            tmp_path / "root-oci.yaml",
            f"source: oci:127.0.0.1:{registry.port}/acme/shared\n            namespace: shared\n            version: '>=1.0,<2.0'",
        )
        resolve = runner.invoke(app, ["sdl", "resolve", str(root)])
        assert resolve.exit_code == 0, resolve.output

        lockfile = load_lockfile(tmp_path)
        assert lockfile is not None
        assert lockfile.imports[0].module_version == "1.2.3"

        locked = _root_import(
            tmp_path / "root-locked.yaml",
            f"source: locked:{lockfile.imports[0].resolved_source}\n            namespace: shared",
        )
        remote_model = compile_runtime_model(parse_sdl_file(root))
        locked_model = compile_runtime_model(parse_sdl_file(locked))

        assert (
            remote_model.node_deployments.keys() == locked_model.node_deployments.keys() == {"provision.node.shared.vm"}
        )


@pytest.mark.integration
def test_untrusted_and_unsigned_oci_imports_fail_closed(tmp_path: Path):
    module_path = _local_module(tmp_path / "shared.yaml")
    unsigned = publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")
    layout_dir = Path(unsigned["layout_dir"])

    with _OCIRegistry(layout_dir, repo="acme/shared") as registry:
        root = _root_import(
            tmp_path / "root-oci.yaml",
            f"source: oci:127.0.0.1:{registry.port}/acme/shared\n            namespace: shared\n            version: 1.2.3",
        )
        with pytest.raises(SDLParseError, match="not allowed by trust policy"):
            parse_sdl_file(root)

        _write(
            tmp_path / "raes-trust.yaml",
            f"""
            schema_version: raes-trust/v1
            registries:
              "127.0.0.1:{registry.port}":
                require_signatures: true
                allow_insecure_http: true
                trusted_signers: {{}}
            """,
        )
        with pytest.raises(SDLParseError, match="No valid trusted signer signature found"):
            parse_sdl_file(root)


def test_database_and_application_refs_survive_module_namespacing():
    """Qualified runtime DB/application refs are rewritten when namespaced.

    ADR-027 §2: refs published into the named-reference index must also be
    rewritten by module composition so an application-to-database relationship
    survives being imported under a namespace.
    """
    from raes._module_symbols import symbol_index
    from raes.scenario import ModuleDescriptor, Scenario

    scenario = Scenario(
        name="db-module",
        nodes={
            "db": {
                "type": "compute",
                "services": [{"port": 5432, "name": "pg"}],
                "runtime": {
                    "database_services": [
                        {
                            "database_service_id": "tv-pg",
                            "service": "pg",
                            "engine": "postgresql",
                            "protocol": "postgresql",
                            "databases": [{"database_id": "tv-db", "name": "techvault"}],
                        }
                    ]
                },
            },
            "web": {
                "type": "compute",
                "services": [{"port": 8080, "name": "http"}],
                "runtime": {"applications": [{"application_id": "webapp", "service": "http"}]},
            },
        },
    )
    index = symbol_index(
        scenario,
        namespace="shared",
        descriptor=ModuleDescriptor(id="raes/db-module", version="1.0.0"),
    )
    named = index["named"]
    assert named["nodes.db.runtime.database_services.tv-pg"] == ("nodes.shared.db.runtime.database_services.tv-pg")
    assert named["nodes.db.runtime.database_services.tv-pg.databases.tv-db"] == (
        "nodes.shared.db.runtime.database_services.tv-pg.databases.tv-db"
    )
    assert named["nodes.web.runtime.applications.webapp"] == ("nodes.shared.web.runtime.applications.webapp")


# ---------------------------------------------------------------------------
# Issue #12: bound OCI import fetches (memory/disk exhaustion).
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal urlopen-response double for the bounded reader (issue #12)."""

    def __init__(self, payload: bytes, *, content_length: str | None = None) -> None:
        self._payload = payload
        self.headers = {} if content_length is None else {"Content-Length": content_length}

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    def read(self, amt: int = -1) -> bytes:
        if amt is None or amt < 0:
            return self._payload
        return self._payload[:amt]


def _fake_urlopen_returning(response: _FakeResponse):
    def fake_urlopen(request, *, timeout=None):
        del request, timeout
        return response

    return fake_urlopen


def _gzip_tar(members: list[tuple[str, bytes]]) -> io.BytesIO:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, payload in members:
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    buffer.seek(0)
    return buffer


@pytest.mark.parametrize("replaced_relative", ["module.yaml", "nested/child.yaml"])
def test_oci_composition_uses_one_snapshot_after_cache_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replaced_relative: str,
) -> None:
    bundle = _gzip_tar(
        [
            (
                "module.yaml",
                b"""name: remote-root
module: {id: acme/remote-root, version: 1.0.0}
imports:
  - source: local:nested/child.yaml
    namespace: child
""",
            ),
            (
                "nested/child.yaml",
                b"""name: child
module: {id: acme/child, version: 1.0.0}
""",
            ),
        ]
    ).getvalue()
    content_digest = f"sha256:{module_registry._sha256_digest(bundle)}"
    descriptor = module_registry.ModuleDescriptor(id="acme/remote-root", version="1.0.0")
    monkeypatch.setattr(
        module_registry_resolution,
        "_resolve_oci_manifest",
        lambda **_kwargs: ("sha256:" + "a" * 64, {}),
    )
    monkeypatch.setattr(
        module_registry_resolution,
        "_resolve_oci_config",
        lambda **_kwargs: (
            {"module": descriptor.model_dump(mode="python"), "root_file": "module.yaml"},
            content_digest,
        ),
    )
    monkeypatch.setattr(module_registry_resolution, "_fetch_oci_bundle", lambda **_kwargs: bundle)

    admitted = False
    original_extract = module_registry._extract_bundle_to_cache
    original_resolve = Path.resolve
    original_load_lockfile = composition_expand.load_lockfile
    original_load_trust_policy = composition_expand.load_trust_policy

    def replace_after_snapshot(**kwargs):
        nonlocal admitted
        snapshot = original_extract(**kwargs)
        assert isinstance(snapshot, module_registry._VerifiedSourceBundle)
        target = snapshot.cache_root.joinpath(*replaced_relative.split("/"))
        replacement = target.with_name(f".{target.name}.replacement")
        replacement.write_bytes(b"\xff")
        os.replace(replacement, target)
        admitted = True
        return snapshot

    def reject_cache_resolution(path: Path, *args, **kwargs):
        if admitted and ".raes" in path.parts:
            pytest.fail("admitted OCI cache paths must retain lexical identities")
        return original_resolve(path, *args, **kwargs)

    def reject_cache_lockfile_discovery(base_dir: Path):
        if admitted and ".raes" in base_dir.parts:
            pytest.fail("admitted OCI bundles must not discover cache-local lockfiles")
        return original_load_lockfile(base_dir)

    def reject_cache_policy_discovery(base_dir: Path):
        if admitted and ".raes" in base_dir.parts:
            pytest.fail("admitted OCI bundles must not discover cache-local trust policy")
        return original_load_trust_policy(base_dir)

    monkeypatch.setattr(module_registry, "_extract_bundle_to_cache", replace_after_snapshot)
    monkeypatch.setattr(Path, "resolve", reject_cache_resolution)
    monkeypatch.setattr(composition_expand, "load_lockfile", reject_cache_lockfile_discovery)
    monkeypatch.setattr(composition_expand, "load_trust_policy", reject_cache_policy_discovery)
    _write(
        tmp_path / "raes-trust.yaml",
        """
        schema_version: raes-trust/v1
        allow_unsigned_local_sources: false
        registries:
          registry.example:
            require_signatures: false
        """,
    )
    root = _root_import(
        tmp_path / "root.yaml",
        "source: oci:registry.example/acme/remote-root\n            namespace: remote",
    )

    scenario = parse_sdl_file(root)

    assert admitted
    assert len(scenario.expansion_provenance.imports) == 2


def test_nested_oci_import_replaces_the_parent_source_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundles = {
        "acme/parent": _gzip_tar(
            [
                (
                    "module.yaml",
                    b"""name: parent
module: {id: acme/parent, version: 1.0.0}
imports:
  - source: oci:registry.example/acme/child
    namespace: child
""",
                )
            ]
        ).getvalue(),
        "acme/child": _gzip_tar(
            [("module.yaml", b"name: child\nmodule: {id: acme/child, version: 1.0.0}\n")]
        ).getvalue(),
    }
    manifest_digests = {
        "acme/parent": "sha256:" + "a" * 64,
        "acme/child": "sha256:" + "b" * 64,
    }
    captured_snapshots: list[module_registry._VerifiedSourceBundle] = []

    def resolve_manifest(*, repository: str, **_kwargs):
        return manifest_digests[repository], {"repository": repository}

    def resolve_config(*, manifest: dict[str, str], **_kwargs):
        repository = manifest["repository"]
        return (
            {
                "module": {"id": repository, "version": "1.0.0"},
                "root_file": "module.yaml",
            },
            f"sha256:{module_registry._sha256_digest(bundles[repository])}",
        )

    def fetch_bundle(*, repository: str, **_kwargs):
        return bundles[repository]

    monkeypatch.setattr(module_registry_resolution, "_resolve_oci_manifest", resolve_manifest)
    monkeypatch.setattr(module_registry_resolution, "_resolve_oci_config", resolve_config)
    monkeypatch.setattr(module_registry_resolution, "_fetch_oci_bundle", fetch_bundle)
    original_extract = module_registry._extract_bundle_to_cache

    def capture_snapshot(**kwargs):
        snapshot = original_extract(**kwargs)
        assert isinstance(snapshot, module_registry._VerifiedSourceBundle)
        captured_snapshots.append(snapshot)
        return snapshot

    monkeypatch.setattr(module_registry, "_extract_bundle_to_cache", capture_snapshot)
    _write(
        tmp_path / "raes-trust.yaml",
        """
        schema_version: raes-trust/v1
        registries:
          registry.example:
            require_signatures: false
        """,
    )
    root = _root_import(
        tmp_path / "root.yaml",
        "source: oci:registry.example/acme/parent\n            namespace: parent",
    )

    scenario = parse_sdl_file(root)

    assert [record.module_id for record in scenario.expansion_provenance.imports] == ["acme/parent", "acme/child"]
    assert len(captured_snapshots) == 2
    assert not captured_snapshots[1].cache_root.is_relative_to(captured_snapshots[0].cache_root)


def _gzip_metadata_archive(kind: str) -> tuple[bytes, bytes]:
    raw = io.BytesIO()
    archive_format = tarfile.PAX_FORMAT if kind == "pax" else tarfile.GNU_FORMAT
    with tarfile.open(fileobj=raw, mode="w", format=archive_format) as archive:
        info = tarfile.TarInfo(name="module.yaml" if kind == "pax" else f"{'a' * 65536}/module.yaml")
        if kind == "pax":
            info.pax_headers = {"comment": "x" * 65536}
        payload = b"name: metadata\n"
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    decoded = raw.getvalue()
    return gzip.compress(decoded, compresslevel=9, mtime=0), decoded


def test_oci_resource_limits_separate_compressed_from_extracted():
    limits = module_registry._OCI_LIMITS
    # Compressed-download and extracted-archive caps are deliberately distinct so a
    # small gzip cannot smuggle a large extraction past the download limit.
    assert limits.max_bundle_bytes > limits.max_metadata_bytes
    assert limits.max_total_bytes >= limits.max_member_bytes
    assert limits.max_tar_stream_bytes > limits.max_total_bytes
    assert limits.max_gzip_expansion_ratio > 1


def test_oci_tree_depth_is_bounded_before_extraction_and_during_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(module_registry._OCI_LIMITS, max_tree_depth=3),
    )
    deep_name = "a/b/c/module.yaml"
    bundle = _gzip_tar([(deep_name, b"name: deep\n")]).getvalue()

    with pytest.raises(SDLParseError, match="path-depth limit"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="deep-archive",
            root_file=deep_name,
            base_dir=tmp_path,
        )
    versions = module_registry._oci_cache_dir(tmp_path) / "deep-archive" / "versions"
    assert not list(versions.glob(".staged-*"))

    tree = tmp_path / "inventory"
    tree.mkdir()
    current = tree
    for component in ("a", "b", "c", "d"):
        current = current / component
        current.mkdir()
    with pytest.raises(SDLParseError, match="integrity validation"):
        module_registry._cache_tree_entries(tree)


@pytest.mark.parametrize("metadata_kind", ["pax", "gnu"])
def test_oci_metadata_bomb_is_bounded_before_tar_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata_kind: str,
):
    bundle, decoded = _gzip_metadata_archive(metadata_kind)
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(
            module_registry._OCI_LIMITS,
            max_tar_stream_bytes=len(decoded) - 1,
            max_gzip_expansion_ratio=1_000_000,
        ),
    )

    def parsed_too_early(*args, **kwargs):
        del args, kwargs
        pytest.fail("tarfile must not parse metadata before decoded-stream admission")

    monkeypatch.setattr(module_registry.tarfile, "open", parsed_too_early)

    with pytest.raises(SDLParseError, match="uncompressed tar stream"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest=f"metadata-{metadata_kind}",
            root_file="module.yaml",
            base_dir=tmp_path,
        )


def test_oci_gzip_ratio_is_bounded_before_tar_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bundle, decoded = _gzip_metadata_archive("pax")
    exact_ratio = (len(decoded) + len(bundle) - 1) // len(bundle)
    assert exact_ratio > 1
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(
            module_registry._OCI_LIMITS,
            max_tar_stream_bytes=len(decoded) + 1,
            max_gzip_expansion_ratio=exact_ratio - 1,
        ),
    )

    def parsed_too_early(*args, **kwargs):
        del args, kwargs
        pytest.fail("tarfile must not parse metadata before gzip-ratio admission")

    monkeypatch.setattr(module_registry.tarfile, "open", parsed_too_early)

    with pytest.raises(SDLParseError, match="expansion"):
        module_registry._extract_bundle_to_cache(
            bundle_bytes=bundle,
            manifest_digest="metadata-ratio",
            root_file="module.yaml",
            base_dir=tmp_path,
        )


def test_oci_decoded_tar_accepts_exact_absolute_and_ratio_boundaries(monkeypatch: pytest.MonkeyPatch):
    bundle, decoded = _gzip_metadata_archive("pax")
    exact_ratio = (len(decoded) + len(bundle) - 1) // len(bundle)
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(
            module_registry._OCI_LIMITS,
            max_tar_stream_bytes=len(decoded),
            max_gzip_expansion_ratio=exact_ratio,
        ),
    )

    with module_registry._bounded_gzip_tar_stream(bundle) as admitted:
        assert admitted.read() == decoded


def test_oci_decoded_tar_rejects_invalid_limit_configuration(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(module_registry._OCI_LIMITS, max_tar_stream_bytes=-1),
    )

    with (
        pytest.raises(SDLParseError, match="non-negative"),
        module_registry._bounded_gzip_tar_stream(b""),
    ):
        pass


def test_oci_metadata_request_rejects_oversized_response(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        module_registry, "urlopen", _fake_urlopen_returning(_FakeResponse(b'{"tags":["' + b"a" * 64 + b'"]}'))
    )
    with pytest.raises(SDLParseError, match="exceeds"):
        module_registry._json_request("https://registry.example/v2/acme/tags/list", max_bytes=16)


def test_oci_bytes_request_rejects_oversized_response(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(module_registry, "urlopen", _fake_urlopen_returning(_FakeResponse(b"x" * 64)))
    with pytest.raises(SDLParseError, match="exceeds"):
        module_registry._bytes_request("https://registry.example/v2/acme/blobs/sha256:abc", max_bytes=16)


def test_oci_bytes_request_accepts_payload_at_limit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(module_registry, "urlopen", _fake_urlopen_returning(_FakeResponse(b"x" * 16)))
    assert (
        module_registry._bytes_request("https://registry.example/v2/acme/blobs/sha256:abc", max_bytes=16) == b"x" * 16
    )


def test_oci_response_rejects_oversized_content_length(monkeypatch: pytest.MonkeyPatch):
    # A registry cannot force a large buffer by declaring a huge Content-Length: the
    # advisory header is rejected before any bytes are read.
    monkeypatch.setattr(
        module_registry,
        "urlopen",
        _fake_urlopen_returning(_FakeResponse(b"x", content_length="1048576")),
    )
    with pytest.raises(SDLParseError, match="Content-Length"):
        module_registry._bytes_request("https://registry.example/v2/acme/blobs/sha256:abc", max_bytes=16)


def test_oci_response_rejects_invalid_content_length(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        module_registry,
        "urlopen",
        _fake_urlopen_returning(_FakeResponse(b"x", content_length="not-a-number")),
    )
    with pytest.raises(SDLParseError, match="Content-Length"):
        module_registry._bytes_request("https://registry.example/v2/acme/blobs/sha256:abc", max_bytes=16)


def test_oci_response_rejects_negative_content_length(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        module_registry,
        "urlopen",
        _fake_urlopen_returning(_FakeResponse(b"x", content_length="-1")),
    )
    with pytest.raises(SDLParseError, match="negative Content-Length"):
        module_registry._bytes_request("https://registry.example/v2/acme/blobs/sha256:abc", max_bytes=16)


def test_oci_bundle_rejects_excess_member_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(module_registry._OCI_LIMITS, max_bundle_members=1),
    )
    buffer = _gzip_tar([("a.yaml", b"a\n"), ("b.yaml", b"b\n")])
    with (
        tarfile.open(fileobj=buffer, mode="r:gz") as tar,
        pytest.raises(SDLParseError, match="archive members"),
    ):
        module_registry._safe_tar_members(tar, tmp_path / "cache")


def test_oci_cache_manifest_does_not_consume_member_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(module_registry._OCI_LIMITS, max_bundle_members=1),
    )
    bundle = _gzip_tar([("module.yaml", b"name: bounded\n")]).getvalue()

    root = module_registry._extract_bundle_to_cache(
        bundle_bytes=bundle,
        manifest_digest="one-member-boundary",
        root_file="module.yaml",
        base_dir=tmp_path,
    )

    assert root.read_bytes() == b"name: bounded\n"


def test_oci_bundle_rejects_oversized_member(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(module_registry._OCI_LIMITS, max_member_bytes=4),
    )
    buffer = _gzip_tar([("big.yaml", b"x" * 16)])
    with (
        tarfile.open(fileobj=buffer, mode="r:gz") as tar,
        pytest.raises(SDLParseError, match="per-member"),
    ):
        module_registry._safe_tar_members(tar, tmp_path / "cache")


def test_oci_bundle_rejects_excess_total_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        module_registry,
        "_OCI_LIMITS",
        dataclasses.replace(module_registry._OCI_LIMITS, max_member_bytes=100, max_total_bytes=8),
    )
    buffer = _gzip_tar([("a.yaml", b"x" * 6), ("b.yaml", b"y" * 6)])
    with (
        tarfile.open(fileobj=buffer, mode="r:gz") as tar,
        pytest.raises(SDLParseError, match="total extraction"),
    ):
        module_registry._safe_tar_members(tar, tmp_path / "cache")


def test_oci_bundle_rejects_duplicate_member(tmp_path: Path):
    buffer = _gzip_tar([("dup.yaml", b"a\n"), ("dup.yaml", b"b\n")])
    with (
        tarfile.open(fileobj=buffer, mode="r:gz") as tar,
        pytest.raises(SDLParseError, match="Duplicate"),
    ):
        module_registry._safe_tar_members(tar, tmp_path / "cache")


# ---------------------------------------------------------------------------
# Issue #14: config-blob integrity + root_file signature binding.
# ---------------------------------------------------------------------------


def _rewrite_config_field(layout_dir: Path, field: str, value: object) -> None:
    """Rewrite a published OCI layout so the config's ``field`` becomes ``value``.

    Models a compromised registry that keeps the signer's signature intact but
    alters an unsigned config field, then re-derives the config digest, manifest
    digest, and index so every served blob is internally consistent. Fix 1
    (config-digest verification) therefore passes; only a signature that binds
    ``field`` can catch the tamper.
    """
    blobs = layout_dir / "blobs" / "sha256"
    index = json.loads((layout_dir / "index.json").read_text(encoding="utf-8"))
    manifest_digest = index["manifests"][0]["digest"]
    manifest = json.loads((blobs / manifest_digest.removeprefix("sha256:")).read_bytes())
    config_digest = manifest["config"]["digest"]
    config = json.loads((blobs / config_digest.removeprefix("sha256:")).read_bytes())
    config[field] = value
    new_config_bytes = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    new_config_digest = f"sha256:{module_registry._sha256_digest(new_config_bytes)}"
    (blobs / new_config_digest.removeprefix("sha256:")).write_bytes(new_config_bytes)
    manifest["config"]["digest"] = new_config_digest
    manifest["config"]["size"] = len(new_config_bytes)
    new_manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    new_manifest_digest = f"sha256:{module_registry._sha256_digest(new_manifest_bytes)}"
    (blobs / new_manifest_digest.removeprefix("sha256:")).write_bytes(new_manifest_bytes)
    index["manifests"][0]["digest"] = new_manifest_digest
    index["manifests"][0]["size"] = len(new_manifest_bytes)
    (layout_dir / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@pytest.mark.integration
def test_oci_import_rejects_tampered_config_blob(tmp_path: Path):
    """A registry serving config bytes that do not hash to manifest ``config.digest``
    is rejected before the config JSON is trusted (issue #14, fix 1)."""
    module_path = _local_module(tmp_path / "shared.yaml")
    published = publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")
    layout_dir = Path(published["layout_dir"])

    # Overwrite the config blob with bytes that no longer match its digest-keyed
    # filename, so the in-process registry serves them under the advertised
    # config.digest (the manifest is left untouched).
    index = json.loads((layout_dir / "index.json").read_text(encoding="utf-8"))
    manifest_digest = index["manifests"][0]["digest"]
    blobs = layout_dir / "blobs" / "sha256"
    manifest = json.loads((blobs / manifest_digest.removeprefix("sha256:")).read_bytes())
    config_blob = blobs / manifest["config"]["digest"].removeprefix("sha256:")
    tampered = json.loads(config_blob.read_bytes())
    tampered["root_file"] = "evil.yaml"
    config_blob.write_bytes(json.dumps(tampered, sort_keys=True, separators=(",", ":")).encode("utf-8"))

    with _OCIRegistry(layout_dir, repo="acme/shared") as registry:
        _write(
            tmp_path / "raes-trust.yaml",
            f"""
            schema_version: raes-trust/v1
            registries:
              "127.0.0.1:{registry.port}":
                require_signatures: false
                allow_insecure_http: true
            """,
        )
        root = _root_import(
            tmp_path / "root-oci.yaml",
            f"source: oci:127.0.0.1:{registry.port}/acme/shared\n            namespace: shared\n            version: 1.2.3",
        )
        with pytest.raises(SDLParseError, match="config digest verification failed"):
            parse_sdl_file(root)


@pytest.mark.integration
def test_oci_import_rejects_root_file_tampering(tmp_path: Path):
    """A compromised registry cannot repoint ``root_file`` inside an otherwise-signed
    bundle: ``root_file`` is bound into the signature payload, so altering it while
    keeping the original signature fails verification (issue #14, fix 2)."""
    module_path = _local_module(tmp_path / "shared.yaml")
    private_key = Ed25519PrivateKey.generate()
    private_key_path = tmp_path / "signing-key.pem"
    private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    published = publish_module_to_oci_layout(
        module_path,
        output_dir=tmp_path / "dist",
        signer_id="test-signer",
        private_key_path=private_key_path,
    )
    layout_dir = Path(published["layout_dir"])
    # Keep the signature intact; only repoint the entrypoint.
    _rewrite_config_field(layout_dir, "root_file", "smuggled.yaml")

    with _OCIRegistry(layout_dir, repo="acme/shared") as registry:
        _write(
            tmp_path / "raes-trust.yaml",
            f"""
            schema_version: raes-trust/v1
            registries:
              "127.0.0.1:{registry.port}":
                require_signatures: true
                allow_insecure_http: true
                trusted_signers:
                  test-signer: "{base64.b64encode(public_key).decode("utf-8")}"
            """,
        )
        root = _root_import(
            tmp_path / "root-oci.yaml",
            f"source: oci:127.0.0.1:{registry.port}/acme/shared\n            namespace: shared\n            version: 1.2.3",
        )
        with pytest.raises(SDLParseError, match="No valid trusted signer signature found"):
            parse_sdl_file(root)


@pytest.mark.integration
def test_oci_import_rejects_non_string_root_file(tmp_path: Path):
    """A config declaring a non-string ``root_file`` fails closed with SDLParseError
    rather than flowing a bad type into the signature payload / extraction and
    surfacing a confusing downstream TypeError (issue #14)."""
    module_path = _local_module(tmp_path / "shared.yaml")
    published = publish_module_to_oci_layout(module_path, output_dir=tmp_path / "dist")
    layout_dir = Path(published["layout_dir"])
    # Re-derive the digests so Fix 1 (config-digest verification) passes and the
    # root_file type check is what rejects the module.
    _rewrite_config_field(layout_dir, "root_file", ["evil.yaml"])

    with _OCIRegistry(layout_dir, repo="acme/shared") as registry:
        _write(
            tmp_path / "raes-trust.yaml",
            f"""
            schema_version: raes-trust/v1
            registries:
              "127.0.0.1:{registry.port}":
                require_signatures: false
                allow_insecure_http: true
            """,
        )
        root = _root_import(
            tmp_path / "root-oci.yaml",
            f"source: oci:127.0.0.1:{registry.port}/acme/shared\n            namespace: shared\n            version: 1.2.3",
        )
        with pytest.raises(SDLParseError, match="non-string root_file"):
            parse_sdl_file(root)


def test_oci_signature_over_legacy_payload_without_root_file_is_rejected():
    """A signature computed over the pre-#14 payload (which omitted ``root_file``)
    fails closed under ``require_signatures`` — no compatibility fallback."""
    descriptor = module_registry.ModuleDescriptor(id="acme/shared", version="1.2.3", exports={"nodes": ["vm"]})
    content_digest = "sha256:" + "0" * 64
    legacy_payload = json.dumps(
        {
            "module_id": descriptor.id,
            "module_version": descriptor.version,
            "exports": descriptor.exports,
            "content_digest": content_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signature = base64.b64encode(private_key.sign(legacy_payload)).decode("utf-8")
    policy = module_registry.RegistryTrustPolicy(
        require_signatures=True,
        trusted_signers={"test-signer": base64.b64encode(public_key).decode("utf-8")},
    )
    with pytest.raises(SDLParseError, match="No valid trusted signer signature found"):
        module_registry._verify_signatures(
            signatures=[{"signer_id": "test-signer", "signature": signature}],
            trust_policy=policy,
            module_descriptor=descriptor,
            content_digest=content_digest,
            root_file="module.yaml",
        )


def test_oci_signature_binds_root_file():
    """The canonical signing payload includes ``root_file`` so a differing
    ``root_file`` produces a different signable payload (issue #14, fix 2)."""
    descriptor = module_registry.ModuleDescriptor(id="acme/shared", version="1.2.3", exports={"nodes": ["vm"]})
    content_digest = "sha256:" + "0" * 64
    payload_a = module_registry._signable_payload(descriptor, content_digest=content_digest, root_file="module.yaml")
    payload_b = module_registry._signable_payload(descriptor, content_digest=content_digest, root_file="other.yaml")
    assert payload_a != payload_b
    assert b"root_file" in payload_a

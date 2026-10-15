"""Substituted daemon runner tests; concrete OCI effects are tested in CI separately."""

import io
import json
import tarfile
from time import monotonic
from types import SimpleNamespace

import pytest
from raes_contracts.contracts import backend_operation_request_digest
from raes_reference_backend.drivers.oci import ImageTrustPolicy, OciDeploymentDriver
from test_issue_1366_inject_occurrence_outcomes import invocation

IMAGE = "trusted/inject:1"
CONFIG_DIGEST = "sha256:" + "a" * 64
NODE = "provision.node.host"
BINDING = "orchestration.inject-binding.host.release"


@pytest.fixture(autouse=True)
def mock_oci_runtime(monkeypatch):
    """All substituted-daemon cases run without a discoverable host runtime."""

    from raes_reference_backend.drivers import oci_inject

    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(oci_inject, "shutil", SimpleNamespace(which=lambda _: "/fixture/bin/docker"))


def test_native_runtime_discovery_still_refuses_an_unavailable_executable(monkeypatch):
    from raes_reference_backend.drivers import oci_inject

    monkeypatch.setattr(oci_inject, "shutil", SimpleNamespace(which=lambda _: None))
    with pytest.raises(ValueError, match="runtime is unavailable"):
        configured()


class DaemonFixture:
    def __init__(self, deployment):
        self.deployment = deployment
        self.calls = []
        self.native_id = "b" * 64
        self.workspace = deployment._workspace
        self.running = True
        self.effects = {}
        self.probe = b"before"
        self.exit_code = 0

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[1:3] == ["image", "inspect"]:
            return json.dumps({"id": CONFIG_DIGEST, "volumes": None}).encode()
        if argv[1] == "create":
            name = argv[argv.index("--name") + 1]
            labels = dict(
                item.split("=", 1) for index, item in enumerate(argv) if index and argv[index - 1] == "--label"
            )
            self.effects[name] = {
                "id": "e" * 64,
                "workspace": self.workspace,
                "address": BINDING,
                "name": "/" + name,
                "invocation": labels["raes.inject-invocation"],
                "revision": labels["raes.inject-target-revision"],
                "image": CONFIG_DIGEST,
                "network": "container:" + self.native_id,
                "status": "created",
                "exit_code": 0,
                "finished_at": "2026-10-15T00:00:00Z",
            }
            return b"e" * 64 + b"\n"
        if argv[1] == "start":
            self.effects[argv[-1]]["status"] = "exited"
            self.effects[argv[-1]]["exit_code"] = self.exit_code
            self.probe = b"after"
            return argv[-1].encode()
        if argv[1] == "cp":
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w") as archive:
                member = tarfile.TarInfo("world-state")
                member.size = len(self.probe)
                archive.addfile(member, io.BytesIO(self.probe))
            return output.getvalue()
        assert argv[1] == "inspect"
        if argv[-1] in self.effects:
            return json.dumps(self.effects[argv[-1]]).encode()
        return json.dumps(
            {
                "id": self.native_id,
                "workspace": self.workspace,
                "address": NODE,
                "name": "/" + self.deployment._name_for(NODE),
                "running": self.running,
            }
        ).encode()


def configured():
    from raes_reference_backend.drivers.oci_inject import OciInjectDriver

    deployment = OciDeploymentDriver(workspace="inject-fixture", image_policy=ImageTrustPolicy(allowed_images=(IMAGE,)))
    daemon = DaemonFixture(deployment)
    return OciInjectDriver(deployment, runner=daemon), daemon


def descriptor(**changes):
    from raes_reference_backend.inject_bindings import OciInjectSourceModel

    return OciInjectSourceModel.model_validate(
        {"profile": "reference-oci-entrypoint/v1", "image": IMAGE, "image_config_digest": CONFIG_DIGEST, **changes}
    )


def test_target_selection_is_bound_to_native_ownership_and_revision():
    native, daemon = configured()
    binding = native.binding(BINDING, NODE, deadline=monotonic() + 2)
    assert binding.node == NODE
    assert daemon.native_id not in binding.model_dump_json()
    daemon.native_id = "c" * 64
    check_started_at_1 = monotonic()
    with pytest.raises(ValueError, match="revision"):
        native.require_target(binding, deadline=check_started_at_1 + 2)
    daemon.workspace = "another-run"
    check_started_at_2 = monotonic()
    with pytest.raises(ValueError, match="ownership"):
        native.binding(BINDING, NODE, deadline=check_started_at_2 + 2)


def test_source_requires_operator_trust_and_exact_installed_image_content():
    native, daemon = configured()
    assert native.image(descriptor(), deadline=monotonic() + 2) == CONFIG_DIGEST
    checked_source_3 = descriptor(image="untrusted/image:latest")
    check_started_at_4 = monotonic()
    with pytest.raises(ValueError, match="trust"):
        native.image(checked_source_3, deadline=check_started_at_4 + 2)
    checked_source_5 = descriptor(image_config_digest="sha256:" + "d" * 64)
    check_started_at_6 = monotonic()
    with pytest.raises(ValueError, match="image"):
        native.image(checked_source_5, deadline=check_started_at_6 + 2)


def test_native_probe_reader_never_extracts_archives_or_accepts_links():
    from raes_reference_backend.drivers.oci_inject import read_probe_archive

    def archive(link=False):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as bundle:
            item = tarfile.TarInfo("world-state")
            item.size = 6
            if link:
                item.type, item.linkname = tarfile.SYMTYPE, "/private-target"
            bundle.addfile(item, None if link else io.BytesIO(b"effect"))
        return output.getvalue()

    assert read_probe_archive(archive(), "/tmp/world-state", 64) == b"effect"
    probe_bundle_7 = archive(link=True)
    with pytest.raises(ValueError, match="probe"):
        read_probe_archive(probe_bundle_7, "/tmp/world-state", 64)
    probe_bundle_8 = archive()
    with pytest.raises(ValueError, match="probe"):
        read_probe_archive(probe_bundle_8, "/tmp/world-state", 2)


def test_source_descriptor_has_no_request_supplied_command_or_environment():
    with pytest.raises(ValueError):
        descriptor(command="untrusted command")
    with pytest.raises(ValueError):
        descriptor(environment={"CREDENTIAL": "private-test-value"})


def test_authored_image_entrypoint_is_isolated_and_requires_independent_world_readback():
    from raes_reference_backend.inject_bindings import OciInjectProbe

    native, daemon = configured()
    probe = OciInjectProbe(
        binding=native.binding(BINDING, NODE, deadline=monotonic() + 2),
        path="/tmp/world-state",
        before=b"before",
        after=b"after",
    )
    request = invocation("inject-release")
    assert native.read_probe(probe, deadline=monotonic() + 2) == b"before"
    native.start(request, probe, descriptor(), deadline=monotonic() + 2)
    observed = native.observe(request, probe, descriptor(), deadline=monotonic() + 2)
    assert observed.ceased
    assert observed.exit_code == 0
    assert observed.readback == b"after"
    created = next(argv for argv, _ in daemon.calls if argv[1] == "create")
    assert created[-1] == CONFIG_DIGEST
    assert created[created.index("--network") + 1] == "container:" + daemon.native_id
    assert created[created.index("--user") + 1] == "65534:65534"
    assert "--read-only" in created
    assert "--pull=never" in created
    assert created[created.index("--cap-drop") + 1] == "ALL"
    assert not {"--privileged", "--volume", "--mount", "--env"}.intersection(created)
    daemon.probe = b"different-world-content"
    assert native.observe(request, probe, descriptor(), deadline=monotonic() + 2).readback != probe.after
    effect = next(iter(daemon.effects.values()))
    effect["invocation"] = backend_operation_request_digest(request).replace("a", "0")
    checked_source_9 = descriptor()
    check_started_at_10 = monotonic()
    with pytest.raises(ValueError, match="ownership"):
        native.observe(request, probe, checked_source_9, deadline=check_started_at_10 + 2)


@pytest.mark.parametrize(
    "image", ["user:credential@registry/image", "https://registry/image", "--runtime-option", "image with spaces"]
)
def test_explicit_image_allowlisting_cannot_expose_credentials_or_native_options(image):
    assert not ImageTrustPolicy(allowed_images=(image,)).permits(image)
    with pytest.raises(ValueError):
        descriptor(image=image)

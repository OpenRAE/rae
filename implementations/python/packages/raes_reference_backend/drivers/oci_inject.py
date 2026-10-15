"""Private native target/image/readback checks over the provisioner's admitted OCI owner."""

from __future__ import annotations

import io
import re
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from raes_backend_protocols.naming import provider_resource_name
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import InjectTargetBindingModel, backend_operation_request_digest
from raes_contracts.json_ingress import parse_bounded_json_object

from ..inject_bindings import OciInjectSourceModel
from .oci import OciDeploymentDriver
from .oci_observation import ownership_fields_match
from .oci_process import run_bounded_process

_TARGET_FORMAT = (
    '{"id":{{json .Id}},"workspace":{{json (index .Config.Labels "raes.workspace")}},'
    '"address":{{json (index .Config.Labels "raes.address")}},"name":{{json .Name}},'
    '"running":{{json .State.Running}}}'
)
_IMAGE_FORMAT = '{"id":{{json .Id}},"volumes":{{json .Config.Volumes}}}'
_EFFECT_FORMAT = (
    '{"id":{{json .Id}},"workspace":{{json (index .Config.Labels "raes.workspace")}},'
    '"address":{{json (index .Config.Labels "raes.address")}},"name":{{json .Name}},'
    '"invocation":{{json (index .Config.Labels "raes.inject-invocation")}},'
    '"revision":{{json (index .Config.Labels "raes.inject-target-revision")}},'
    '"image":{{json .Image}},"network":{{json .HostConfig.NetworkMode}},'
    '"status":{{json .State.Status}},"exit_code":{{json .State.ExitCode}},'
    '"finished_at":{{json .State.FinishedAt}}}'
)


@dataclass(frozen=True)
class NativeInjectObservation:
    ceased: bool
    exit_code: int | None
    finished_at: str
    readback: bytes | None


def read_probe_archive(content: bytes, path: str, limit: int) -> bytes:
    """Read one bounded regular member without extraction or link following."""

    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:") as archive:
            members = archive.getmembers()
            if (
                len(members) != 1
                or not members[0].isfile()
                or members[0].name != PurePosixPath(path).name
                or not 0 <= members[0].size <= limit
            ):
                raise ValueError("invalid OCI inject probe archive")
            stream = archive.extractfile(members[0])
            if stream is None:
                raise ValueError("OCI inject probe is unavailable")
            result = stream.read(limit + 1)
            if len(result) != members[0].size:
                raise ValueError("OCI inject probe content is invalid")
            return result
    except (tarfile.TarError, OSError):
        raise ValueError("OCI inject probe archive is invalid") from None


class OciInjectDriver:
    def __init__(self, deployment: OciDeploymentDriver, *, runner=run_bounded_process):
        if not isinstance(deployment, OciDeploymentDriver):
            raise TypeError("OCI inject execution requires the admitted OCI deployment driver")
        executable = shutil.which(deployment._runtime)
        if executable is None:
            raise ValueError("OCI inject runtime is unavailable")
        self.deployment, self._runner, self._executable = deployment, runner, executable

    def call(self, arguments, *, deadline, max_output_bytes=4096):
        return self._runner([self._executable, *arguments], deadline=deadline, max_output_bytes=max_output_bytes)

    def _target(self, node, *, deadline):
        name = self.deployment._name_for(node)
        content = self.call(["inspect", "--format", _TARGET_FORMAT, "--", name], deadline=deadline)
        data = parse_bounded_json_object(content, max_bytes=4096, max_depth=4)
        fields = [data.get(key) for key in ("id", "workspace", "address", "name")]
        if (
            data.keys() != {"id", "workspace", "address", "name", "running"}
            or not isinstance(fields[0], str)
            or re.fullmatch(r"[a-f0-9]{64}", fields[0]) is None
            or data["running"] is not True
            or not ownership_fields_match(
                fields, address=node, expected_name=name, expected_native_id=None, workspace=self.deployment._workspace
            )
        ):
            raise ValueError("OCI inject target ownership is unavailable")
        return fields[0]

    def binding(self, binding, node, *, deadline):
        native_id = self._target(node, deadline=deadline)
        return InjectTargetBindingModel(
            binding=binding,
            node=node,
            instance=provider_resource_name(node, prefix="instance", namespace=self.deployment._workspace),
            revision=canonical_json_digest({"domain": "raes.oci-inject-target/v1", "native_id": native_id}),
        )

    def require_target(self, binding, *, deadline):
        native_id = self._target(binding.node, deadline=deadline)
        expected_instance = provider_resource_name(
            binding.node, prefix="instance", namespace=self.deployment._workspace
        )
        revision = canonical_json_digest({"domain": "raes.oci-inject-target/v1", "native_id": native_id})
        if (binding.instance, binding.revision) != (expected_instance, revision):
            raise ValueError("OCI inject target instance or revision is stale")
        return native_id

    def image(self, source: OciInjectSourceModel, *, deadline):
        if not self.deployment._image_policy.permits(source.image):
            raise ValueError("OCI inject source does not satisfy image trust policy")
        content = self.call(["image", "inspect", "--format", _IMAGE_FORMAT, "--", source.image], deadline=deadline)
        data = parse_bounded_json_object(content, max_bytes=4096, max_depth=4)
        if (
            data.keys() != {"id", "volumes"}
            or data["id"] != source.image_config_digest
            or data["volumes"] not in (None, {})
        ):
            raise ValueError("OCI inject image content or volume contract is unsupported")
        return source.image_config_digest

    def read_probe(self, probe, *, deadline):
        native_id = self.require_target(probe.binding, deadline=deadline)
        content = self.call(
            ["cp", "--", f"{native_id}:{probe.path}", "-"], deadline=deadline, max_output_bytes=128 * 1024
        )
        result = read_probe_archive(content, probe.path, 65536)
        if self.require_target(probe.binding, deadline=deadline) != native_id:
            raise ValueError("OCI inject probe target changed during readback")
        return result

    @staticmethod
    def effect_name(request, binding):
        return provider_resource_name(
            binding.binding,
            prefix="raes-inject",
            namespace=canonical_json_digest(
                {
                    "request": backend_operation_request_digest(request),
                    "binding": binding.model_dump(mode="json"),
                }
            ),
        )

    def start(self, request, probe, source, *, deadline):
        target = self.require_target(probe.binding, deadline=deadline)
        image = self.image(source, deadline=deadline)
        name = self.effect_name(request, probe.binding)
        # A retained native name is another one-use boundary. Failed create or
        # lost acknowledgement never falls through to starting an old object.
        self.call(
            [
                "create",
                "--pull=never",
                "--name",
                name,
                "--label",
                f"raes.workspace={self.deployment._workspace}",
                "--label",
                f"raes.address={probe.binding.binding}",
                "--label",
                f"raes.inject-invocation={backend_operation_request_digest(request)}",
                "--label",
                f"raes.inject-target-revision={probe.binding.revision}",
                "--network",
                f"container:{target}",
                "--user",
                "65534:65534",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--read-only",
                "--pids-limit",
                "32",
                "--memory",
                "64m",
                "--cpus",
                "1",
                "--log-driver",
                "none",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,noexec,size=16m",  # noqa: S108 -- private container tmpfs, never a host path.
                image,
            ],
            deadline=deadline,
        )
        self.call(["start", "--", name], deadline=deadline)

    def _effect(self, request, probe, source, *, deadline):
        name = self.effect_name(request, probe.binding)
        content = self.call(["inspect", "--format", _EFFECT_FORMAT, "--", name], deadline=deadline)
        data = parse_bounded_json_object(content, max_bytes=4096, max_depth=4)
        fields = [data.get(key) for key in ("id", "workspace", "address", "name")]
        if (
            data.keys()
            != {
                "id",
                "workspace",
                "address",
                "name",
                "invocation",
                "revision",
                "image",
                "network",
                "status",
                "exit_code",
                "finished_at",
            }
            or not isinstance(fields[0], str)
            or re.fullmatch(r"[a-f0-9]{64}", fields[0]) is None
            or not ownership_fields_match(
                fields,
                address=probe.binding.binding,
                expected_name=name,
                expected_native_id=None,
                workspace=self.deployment._workspace,
            )
            or data["invocation"] != backend_operation_request_digest(request)
            or data["revision"] != probe.binding.revision
            or data["image"] != source.image_config_digest
        ):
            raise ValueError("OCI inject execution ownership is unavailable")
        return data

    def observe(self, request, probe, source, *, deadline):
        target = self.require_target(probe.binding, deadline=deadline)
        data = self._effect(request, probe, source, deadline=deadline)
        if data["network"] != "container:" + target:
            raise ValueError("OCI inject execution target ownership changed")
        if data["status"] != "exited":
            return NativeInjectObservation(False, None, request.budget.started_at, None)
        if type(data["exit_code"]) is not int or not isinstance(data["finished_at"], str):
            raise ValueError("OCI inject cessation evidence is invalid")
        try:
            readback = self.read_probe(probe, deadline=deadline)
        except ValueError:
            readback = None
        return NativeInjectObservation(True, data["exit_code"], data["finished_at"], readback)

    def remove(self, request, probe, source, *, deadline):
        self._effect(request, probe, source, deadline=deadline)
        self.call(["rm", "--force", "--", self.effect_name(request, probe.binding)], deadline=deadline)

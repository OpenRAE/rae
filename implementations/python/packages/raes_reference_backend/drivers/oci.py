"""OCI deployment driver (docker/podman) for the reference backend.

Security boundary (binding guardrails, issue #197 preflight):

- Every host-process invocation uses a FIXED argv list -- never a shell
  string, never ``shell=True``. The container runtime name is validated
  against a closed allowlist so it can never carry an injected command.
- Every invocation has a bounded ``timeout``; a timeout becomes a portable
  diagnostic, not an escaped exception.
- No tokens, passwords, credentials, or host environment ever appear in
  argv.
- Backend-native output (container ids, daemon inspect payloads, raw
  stderr) is consumed privately and NEVER placed into the returned portable
  handles or diagnostics. Diagnostics carry the RAES address and a fixed
  message only.

The actual subprocess call is the only impure leaf; it is injected as
``runner`` so tests exercise the full argv/timeout/redaction logic without
a real daemon, and the real default runner line is marked ``# pragma: no
cover``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from raes_backend_protocols.naming import provider_resource_name
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.realization_observation import RealizationObservation

from raes_reference_backend.driver import (
    ContainerHandle,
    ContainerSpec,
    DriverResult,
    NetworkHandle,
    NetworkSpec,
)
from raes_reference_backend.drivers.oci_image_trust import ImageTrustPolicy
from raes_reference_backend.drivers.oci_observation import ownership_fields_match, substrate_observations

_DOMAIN = "runtime"
_ALLOWED_RUNTIMES = frozenset({"docker", "podman"})
_DEFAULT_TIMEOUT_SECONDS = 120

_CODE_TIMEOUT = "reference-backend.driver.timeout"
_CODE_RUNTIME_UNAVAILABLE = "reference-backend.driver.runtime-unavailable"
_CODE_COMMAND_FAILED = "reference-backend.driver.command-failed"
_CODE_IMAGE_NOT_ALLOWED = "reference-backend.driver.image-not-allowed"
_CODE_NETWORK_NAMESPACE_TARGET_UNAVAILABLE = "reference-backend.driver.network-namespace-target-unavailable"
_CODE_NETWORK_NAMESPACE_CONFLICT = "reference-backend.driver.network-namespace-conflict"

_OWNERSHIP_INSPECT_FORMAT = (
    '{{.Id}}\n{{index .Config.Labels "raes.workspace"}}\n{{index .Config.Labels "raes.address"}}\n{{.Name}}'
)

_KIND_TO_CODE = {
    "timeout": _CODE_TIMEOUT,
    "runtime-missing": _CODE_RUNTIME_UNAVAILABLE,
    "command-failed": _CODE_COMMAND_FAILED,
}

Runner = Callable[..., subprocess.CompletedProcess]


def _default_runner(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    # The real subprocess call is the impure IO leaf; tests inject a fake
    # runner, and coverage excludes this function (see pyproject exclude_also).
    return subprocess.run(argv, **kwargs)


_DEFAULT_IMAGE_POLICY = ImageTrustPolicy()


class OciDeploymentDriver:
    """Realize portable specs against a real container runtime."""

    driver_mode = "oci-container"

    def __init__(
        self,
        *,
        runtime: str = "docker",
        workspace: str,
        runner: Runner | None = None,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        keep_alive: tuple[str, ...] = ("sleep", "3600"),
        image_policy: ImageTrustPolicy = _DEFAULT_IMAGE_POLICY,
    ) -> None:
        if runtime not in _ALLOWED_RUNTIMES:
            raise ValueError(f"Unsupported container runtime; allowed: {sorted(_ALLOWED_RUNTIMES)}.")
        if not workspace or not workspace.strip():
            raise ValueError("OciDeploymentDriver requires a non-empty workspace label.")
        if not 0 < timeout_seconds <= 600:
            raise ValueError("OciDeploymentDriver timeout_seconds must be in (0, 600].")
        self._runtime = runtime
        self._workspace = workspace
        self._runner = runner or _default_runner
        self._timeout = timeout_seconds
        self._keep_alive = tuple(keep_alive)
        self._image_policy = image_policy
        self._realized: set[str] = set()
        # RAES address -> the runtime object name realize() used, so destroy()
        # removes exactly what was created even when a payload pinned an
        # explicit name that differs from the address's last segment.
        self._names: dict[str, str] = {}
        # Native identifiers never cross the portable driver boundary. They are
        # retained only so namespace joins can prove that the current runtime
        # object is the exact container this driver created in this realize()
        # transaction, rather than trusting a stale RAES address/name mapping.
        self._native_ids: dict[str, str] = {}

    def _label_args(self, address: str) -> list[str]:
        return [
            "--label",
            f"raes.workspace={self._workspace}",
            "--label",
            f"raes.address={address}",
        ]

    def _invoke(self, argv: list[str]) -> tuple[bool, str | None, str]:
        """Run fixed argv and privately return native stdout for verification."""

        try:
            completed = self._runner(
                argv,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "timeout", ""
        except OSError:
            # A missing runtime binary (FileNotFoundError), a socket/binary the
            # process may not access (PermissionError), and any other OS-level
            # spawn failure all collapse to one portable "runtime unavailable"
            # kind; the native errno/strerror never crosses the boundary.
            return False, "runtime-missing", ""
        kind = None if completed.returncode == 0 else "command-failed"
        stdout = completed.stdout if isinstance(completed.stdout, str) else ""
        return kind is None, kind, stdout

    def _run(self, argv: list[str]) -> tuple[bool, str | None]:
        """Run a fixed argv; return (success, failure_kind).

        Native stdout/stderr is consumed but never returned to the caller --
        only a coarse, fixed failure-kind string used to pick a diagnostic.
        """

        ok, kind, _stdout = self._invoke(argv)
        return ok, kind

    def realize(
        self,
        *,
        networks: tuple[NetworkSpec, ...],
        containers: tuple[ContainerSpec, ...],
    ) -> DriverResult:
        diagnostics: list[Diagnostic] = []
        diagnostics.extend(self._network_namespace_diagnostics(containers))
        if diagnostics:
            return DriverResult(diagnostics=tuple(diagnostics))
        network_handles = self._realize_networks(networks, diagnostics)
        container_handles = self._realize_containers(containers, diagnostics)
        result = DriverResult(
            networks=tuple(network_handles),
            containers=tuple(container_handles),
            diagnostics=tuple(diagnostics),
        )
        # Transactional boundary: if any resource failed, roll back the ones
        # that succeeded so a partial realize never leaves an orphan runtime
        # resource behind a failed operation.
        if result.diagnostics:
            self._rollback(network_handles, container_handles)
            return DriverResult(diagnostics=result.diagnostics)
        return result

    def _substrate_observations(
        self,
        handles: list[ContainerHandle],
        diagnostics: list[Diagnostic],
        *,
        allow_rehydrate: bool = False,
    ) -> tuple[RealizationObservation, ...]:
        ownership_readback = self._readback_owned_container if allow_rehydrate else self._is_current_owned_container
        observations, observation_diagnostics = substrate_observations(
            handles,
            runtime=self._runtime,
            ownership_readback=ownership_readback,
        )
        diagnostics.extend(observation_diagnostics)
        return observations

    def observe(self, *, containers: tuple[ContainerSpec, ...]) -> DriverResult:
        """Inspect existing owned containers without invoking create or update."""

        diagnostics: list[Diagnostic] = []
        handles = [ContainerHandle(address=spec.address, realized=True) for spec in containers]
        observations = self._substrate_observations(handles, diagnostics, allow_rehydrate=True)
        return DriverResult(
            containers=tuple(handle for handle in handles if handle.address in self._realized),
            diagnostics=tuple(diagnostics),
            observations=observations,
        )

    def _realize_networks(
        self,
        networks: tuple[NetworkSpec, ...],
        diagnostics: list[Diagnostic],
    ) -> list[NetworkHandle]:
        handles: list[NetworkHandle] = []
        for spec in networks:
            runtime_name = provider_resource_name(spec.address, prefix="raes")
            argv = [self._runtime, "network", "create", *self._label_args(spec.address), runtime_name]
            ok, kind = self._run(argv)
            if ok:
                self._realized.add(spec.address)
                self._names[spec.address] = runtime_name
                handles.append(NetworkHandle(address=spec.address, realized=True))
            else:
                diagnostics.append(self._failure(spec.address, kind))
        return handles

    def _realize_containers(
        self,
        containers: tuple[ContainerSpec, ...],
        diagnostics: list[Diagnostic],
    ) -> list[ContainerHandle]:
        handles: list[ContainerHandle] = []
        for spec in self._ordered_containers(containers):
            target_diagnostic = self._current_target_diagnostic(spec)
            if target_diagnostic is not None:
                diagnostics.append(target_diagnostic)
                continue
            image = self._image_policy.image_for(spec.image_ref)
            if not self._image_policy.permits(image):
                diagnostics.append(self._image_rejected(spec.address))
                continue
            runtime_name = provider_resource_name(spec.address, prefix="raes")
            argv = self._container_run_argv(spec, runtime_name=runtime_name, image=image)
            ok, kind, native_stdout = self._invoke(argv)
            if ok:
                self._record_realized_container(spec.address, runtime_name, native_stdout)
                handles.append(ContainerHandle(address=spec.address, realized=True))
            else:
                diagnostics.append(self._failure(spec.address, kind))
        return handles

    def _current_target_diagnostic(self, spec: ContainerSpec) -> Diagnostic | None:
        target = spec.network_namespace_target
        if target and not self._is_current_owned_container(target):
            return self._network_namespace_diagnostic(
                spec.address,
                code=_CODE_NETWORK_NAMESPACE_TARGET_UNAVAILABLE,
                message="The network namespace target is not a current run-owned container.",
            )
        return None

    def _container_run_argv(self, spec: ContainerSpec, *, runtime_name: str, image: str) -> list[str]:
        return [
            self._runtime,
            "run",
            "--detach",
            "--rm",
            *self._label_args(spec.address),
            "--name",
            runtime_name,
            # Attach the container to every requested network created in this
            # transaction, or to its verified namespace owner.
            *self._network_args(spec),
            image,
            # Fixed keep-alive so generic images do not exit immediately.
            *self._keep_alive,
        ]

    def _record_realized_container(self, address: str, runtime_name: str, native_stdout: str) -> None:
        self._realized.add(address)
        self._names[address] = runtime_name
        native_id = native_stdout.strip().splitlines()[0] if native_stdout.strip() else ""
        if native_id:
            self._native_ids[address] = native_id

    def _network_args(self, spec: ContainerSpec) -> list[str]:
        if spec.network_namespace_target:
            return ["--network", f"container:{self._name_for(spec.network_namespace_target)}"]
        args: list[str] = []
        for address in spec.networks:
            args.extend(("--network", self._name_for(address)))
        return args

    def _network_namespace_diagnostics(self, containers: tuple[ContainerSpec, ...]) -> list[Diagnostic]:
        # Namespace sharing is a transaction-local relation. A prior realized
        # address may now name a replaced runtime object and is never sufficient
        # proof of ownership for a new join.
        available = {spec.address for spec in containers}
        diagnostics: list[Diagnostic] = []
        for spec in containers:
            target = spec.network_namespace_target
            if not target:
                continue
            if spec.networks:
                diagnostics.append(
                    self._network_namespace_diagnostic(
                        spec.address,
                        code=_CODE_NETWORK_NAMESPACE_CONFLICT,
                        message="A shared network namespace cannot be combined with independent networks.",
                    )
                )
            elif target == spec.address or target not in available:
                diagnostics.append(
                    self._network_namespace_diagnostic(
                        spec.address,
                        code=_CODE_NETWORK_NAMESPACE_TARGET_UNAVAILABLE,
                        message="The network namespace target is not a run-owned container.",
                    )
                )
        return diagnostics

    def _is_current_owned_container(self, address: str) -> bool:
        return self._owned_container_readback(address, require_known_native_id=True)

    def _readback_owned_container(self, address: str) -> bool:
        return self._owned_container_readback(address, require_known_native_id=False)

    def _owned_container_readback(self, address: str, *, require_known_native_id: bool) -> bool:
        expected_native_id = self._native_ids.get(address)
        expected_name = self._name_for(address)
        if not expected_name or (expected_native_id is None and require_known_native_id):
            return False
        fields = self._inspect_container_ownership(expected_name)
        if fields is None or not ownership_fields_match(
            fields,
            address=address,
            expected_name=expected_name,
            expected_native_id=expected_native_id,
            workspace=self._workspace,
        ):
            return False
        native_id = fields[0]
        self._native_ids[address] = native_id
        self._names[address] = expected_name
        self._realized.add(address)
        return True

    def _inspect_container_ownership(self, expected_name: str) -> list[str] | None:
        ok, _kind, stdout = self._invoke(
            [
                self._runtime,
                "inspect",
                "--format",
                _OWNERSHIP_INSPECT_FORMAT,
                expected_name,
            ]
        )
        fields = stdout.rstrip("\n").split("\n")
        return fields if ok and len(fields) == 4 else None

    @staticmethod
    def _ordered_containers(containers: tuple[ContainerSpec, ...]) -> tuple[ContainerSpec, ...]:
        by_address = {spec.address: spec for spec in containers}
        ordered: list[ContainerSpec] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(address: str) -> None:
            if address in visited or address in visiting:
                return
            visiting.add(address)
            spec = by_address[address]
            if spec.network_namespace_target in by_address:
                visit(spec.network_namespace_target)
            visiting.remove(address)
            visited.add(address)
            ordered.append(spec)

        for address in sorted(by_address):
            visit(address)
        return tuple(ordered)

    @staticmethod
    def _network_namespace_diagnostic(address: str, *, code: str, message: str) -> Diagnostic:
        return Diagnostic(
            code=code,
            domain=_DOMAIN,
            address=address,
            message=f"Container runtime rejected network namespace sharing for '{address}': {message}",
            severity=Severity.ERROR,
        )

    def _rollback(
        self,
        networks: list[NetworkHandle],
        containers: list[ContainerHandle],
    ) -> None:
        realized_containers = tuple(handle.address for handle in containers if handle.realized)
        realized_networks = tuple(handle.address for handle in networks if handle.realized)
        if realized_containers or realized_networks:
            self.destroy(networks=realized_networks, containers=realized_containers)

    def _name_for(self, address: str) -> str:
        return self._names.get(address, provider_resource_name(address, prefix="raes"))

    def destroy(
        self,
        *,
        networks: tuple[str, ...],
        containers: tuple[str, ...],
    ) -> DriverResult:
        diagnostics: list[Diagnostic] = []
        container_handles: list[ContainerHandle] = []
        for address in containers:
            argv = [self._runtime, "rm", "--force", self._name_for(address)]
            ok, kind = self._run(argv)
            if ok:
                # Only forget the resource once it is actually gone; a failed
                # teardown stays tracked so a retry can reconcile it.
                self._realized.discard(address)
                self._names.pop(address, None)
                self._native_ids.pop(address, None)
            else:
                diagnostics.append(self._failure(address, kind))
            container_handles.append(ContainerHandle(address=address, realized=not ok))
        network_handles: list[NetworkHandle] = []
        for address in networks:
            argv = [self._runtime, "network", "rm", self._name_for(address)]
            ok, kind = self._run(argv)
            if ok:
                self._realized.discard(address)
                self._names.pop(address, None)
            else:
                diagnostics.append(self._failure(address, kind))
            network_handles.append(NetworkHandle(address=address, realized=not ok))
        return DriverResult(
            networks=tuple(network_handles),
            containers=tuple(container_handles),
            diagnostics=tuple(diagnostics),
        )

    def realized_addresses(self) -> frozenset[str]:
        return frozenset(self._realized)

    @staticmethod
    def _failure(address: str, kind: str | None) -> Diagnostic:
        code = _KIND_TO_CODE.get(kind or "command-failed", _CODE_COMMAND_FAILED)
        message = {
            _CODE_TIMEOUT: f"Container runtime operation for '{address}' exceeded the bounded timeout.",
            _CODE_RUNTIME_UNAVAILABLE: f"Container runtime is unavailable for '{address}'.",
            _CODE_COMMAND_FAILED: f"Container runtime operation for '{address}' did not succeed.",
        }[code]
        return Diagnostic(code=code, domain=_DOMAIN, address=address, message=message, severity=Severity.ERROR)

    @staticmethod
    def _image_rejected(address: str) -> Diagnostic:
        # The rejected image ref is plan-controlled; keep it out of the message
        # so the diagnostic never echoes attacker-chosen content.
        return Diagnostic(
            code=_CODE_IMAGE_NOT_ALLOWED,
            domain=_DOMAIN,
            address=address,
            message=(
                f"Container image for '{address}' is not permitted by the driver image-trust policy; "
                "configure default_image, allowed_images, or a digest-pinned ref."
            ),
            severity=Severity.ERROR,
        )

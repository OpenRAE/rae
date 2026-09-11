"""Lazy libvirt connection adapter for the libvirt/QEMU backend."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import cast

from raes_backend_protocols.naming import provider_resource_name
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.realization_envelope import ObservationStrength, RealizationConcern
from raes_contracts.realization_observation import RealizationObservation

from raes_backend_libvirt._observability import record_suppressed_failure as _record_suppressed_failure
from raes_backend_libvirt.driver import (
    DomainHandle,
    DomainSpec,
    DriverResult,
    NetworkHandle,
    NetworkSpec,
)

from ...envelopes import load_libvirt_realization_envelope
from .._libvirt_xml import _domain_xml, _network_xml, _nwfilter_xml
from ..seed import _SEED_DIR_MODE, GenisoimageSeedBuilder, SeedBuilder, write_seed_files
from ._deployment_batch import realize_domain_specs, realize_network_specs
from ._deployment_diagnostics import (
    _CODE_OPERATION_FAILED,
    _CODE_OWNERSHIP_CONFLICT,
    _CODE_UNAVAILABLE,
    _CONNECTION_ADDRESS,
    _failure,
)
from ._native import (
    Connector,
    _call_libvirt,
    _default_connector,
    _existing_uuid,
    _filter_owner_uuid,
    _find_native,
    _is_absence_error,
    _NativeLookupError,
    _NativeResource,
    _OwnershipConflict,
    _raes_uuid,
    _safe_name,
    _stop_native,
)

_DEFAULT_CONNECTION_URI = "qemu:///system"
_WORKSPACE_PREFIX = "raes-libvirt-"


class LibvirtDeploymentDriver:
    """Realize portable specs against a libvirt connection."""

    driver_mode = "generic"

    def __init__(
        self,
        *,
        connection: object | None = None,
        connection_uri: str = _DEFAULT_CONNECTION_URI,
        connector: Connector | None = None,
        name_prefix: str = "raes",
        workspace: str | Path | None = None,
        seed_builder: SeedBuilder | None = None,
    ) -> None:
        if not connection_uri or not connection_uri.strip():
            raise ValueError("LibvirtDeploymentDriver connection_uri must be non-empty.")
        if not name_prefix or not name_prefix.strip():
            raise ValueError("LibvirtDeploymentDriver name_prefix must be non-empty.")
        self._connection = connection
        self._connection_uri = connection_uri
        self._connector = connector or _default_connector
        self._name_prefix = _safe_name(name_prefix, fallback="raes", prefix="")
        self._workspace = Path(workspace) if workspace is not None else None
        self._seed_builder = seed_builder if seed_builder is not None else GenisoimageSeedBuilder()
        self._names: dict[str, str] = {}
        self._realized: set[str] = set()
        self._seeds: dict[str, Path] = {}
        self._filters: dict[str, str] = {}

    def realize(
        self,
        *,
        networks: tuple[NetworkSpec, ...],
        domains: tuple[DomainSpec, ...],
    ) -> DriverResult:
        diagnostics: list[Diagnostic] = []
        network_handles: list[NetworkHandle] = []
        domain_handles: list[DomainHandle] = []
        # Addresses this call newly created (no owned object pre-existed). Only
        # these are rolled back on failure — never a pre-existing resource an
        # UPDATE converged, whose destruction would contradict the baseline
        # snapshot the failed apply preserves.
        created_networks: list[str] = []
        created_domains: list[str] = []
        try:
            connection = self._conn()
        except Exception as exc:
            _record_suppressed_failure("realize", exc)
            return DriverResult(diagnostics=(_failure(_CONNECTION_ADDRESS, _CODE_UNAVAILABLE),))

        realize_network_specs(self, connection, networks, created_networks, network_handles, diagnostics)
        realize_domain_specs(
            self,
            connection,
            domains,
            created_domains,
            domain_handles,
            diagnostics,
        )

        if diagnostics:
            # Roll back only newly-created objects — including a domain whose XML was
            # defined before native.create() failed — so a partial CREATE never
            # orphans a defined domain, its seed media, or its nwfilter, while a
            # pre-existing resource an UPDATE converged is left intact (its baseline
            # snapshot entry remains truthful). destroy() is idempotent and
            # ownership-safe, so a never-defined address is a harmless no-op.
            self._rollback(created_networks, created_domains)
            return DriverResult(diagnostics=tuple(diagnostics))
        return DriverResult(
            networks=tuple(network_handles),
            domains=tuple(domain_handles),
        )

    @staticmethod
    def _operation_failure(address: str) -> Diagnostic:
        return _failure(address, _CODE_OPERATION_FAILED)

    def _compute_substrate_observation(
        self,
        connection: object,
        address: str,
        *,
        sequence: int,
    ) -> RealizationObservation | None:
        """Read the current owned domain back from libvirt after realization."""

        observation = None
        lookup = getattr(connection, "lookupByName", None)
        if callable(lookup):
            try:
                native = lookup(self._name_for(address))
                active = getattr(native, "isActive", None)
                owned_and_active = _existing_uuid(native) == _raes_uuid(address) and callable(active) and active() == 1
            except Exception as exc:
                _record_suppressed_failure("_compute_substrate_observation", exc)
                owned_and_active = False
            if owned_and_active:
                envelope = load_libvirt_realization_envelope(self.driver_mode)
                observation = RealizationObservation(
                    address=address,
                    field_path="compute-substrate",
                    concern=RealizationConcern.COMPUTE_SUBSTRATE,
                    source=ObservationStrength.DAEMON_OBSERVED,
                    value="virtual-machine",
                    envelope_digest=envelope.digest,
                    configuration_digest=envelope.configuration.configuration_digest,
                    observer_version="libvirt-domain-readback/v1",
                    sequence=sequence,
                    binding_verified=True,
                )
        return observation

    def observe(self, *, domains: tuple[DomainSpec, ...]) -> DriverResult:
        """Read current owned domains without converging or restarting them."""

        try:
            connection = self._conn()
        except Exception as exc:
            _record_suppressed_failure("observe", exc)
            return DriverResult(diagnostics=(_failure(_CONNECTION_ADDRESS, _CODE_UNAVAILABLE),))
        observations: list[RealizationObservation] = []
        diagnostics: list[Diagnostic] = []
        handles: list[DomainHandle] = []
        for spec in domains:
            observation = self._compute_substrate_observation(
                connection,
                spec.address,
                sequence=len(observations),
            )
            if observation is None:
                diagnostics.append(_failure(spec.address, _CODE_OPERATION_FAILED))
                continue
            self._realized.add(spec.address)
            handles.append(DomainHandle(address=spec.address, realized=True))
            observations.append(observation)
        return DriverResult(
            domains=tuple(handles),
            diagnostics=tuple(diagnostics),
            observations=tuple(observations),
        )

    def _realize_network(self, connection: object, spec: NetworkSpec, created: list[str]) -> Diagnostic | None:
        """Realize one network, or return a redacted failure diagnostic.

        Records the address in ``created`` when no owned object pre-existed so a
        partial define is rolled back; on success adds it to the realized set.
        """

        name = self._runtime_name(spec.address, spec.name)
        # Record the runtime name before touching the host so a partial define can
        # still be located and rolled back by address; the value is deterministic,
        # so re-setting it on success is a no-op.
        self._names[spec.address] = name
        try:
            # The provisioner only dispatches CREATE/UPDATE specs (UNCHANGED is
            # filtered upstream), so a spec that reaches the driver must be
            # (re)applied. Converge any object a prior apply left behind — stop it
            # and drop its stale definition — before redefining, so the new state is
            # genuinely enforced and no duplicate is ever created.
            pre_existing = self._converge_existing(connection, "networkLookupByName", name, spec.address)
            if not pre_existing:
                created.append(spec.address)
            network_xml = _network_xml(spec, name, _raes_uuid(spec.address))
            native = _call_libvirt(connection, "networkDefineXML", network_xml)
            native.create()
        except _OwnershipConflict:
            return _failure(spec.address, _CODE_OWNERSHIP_CONFLICT)
        except Exception as exc:
            _record_suppressed_failure("_realize_network", exc)
            return _failure(spec.address, _CODE_OPERATION_FAILED)
        self._realized.add(spec.address)
        return None

    def _realize_domain(self, connection: object, spec: DomainSpec, created: list[str]) -> Diagnostic | None:
        """Realize one domain (plus its seed media and nwfilter), or return a failure.

        Records the address in ``created`` when no owned object pre-existed so a
        partial define is rolled back; on success adds it to the realized set.
        """

        name = self._runtime_name(spec.address, spec.name)
        self._names[spec.address] = name
        network_names = tuple(self._name_for(address) for address in spec.networks)
        try:
            # Converge first so a tightened ACL, a disabled account, a changed
            # seed/image, or an existing-but-inactive domain is actually applied —
            # never silently skipped while reporting realized.
            pre_existing = self._converge_existing(connection, "lookupByName", name, spec.address)
            if not pre_existing:
                created.append(spec.address)
            seed_path = self._build_seed(spec, name)
            filter_name = self._define_nwfilter(connection, spec, name)
            xml = _domain_xml(spec, name, network_names, seed_path, _raes_uuid(spec.address), filter_name)
            native = _call_libvirt(connection, "defineXML", xml)
            native.create()
        except _OwnershipConflict:
            return _failure(spec.address, _CODE_OWNERSHIP_CONFLICT)
        except Exception as exc:
            _record_suppressed_failure("_realize_domain", exc)
            return _failure(spec.address, _CODE_OPERATION_FAILED)
        self._realized.add(spec.address)
        return None

    def destroy(
        self,
        *,
        networks: tuple[str, ...],
        domains: tuple[str, ...],
    ) -> DriverResult:
        diagnostics: list[Diagnostic] = []
        try:
            connection = self._conn()
        except Exception as exc:
            _record_suppressed_failure("destroy", exc)
            return DriverResult(diagnostics=(_failure(_CONNECTION_ADDRESS, _CODE_UNAVAILABLE),))

        domain_handles = self._destroy_domains(connection, domains, diagnostics)
        network_handles = self._destroy_networks(connection, networks, diagnostics)

        return DriverResult(
            networks=tuple(network_handles),
            domains=tuple(domain_handles),
            diagnostics=tuple(diagnostics),
        )

    def _destroy_domains(
        self,
        connection: object,
        addresses: tuple[str, ...],
        diagnostics: list[Diagnostic],
    ) -> list[DomainHandle]:
        handles: list[DomainHandle] = []
        for address in addresses:
            try:
                ok = self._destroy_one(connection, "lookupByName", address)
            except _OwnershipConflict:
                diagnostics.append(_failure(address, _CODE_OWNERSHIP_CONFLICT))
                handles.append(DomainHandle(address=address, realized=True))
                continue
            if ok:
                self._realized.discard(address)
                self._names.pop(address, None)
                self._cleanup_seed(address)
                self._undefine_nwfilter(connection, address)
            else:
                diagnostics.append(_failure(address, _CODE_OPERATION_FAILED))
            handles.append(DomainHandle(address=address, realized=not ok))
        return handles

    def _destroy_networks(
        self,
        connection: object,
        addresses: tuple[str, ...],
        diagnostics: list[Diagnostic],
    ) -> list[NetworkHandle]:
        handles: list[NetworkHandle] = []
        for address in addresses:
            try:
                ok = self._destroy_one(connection, "networkLookupByName", address)
            except _OwnershipConflict:
                diagnostics.append(_failure(address, _CODE_OWNERSHIP_CONFLICT))
                handles.append(NetworkHandle(address=address, realized=True))
                continue
            if ok:
                self._realized.discard(address)
                self._names.pop(address, None)
            else:
                diagnostics.append(_failure(address, _CODE_OPERATION_FAILED))
            handles.append(NetworkHandle(address=address, realized=not ok))
        return handles

    def realized_addresses(self) -> frozenset[str]:
        return frozenset(self._realized)

    def _conn(self) -> object:
        if self._connection is None:
            self._connection = self._connector(self._connection_uri)
        if self._connection is None:
            raise RuntimeError("libvirt connection unavailable")
        return self._connection

    def _runtime_name(self, address: str, preferred: str) -> str:
        del preferred
        return provider_resource_name(address, prefix=self._name_prefix)

    def _name_for(self, address: str) -> str:
        return self._names.get(address, self._runtime_name(address, ""))

    def _build_seed(self, spec: DomainSpec, name: str) -> Path | None:
        cloud_init = spec.cloud_init
        if cloud_init is None or cloud_init.is_empty:
            return None
        seed_dir = self._seed_workspace() / name
        write_seed_files(cloud_init, seed_dir)
        seed_path = self._seed_builder.build(seed_dir=seed_dir)
        self._seeds[spec.address] = seed_path
        return seed_path

    def _seed_workspace(self) -> Path:
        if self._workspace is None:
            # mkdtemp atomically creates an unpredictable directory; relax it to
            # 0o711 (traversable, not listable) so the libvirt/QEMU process can
            # reach the attached seed ISO while other local users still cannot
            # enumerate it or read the 0o600 source files inside.
            self._workspace = Path(tempfile.mkdtemp(prefix=_WORKSPACE_PREFIX))
            os.chmod(self._workspace, _SEED_DIR_MODE)
        else:
            # A configured workspace is attacker-influenceable, so verify it
            # resolves to a directory we own and is not a symlink before trusting
            # it to hold rendered seed content.
            workspace = self._workspace
            if workspace.is_symlink():
                raise PermissionError(f"seed workspace '{workspace}' is a symlink")
            workspace.mkdir(parents=True, exist_ok=True)
            info = os.lstat(workspace)
            if info.st_uid != os.getuid():
                raise PermissionError(f"seed workspace '{workspace}' is not owned by the current user")
            os.chmod(workspace, _SEED_DIR_MODE)
        return self._workspace

    def _cleanup_seed(self, address: str) -> None:
        seed_path = self._seeds.pop(address, None)
        if seed_path is not None:
            shutil.rmtree(seed_path.parent, ignore_errors=True)

    def _define_nwfilter(self, connection: object, spec: DomainSpec, name: str) -> str | None:
        if not spec.network_acls:
            return None
        filter_name = _safe_name(f"{name}-acl", fallback="acl", prefix="")
        owner = _filter_owner_uuid(spec.address)
        # nwfilters are host-global and named-only, so — like domains/networks —
        # refuse to redefine a filter at this name unless it is owner-stamped for
        # this RAES address. A foreign filter (or one for another address that
        # normalizes to the same name) is never overwritten; apply fails closed.
        # Unlike domain/network definition, nwfilterDefineXML is an upsert and
        # cannot surface a lookup failure as a later duplicate-name conflict.
        # Distinguish proven absence from every other lookup failure here so a
        # mismatched native error can never authorize replacing a host-global
        # filter whose ownership was not verified.
        existing = _find_native(connection, "nwfilterLookupByName", filter_name)
        if existing is not None and _existing_uuid(existing) != owner:
            raise _OwnershipConflict(filter_name)
        define = getattr(connection, "nwfilterDefineXML", None)
        if define is not None:
            # nwfilterDefineXML is upsert: redefining replaces our own filter in
            # place, so a tightened/loosened ACL on re-apply is genuinely enforced.
            define(_nwfilter_xml(filter_name, owner, spec.network_acls))
        self._filters[spec.address] = filter_name
        return filter_name

    @staticmethod
    def _converge_existing(connection: object, lookup_method: str, name: str, address: str) -> bool:
        """Stop and undefine the RAES object this apply owns at ``name``.

        Convergence is destructive, so it only proceeds when the existing object's
        UUID proves it is the RAES realization of *this* ``address``. A name hit
        whose UUID is absent or different — a foreign object, or one realized for a
        different RAES address that merely normalizes to the same name — raises
        :class:`_OwnershipConflict` so the apply fails closed instead of replacing
        an object it does not own. A running object we own is stopped first via
        :func:`_stop_native`, which tolerates an already-inactive object but lets a
        permission/internal stop failure propagate — so convergence never undefines
        (and silently replaces) a domain it could not actually stop.

        Returns True when an existing RAES-owned object was converged (this address
        is an UPDATE of a pre-existing resource) and False when none existed (a
        fresh CREATE). Callers use this to roll back only newly-created objects on
        failure, never a pre-existing resource an UPDATE would otherwise destroy.
        """

        native = _find_native(connection, lookup_method, name)
        if native is None:
            return False
        if _existing_uuid(native) != _raes_uuid(address):
            raise _OwnershipConflict(name)
        _stop_native(native)
        cast(_NativeResource, native).undefine()
        return True

    def _undefine_nwfilter(self, connection: object, address: str) -> None:
        filter_name = self._filters.get(address)
        if filter_name is None:
            return
        try:
            native = _find_native(connection, "nwfilterLookupByName", filter_name)
        except _NativeLookupError as exc:
            _record_suppressed_failure("_undefine_nwfilter", exc.__cause__ or exc)
            return
        if native is None:
            self._filters.pop(address, None)
        elif _existing_uuid(native) != _filter_owner_uuid(address):
            # A filter at this name we do not own must never be undefined.
            self._filters.pop(address, None)
        else:
            # Best-effort cleanup of our own filter: a filter that cannot be
            # undefined (in use, missing) must not fail the destroy.
            try:
                cast(_NativeResource, native).undefine()
            except Exception as exc:
                if _is_absence_error(exc):
                    self._filters.pop(address, None)
                else:
                    _record_suppressed_failure("_undefine_nwfilter", exc)
            else:
                self._filters.pop(address, None)

    def _destroy_one(self, connection: object, lookup_method: str, address: str) -> bool:
        removed = True
        try:
            native = _find_native(connection, lookup_method, self._name_for(address))
        except _NativeLookupError as exc:
            # Connection/permission/internal lookup failure: fail closed so the
            # snapshot is preserved for retry instead of claiming the object gone.
            _record_suppressed_failure("_destroy_one", exc.__cause__ or exc)
            removed = False
        else:
            # A None result is genuine absence — teardown is idempotently satisfied.
            # A present object is torn down only when its UUID proves RAES ownership
            # (the same invariant as convergence), never a foreign name collision.
            if native is not None:
                if _existing_uuid(native) != _raes_uuid(address):
                    raise _OwnershipConflict(address)
                try:
                    _stop_native(native)
                    cast(_NativeResource, native).undefine()
                except Exception as exc:
                    # An object that vanished between lookup and undefine is still torn
                    # down; a stop/undefine that failed for permission or an internal
                    # reason fails closed and preserves the snapshot for retry.
                    removed = _is_absence_error(exc)
                    if not removed:
                        _record_suppressed_failure("_destroy_one", exc)
        return removed

    def _rollback(self, networks: list[str], domains: list[str]) -> None:
        if networks or domains:
            self.destroy(networks=tuple(networks), domains=tuple(domains))

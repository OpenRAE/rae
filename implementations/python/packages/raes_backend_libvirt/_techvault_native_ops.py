"""Diagnostic codes and low-level native-object helpers for the TechVault driver.

Holds the shared diagnostic-code constants, the native-resource protocol, and the
thin libvirt-call/name-availability/artifact-token/diagnostic helpers used by the
native TechVault driver and its teardown paths. Split from
:mod:`raes_backend_libvirt.techvault_native` to keep that module under the ADR-015
source-size cap; the driver re-imports these names so existing call sites and the
guest-certified subclass's ``_artifact_token`` import stay stable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, cast

from raes_contracts.diagnostics import Diagnostic, Severity

from .drivers.libvirt import _existing_uuid, _is_expected_lookup_absence, _raes_uuid
from .techvault_lifecycle import (
    NativeOwnershipConflict as _OwnershipConflict,
)

_DOMAIN = "runtime"
_CODE_OPERATION_FAILED = "libvirt-backend.techvault-native.operation-failed"
_CODE_KERNEL_UNAVAILABLE = "libvirt-backend.techvault-native.kernel-unavailable"
_CODE_GUEST_FRESHNESS_UNAVAILABLE = "libvirt-backend.guest.freshness-preflight-failed"
_CODE_OWNERSHIP_CONFLICT = "libvirt-backend.techvault-native.ownership-conflict"
_CODE_READBACK_FAILED = "libvirt-backend.techvault-native.readback-failed"
_CODE_RESIDUAL_STATE = "libvirt-backend.techvault-native.residual-state"
_CODE_UNAVAILABLE = "libvirt-backend.techvault-native.unavailable"
_CODE_TOOLCHAIN_UNAVAILABLE = "libvirt-backend.techvault-native.initramfs-toolchain-unavailable"
_DEFAULT_CONNECTION_URI = "qemu:///system"


class _NativeResource(Protocol):
    def create(self) -> None: ...

    def destroy(self) -> None: ...

    def undefine(self) -> None: ...


def _call(connection: object, method_name: str, payload: str) -> _NativeResource:
    method = cast(Callable[[str], _NativeResource], getattr(connection, method_name))
    return method(payload)


def _ensure_name_available(connection: object, method_name: str, name: str, address: str) -> None:
    method = getattr(connection, method_name, None)
    if not callable(method):
        raise RuntimeError("native lookup is unavailable")
    try:
        native = method(name)
    except Exception as exc:
        if _is_expected_lookup_absence(exc, method_name):
            return
        raise
    if _existing_uuid(native) != _raes_uuid(address):
        raise _OwnershipConflict(address)
    raise RuntimeError("owned native object already exists for CREATE")


def _artifact_token(address: str) -> str:
    return _raes_uuid(address).replace("-", "")


_MESSAGES = {
    _CODE_GUEST_FRESHNESS_UNAVAILABLE: (
        "A fresh guest challenge and empty fact channel could not be established before native mutation."
    ),
    _CODE_KERNEL_UNAVAILABLE: "The configured kernel is not a readable regular file; refusing native mutation.",
    _CODE_TOOLCHAIN_UNAVAILABLE: (
        "The injected or discovered initramfs executable failed static target-toolchain preflight."
    ),
    _CODE_UNAVAILABLE: "Libvirt connection is unavailable for native TechVault realization.",
    _CODE_RESIDUAL_STATE: "TechVault rollback could not verify cleanup for '{address}'; residual state may remain.",
    _CODE_OWNERSHIP_CONFLICT: "Native object for '{address}' is not owned by that RAES address; refusing mutation.",
    _CODE_READBACK_FAILED: "Native libvirt TechVault readback for '{address}' did not succeed.",
}
_DEFAULT_MESSAGE = "Native libvirt TechVault operation for '{address}' did not succeed."


def _diagnostic(code: str, address: str) -> Diagnostic:
    message = _MESSAGES.get(code, _DEFAULT_MESSAGE).format(address=address)
    return Diagnostic(code=code, domain=_DOMAIN, address=address, message=message, severity=Severity.ERROR)

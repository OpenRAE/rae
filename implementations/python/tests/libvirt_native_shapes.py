"""Captured libvirt shapes for the hermetic TechVault libvirt fakes (issue #1344).

The TechVault-family tests fake libvirt without a daemon. Real libvirt reports a
missing object as ``libvirt.libvirtError`` with a ``VIR_ERR_NO_*`` code, never as
``KeyError``, and ``XMLDesc`` returns libvirt's normalized readback, not the XML
that was defined. ``data/boundary_captures/libvirt-test-driver.json`` records both
for production-rendered TechVault XML. The fakes raise its lookup errors and apply
libvirt's memory and vcpu normalization, which a test checks against its readback.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType

import pytest

CAPTURE_PATH = Path(__file__).parent / "data" / "boundary_captures" / "libvirt-test-driver.json"
CAPTURE = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
_KIB_PER_UNIT = {"KiB": 1, "MiB": 1024, "GiB": 1024 * 1024}


class LibvirtError(Exception):
    """Stand-in for ``libvirt.libvirtError`` exposing ``get_error_code()``."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self._code = code

    def get_error_code(self) -> int:
        return self._code


def install_libvirt_error_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register the stand-in as the loaded binding's error type, as the real import would."""

    module = ModuleType("libvirt")
    module.libvirtError = LibvirtError
    monkeypatch.setitem(sys.modules, "libvirt", module)


def lookup(objects: Mapping[str, object], name: str, method_name: str) -> object:
    """Return ``objects[name]`` or raise the error libvirt raised for ``method_name`` on a missing name."""

    try:
        return objects[name]
    except KeyError:
        missing = CAPTURE["absence"][method_name]
        raise LibvirtError(missing["code"], missing["message"]) from None


def libvirt_readback(defined_xml: str) -> str:
    """Return ``defined_xml`` as libvirt reads it back: memory in KiB with ``currentMemory``, static vcpu placement."""

    if not defined_xml:
        return defined_xml
    root = ET.fromstring(defined_xml)  # noqa: S314 - test-generated XML
    memory = root.find("memory")
    if memory is not None and memory.text is not None:
        kib = str(int(memory.text) * _KIB_PER_UNIT[memory.get("unit", "KiB")])
        memory.attrib = {"unit": "KiB"}
        memory.text = kib
        current = ET.Element("currentMemory", {"unit": "KiB"})
        current.text = kib
        root.insert(list(root).index(memory) + 1, current)
    vcpu = root.find("vcpu")
    if vcpu is not None:
        vcpu.set("placement", "static")
    return ET.tostring(root, encoding="unicode")

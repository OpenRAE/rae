"""Bounded daemon observations and source-separated TechVault reports."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import xml.etree.ElementTree as StdET
from collections.abc import Mapping, Sequence
from pathlib import Path

from defusedxml import ElementTree as SafeET
from raes_contracts.realization_envelope import ObservationStrength, RealizationConcern

from .driver import RealizationObservation
from .techvault_matrix import as_sequence

_SUBSTRATE = "libvirt-qemu-initramfs"
_MAX_NATIVE_XML_CHARS = 1_000_000


def network_observations(
    native: object,
    expected: Mapping[str, object],
) -> tuple[RealizationObservation, ...]:
    root = native_xml(native)
    address = str(expected.get("address", ""))
    active = native_active(native)
    actual_name = root.findtext("name", default="")
    ip_node = root.find("ip")
    gateway = "" if ip_node is None else ip_node.get("address", "")
    netmask = "" if ip_node is None else ip_node.get("netmask", "")
    cidr = str(ipaddress.ip_network(f"{gateway}/{netmask}", strict=False)) if gateway and netmask else ""
    forward = root.find("forward")
    internal = forward is None
    forward_mode = "none" if forward is None else forward.get("mode", "")
    return (
        observation(
            address,
            "exists",
            RealizationConcern.TOPOLOGY,
            active and actual_name == expected.get("runtime_name"),
        ),
        observation(address, "native-name", RealizationConcern.TOPOLOGY, actual_name),
        observation(address, "cidr", RealizationConcern.NETWORK, cidr),
        observation(address, "gateway", RealizationConcern.NETWORK, gateway),
        observation(address, "internal", RealizationConcern.NETWORK, internal),
        observation(address, "forward-mode", RealizationConcern.NETWORK, forward_mode),
    )


def domain_observations(
    native: object,
    expected: Mapping[str, object],
    network_addresses: Mapping[str, str],
    *,
    kernel: Path,
    initrd: Path,
) -> tuple[RealizationObservation, ...]:
    root = native_xml(native)
    address = str(expected.get("address", ""))
    active = native_active(native)
    actual_name = root.findtext("name", default="")
    os_type = root.find("./os/type")
    architecture = "" if os_type is None else os_type.get("arch", "")
    image_policy = (
        "generated-initramfs-appliance"
        if root.findtext("./os/kernel") == str(kernel)
        and root.findtext("./os/initrd") == str(initrd)
        and root.find("./os/loader") is None
        and root.find("./os/nvram") is None
        and root.find("./devices/disk") is None
        else ""
    )
    attachments = tuple(
        network_addresses.get(source.get("network", "")) for source in root.findall("./devices/interface/source")
    )
    return (
        observation(
            address,
            "exists",
            RealizationConcern.TOPOLOGY,
            active and actual_name == expected.get("runtime_name"),
        ),
        observation(address, "native-name", RealizationConcern.TOPOLOGY, actual_name),
        observation(address, "architecture", RealizationConcern.ARCHITECTURE, architecture),
        observation(address, "image-policy", RealizationConcern.IMAGE, image_policy),
        observation(address, "memory-mib", RealizationConcern.RESOURCE_ALLOCATION, memory_mib(root)),
        observation(address, "vcpus", RealizationConcern.RESOURCE_ALLOCATION, xml_int(root.findtext("vcpu"))),
        observation(address, "network-attachments", RealizationConcern.NETWORK, attachments),
    )


def substrate_observation(address: str) -> RealizationObservation:
    from .envelopes import LibvirtDriverMode, load_libvirt_realization_envelope

    envelope = load_libvirt_realization_envelope(LibvirtDriverMode.TECHVAULT_APPLIANCE)
    return RealizationObservation(
        address=address,
        field_path="compute-substrate",
        concern=RealizationConcern.COMPUTE_SUBSTRATE,
        source=ObservationStrength.DAEMON_OBSERVED,
        value="virtual-machine",
        envelope_digest=envelope.digest,
        configuration_digest=envelope.configuration.configuration_digest,
        observer_version="libvirt-domain-xml-readback/v1",
        sequence=0,
        binding_verified=True,
    )


def snapshot_from_observations(
    matrix: Mapping[str, object],
    observations: Sequence[RealizationObservation],
    *,
    binding: Mapping[str, object],
) -> dict[str, object]:
    values = {(item.address, item.field_path): item.value for item in observations}
    networks = [
        {
            "address": str(item.get("address", "")),
            "name": values.get((str(item.get("address", "")), "native-name")),
            "cidr": values.get((str(item.get("address", "")), "cidr")),
            "gateway": values.get((str(item.get("address", "")), "gateway")),
            "internal": values.get((str(item.get("address", "")), "internal")),
            "forward_mode": values.get((str(item.get("address", "")), "forward-mode")),
            "observation_source": ObservationStrength.DAEMON_OBSERVED.value,
        }
        for item in as_sequence(matrix.get("networks"))
        if isinstance(item, Mapping) and values.get((str(item.get("address", "")), "exists")) is True
    ]
    domains = [
        {
            "address": str(item.get("address", "")),
            "name": values.get((str(item.get("address", "")), "native-name")),
            "architecture": values.get((str(item.get("address", "")), "architecture")),
            "image_policy": values.get((str(item.get("address", "")), "image-policy")),
            "memory_mib": values.get((str(item.get("address", "")), "memory-mib")),
            "vcpus": values.get((str(item.get("address", "")), "vcpus")),
            "network_attachments": values.get((str(item.get("address", "")), "network-attachments"), ()),
            "observation_source": ObservationStrength.DAEMON_OBSERVED.value,
        }
        for item in as_sequence(matrix.get("domains"))
        if isinstance(item, Mapping) and values.get((str(item.get("address", "")), "exists")) is True
    ]
    return {
        "substrate": _SUBSTRATE,
        "source": ObservationStrength.DAEMON_OBSERVED.value,
        "domains": domains,
        "networks": networks,
        "realized_addresses": sorted([item["address"] for item in (*networks, *domains)]),
        "containers": [],
        "guest_observed": [],
        "binding": dict(binding),
    }


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def native_xml(native: object) -> StdET.Element:
    reader = getattr(native, "XMLDesc", None)
    if not callable(reader):
        raise TypeError("native resource does not expose XML readback")
    payload = reader(0)
    if not isinstance(payload, str):
        raise TypeError("native XML readback is not text")
    if len(payload) > _MAX_NATIVE_XML_CHARS:
        raise ValueError("native XML readback exceeds the bounded size limit")
    return SafeET.fromstring(payload)


def native_active(native: object) -> bool:
    reader = getattr(native, "isActive", None)
    if not callable(reader):
        return False
    return reader() == 1


def memory_mib(root: StdET.Element) -> int:
    memory = root.find("memory")
    if memory is None:
        return 0
    value = xml_int(memory.text)
    unit = memory.get("unit", "KiB").lower()
    factors = {"b": 1 / (1024 * 1024), "kib": 1 / 1024, "mib": 1, "gib": 1024}
    factor = factors.get(unit)
    return int(value * factor) if factor is not None else 0


def xml_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def observation(
    address: str,
    field_path: str,
    concern: RealizationConcern,
    value: object,
) -> RealizationObservation:
    return RealizationObservation(
        address=address,
        field_path=field_path,
        concern=concern,
        source=ObservationStrength.DAEMON_OBSERVED,
        value=value,
    )


__all__ = [
    "canonical_digest",
    "domain_observations",
    "file_digest",
    "network_observations",
    "snapshot_from_observations",
]

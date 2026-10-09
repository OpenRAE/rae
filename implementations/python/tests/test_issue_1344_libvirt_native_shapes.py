"""Issue #1344: drive the TechVault readers with what libvirt actually returned.

``data/boundary_captures/libvirt-test-driver.json`` holds libvirt 12.7.0 readbacks of
production-rendered TechVault XML. These tests keep that capture tied to today's
renderer, run the production readers and concern gate on it, and check that the
hermetic fakes report the same shape.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

from libvirt_native_shapes import CAPTURE, libvirt_readback
from raes_backend_libvirt.driver import DomainSpec, DriverResult, NetworkSpec, RealizationObservation
from raes_backend_libvirt.techvault_concerns import techvault_observation_diagnostics
from raes_backend_libvirt.techvault_matrix import domain_xml, native_matrix, network_xml
from raes_backend_libvirt.techvault_observation import domain_observations, network_observations

_ISOLATED = NetworkSpec(
    address="provision.network.lab",
    name="lab",
    cidr="192.0.2.0/24",
    gateway="192.0.2.1",
    labels={"internal": "true"},
)
_NAT = NetworkSpec(
    address="provision.network.natlab",
    name="natlab",
    cidr="198.51.100.0/24",
    gateway="198.51.100.1",
    labels={"internal": "false"},
)
_DOMAIN = DomainSpec(
    address="provision.node.demo",
    name="demo",
    image_ref=None,
    memory_mib=128,
    vcpus=2,
    networks=(_ISOLATED.address, _NAT.address),
)
_NETWORK_KEYS = ("network_isolated", "network_nat")
_KERNEL = Path(CAPTURE["rendered_by"]["kernel"])
_INITRD = Path(CAPTURE["rendered_by"]["initrd"])


def _matrix() -> dict[str, object]:
    return native_matrix(
        networks=(_ISOLATED, _NAT),
        domains=(_DOMAIN,),
        name_prefix=CAPTURE["rendered_by"]["name_prefix"],
    )


def _observations(xml_by_key: Mapping[str, str]) -> tuple[RealizationObservation, ...]:
    matrix = _matrix()
    networks = matrix["networks"]
    domain = matrix["domains"][0]
    observed: list[RealizationObservation] = []
    for key, network in zip(_NETWORK_KEYS, networks, strict=True):
        observed.extend(network_observations(_readback(xml_by_key[key]), network))
    observed.extend(
        domain_observations(
            _readback(xml_by_key["domain"]),
            domain,
            {str(network["runtime_name"]): str(network["address"]) for network in networks},
            kernel=_KERNEL,
            initrd=_INITRD,
        )
    )
    return tuple(observed)


def _readback(xml: str) -> SimpleNamespace:
    # Every captured object was started with create() before its readback.
    return SimpleNamespace(XMLDesc=lambda _flags: xml, isActive=lambda: 1)


def _values(observations: tuple[RealizationObservation, ...]) -> dict[tuple[str, str], object]:
    return {(item.address, item.field_path): item.value for item in observations}


def test_captured_input_is_what_the_renderer_produces_today() -> None:
    # A renderer change makes the capture stale: re-run the capture procedure it records.
    matrix = _matrix()
    rendered = {
        "network_isolated": network_xml(matrix["networks"][0]),
        "network_nat": network_xml(matrix["networks"][1]),
        "domain": domain_xml(matrix["domains"][0], kernel=_KERNEL, initrd=_INITRD),
    }

    assert rendered == CAPTURE["rendered"]


def test_libvirt_readback_satisfies_the_techvault_concern_gate() -> None:
    result = DriverResult(observations=_observations(CAPTURE["readback"]))

    assert techvault_observation_diagnostics(networks=(_ISOLATED, _NAT), domains=(_DOMAIN,), result=result) == []


def test_fake_readback_reports_the_shape_libvirt_reports() -> None:
    fake = {key: libvirt_readback(CAPTURE["rendered"][key]) for key in (*_NETWORK_KEYS, "domain")}
    fake_domain = ET.fromstring(fake["domain"])  # noqa: S314 - test-generated XML
    real_domain = ET.fromstring(CAPTURE["readback"]["domain"])  # noqa: S314 - captured libvirt XML

    for tag in ("memory", "currentMemory", "vcpu"):
        assert (fake_domain.find(tag).attrib, fake_domain.find(tag).text) == (
            real_domain.find(tag).attrib,
            real_domain.find(tag).text,
        ), tag
    assert _values(_observations(fake)) == _values(_observations(CAPTURE["readback"]))

"""Compiled tuples and transported arrays compare as the same realization payload."""

from raes_processor.semantics.realization_snapshot_sanitization import realization_payloads_match


def test_tuple_and_array_carriers_of_the_same_values_match():
    declared = {"name": "ad", "domain_topology": {"controller_addresses": ("nodes.ad", "nodes.ad2")}}
    returned = {"name": "ad", "domain_topology": {"controller_addresses": ["nodes.ad", "nodes.ad2"]}}
    assert realization_payloads_match("provision.node.ad", declared, returned, ())
    reordered = {"name": "ad", "domain_topology": {"controller_addresses": ["nodes.ad2", "nodes.ad"]}}
    assert not realization_payloads_match("provision.node.ad", declared, reordered, ())
    assert not realization_payloads_match("provision.node.ad", declared, {**returned, "name": "other"}, ())


def test_portable_payload_matching_keeps_scalar_types_exact():
    declared = {"spec": {"enabled": True, "count": 1}}

    assert realization_payloads_match("provision.node.ad", declared, declared, ())
    assert not realization_payloads_match("provision.node.ad", declared, {"spec": {"enabled": 1, "count": 1}}, ())
    assert not realization_payloads_match("provision.node.ad", declared, {"spec": {"enabled": True, "count": True}}, ())

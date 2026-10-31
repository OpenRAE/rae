"""Fixed results of public consumers of the shared primitives (issue #1710, ADR-118).

The values were recorded from the implementation before the primitives moved to
``raes_contracts``. Persisted records and evidence contain these digests and
texts, so each value must stay byte-identical.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


def test_sorted_json_digests_of_record_consumers():
    import raes_contracts.realization_envelope  # noqa: F401  (imports the carrier in its supported order)
    from raes_contracts.realization_envelope_carrier import realization_envelope_digest
    from raes_runtime.control_plane_store_local_codec import encode_payload
    from raes_runtime.participant_crossing_state_cut import canonical_crossing_digest

    assert realization_envelope_digest({"b": "é", "a": [1, 2.5, None], "digest": "drop"}) == (
        "sha256:45584828a616e524473fb887d415f828918fb9676efdaa57c062231771111499"
    )
    assert canonical_crossing_digest({"at": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC), "name": "é"}) == (
        "sha256:4a9abbe69ea508445a2b721347770e7cea9463243182690cefc03902c9edcc4d"
    )
    assert encode_payload({"b": "é", "a": 1}) == (
        '{"a":1,"b":"\\u00e9"}',
        "6071e7aa781e8adc235db31b17e6d0ee414a17031b1744a38fbf2cd17effcbce",
    )


def test_history_prefix_digests_chain_the_finite_record_text():
    from raes_contracts.immutable_history import HistoryMap

    history = HistoryMap("evaluation_history", {"run": [{"b": "é", "a": 1.5}, {"n": 2}]})["run"]
    assert history.prefix_digest(1) == "89ccac4d48f160d06321e09fa58a74e5ce8fa3449200ceb6cd62ac73537eae74"
    assert history.prefix_digest(2) == "309992bef4a01e4c6ead01778702100f9c47e4ed373417364bbb0ae9704c340d"
    with pytest.raises(ValueError, match="Out of range float values are not JSON compliant"):
        HistoryMap("evaluation_history", {"run": [{"x": float("nan")}]})


def test_jcs_identities():
    from raes_contracts.exploit_path import canonical_state_digest
    from raes_processor.trial_compiler.profiles import derive_identity

    assert canonical_state_digest(("b", "a")) == (
        "sha256:02d8bc3008a9bb0dcc4b86d7fd3428ced792355c733c19756bec5a56dc61b2c5"
    )
    assert derive_identity("kind", {"x": 1}) == "kind-1e07f9ef0b3bc1f9242b3bc15a243b2f8db4c523d4e4b65db85caa901d4d3399"
    assert derive_identity("kind", {"x": 1}, mixed_composition=True) == (
        "kind-b53a6c83b3404b8b883f14a17190a616f082c420e84d45c3007b3ffc50960e44"
    )


def test_domain_framed_sha256_identities():
    from raes.semantic_revisions import source_byte_digest
    from raes_backend_protocols.naming import provider_resource_name
    from raes_contracts.contracts.participant_resource_types import participant_resource_pool_state_ref
    from raes_contracts.participant_tool_actions import tool_action_instance_id

    assert provider_resource_name("node.web-01", namespace="run-1") == "node.web-01-cf0c7d40e8cd"
    assert provider_resource_name("node.web-01") == "node.web-01-892ec1143d57"
    assert tool_action_instance_id("action-1", episode_id="ep", execution_generation=2, tool_call_id="call") == (
        "participant-tool-action-80a151f5daaee481f85308ca745b501fdc973ee7d02e158fd1a081860bbf6ffe"
    )
    assert source_byte_digest("é\n") == "sha256:edd3a863872a04239eb29ad4bc12fc892b3d4ae57cc7e786a3697816f8e141c2"
    assert source_byte_digest("x\ud800") == "sha256:79910d1567b1f0bf798f6c7c4cee462dafac2844f9a95b9a41b5ceac02d5b8ab"
    assert participant_resource_pool_state_ref(
        pool_ref="pool.a",
        owner_kind="participant",
        owner_ref="red",
        resource_kind="cpu",
        unit="core",
        accounting_mode="metered",
        meter_profile_ref="meter.v1",
    ) == ("participant-resource-pool:sha256:c297b460bd63899d42eba500d3f6997cb5017c95cd24d45d9632f6bb63613d31")


def test_pointer_consumers():
    from raes._scenario_instantiation import resolve_json_pointer
    from raes_contracts.diagnostics import Diagnostic, portable_diagnostic_payload

    assert resolve_json_pointer({"a/b": {"~": [10, 20]}}, "/a~1b/~0/1") == 20

    def pointer(address: str) -> str:
        diagnostic = Diagnostic(code="x.y", domain="runtime", address=address, message="m")
        return portable_diagnostic_payload(diagnostic)["address"]

    assert pointer("a/b~c") == "/a~1b~0c"
    assert pointer("nodes.web.x") == "/nodes.web.x"
    assert pointer("") == ""


def test_public_runtime_timestamp_parsers():
    from raes_runtime.control_plane_workflows import parse_timestamp
    from raes_runtime.runtime_fact_binding_policy import parse_datetime

    assert parse_timestamp("2024-01-01T05:00:00+05:00").isoformat() == "2024-01-01T00:00:00+00:00"
    for raw in ("2024-01-01T00:00:00", "x"):
        with pytest.raises(ValueError, match="^timestamp must be an ISO-8601 value with an explicit UTC offset$"):
            parse_timestamp(raw)
    assert parse_datetime("2024-01-01T05:00:00z", "observed_at").isoformat() == "2024-01-01T05:00:00+00:00"
    assert parse_datetime("2024-01-01T05:00:00+05:00").isoformat() == "2024-01-01T05:00:00+05:00"
    with pytest.raises(ValueError, match="^observed_at must be an ISO 8601 date-time with an explicit UTC offset$"):
        parse_datetime("2024-01-01T00:00:00", "observed_at")


def test_planner_order_and_cycles():
    from raes_processor.semantics.planner import dependency_cycles, topological_dependency_order

    graph = {"n.c": (), "n.a": (), "n.b": ("n.a",), "n.d": ("n.e",), "n.e": ("n.d",), "n.f": ("n.f",)}
    assert topological_dependency_order(graph) == ["n.a", "n.c", "n.b", "n.d", "n.e", "n.f"]
    assert dependency_cycles(graph) == [("n.d", "n.e"), ("n.f",)]

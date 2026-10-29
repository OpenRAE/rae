"""Temporal delivery is stable bookkeeping, never another effect permission."""

import pytest
from test_issue_1360_backend_operations import request


def test_temporal_uses_a_stable_identity_single_attempt_effects_and_opaque_references():
    from raes_runtime.operation_temporal import TemporalExecutionAdapter, TemporalExecutionConfiguration

    starts = []

    class Client:
        namespace = "rae-test"

        async def start_workflow(self, name, reference, **options):
            starts.append((name, reference, options))
            return object()

    async def client():
        return Client()

    adapter = TemporalExecutionAdapter(
        TemporalExecutionConfiguration(namespace="rae-test", worker_identity="worker-1"),
        client_factory=client,
    )
    try:
        operation = request()
        adapter.submit(operation)
        adapter.submit(operation)
        assert starts[0][2]["id"] == starts[1][2]["id"]
        assert starts[0][2]["retry_policy"].maximum_attempts == 1
        reference = starts[0][1]
        assert "command" not in reference
        assert "context" not in reference
        assert "credentials" not in reference
        assert reference["operation_id"] == operation.binding.operation_id
        assert reference["effect_queue"] != reference["control_queue"]
        assert reference["worker_id"] == "worker-1"
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "options", [{"rpc_budget_ms": True}, {"effect_queue": "same", "control_queue": "same"}, {"worker_identity": ""}]
)
def test_temporal_settings_refuse_unbounded_or_shared_control_configuration(options):
    from raes_runtime.operation_temporal import TemporalExecutionConfiguration

    with pytest.raises((TypeError, ValueError)):
        TemporalExecutionConfiguration(**options)


def test_an_ambiguous_engine_start_resubmits_the_same_identity_without_touching_effects():
    from raes_runtime.operation_temporal import TemporalExecutionAdapter, TemporalExecutionConfiguration

    ids = []

    class Client:
        namespace = "rae-test"

        async def start_workflow(self, name, reference, **options):
            ids.append(options["id"])
            if len(ids) == 1:
                raise TimeoutError("synthetic lost acknowledgement")
            return object()

    async def client():
        return Client()

    adapter = TemporalExecutionAdapter(
        TemporalExecutionConfiguration(namespace="rae-test", worker_identity="worker-1"), client_factory=client
    )
    try:
        operation = request()
        with pytest.raises(TimeoutError):
            adapter.submit(operation)
        adapter.submit(operation)
        assert ids[0] == ids[1]
    finally:
        adapter.close()

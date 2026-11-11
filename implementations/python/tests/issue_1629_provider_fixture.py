"""Installed protocol owner backed by the fixture's actual component effects."""

from copy import deepcopy
from dataclasses import replace

from raes_contracts.canonical import canonical_json_digest
from raes_runtime.control_plane_store_snapshots import _snapshot_payload
from test_issue_1660_provider_observation import CompositeProvider


class TrialProvider(CompositeProvider):
    def start_operation(self, request):
        native, predecessor = self.commands[request.command.digest]
        result = native.method(replace(native.plan, operation_id=request.binding.operation_id), deepcopy(predecessor))
        self.results[request.binding.operation_id] = result
        self.snapshot = result.snapshot
        self.outcome = "succeeded" if result.success else "failed"
        # Retain the actual effect result before returning acknowledgement.
        from test_issue_1362_provider_execution import Provider

        return Provider.start_operation(self, request)

    def operation_capabilities(self):
        return super().operation_capabilities().model_copy(update={"backend_id": "trial"})

    def validate_effects(self, request, response):
        result = self.results.get(request.binding.operation_id)
        return (
            result is not None
            and response.binding == request.binding
            and response.message.result.digest == canonical_json_digest(_snapshot_payload(result.snapshot))
        )


def install_command_owner(monkeypatch, provider):
    """Connect the installed test artifact owner to each admitted native command."""
    from raes_runtime import control_plane_supervised_execution, operation_provider_execution

    original = control_plane_supervised_execution.invocation_request

    def bind(plane, native, operation_id, submitted_at):
        request = original(plane, native, operation_id, submitted_at)
        provider.commands[request.command.digest] = (native, deepcopy(plane._snapshot))
        return request

    monkeypatch.setattr(control_plane_supervised_execution, "invocation_request", bind)
    monkeypatch.setattr(operation_provider_execution, "invocation_request", bind)

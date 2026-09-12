"""Opt-in backend-owned selection must be admitted before mutation."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from test_issue_1200_mixed_runtime_constraints import _fixture, _returned


def _request(*, offered_engine=None, closed_offer=False):
    from raes_backend_protocols.manifest import backend_manifest_v2_model
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.realization_preparation import RealizationPreparationAuthority

    _, plan, manifest = _fixture({"database_services": [{"database_service_id": "db", "engine": "other"}]})
    if offered_engine is not None:
        from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel, realization_envelope_digest

        payload = manifest.realization_envelope.model_dump(mode="json")
        payload["expression"]["domains"] = {"engine": {"kind": "exact", "value": offered_engine}}
        payload["expression"]["bindings"] = [
            {
                "path": "nodes.host.runtime.database_services[0].engine",
                "scope": "field",
                "posture": "exact",
                "domain": "engine",
            }
        ]
        if closed_offer:
            payload["expression"]["domains"]["service"] = {
                "kind": "record",
                "fields": {"engine": "engine"},
                "extra": False,
            }
            payload["expression"]["bindings"][0].update(
                path="nodes.host.runtime.database_services[0]",
                domain="service",
                posture="constrained",
            )
        payload["digest"] = realization_envelope_digest(payload)
        manifest = replace(manifest, realization_envelope=BackendRealizationEnvelopeModel.model_validate(payload))
        plan = replace(plan, realization_envelope=manifest.realization_envelope.identity)
    manifest = replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions | {"backend-realization-preparation-v1"},
    )
    authority = RealizationPreparationAuthority(
        manifest_digest=canonical_json_digest(backend_manifest_v2_model(manifest).model_dump(mode="json"))
    )
    return replace(plan, preparation=authority), manifest


class _PreparingBackend:
    def __init__(self, engine="sqlite", identity="db", *, delivered_engine=None, corrupt_binding=False):
        self.engine = engine
        self.identity = identity
        self.delivered_engine = delivered_engine
        self.corrupt_binding = corrupt_binding
        self.prepares = 0
        self.applies = 0

    def prepare(self, plan, snapshot):
        from raes_contracts.realization_preparation import RealizationPreparation

        self.prepares += 1
        operations = deepcopy(plan.operations)
        operations[0].payload["spec"]["node"]["runtime"]["database_services"] = [
            {"database_service_id": self.identity, "engine": self.engine}
        ]
        result = RealizationPreparation.for_request(plan, snapshot, operations=tuple(operations))
        if self.corrupt_binding:
            result = replace(result, request_digest="sha256:" + "0" * 64)
        return result

    def validate(self, plan):
        return []

    def apply(self, plan, snapshot):
        self.applies += 1
        runtime = deepcopy(plan.operations[0].payload["spec"]["node"]["runtime"])
        if self.delivered_engine:
            runtime["database_services"][0]["engine"] = self.delivered_engine
        returned = _returned(plan, runtime)
        returned.metadata = deepcopy(snapshot.metadata)
        return ApplyResult(True, returned, changed_addresses=list(returned.entries))


def _apply(backend, **request_options):
    plan, manifest = _request(**request_options)
    snapshot = RuntimeSnapshot(metadata={"trusted": ["immediate-predecessor"]})
    result = _call_backend_apply(
        backend.apply,
        plan,
        snapshot,
        address="runtime.test.preparation",
        snapshot=snapshot,
        realization=_RealizationApplyContext(plan=plan, manifest=manifest),
    )
    return snapshot, result


def test_backend_selects_supported_completion_before_apply():
    backend = _PreparingBackend()
    _, result = _apply(backend)
    assert result.success, result.diagnostics
    assert (backend.prepares, backend.applies) == (1, 1)
    entry = next(iter(result.snapshot.entries.values()))
    assert entry.payload["spec"]["node"]["runtime"]["database_services"][0]["engine"] == "sqlite"


def test_equal_detached_authority_still_applies_the_prepared_completion():
    backend = _PreparingBackend()
    request, manifest = _request()
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.detached-authority",
        realization=_RealizationApplyContext(plan=deepcopy(request), manifest=manifest),
    )
    assert result.success, result.diagnostics
    assert backend.applies == 1
    assert (
        result.snapshot.entries[request.operations[0].address].payload["spec"]["node"]["runtime"]["database_services"][
            0
        ]["engine"]
        == "sqlite"
    )


@pytest.mark.parametrize("options", [{"engine": "unknown"}, {"identity": "renamed"}, {"corrupt_binding": True}])
def test_invalid_preparation_never_reaches_apply(options):
    backend = _PreparingBackend(**options)
    previous, result = _apply(backend)
    assert backend.prepares == 1
    assert backend.applies == 0
    assert not result.success
    assert result.snapshot == previous
    assert result.changed_addresses == []
    assert result.details == {}
    assert result.diagnostics[0].code == "runtime.backend-preparation-invalid"


def test_successful_delivery_must_match_the_admitted_completion():
    backend = _PreparingBackend(delivered_engine="postgresql")
    previous, result = _apply(backend)
    assert (backend.prepares, backend.applies) == (1, 1)
    assert not result.success
    assert result.snapshot == previous
    assert result.diagnostics[0].code == "runtime.backend-contract-invalid"


def test_selected_values_must_pass_the_backend_validation_before_apply():
    from raes_contracts.diagnostics import Diagnostic

    class RejectingBackend(_PreparingBackend):
        def validate(self, plan):
            return [Diagnostic("test.unsupported", "runtime", "runtime.preparation", "Unsupported selection.")]

    backend = RejectingBackend()
    previous, result = _apply(backend)
    assert backend.prepares == 1
    assert backend.applies == 0
    assert not result.success
    assert result.snapshot == previous


def test_preparation_and_validation_warnings_survive_successful_apply():
    from raes_contracts.diagnostics import Diagnostic, Severity

    warning = Diagnostic(
        "test.preparation-warning", "runtime", "runtime.preparation", "Selection warning.", severity=Severity.WARNING
    )
    validation = replace(warning, code="test.validation-warning")

    class WarningBackend(_PreparingBackend):
        def prepare(self, plan, snapshot):
            return replace(super().prepare(plan, snapshot), diagnostics=(warning,))

        def validate(self, plan):
            return [validation]

    backend = WarningBackend()
    _, result = _apply(backend)
    assert result.success, result.diagnostics
    assert backend.applies == 1
    assert result.diagnostics == [warning, validation]


@pytest.mark.parametrize("offered,accepted", [("sqlite", True), ("postgresql", False)])
def test_prepared_choice_must_belong_to_the_configured_backend_offer(offered, accepted):
    backend = _PreparingBackend()
    previous, result = _apply(backend, offered_engine=offered)
    assert result.success is accepted
    assert backend.applies == int(accepted)
    if not accepted:
        assert result.snapshot == previous


def test_preparation_honors_backend_record_closure_not_only_leaf_domains():
    backend = _PreparingBackend()
    previous, result = _apply(backend, offered_engine="sqlite", closed_offer=True)
    # The configured closed record admits only engine, not database_service_id.
    # Matching that leaf alone is insufficient to establish a supported completion.
    assert backend.applies == 0
    assert not result.success
    assert result.snapshot == previous
    assert result.diagnostics[0].code == "runtime.backend-preparation-invalid"


@pytest.mark.parametrize("selected_version,accepted", [("", True), ("3.46", False)])
def test_closed_offer_uses_typed_default_presence_for_prepared_values(selected_version, accepted):
    from pydantic import TypeAdapter
    from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel, realization_envelope_digest
    from raes_processor.planner.realization_preparation import preparation_authority
    from raes_processor.semantics.realization_runtime_concern_profiles import runtime_path_annotation

    class DefaultCarryingBackend(_PreparingBackend):
        def prepare(self, plan, snapshot):
            response = super().prepare(plan, snapshot)
            runtime = response.operations[0].payload["spec"]["node"]["runtime"]
            adapter = TypeAdapter(runtime_path_annotation(("database_services",)))
            values = adapter.dump_python(adapter.validate_python(runtime["database_services"]), mode="json")
            values[0]["version"] = selected_version
            runtime["database_services"] = values
            return response

    request, manifest = _request(offered_engine="sqlite", closed_offer=True)
    payload = manifest.realization_envelope.model_dump(mode="json")
    payload["expression"]["domains"]["identity"] = {"kind": "exact", "value": "db"}
    payload["expression"]["domains"]["service"]["fields"]["database_service_id"] = "identity"
    payload["digest"] = realization_envelope_digest(payload)
    manifest = replace(manifest, realization_envelope=BackendRealizationEnvelopeModel.model_validate(payload))
    request = replace(
        request,
        realization_envelope=manifest.realization_envelope.identity,
        preparation=preparation_authority(manifest),
    )
    backend = DefaultCarryingBackend()
    previous = RuntimeSnapshot()
    if accepted:
        from raes_processor.planner.realization_preparation import prepared_realization_violation
        from raes_runtime.backend_preparation import _selected_plan

        completion = _selected_plan(request, backend.prepare(request, previous))
        assert prepared_realization_violation(request, completion, manifest) is None
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.typed-offer",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert result.success is accepted, result.diagnostics
    assert backend.applies == int(accepted)
    if not accepted:
        assert result.snapshot == previous


def test_negotiated_preparation_does_not_claim_universal_linux_coverage():
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan
    from test_sem_218_realization_designation import _open_manifest_with_envelope, _scenario

    model = compile_runtime_model(_scenario("realization:\n  default: open"))
    legacy = _open_manifest_with_envelope(path="nodes.web.os", value="linux")
    assert any(
        d.code == "realization-envelope.subsumption.requested-unconstrained" for d in plan(model, legacy).diagnostics
    )
    capable = replace(
        legacy, supported_contract_versions=legacy.supported_contract_versions | {"backend-realization-preparation-v1"}
    )
    execution = plan(model, capable)
    assert execution.is_valid, execution.diagnostics
    assert execution.provisioning.preparation.contract_id == "backend-realization-preparation-v1"


@pytest.mark.parametrize("corruption", ["action", "predecessor", "duplicate", "cycle"])
def test_mutated_preparation_carriers_fail_before_apply(corruption):
    class MutatedResponseBackend(_PreparingBackend):
        def prepare(self, plan, snapshot):
            response = super().prepare(plan, snapshot)
            if corruption == "action":
                object.__setattr__(response.operations[0], "action", "create")
            elif corruption == "predecessor":
                response = replace(response, predecessor_digest="sha256:" + "c" * 64)
            elif corruption == "duplicate":
                response = replace(response, operations=response.operations * 2)
            else:
                response.operations[0].payload["cycle"] = response.operations[0].payload
            return response

    backend = MutatedResponseBackend()
    previous, result = _apply(backend)
    assert backend.applies == 0
    assert not result.success
    assert result.snapshot == previous
    assert result.diagnostics[0].code == "runtime.backend-preparation-invalid"


def test_preparation_cannot_be_replayed_for_a_new_operation():
    class ReplayingBackend(_PreparingBackend):
        response = None

        def prepare(self, plan, snapshot):
            if self.response is None:
                self.response = super().prepare(plan, snapshot)
            return self.response

    backend = ReplayingBackend()
    _, first = _apply(backend)
    assert first.success, first.diagnostics
    previous, second = _apply(backend)
    assert not second.success
    assert backend.applies == 1
    assert second.snapshot == previous
    assert second.diagnostics[0].code == "runtime.backend-preparation-invalid"

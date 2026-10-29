"""Admitted first-party preparation additions receive runtime-owned concern rows."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes import parse_sdl
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
from raes_contracts.planning import PlanScope
from raes_contracts.realization_preparation import BACKEND_PREPARATION_CONTRACT, RealizationPreparation
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.vocabulary import RealizationSupportMode
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_processor.reference import run_reference_processor
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from test_sem_218_realization_designation import _manifest

_SOURCE = (
    "name: original\nrealization:\n  default: closed\n  scopes:\n"
    "    - {field_pointer: /nodes, posture: open}\n"
    "    - {field_pointer: /nodes/holder, posture: closed}\n"
    "nodes: {holder: {type: switch}}\n"
)


class AddingProvisioner(StubProvisioner):
    def __init__(self, manifest, node):
        super().__init__(manifest.realization_envelope)
        extra = run_reference_processor(
            parse_sdl("name: apparatus\nnodes:\n  capture: " + node),
            manifest,
            scope=PlanScope(run_id="apparatus", target_name=manifest.name),
        )
        assert extra.execution_plan.is_valid, extra.diagnostics
        self.extra = extra.execution_plan.provisioning.operations[0]
        self.add = True
        self.applies = 0
        self.failure = None
        self.observe_os = False

    def prepare(self, request, previous):
        extra = (deepcopy(self.extra),) if self.add else ()
        return RealizationPreparation.for_request(
            request, previous, operations=(*request.operations, *extra), success=self.failure != "refused"
        )

    def apply(self, request, previous):
        self.applies += 1
        result = super().apply(request, previous)
        if self.observe_os:
            from test_sem_218_runtime_realization import _ObservedProvisioner

            result = _ObservedProvisioner().apply(request, previous)
        if self.failure == "native-failure":
            return replace(result, success=False)
        if self.failure == "changed-delivery":
            result.snapshot.entries.pop(self.extra.address)
            result.changed_addresses.remove(self.extra.address)
        if self.failure == "ledger-spoof":
            from raes_contracts.runtime_state import RealizationProvenanceEntry

            result = replace(
                result,
                snapshot=replace(
                    result.snapshot,
                    realization_provenance=(
                        RealizationProvenanceEntry(
                            address=self.extra.address,
                            field_path="nodes.capture.type",
                            domain="runtime-realization",
                            requirement_kind="node-type",
                            explicitness=ExplicitnessClass.EXACT,
                            provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
                        ),
                    ),
                ),
            )
        return result


def prepared_target(node="{type: switch}"):
    target = create_stub_target()
    support = _manifest(RealizationSupportMode.OPEN_REALIZATION).realization_support
    manifest = replace(
        target.manifest,
        supported_contract_versions=target.manifest.supported_contract_versions | {BACKEND_PREPARATION_CONTRACT},
        realization_support=tuple(
            replace(
                item,
                supported_exact_requirement_kinds=item.supported_exact_requirement_kinds
                | {"runtime-environment", "runtime-container-command"},
            )
            for item in support
        ),
        capabilities=replace(
            target.manifest.capabilities,
            provisioner=replace(
                target.manifest.provisioner,
                operating_systems=_manifest(RealizationSupportMode.OPEN_REALIZATION).provisioner.operating_systems,
            ),
        ),
    )
    backend = AddingProvisioner(manifest, node)
    return replace(target, manifest=manifest, provisioner=backend), backend


def apply_prepared(target, source=_SOURCE, previous=None):
    previous = previous or RuntimeSnapshot()
    execution = plan(compile_runtime_model(parse_sdl(source)), target.manifest, previous)
    assert execution.is_valid, execution.diagnostics
    result = _call_backend_apply(
        target.provisioner.apply,
        execution.provisioning,
        previous,
        snapshot=previous,
        address="runtime.prepared-provenance",
        realization=_RealizationApplyContext(plan=execution.provisioning, manifest=target.manifest),
    )
    return result, execution


@pytest.mark.parametrize(
    "node,address,kinds",
    [
        ("{type: switch}", "provision.network.capture", {"node-type"}),
        (
            "{type: compute, runtime: {environment: []}}",
            "provision.node.capture",
            {"node-type", "runtime-environment", "compute-substrate"},
        ),
        (
            "{type: compute, runtime: {container: {command: [capture]}}}",
            "provision.node.capture",
            {"node-type", "runtime-container-command", "compute-substrate"},
        ),
    ],
)
def test_prepared_addition_has_open_backend_concern_provenance(node, address, kinds):
    target, backend = prepared_target(node)
    result, execution = apply_prepared(target)
    assert result.success, result.diagnostics
    assert backend.applies == 1
    assert address in result.snapshot.entries
    rows = [row for row in result.snapshot.realization_provenance if row.address == address]
    assert kinds == {row.requirement_kind for row in rows}
    assert all(row.explicitness is ExplicitnessClass.OPEN for row in rows)
    assert all(row.provenance is ExplicitnessProvenance.BACKEND_REALIZED for row in rows)
    assert all(
        row.governing_scope == execution.provisioning.preparation.node_collection.governing_scope for row in rows
    )
    holder = next(row for row in result.snapshot.realization_provenance if row.field_path == "nodes.holder.type")
    assert holder.explicitness is ExplicitnessClass.EXACT
    assert holder.provenance is ExplicitnessProvenance.AUTHOR_DECLARED


@pytest.mark.parametrize("failure", ["closed", "refused", "native-failure", "changed-delivery", "ledger-spoof"])
def test_unsuccessful_preparation_or_delivery_does_not_mint_provenance(failure):
    target, backend = prepared_target()
    source = _SOURCE
    if failure == "closed":
        source = _SOURCE.replace("field_pointer: /nodes, posture: open", "field_pointer: /nodes, posture: closed")
    backend.failure = failure
    result, _ = apply_prepared(target, source)
    assert not result.success
    assert result.snapshot.realization_provenance == ()
    assert backend.applies == (0 if failure in {"closed", "refused"} else 1)
    if failure != "native-failure":
        assert result.snapshot.entries == {}


def test_retained_addition_keeps_rows_and_deletion_removes_them():
    target, backend = prepared_target()
    first, _ = apply_prepared(target)
    assert first.success, first.diagnostics
    expected = [row for row in first.snapshot.realization_provenance if row.address == backend.extra.address]
    assert expected
    backend.add = False
    retained, _ = apply_prepared(target, previous=first.snapshot)
    assert retained.success, retained.diagnostics
    assert [row for row in retained.snapshot.realization_provenance if row.address == backend.extra.address] == expected
    closed = _SOURCE.replace("field_pointer: /nodes, posture: open", "field_pointer: /nodes, posture: closed")
    removed, _ = apply_prepared(target, closed, retained.snapshot)
    assert removed.success, removed.diagnostics
    assert backend.extra.address not in removed.snapshot.entries
    assert not any(row.address == backend.extra.address for row in removed.snapshot.realization_provenance)


def test_prepared_update_replaces_removed_concerns_without_duplicate_identities():
    from raes_contracts.planning import ChangeAction

    target, backend = prepared_target("{type: compute, runtime: {environment: []}}")
    first, _ = apply_prepared(target)
    assert first.success, first.diagnostics
    assert any(row.requirement_kind == "runtime-environment" for row in first.snapshot.realization_provenance)
    replacement = AddingProvisioner(target.manifest, "{type: compute}").extra
    backend.extra = replace(replacement, action=ChangeAction.UPDATE)
    updated, _ = apply_prepared(target, previous=first.snapshot)
    assert updated.success, updated.diagnostics
    rows = updated.snapshot.realization_provenance
    assert not any(row.requirement_kind == "runtime-environment" for row in rows)
    keys = [(row.address, row.field_path, row.domain, row.requirement_kind) for row in rows]
    assert len(keys) == len(set(keys))


def test_published_stub_reproduction_records_added_switch_provenance():
    from raes_runtime.manager import RuntimeManager

    base = create_stub_target()
    manifest = replace(
        base.manifest,
        supported_contract_versions=base.manifest.supported_contract_versions | {BACKEND_PREPARATION_CONTRACT},
    )
    backend = AddingProvisioner(manifest, "{type: switch}")
    target = replace(base, manifest=manifest, provisioner=backend)
    with RuntimeManager(target) as runtime:
        execution = runtime.plan(parse_sdl(_SOURCE))
        assert execution.is_valid, execution.diagnostics
        result = runtime.apply(execution)
        assert result.success, result.diagnostics
        assert {row.address for row in result.snapshot.realization_provenance} == {
            "provision.network.holder",
            "provision.network.capture",
        }


def test_prepared_protected_values_are_sanitized_before_persistence():
    target, backend = prepared_target(
        "{type: compute, runtime: {environment: [{name: CAPTURE_SETTING, value: private-capture-setting}]}}"
    )
    result, _ = apply_prepared(target)
    assert result.success, result.diagnostics
    assert "private-capture-setting" not in repr(result.snapshot)
    rows = [row for row in result.snapshot.realization_provenance if row.address == backend.extra.address]
    assert any(row.requirement_kind == "runtime-environment" for row in rows)
    assert all(row.provenance is ExplicitnessProvenance.BACKEND_REALIZED for row in rows)


def test_safe_node_default_normalization_does_not_restore_committed_raw_values():
    from raes_processor.planner.materialization_admission import _with_node_defaults

    target, backend = prepared_target("{type: compute, runtime: {environment: [{name: MODE, value: enabled}]}}")
    applied, _ = apply_prepared(target)
    assert applied.success, applied.diagnostics
    entry = applied.snapshot.entries[backend.extra.address]
    before = entry.payload["spec"]["node"]["runtime"]["environment"][0]
    normalized = _with_node_defaults(entry).payload["spec"]["node"]["runtime"]["environment"][0]
    assert "value" not in normalized
    assert normalized["value_commitment"] == before["value_commitment"]


def test_added_compute_does_not_turn_required_substrate_observation_into_selection():
    from raes_contracts.observation_demand import ObservationSelector
    from test_issue_1212_runtime_boundaries import _demands

    target, backend = prepared_target("{type: compute}")
    previous = RuntimeSnapshot()
    execution = plan(compile_runtime_model(parse_sdl(_SOURCE)), target.manifest)
    selector = ObservationSelector(semantic_scope="/nodes/capture", data_kind="field", names=("compute-substrate",))
    request = replace(
        execution.provisioning,
        observation_demands=_demands(selector, purpose="experimental", collection="require", required=True),
    )
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.prepared-observation",
        realization=_RealizationApplyContext(plan=request, manifest=target.manifest),
    )
    assert not result.success
    assert result.snapshot == previous
    assert result.snapshot.realization_provenance == ()


def test_prepared_acceptance_keeps_the_native_proposal_immutable():
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.contracts import OperationArtifactReferenceModel
    from raes_contracts.runtime_state import OperationState
    from raes_runtime.backend_calls import _BackendCallContext
    from raes_runtime.backend_observation_calls import _ObservationApplyRequest
    from raes_runtime.backend_preparation import prepare_backend_apply
    from raes_runtime.control_plane_store_snapshots import _snapshot_payload
    from raes_runtime.operation_result_finalization import finalize_protocol_result

    target, backend = prepared_target()
    previous = RuntimeSnapshot()
    execution = plan(compile_runtime_model(parse_sdl(_SOURCE)), target.manifest)
    request = replace(execution.provisioning, operation_id="prepared-proposal")
    context = _RealizationApplyContext(plan=request, operation_plan=request, manifest=target.manifest)
    selected, diagnostics = prepare_backend_apply(backend.apply, request, previous, context)
    assert selected is not None, diagnostics
    proposal = backend.apply(selected, previous)
    digest = canonical_json_digest(_snapshot_payload(proposal.snapshot))
    reference = OperationArtifactReferenceModel(contract_id="runtime-snapshot-v1", artifact_id="native", digest=digest)
    accepted, _ = finalize_protocol_result(
        proposal,
        reference,
        OperationState.SUCCEEDED,
        observation_request=_ObservationApplyRequest(
            address="runtime.prepared-proposal",
            snapshot=previous,
            plan=request,
            manifest=target.manifest,
            runtime=None,
        ),
        realization=replace(context, operation_plan=selected, completion_plan=selected),
        call=_BackendCallContext(),
        execute_observation=False,
    )
    assert accepted.success, accepted.diagnostics
    assert any(row.address == backend.extra.address for row in accepted.snapshot.realization_provenance)
    assert proposal.snapshot.realization_provenance == ()
    assert canonical_json_digest(_snapshot_payload(proposal.snapshot)) == digest


def test_public_manager_preserves_processor_origin_and_persists_added_rows(tmp_path):
    from raes import instantiate_scenario
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore
    from raes_runtime.manager import RuntimeManager

    target, backend = prepared_target()
    backend.observe_os = True
    source = _SOURCE.replace(
        "nodes: {holder: {type: switch}}",
        "nodes: {holder: {type: compute, os: '${family}', os_distribution: ubuntu, os_version: '22.04'}}",
    )
    source += "variables: {family: {type: string, default: linux, allowed_values: [linux]}}\n"
    store = LocalControlPlaneStore(tmp_path / "state")
    with RuntimeManager(target, store=store) as runtime:
        execution = runtime.plan(instantiate_scenario(parse_sdl(source)))
        assert execution.is_valid, execution.diagnostics
        result = runtime.apply(execution)
        assert result.success, result.diagnostics
        holder = next(row for row in result.snapshot.realization_provenance if row.field_path == "nodes.holder.os")
        assert holder.provenance is ExplicitnessProvenance.PROCESSOR_DERIVED
        assert any(row.address == backend.extra.address for row in runtime.snapshot.realization_provenance)
        ledger = runtime.snapshot.realization_provenance
    with RuntimeManager(target, store=LocalControlPlaneStore(tmp_path / "state")) as reopened:
        assert reopened.snapshot.realization_provenance == ledger

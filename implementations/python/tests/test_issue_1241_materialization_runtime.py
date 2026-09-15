"""An attestation is bound and validated after apply without replacing authority."""

import json
from dataclasses import replace

import pytest
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_backend_stubs.stubs import StubProvisioner
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.realization_preparation import preparation_snapshot_digest
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_runtime.backend_calls import _BackendCallContext, _call_backend_apply, _RealizationApplyContext
from test_issue_1241_materialization_context import attesting_plan
from test_issue_1241_materialized_sdl import materialization_provenance


class ReportingProvisioner:
    def __init__(self, manifest, mutate=None, *, omit=False, realize=False):
        self.manifest, self.mutate, self.omit = manifest, mutate, omit
        self.realize = realize
        self.calls = 0

    def validate(self, request):
        return []

    def apply(self, request, previous):
        self.calls += 1
        result = StubProvisioner(self.manifest.realization_envelope).apply(request, previous)
        return self.report(request, previous, result)

    def report(self, request, previous, result):
        from raes_contracts.materialization import MaterializationSubmission

        if self.omit or request.materialization_source is None:
            return result
        source = request.materialization_source
        document = json.loads(source.snapshot)["scenario"]
        document.pop("instantiation_provenance")
        document["materialization_provenance"] = materialization_provenance(
            authored_digest={"profile": "raes-sdl-semantic/v2", "algorithm": "sha256", "value": source.authored_digest},
            instantiated_digest={
                "profile": "raes-sdl-instantiated-snapshot/v2",
                "algorithm": "sha256",
                "value": source.instantiated_digest,
            },
            plan_digest=runtime_plan_digest(request),
            predecessor_digest=preparation_snapshot_digest(previous),
            operation_id=request.operation_id,
            run_id=source.run_id,
            producer={
                "name": self.manifest.name,
                "version": self.manifest.version,
                "manifest_digest": canonical_json_digest(
                    backend_manifest_v2_model(self.manifest).model_dump(mode="json")
                ),
                "configuration_digest": self.manifest.realization_envelope.configuration.configuration_digest,
            },
            resource_bindings=[
                {"address": "provision.node.host", "node_name": "host", "source_node": "host", "instance_index": 0}
            ],
        )
        if self.mutate:
            self.mutate(document)
        if self.realize:
            from raes import admit_instantiated_scenario, parse_sdl
            from raes_processor.compiler import compile_runtime_model, materialization_differences
            from raes_processor.planner import plan

            original = admit_instantiated_scenario(json.loads(source.snapshot)["scenario"])
            parsed = parse_sdl(json.dumps(document))
            document["materialization_provenance"]["origins"] = [
                origin.model_dump(mode="json") for origin in materialization_differences(original, parsed)
            ]
            resources = plan(compile_runtime_model(parsed), self.manifest).provisioning.resources
            entries = {
                address: replace(entry, payload=resources[address].payload)
                for address, entry in result.snapshot.entries.items()
            }
            result = replace(result, snapshot=result.snapshot.with_entries(entries))
        return replace(result, materialization_attestation=MaterializationSubmission(sdl=json.dumps(document)))


def _apply(tmp_path, *, mutate=None, omit=False, archive=True, source=None, realize=False):
    execution, _model = attesting_plan(source)
    backend = ReportingProvisioner(execution.manifest, mutate, omit=omit, realize=realize)
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        backend.apply,
        execution.provisioning,
        previous,
        snapshot=previous,
        address="runtime.attesting",
        realization=_RealizationApplyContext(plan=execution.provisioning, manifest=execution.manifest),
        call=_BackendCallContext(materialization_archive=RunMaterializationArchive(tmp_path) if archive else None),
    )
    return result, backend


def test_no_additions_still_returns_and_archives_a_first_class_attestation(tmp_path):
    result, backend = _apply(tmp_path)
    assert result.success, result.diagnostics
    assert backend.calls == 1
    assert result.materialization_attestation is not None
    assert len(result.snapshot.materialization_attestations) == 1
    assert (tmp_path / result.snapshot.materialization_attestations[0].reference.ref_path).is_file()


def test_missing_mandatory_report_is_not_success_and_keeps_cleanup_inventory(tmp_path):
    result, backend = _apply(tmp_path, omit=True)
    assert not result.success
    assert backend.calls == 1
    assert "provision.node.host" in result.snapshot.entries
    assert not result.snapshot.materialization_attestations


def test_missing_archive_owner_fails_before_mutating_the_backend(tmp_path):
    result, backend = _apply(tmp_path, archive=False)
    assert not result.success
    assert backend.calls == 0


@pytest.mark.parametrize(
    "field", ["authored_digest", "instantiated_digest", "plan_digest", "predecessor_digest", "operation_id", "run_id"]
)
def test_stale_or_cross_run_attestation_is_refused(tmp_path, field):
    def mutate(document):
        value = document["materialization_provenance"][field]
        if isinstance(value, dict):
            value["value"] = "sha256:" + "0" * 64
        else:
            document["materialization_provenance"][field] = (
                "sha256:" + "0" * 64 if field.endswith("digest") else "wrong"
            )

    result, backend = _apply(tmp_path, mutate=mutate)
    assert not result.success
    assert backend.calls == 1
    assert "provision.node.host" in result.snapshot.entries
    assert not result.snapshot.materialization_attestations
    assert not list(tmp_path.iterdir())


def test_source_echo_cannot_hide_missing_returned_inventory(tmp_path):
    def mutate(document):
        document["nodes"].clear()
        document["materialization_provenance"]["origins"] = [
            {
                "change": "removed",
                "field_pointer": "/nodes/host",
                "source_pointer": "/nodes/host",
                "origin": "backend-realized",
            }
        ]
        document["materialization_provenance"]["resource_bindings"] = []

    result, _backend = _apply(tmp_path, mutate=mutate)
    assert not result.success
    assert not result.snapshot.materialization_attestations


def test_manager_returns_the_attestation_through_the_existing_apply_flow(tmp_path):
    from raes_runtime import RuntimeManager
    from raes_runtime.registry import RuntimeTarget

    execution, _model = attesting_plan()
    backend = ReportingProvisioner(execution.manifest)
    manager = RuntimeManager(
        RuntimeTarget(name="attesting", manifest=execution.manifest, provisioner=backend),
        materialization_archive=RunMaterializationArchive(tmp_path),
    )
    result = manager.apply(replace(execution, target_name="attesting"))
    assert result.success, result.diagnostics
    assert result.materialization_attestation is not None
    assert manager.snapshot.materialization_attestations == result.snapshot.materialization_attestations


def test_cleanup_does_not_require_a_new_materialization_attestation(tmp_path):
    from raes_runtime import RuntimeManager
    from raes_runtime.registry import RuntimeTarget

    execution, _model = attesting_plan()
    backend = ReportingProvisioner(execution.manifest)
    manager = RuntimeManager(
        RuntimeTarget(name="attesting", manifest=execution.manifest, provisioner=backend),
        materialization_archive=RunMaterializationArchive(tmp_path),
    )
    applied = manager.apply(replace(execution, target_name="attesting"))
    assert applied.success
    destroyed = manager.destroy()
    assert destroyed.success, destroyed.diagnostics
    assert not destroyed.snapshot.entries
    assert destroyed.snapshot.materialization_attestations == applied.snapshot.materialization_attestations


def test_scoped_stop_is_not_a_materialization_request():
    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.runtime_state import ApplyResult

    execution, _model = attesting_plan()
    previous = RuntimeSnapshot()
    calls = []

    def stop(snapshot):
        calls.append(True)
        return ApplyResult(True, snapshot)

    result = _call_backend_apply(
        stop,
        previous,
        address="runtime.stop",
        snapshot=previous,
        realization=_RealizationApplyContext(manifest=execution.manifest, stop_domain=RuntimeDomain.PROVISIONING),
    )
    assert result.success, result.diagnostics
    assert calls == [True]


@pytest.mark.parametrize("indices,success", [([0, 1], True), ([0], False), ([0, 2], False)])
def test_every_replica_has_a_distinct_complete_instance_binding(tmp_path, indices, success):
    def mutate(document):
        document["materialization_provenance"]["resource_bindings"] = [
            {"address": "provision.node.host", "node_name": "host", "source_node": "host", "instance_index": index}
            for index in indices
        ]

    result, _ = _apply(
        tmp_path,
        mutate=mutate,
        source="name: replicas\nnodes:\n  host: {type: compute}\ninfrastructure:\n  host: {count: 2}",
    )
    assert result.success is success, result.diagnostics


def test_faulty_archive_cannot_substitute_another_run_record(tmp_path):
    class SubstitutingArchive:
        def publish(self, content):
            record = RunMaterializationArchive(tmp_path).publish(content)
            return record.model_copy(update={"run_id": "another-run"})

    execution, _ = attesting_plan()
    previous = RuntimeSnapshot()
    backend = ReportingProvisioner(execution.manifest)
    result = _call_backend_apply(
        backend.apply,
        execution.provisioning,
        previous,
        snapshot=previous,
        address="runtime.attesting",
        realization=_RealizationApplyContext(plan=execution.provisioning, manifest=execution.manifest),
        call=_BackendCallContext(materialization_archive=SubstitutingArchive()),
    )
    assert not result.success
    assert "provision.node.host" in result.snapshot.entries
    assert not result.snapshot.materialization_attestations


def test_permitted_in_world_addition_is_archived_at_member_granularity(tmp_path):
    def mutate(document):
        document["nodes"]["host"]["services"] = [{"name": "metrics", "port": 9090}]

    result, _ = _apply(
        tmp_path,
        mutate=mutate,
        realize=True,
        source="name: augmented\nrealization: {default: open}\nnodes:\n  host: {type: compute}",
    )
    assert result.success, result.diagnostics
    from raes import parse_sdl

    report = parse_sdl(result.materialization_attestation.sdl)
    assert report.nodes["host"].services[0].name == "metrics"
    assert all(origin.field_pointer != "/nodes/host" for origin in report.materialization_provenance.origins)


def test_truthful_report_does_not_excuse_a_changed_exact_authored_value(tmp_path):
    result, _ = _apply(
        tmp_path,
        mutate=lambda document: document["nodes"]["host"].update(architecture="aarch64"),
        realize=True,
        source="name: exact\nrealization: {default: open}\nnodes:\n  host: {type: compute, architecture: x86_64}",
    )
    assert not result.success
    assert any(diagnostic.code != "runtime.materialization-attestation-invalid" for diagnostic in result.diagnostics)
    assert not result.snapshot.materialization_attestations


@pytest.mark.parametrize("phase", ["orchestration", "evaluation"])
def test_non_provisioning_materialization_returns_a_bound_no_additions_report(tmp_path, phase):
    from raes_contracts.runtime_state import ApplyResult

    execution, _ = attesting_plan("name: empty-world")
    reporter = ReportingProvisioner(
        execution.manifest, lambda document: document["materialization_provenance"].update(resource_bindings=[])
    )
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        lambda request, prior: reporter.report(request, prior, ApplyResult(True, prior)),
        getattr(execution, phase),
        previous,
        snapshot=previous,
        address="runtime.materialization",
        realization=_RealizationApplyContext(manifest=execution.manifest),
        call=_BackendCallContext(materialization_archive=RunMaterializationArchive(tmp_path)),
    )
    assert result.success, result.diagnostics
    assert result.materialization_attestation is not None
    assert len(result.snapshot.materialization_attestations) == 1


def test_evaluator_cannot_claim_unreturned_provisioning_effects(tmp_path):
    from raes_contracts.runtime_state import ApplyResult

    def mutate(document):
        document["nodes"] = {"sensor": {"type": "compute"}}
        document["materialization_provenance"].update(
            origins=[{"field_pointer": "/nodes/sensor", "change": "added", "origin": "backend-realized"}],
            resource_bindings=[{"address": "provision.node.sensor", "node_name": "sensor"}],
        )

    execution, _ = attesting_plan("name: empty-world")
    reporter = ReportingProvisioner(execution.manifest, mutate)
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        lambda request, prior: reporter.report(request, prior, ApplyResult(True, prior)),
        execution.evaluation,
        previous,
        snapshot=previous,
        address="runtime.materialization",
        realization=_RealizationApplyContext(manifest=execution.manifest),
        call=_BackendCallContext(materialization_archive=RunMaterializationArchive(tmp_path)),
    )
    assert not result.success
    assert not result.snapshot.materialization_attestations

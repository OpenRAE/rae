"""Target conformance qualifies negotiated materialization producers (issue #1667)."""

import shutil
import stat
from dataclasses import replace
from types import SimpleNamespace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_conformance import realization
from raes_conformance._materialization_scope import materialization_probe_scope
from raes_conformance.conformance import probe_runtime, run_target_conformance, target_probes
from raes_conformance.conformance.target_planning import target_probe_execution_plan
from raes_conformance.realization import ExecutionBasis, run_realization_conformance
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import InvalidInputError
from raes_contracts.runtime_state import RuntimeSnapshot, RuntimeSnapshotEnvelope
from raes_operations.run_artifacts import RunMaterializationArchive, is_valid_run_id_label
from raes_processor.reference import run_reference_processor
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.registry import RuntimeTarget
from runtime_descendant_fixtures import CONTRACT, DescendantBackend
from test_issue_1241_materialization_context import attesting_plan
from test_issue_1241_materialization_runtime import ReportingProvisioner
from test_realization_honesty_conformance import _ScriptedHarness
from test_realization_honesty_conformance import _target as _honesty_target

SCENARIO = "name: dynamic\nrealization: {default: open}\nnodes:\n  host: {type: compute}"
ATTESTATION = "backend-materialization-attestation-v1"


class _RecordingArchive(RunMaterializationArchive):
    """The real protected writer, recording each publication while the probe runs."""

    def __init__(self, output_dir, sink):
        super().__init__(output_dir)
        self.published = []
        sink.append(self)

    def publish(self, content):
        record = super().publish(content)
        path = self.output_dir / record.reference.ref_path
        self.published.append((record, stat.S_IMODE(path.stat().st_mode), stat.S_IMODE(self.output_dir.stat().st_mode)))
        return record


class _FailingArchive(RunMaterializationArchive):
    def __init__(self, output_dir, sink):
        super().__init__(output_dir)
        sink.append(self)

    def publish(self, content):
        raise OSError("archive device unavailable")


def _install_archive(monkeypatch, archive_type):
    archives = []
    monkeypatch.setattr(probe_runtime, "RunMaterializationArchive", lambda root: archive_type(root, archives))
    return archives


def _descendant_target():
    execution, _ = attesting_plan()
    manifest = replace(
        execution.manifest,
        supported_contract_versions=execution.manifest.supported_contract_versions | {CONTRACT},
    )
    backend = DescendantBackend(manifest)
    return RuntimeTarget(name="descendants", manifest=manifest, provisioner=backend), backend


def _attesting_target(**reporting):
    execution, _ = attesting_plan()
    backend = ReportingProvisioner(execution.manifest, **reporting)
    return RuntimeTarget(name="attesting", manifest=execution.manifest, provisioner=backend), backend


def _cases(target):
    report = run_target_conformance(target, profile="provisioning-only", reference_scenario=SCENARIO)
    return {case.name: case for case in report.cases}


def test_descendant_producer_reaches_apply_and_its_report_is_archived(monkeypatch):
    archives = _install_archive(monkeypatch, _RecordingArchive)
    target, backend = _descendant_target()

    cases = _cases(target)

    assert {ATTESTATION, CONTRACT} <= target.manifest.supported_contract_versions
    assert backend.applies == 1
    assert cases["target-provisioning"].passed, cases["target-provisioning"].diagnostics
    assert cases["target-snapshot"].passed, cases["target-snapshot"].diagnostics
    source = backend.last_request.materialization_source
    assert source.target_scope == "target:descendants"
    assert is_valid_run_id_label(source.run_id)
    assert backend.last_request.run_id == source.run_id
    [archive] = archives
    [(record, file_mode, root_mode)] = archive.published
    assert (file_mode, root_mode) == (0o600, 0o700)
    assert record.run_id == source.run_id
    assert record.inventory.target_scope == "target:descendants"
    assert {descendant.address for descendant in record.inventory.descendants} == {
        "provision.node.worker",
        "provision.node.leaf",
    }
    assert not archive.output_dir.exists()


def test_attestation_only_producer_passes_with_a_no_additions_report(monkeypatch):
    archives = _install_archive(monkeypatch, _RecordingArchive)
    target, backend = _attesting_target()

    cases = _cases(target)

    assert backend.calls == 1
    assert cases["target-provisioning"].passed, cases["target-provisioning"].diagnostics
    assert cases["target-snapshot"].passed, cases["target-snapshot"].diagnostics
    [archive] = archives
    assert len(archive.published) == 1
    assert not archive.output_dir.exists()


def _misbound_run(document):
    document["materialization_provenance"]["run_id"] = "another-run"


@pytest.mark.parametrize(
    ("reporting", "archive_type"),
    [
        ({"omit": True}, _RecordingArchive),
        ({"mutate": _misbound_run}, _RecordingArchive),
        ({}, _FailingArchive),
    ],
    ids=["missing-report", "invalid-report", "failed-archive-delivery"],
)
def test_rejected_report_or_delivery_fails_the_provisioning_probe(monkeypatch, reporting, archive_type):
    archives = _install_archive(monkeypatch, archive_type)
    target, backend = _attesting_target(**reporting)

    cases = _cases(target)

    assert backend.calls == 1
    provisioning = cases["target-provisioning"]
    assert not provisioning.passed
    assert [diagnostic.code for diagnostic in provisioning.diagnostics] == ["conformance.provisioning-failed"]
    assert "protected archival delivery failed" in provisioning.diagnostics[0].message
    assert "another-run" not in provisioning.diagnostics[0].message
    assert "archive device unavailable" not in provisioning.diagnostics[0].message
    assert not cases["target-snapshot"].passed
    assert "conformance.materialization-not-archived" in {
        diagnostic.code for diagnostic in cases["target-snapshot"].diagnostics
    }
    [archive] = archives
    assert not archive.output_dir.exists()


def test_each_probe_receives_a_fresh_target_bound_run_identity():
    target, _backend = _descendant_target()

    first, second = materialization_probe_scope(target), materialization_probe_scope(target)

    assert first.target_name == second.target_name == "descendants"
    assert first.run_id != second.run_id
    assert is_valid_run_id_label(first.run_id)


def test_unsafe_target_identity_fails_before_backend_execution(monkeypatch):
    archives = _install_archive(monkeypatch, _RecordingArchive)
    target, backend = _descendant_target()
    target = replace(target, name="local descendants")

    cases = _cases(target)

    assert backend.applies == 0
    assert not archives
    assert "materialization.source-context-required" in cases["target-provisioning"].diagnostics[0].message


def test_targets_without_negotiated_reporting_keep_the_unscoped_probe(monkeypatch):
    archives = _install_archive(monkeypatch, _RecordingArchive)
    target = create_stub_target()

    assert materialization_probe_scope(target) is None
    plan = target_probe_execution_plan(SCENARIO, target, provisioning_only=True)
    assert plan.provisioning.run_id is None
    assert plan.provisioning.materialization_source is None
    cases = {case.name: case for case in run_target_conformance(target).cases}
    assert cases["target-provisioning"].passed, cases["target-provisioning"].diagnostics
    assert cases["target-snapshot"].passed, cases["target-snapshot"].diagnostics
    assert not archives


def test_snapshot_case_requires_an_archived_attestation_for_negotiated_producers():
    snapshot = RuntimeSnapshot()
    control_plane = SimpleNamespace(snapshot=snapshot, get_snapshot=lambda: RuntimeSnapshotEnvelope(snapshot=snapshot))

    required = target_probes._hermetic_snapshot_case(control_plane, materialization_required=True)
    unscoped = target_probes._hermetic_snapshot_case(control_plane)

    assert "conformance.materialization-not-archived" in {diagnostic.code for diagnostic in required.diagnostics}
    assert "conformance.materialization-not-archived" not in {diagnostic.code for diagnostic in unscoped.diagnostics}


def _run_positive_probes(target):
    harness = _ScriptedHarness()
    run = run_realization_conformance(target, harness=harness, execution_basis=ExecutionBasis.HERMETIC_LIVE)
    return run, [request for request in harness.calls if not request.negative]


def test_positive_realization_probes_plan_with_the_target_bound_run_identity():
    base = _honesty_target()
    manifest = replace(
        base.manifest, supported_contract_versions=base.manifest.supported_contract_versions | {ATTESTATION}
    )

    _run, positives = _run_positive_probes(replace(base, manifest=manifest))

    assert positives
    for request in positives:
        source = request.provisioning_plan.materialization_source
        assert source is not None
        assert is_valid_run_id_label(source.run_id)
        assert request.provisioning_plan.run_id == source.run_id


def test_positive_probe_with_planning_errors_never_reaches_the_harness(monkeypatch):
    def failing_processor(*args, **kwargs):
        result = run_reference_processor(*args, **kwargs)
        error = Diagnostic(code="planning.failed", domain="provisioning", address="probe", message="refused")
        return replace(result, execution_plan=replace(result.execution_plan, diagnostics=[error]))

    monkeypatch.setattr(realization, "run_reference_processor", failing_processor)

    run, positives = _run_positive_probes(_honesty_target())

    assert not positives
    positive_cases = [case for case in run.cases if case.name.startswith("realization-positive-")]
    assert positive_cases
    for case in positive_cases:
        assert not case.passed
        assert [diagnostic.code for diagnostic in case.diagnostics] == ["conformance.positive-probe-plan-failed"]


def test_positive_probe_refused_by_the_processor_never_reaches_the_harness(monkeypatch):
    def refusing_processor(*args, **kwargs):
        raise InvalidInputError("observation scope does not resolve")

    monkeypatch.setattr(realization, "run_reference_processor", refusing_processor)

    run, positives = _run_positive_probes(_honesty_target())

    assert not positives
    positive_cases = [case for case in run.cases if case.name.startswith("realization-positive-")]
    assert positive_cases
    for case in positive_cases:
        assert [diagnostic.code for diagnostic in case.diagnostics] == ["conformance.positive-probe-plan-failed"]


def test_positive_probe_planning_defect_is_not_reported_as_a_refusal(monkeypatch):
    def defective_processor(*args, **kwargs):
        raise RuntimeError("planner defect")

    monkeypatch.setattr(realization, "run_reference_processor", defective_processor)

    with pytest.raises(RuntimeError, match="planner defect"):
        _run_positive_probes(_honesty_target())


class _UndrainedRuntime(RuntimeControlPlane):
    """A runtime whose backend call is still unresolved when the probe ends."""

    opened: list = []

    def __init__(self, target, **options):
        super().__init__(target, **options)
        self.undrained = True
        _UndrainedRuntime.opened.append(self)

    def close(self):
        if self.undrained:
            raise TimeoutError("runtime drain has unresolved external calls")
        super().close()


def test_archive_is_retained_while_a_runtime_cannot_drain(monkeypatch):
    archives = _install_archive(monkeypatch, _RecordingArchive)
    monkeypatch.setattr(_UndrainedRuntime, "opened", [])
    monkeypatch.setattr(probe_runtime, "RuntimeControlPlane", _UndrainedRuntime)
    target, backend = _descendant_target()

    with pytest.raises(TimeoutError):
        _cases(target)

    assert backend.applies == 1
    [archive] = archives
    [(record, _file_mode, _root_mode)] = archive.published
    assert (archive.output_dir / record.reference.ref_path).is_file()
    for runtime in _UndrainedRuntime.opened:
        runtime.undrained = False
        runtime.close()
    shutil.rmtree(archive.output_dir)


def test_owner_removes_the_archive_only_after_confirmed_closure(monkeypatch):
    monkeypatch.setattr(_UndrainedRuntime, "opened", [])
    monkeypatch.setattr(probe_runtime, "RuntimeControlPlane", _UndrainedRuntime)
    target, _backend = _descendant_target()
    owner = probe_runtime.ProbeRuntimeOwner(materialization_probe_scope(target))
    runtime = owner.runtime(target)
    root = runtime._materialization_archive.output_dir

    with pytest.raises(TimeoutError):
        owner.close()
    assert root.is_dir()

    runtime.undrained = False
    owner.close()
    assert not root.exists()

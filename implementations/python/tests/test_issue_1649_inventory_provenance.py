"""Concern value origins remain independent of author constraints."""

import pytest
from raes_contracts.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_processor.semantics.realization_requirement import CompiledRealizationRequirement
from raes_processor.semantics.realization_runtime_common import realization_provenance_entry
from runtime_descendant_fixtures import ROOT, descendant_runtime


def test_equal_constrained_backend_selection_does_not_become_author_origin():
    requirement = CompiledRealizationRequirement(
        address=ROOT,
        field_path="nodes.host.type",
        domain="runtime-realization",
        requirement_kind="node-type",
        explicitness=ExplicitnessClass.CONSTRAINED,
        provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
    )
    record = realization_provenance_entry(requirement, True)
    assert record.explicitness is ExplicitnessClass.CONSTRAINED
    assert record.provenance is ExplicitnessProvenance.BACKEND_REALIZED


def test_descendant_reporting_preserves_author_and_processor_concern_origins(tmp_path):
    manager, backend, plan, _target, _archive = descendant_runtime(tmp_path)
    result = manager.apply(plan)
    assert result.success, result.diagnostics
    ledger = result.snapshot.realization_provenance
    assert any(entry.address == ROOT and entry.provenance is ExplicitnessProvenance.AUTHOR_DECLARED for entry in ledger)
    assert any(
        entry.address == "provision.node.worker" and entry.provenance is ExplicitnessProvenance.BACKEND_REALIZED
        for entry in ledger
    )
    requirement = CompiledRealizationRequirement(
        address=ROOT,
        field_path="nodes.host.type",
        domain="runtime-realization",
        requirement_kind="node-type",
        explicitness=ExplicitnessClass.EXACT,
        provenance=ExplicitnessProvenance.PROCESSOR_DERIVED,
    )
    assert realization_provenance_entry(requirement, True).provenance is ExplicitnessProvenance.PROCESSOR_DERIVED
    before = {entry for entry in ledger if entry.address == ROOT}
    refreshed = manager.refresh_inventory(plan)
    assert refreshed.success, refreshed.diagnostics
    assert before <= set(refreshed.snapshot.realization_provenance)
    manager.close()


@pytest.mark.parametrize("backend_choice", [False, True])
def test_public_report_distinguishes_equal_constrained_backend_choice(tmp_path, backend_choice):
    manager, backend, plan, _target, _archive = descendant_runtime(
        tmp_path,
        "name: constrained\nrealization:\n  default: open\n  scopes:\n"
        "    - {field_pointer: /nodes/host/runtime, posture: closed}\n"
        "variables:\n  family: {type: string, default: linux, allowed_values: [linux, windows]}\n"
        "nodes:\n  host: {type: compute, os: '${family}'}\n",
    )
    backend.observe_host_os = True
    if backend_choice:
        backend.selections = [{"address": ROOT, "field_path": "nodes.host.os", "requirement_kind": "os-family"}]
    result = manager.apply(plan)
    assert result.success, result.diagnostics
    record = next(entry for entry in result.snapshot.realization_provenance if entry.field_path == "nodes.host.os")
    assert record.explicitness is ExplicitnessClass.CONSTRAINED
    assert record.provenance is (
        ExplicitnessProvenance.BACKEND_REALIZED if backend_choice else ExplicitnessProvenance.PROCESSOR_DERIVED
    )
    manager.close()


def test_explicit_empty_descendant_concern_has_backend_value_origin(tmp_path):
    manager, backend, plan, _target, _archive = descendant_runtime(tmp_path)
    backend.node_values["worker"] = {"type": "compute", "runtime": {"environment": []}}
    result = manager.apply(plan)
    assert result.success, result.diagnostics
    assert any(
        entry.address == "provision.node.worker"
        and entry.requirement_kind == "runtime-environment"
        and entry.provenance is ExplicitnessProvenance.BACKEND_REALIZED
        for entry in result.snapshot.realization_provenance
    )
    manager.close()

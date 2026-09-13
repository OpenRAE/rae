"""Abstract execution and incomplete capture have distinct admission obligations."""

from raes import parse_sdl
from raes.runtime_configuration import RuntimeConfiguration
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_reference_backend import create_reference_backend_target
from raes_reference_backend.drivers.inprocess import InProcessDriver
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager
from test_issue_1112_capture_admission import _capture_scenario


def test_complete_abstract_model_executes_without_concrete_os_or_automatic_capture():
    driver = InProcessDriver()
    manager = RuntimeManager(create_reference_backend_target(driver=driver))
    scenario = parse_sdl("name: abstract\nnodes:\n  host: {type: compute}\n")
    execution = manager.plan(scenario)
    assert execution.is_valid, execution.diagnostics
    assert not scenario.evidence_requirements
    result = manager.apply(execution)
    assert result.success, result.diagnostics
    assert driver.realized_addresses() == {"provision.node.host"}
    assert not result.snapshot.realization_observations
    assert manager.destroy().success


def test_partial_inventory_does_not_waive_selected_required_capture():
    scenario = _capture_scenario()
    scenario.nodes["vm"].runtime = RuntimeConfiguration(
        datastore_services=[{"datastore_service_id": "search", "data_model": "search_index", "partitions": []}]
    )
    target = create_stub_target()
    execution = plan(compile_runtime_model(scenario), target.manifest, target_name=target.name)
    assert any(row.code == "capture.offer-missing" for row in execution.diagnostics)
    control = RuntimeControlPlane(target)
    receipt = control.submit_provisioning(execution.provisioning)
    assert not receipt.accepted
    assert control.snapshot.entries == {}

"""The canonical minimal scenario stays admissible without a pinned substrate (issue #607).

`cross-backend-minimal.sdl.yaml` authors compute intent without a virtualization
mechanism or an operating system, so a provisioning backend selects a
compatible substrate rather than contradicting an authored value. These tests
pin that portability through two in-process provisioners: the stub, which
reports substrate facts at apply time, and a narrow double that reads them back
through the native readback seam.

Scope, stated plainly. Both targets are daemon-free test doubles, so this
exercises plan admission, capability-envelope checks, typed substrate
disclosure, and snapshot reconciliation. Concrete backends (for example
LilRAE) own native realization evidence; this measures nothing about
fidelity.
"""

from __future__ import annotations

import pytest
from paths import EXAMPLES_DIR
from raes import parse_sdl_file
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.manager import RuntimeManager
from t2_native_readback_double import create_native_readback_target

SCENARIO_PATH = EXAMPLES_DIR / "cross-backend-minimal.sdl.yaml"


def _targets():
    return (
        ("stub", create_stub_target()),
        ("native-readback", create_native_readback_target()),
    )


def _error_codes(diagnostics) -> list[str]:
    return [d.code for d in diagnostics if getattr(d.severity, "value", str(d.severity)) == "error"]


def _scenario():
    return parse_sdl_file(SCENARIO_PATH)


def test_scenario_authors_compute_intent_without_a_virtualization_mechanism():
    """The portability of this scenario rests on not pinning substrate or OS."""

    scenario = _scenario()

    workload = scenario.nodes["workload"]
    assert workload.type.value == "compute"
    # An authored OS becomes an exact SEM-218 realization requirement, which a
    # backend declaring no matching compatibility row must refuse. Leaving it
    # unset is what keeps the scenario admissible on more than one envelope.
    assert workload.os is None
    assert scenario.realization is None


@pytest.mark.parametrize("backend_name", [name for name, _ in _targets()])
def test_scenario_is_admitted_without_diagnostics_by_each_backend(backend_name):
    scenario = _scenario()
    target = dict(_targets())[backend_name]

    execution_plan = plan(compile_runtime_model(scenario), target.manifest)

    assert _error_codes(execution_plan.diagnostics) == []
    assert execution_plan.provisioning.operations


def test_each_backend_preserves_resources_without_implicit_observation():
    """Preserve authored resources without turning backend selection into telemetry."""

    scenario = _scenario()
    realized: dict[str, dict[str, str]] = {}

    for backend_name, target in _targets():
        manager = RuntimeManager(target)
        result = manager.apply(manager.plan(scenario))

        assert result.success, [diagnostic.message for diagnostic in result.diagnostics]
        realized[backend_name] = {address: entry.resource_type for address, entry in result.snapshot.entries.items()}
        substrate_observations = [
            observation
            for observation in result.snapshot.realization_observations
            if observation.requirement_kind == "compute-substrate"
        ]
        assert substrate_observations == []

        substrate_provenance = [
            provenance
            for provenance in result.snapshot.realization_provenance
            if provenance.requirement_kind == "compute-substrate"
        ]
        assert len(substrate_provenance) == 1
        [provenance] = substrate_provenance
        assert provenance.address == "provision.node.workload"
        assert provenance.explicitness.value == "open"
        assert provenance.provenance.value == "backend-realized"

    stub, native = realized["stub"], realized["native-readback"]
    assert stub == native, {
        "only-in-stub": sorted(set(stub) - set(native)),
        "only-in-native-readback": sorted(set(native) - set(stub)),
    }
    assert sorted(stub) == ["provision.network.lab", "provision.node.workload"]

"""The canonical minimal scenario resolves on more than one backend (issue #607).

`cross-backend-minimal.sdl.yaml` authors compute intent without a virtualization
mechanism or an operating system, so each provisioning backend selects a
compatible substrate rather than contradicting an authored value. These tests
pin that portability: one authored scenario, compiled per backend, admitted and
realized by both.

Scope, stated plainly. Both backends run here on daemon-free drivers -- the
reference backend's in-process driver and `RecordingLibvirtDriver` -- so this
exercises plan admission, capability-envelope checks, typed substrate
disclosure, and snapshot reconciliation. It is evidence that the specification
is portable across the two declared envelopes. It is not evidence from either
an OCI runtime or a live libvirt/QEMU daemon, and it measures nothing about
fidelity.
"""

from __future__ import annotations

import pytest
from libvirt_conformance_fixtures import RecordingLibvirtDriver
from paths import EXAMPLES_DIR
from raes import parse_sdl_file
from raes_backend_libvirt import create_libvirt_target
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_reference_backend import create_reference_backend_target
from raes_runtime.manager import RuntimeManager

SCENARIO_PATH = EXAMPLES_DIR / "cross-backend-minimal.sdl.yaml"


def _targets():
    return (
        ("reference", create_reference_backend_target()),
        ("libvirt", create_libvirt_target(driver=RecordingLibvirtDriver(), driver_mode="generic")),
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


def test_both_backends_preserve_resources_without_implicit_observation():
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

    reference, libvirt = realized["reference"], realized["libvirt"]
    assert reference == libvirt, {
        "only-in-reference": sorted(set(reference) - set(libvirt)),
        "only-in-libvirt": sorted(set(libvirt) - set(reference)),
    }
    assert sorted(reference) == ["provision.network.lab", "provision.node.workload"]

"""RUN-313 regression guards for issue #1099's realization-pass hotspot."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import raes_processor.compiler.realization_requirements as realization_requirements
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st
from paths import EXAMPLES_DIR
from raes import instantiate_scenario, parse_sdl, parse_sdl_file
from raes.scenario import InstantiatedScenario
from raes_backend_stubs.stubs import create_stub_manifest
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan


def _generated_scenario(*, node_count: int, constrained_os: bool, open_default: bool):
    os_value = "${os_choice}" if constrained_os else "linux"
    payload: dict[str, object] = {
        "name": f"run-313-{node_count}-{int(constrained_os)}-{int(open_default)}",
        "nodes": {
            f"node-{index}": {
                "type": "compute",
                "os": os_value,
                "resources": {"ram": "1 gib", "cpu": index + 1},
            }
            for index in range(node_count)
        },
    }
    if constrained_os:
        payload["variables"] = {
            "os_choice": {
                "type": "string",
                "default": "linux",
                "allowed_values": ["linux", "windows"],
            }
        }
    if open_default:
        payload["realization"] = {"default": "open"}
    return parse_sdl(yaml.safe_dump(payload, sort_keys=False))


def _compile_with_repeated_explicitness_lookup(scenario):
    """Reference issue #1099's pre-fix per-concern reconstruction behavior."""

    optimized_helper = realization_requirements._compiled_registered_realization

    def repeated_lookup(scenario_arg, registered, _pass_explicitness):
        return optimized_helper(scenario_arg, registered, scenario_arg.explicitness)

    with patch.object(realization_requirements, "_compiled_registered_realization", repeated_lookup):
        return compile_runtime_model(scenario)


@settings(max_examples=12, deadline=None)
@given(
    node_count=st.integers(min_value=1, max_value=5),
    constrained_os=st.booleans(),
    open_default=st.booleans(),
)
def test_single_snapshot_matches_repeated_lookup_runtime_and_plan(
    node_count: int,
    constrained_os: bool,
    open_default: bool,
) -> None:
    """The pass-local snapshot preserves the old lookup semantics end to end."""

    optimized = compile_runtime_model(
        _generated_scenario(
            node_count=node_count,
            constrained_os=constrained_os,
            open_default=open_default,
        )
    )
    reference = _compile_with_repeated_explicitness_lookup(
        _generated_scenario(
            node_count=node_count,
            constrained_os=constrained_os,
            open_default=open_default,
        )
    )

    assert len(optimized.realization_authority) >= node_count * 2
    assert optimized == reference
    manifest = create_stub_manifest()
    assert plan(optimized, manifest) == plan(reference, manifest)


def _compile_with_explicitness_count(scenario: InstantiatedScenario):
    original_getter = InstantiatedScenario.explicitness.fget
    assert original_getter is not None
    calls = 0

    def counted_explicitness(concrete: InstantiatedScenario):
        nonlocal calls
        calls += 1
        return original_getter(concrete)

    with patch.object(InstantiatedScenario, "explicitness", property(counted_explicitness)):
        compiled = compile_runtime_model(scenario)
    return compiled, calls


def test_small_compile_materializes_instantiated_explicitness_once() -> None:
    scenario = instantiate_scenario(_generated_scenario(node_count=3, constrained_os=True, open_default=True))
    compiled, calls = _compile_with_explicitness_count(scenario)
    assert len(compiled.node_deployments) == 3
    assert calls == 1


@pytest.mark.integration
def test_complex_compile_materializes_instantiated_explicitness_once() -> None:
    """Guard work count, not machine-dependent wall-clock latency."""

    source = parse_sdl_file(EXAMPLES_DIR / "hospital-ransomware-surgery-day.sdl.yaml")
    parameters = {name: variable.default for name, variable in source.variables.items() if variable.default is not None}
    scenario = instantiate_scenario(source, parameters=parameters)
    compiled, calls = _compile_with_explicitness_count(scenario)

    assert len(compiled.realization_authority) > 100
    assert calls == 1

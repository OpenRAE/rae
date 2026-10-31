"""SEM-218 explicitness classifier and instantiation downgrade tests."""

from __future__ import annotations

import textwrap

import pytest
from raes import SDLValidationError, instantiate_scenario, parse_sdl
from raes_contracts.explicitness import ExplicitnessClass, ExplicitnessProvenance


def _scenario_with_explicitness_cases():
    return parse_sdl(
        textwrap.dedent("""
        name: sem-218-explicitness
        variables:
          os_choice:
            type: string
            default: linux
            allowed_values: [linux, windows]
          node_count:
            type: integer
            default: 1
            allowed_values: [1, 3]
        nodes:
          net:
            type: switch
          vm:
            type: compute
            os: ${os_choice}
            resources:
              ram: 1 gib
              cpu: 2
            runtime:
              network:
                endpoints:
                  - network: net
                    backend:
                      driver: unknown
        infrastructure:
          net:
            count: 1
            properties:
              cidr: 10.0.0.0/24
              gateway: 10.0.0.1
          vm:
            count: ${node_count}
            links: [net]
        """)
    )


def test_semantic_validator_attaches_exact_constrained_and_open_classifications():
    scenario = _scenario_with_explicitness_cases()

    explicitness = scenario.explicitness

    assert explicitness["nodes.vm.resources.cpu"].classification is ExplicitnessClass.EXACT
    assert explicitness["nodes.vm.os"].classification is ExplicitnessClass.CONSTRAINED
    assert explicitness["nodes.vm.runtime.network.endpoints[0].backend.driver"].classification is ExplicitnessClass.OPEN


def test_instantiation_downgrades_substituted_values_without_creating_false_exactness():
    raw = _scenario_with_explicitness_cases()

    instantiated = instantiate_scenario(raw, parameters={"os_choice": "windows", "node_count": 3})
    explicitness = instantiated.explicitness

    assert instantiated.nodes["vm"].os == "windows"
    assert instantiated.infrastructure["vm"].count == 3
    assert explicitness["nodes.vm.os"].classification is ExplicitnessClass.CONSTRAINED
    assert explicitness["nodes.vm.os"].provenance is ExplicitnessProvenance.PROCESSOR_DERIVED
    assert explicitness["nodes.vm.os"].variables == ("os_choice",)
    assert explicitness["infrastructure.vm.count"].classification is ExplicitnessClass.CONSTRAINED
    assert explicitness["infrastructure.vm.count"].provenance is ExplicitnessProvenance.PROCESSOR_DERIVED
    assert explicitness["nodes.vm.resources.cpu"].classification is ExplicitnessClass.EXACT
    assert explicitness["nodes.vm.resources.cpu"].provenance is ExplicitnessProvenance.AUTHOR_DECLARED


def test_unclassifiable_variable_reference_is_reported_through_validation_errors():
    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(
            textwrap.dedent("""
            name: sem-218-unclassifiable
            nodes:
              vm:
                type: compute
                os: ${missing_os}
                resources:
                  ram: 1 gib
                  cpu: 1
            """)
        )

    assert "Undefined variable 'missing_os' referenced at 'nodes.vm.os'" in str(excinfo.value)
    assert "Cannot classify explicitness for 'nodes.vm.os'" in str(excinfo.value)

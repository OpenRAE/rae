"""SEM-218 part 2: typed compiler emission + planner realization-support gate.

These tests exercise enforcement points 3 (typed compiler emission preserving
the exact/constrained/open class) and 4 (the planner realization-support gate)
of the SEM-218 spec ``specs/formal/realization/explicitness-and-realization.md``.
They follow the cross-stage differential idiom of ``test_fm2_semantics.py``:
the compiled runtime model must preserve the classifier's class, and the
planner must reject an unrealizable exact declaration with a structured
``Diagnostic`` rather than silently approximate it (invariant I2).
"""

from __future__ import annotations

import textwrap

from raes import instantiate_scenario, parse_sdl
from raes_backend_protocols.capabilities import (
    BackendManifest,
    OperatingSystemCompatibility,
    ProvisionerCapabilities,
)
from raes_contracts.apparatus import (
    ConceptBinding,
    RealizationObservationCapability,
    RealizationSupportDeclaration,
)
from raes_contracts.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_contracts.vocabulary import (
    ObservationStrength,
    RealizationSupportMode,
    RealizationVerificationScope,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan

_EXACT_SCENARIO = """
name: sem-218-exact-realization
nodes:
  web:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
"""

_CONSTRAINED_SCENARIO = """
name: sem-218-constrained-realization
variables:
  os_choice: {type: string, default: linux, allowed_values: [linux, windows]}
nodes:
  web:
    type: compute
    os: ${os_choice}
    resources: {ram: 1 gib, cpu: 1}
"""


def _scenario(yaml_str: str):
    return parse_sdl(textwrap.dedent(yaml_str))


def _manifest(
    *,
    realization_support: tuple[RealizationSupportDeclaration, ...],
    node_types: frozenset[str] = frozenset({"compute"}),
    os_families: frozenset[str] = frozenset({"linux"}),
) -> BackendManifest:
    """A minimal backend manifest with caller-controlled realization support.

    The provisioner is sized to accept the test nodes so the only diagnostics
    under test come from the realization-support gate, not the pre-existing
    capability checks.
    """

    return BackendManifest(
        name="realization-gate-test",
        version="0.0.1",
        supported_contract_versions=frozenset({"backend-manifest-v2"}),
        compatible_processors=frozenset({"raes-reference-processor"}),
        realization_support=realization_support,
        concept_bindings=(ConceptBinding(scope="capabilities.provisioner.supported_node_types", family="assets"),),
        provisioner=ProvisionerCapabilities(
            name="realization-gate-provisioner",
            supported_node_types=node_types,
            supported_os_families=os_families,
            operating_systems=tuple(
                OperatingSystemCompatibility(
                    family=family,
                    distribution=("ubuntu" if family == "linux" else "windows-server"),
                    versions=frozenset({"22.04" if family == "linux" else "2022"}),
                )
                for family in sorted(os_families & {"linux", "windows"})
            ),
        ),
    )


def _supporting_manifest(*, constrained: bool = False) -> BackendManifest:
    return _manifest(
        os_families=frozenset({"linux", "windows"}) if constrained else frozenset({"linux"}),
        realization_support=(
            RealizationSupportDeclaration(
                domain="runtime-realization",
                support_mode=RealizationSupportMode.CONSTRAINED,
                supported_constraint_kinds=frozenset({"node-type", "os-family"}),
                supported_exact_requirement_kinds=frozenset({"declared-capability-match"}),
                disclosure_kinds=frozenset({"runtime-snapshot-v1"}),
                observation_capabilities={
                    "operating-system": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.PRESENCE,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    )
                },
            ),
        ),
    )


def test_compiler_preserves_classifier_class_on_realization_requirements():
    """Enforcement point 3: the class flows through compilation as typed fields."""

    model = compile_runtime_model(_scenario(_CONSTRAINED_SCENARIO))
    by_field = {req.field_path: req for req in model.realization_requirements}

    assert by_field["nodes.web.type"].explicitness is ExplicitnessClass.EXACT
    assert by_field["nodes.web.type"].requirement_kind == "node-type"
    assert by_field["nodes.web.type"].domain == "runtime-realization"

    assert by_field["nodes.web.os"].explicitness is ExplicitnessClass.CONSTRAINED
    assert by_field["nodes.web.os"].requirement_kind == "os-family"


def test_compiled_class_matches_scenario_classifier_output():
    """Differential: compiled class == classifier class for every emitted requirement."""

    classified = instantiate_scenario(_scenario(_CONSTRAINED_SCENARIO)).explicitness
    model = compile_runtime_model(_scenario(_CONSTRAINED_SCENARIO))

    assert model.realization_requirements
    for req in model.realization_requirements:
        if req.requirement_kind == "compute-substrate":
            assert req.field_path not in classified
            assert req.explicitness is ExplicitnessClass.OPEN
            continue
        assert req.field_path in classified
        assert req.explicitness is classified[req.field_path].classification


def test_compiled_provenance_matches_scenario_classifier_output():
    """Differential: compilation preserves the classifier's origin authority."""

    classified = instantiate_scenario(_scenario(_CONSTRAINED_SCENARIO)).explicitness
    model = compile_runtime_model(_scenario(_CONSTRAINED_SCENARIO))

    by_field = {req.field_path: req for req in model.realization_requirements}
    assert by_field["nodes.web.os"].provenance is ExplicitnessProvenance.PROCESSOR_DERIVED
    assert by_field["nodes.web.os"].provenance is classified["nodes.web.os"].provenance
    assert by_field["nodes.web.type"].provenance is ExplicitnessProvenance.AUTHOR_DECLARED


def test_planner_rejects_unrealizable_exact_declaration():
    """Enforcement point 4 / invariant I2: an exact requirement with no exact
    realization support fails planning with a structured diagnostic."""

    model = compile_runtime_model(_scenario(_EXACT_SCENARIO))
    manifest = _manifest(
        realization_support=(
            RealizationSupportDeclaration(
                domain="runtime-realization",
                support_mode=RealizationSupportMode.CONSTRAINED,
                supported_constraint_kinds=frozenset({"os-family", "node-type"}),
                disclosure_kinds=frozenset({"runtime-snapshot-v1"}),
            ),
        ),
    )

    execution_plan = plan(model, manifest)

    codes = {diag.code for diag in execution_plan.diagnostics}
    assert "realization.unsupported-exact-requirement" in codes
    assert not execution_plan.is_valid

    messages = [
        diag.message for diag in execution_plan.diagnostics if diag.code == "realization.unsupported-exact-requirement"
    ]
    assert any("nodes.web.os" in message for message in messages)
    assert any("declared-capability-match" in message for message in messages)


def test_planner_accepts_exact_declaration_when_backend_supports_it():
    """The stub manifest declares declared-capability-match, so an exact
    declaration plans without a realization diagnostic."""

    execution_plan = plan(compile_runtime_model(_scenario(_EXACT_SCENARIO)), _supporting_manifest())

    codes = {diag.code for diag in execution_plan.diagnostics}
    assert not any(code.startswith("realization.") for code in codes)


def test_planner_rejects_unsupported_constraint_kind():
    """An unsupported constraint kind fails planning the same way (spec Planning row)."""

    model = compile_runtime_model(_scenario(_CONSTRAINED_SCENARIO))
    manifest = _manifest(
        # Support every allowed os value so the pre-existing provisioner
        # os-family check passes and only the new constraint-kind gate fires.
        os_families=frozenset({"linux", "windows"}),
        realization_support=(
            RealizationSupportDeclaration(
                domain="runtime-realization",
                support_mode=RealizationSupportMode.CONSTRAINED,
                supported_constraint_kinds=frozenset({"node-type"}),
                supported_exact_requirement_kinds=frozenset({"declared-capability-match"}),
                disclosure_kinds=frozenset({"runtime-snapshot-v1"}),
            ),
        ),
    )

    execution_plan = plan(model, manifest)

    codes = {diag.code for diag in execution_plan.diagnostics}
    assert "realization.unsupported-constraint-requirement" in codes
    assert not execution_plan.is_valid

    messages = [
        diag.message
        for diag in execution_plan.diagnostics
        if diag.code == "realization.unsupported-constraint-requirement"
    ]
    assert any("nodes.web.os" in message and "os-family" in message for message in messages)


def test_planner_accepts_constrained_declaration_when_backend_supports_it():
    """Constrained (and open) declarations plan as before against a supporting backend."""

    execution_plan = plan(
        compile_runtime_model(_scenario(_CONSTRAINED_SCENARIO)),
        _supporting_manifest(constrained=True),
    )

    codes = {diag.code for diag in execution_plan.diagnostics}
    assert not any(code.startswith("realization.") for code in codes)

"""Issue #674: target-node CPU architecture semantics.

Layer 1 — governed vocabulary, ``Node.architecture`` field, package-artifact
architecture normalization. Compatibility (semantic-validator) coverage lives in
``test_node_architecture_compat`` classes further below once the validator pass
is wired.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from raes.architectures import (
    NodeArchitecture,
    architectures_compatible,
    normalize_architecture,
)
from raes.nodes import Node
from raes.runtime_configuration import RuntimePackage


class TestNodeArchitectureVocabulary:
    def test_canonical_values(self):
        assert NodeArchitecture.X86_64.value == "x86_64"
        assert NodeArchitecture.AARCH64.value == "aarch64"

    @pytest.mark.parametrize(
        ("raw", "canonical"),
        [
            ("x86_64", NodeArchitecture.X86_64),
            ("X86_64", NodeArchitecture.X86_64),
            ("amd64", NodeArchitecture.X86_64),
            ("AMD64", NodeArchitecture.X86_64),
            ("x64", NodeArchitecture.X86_64),
            ("x86-64", NodeArchitecture.X86_64),
            ("aarch64", NodeArchitecture.AARCH64),
            ("arm64", NodeArchitecture.AARCH64),
            ("ARM64", NodeArchitecture.AARCH64),
        ],
    )
    def test_aliases_normalize_to_canonical(self, raw, canonical):
        assert normalize_architecture(raw) is canonical

    def test_none_stays_none(self):
        assert normalize_architecture(None) is None

    def test_variable_reference_passthrough(self):
        assert normalize_architecture("${node_arch}") == "${node_arch}"

    def test_governed_extension_admitted_as_exact_token(self):
        assert normalize_architecture("x-nvidia:grace") == "x-nvidia:grace"
        # canonical lowercase form is produced from mixed case
        assert normalize_architecture("X-NVIDIA:GRACE") == "x-nvidia:grace"

    @pytest.mark.parametrize(
        "bad",
        [
            "x86",  # ambiguous family label (no width)
            "arm",  # ambiguous family label (no variant)
            "noarch",  # package portability classifier, not a CPU arch
            "any",
            "all",
            "other",  # no catch-all sentinel; absence expresses "no requirement"
            "unknown",
            "sparc",  # not in the governed set and not a governed extension
            "x-Bad Owner:term",  # extension must match the governed pattern
        ],
    )
    def test_unknown_values_fail_closed(self, bad):
        with pytest.raises(ValueError, match="architecture"):
            normalize_architecture(bad)

    def test_non_string_rejected(self):
        with pytest.raises(ValueError, match="architecture"):
            normalize_architecture(123)


class TestNodeArchitectureField:
    def test_vm_node_accepts_canonical(self):
        n = Node(type="compute", architecture="x86_64", resources={"ram": "1 gib", "cpu": 1})
        assert n.architecture is NodeArchitecture.X86_64

    def test_vm_node_accepts_alias(self):
        n = Node(type="compute", architecture="arm64", resources={"ram": "1 gib", "cpu": 1})
        assert n.architecture is NodeArchitecture.AARCH64

    def test_absent_architecture_is_none(self):
        n = Node(type="compute", resources={"ram": "1 gib", "cpu": 1})
        assert n.architecture is None

    def test_variable_placeholder(self):
        n = Node(type="compute", architecture="${arch}", resources={"ram": "1 gib", "cpu": 1})
        assert n.architecture == "${arch}"

    def test_unknown_architecture_rejected(self):
        with pytest.raises(ValidationError, match="architecture"):
            Node(type="compute", architecture="sparc", resources={"ram": "1 gib", "cpu": 1})

    def test_switch_node_rejects_architecture(self):
        with pytest.raises(ValidationError, match="architecture"):
            Node(type="switch", architecture="x86_64")


class TestRuntimePackageArchitecture:
    def test_empty_stays_empty(self):
        pkg = RuntimePackage(manager="apk", name="musl", version="1.2.4-r2")
        assert pkg.architecture == ""

    def test_canonical_token_normalized(self):
        pkg = RuntimePackage(manager="apk", name="musl", version="1", architecture="amd64")
        assert pkg.architecture == "x86_64"

    def test_governed_extension_token(self):
        pkg = RuntimePackage(manager="apk", name="x", version="1", architecture="x-nvidia:grace")
        assert pkg.architecture == "x-nvidia:grace"

    def test_unknown_package_architecture_rejected(self):
        with pytest.raises(ValidationError, match="architecture"):
            RuntimePackage(manager="apk", name="x", version="1", architecture="sparc")


def _scenario(node_arch: str | None, package_arch: str | None) -> str:
    lines = ["name: arch-compat", "nodes:", "  worker:", "    type: compute"]
    if node_arch is not None:
        lines.append(f"    architecture: {node_arch}")
    lines.append("    resources: {ram: 1 gib, cpu: 1}")
    if package_arch is not None:
        lines += [
            "    runtime:",
            "      packages:",
            "        - manager: apk",
            "          name: musl",
            "          version: '1'",
            f"          architecture: {package_arch}",
        ]
    return "\n".join(lines) + "\n"


class TestNodeArchitectureCompatibility:
    """Semantic-validator compatibility rules (issue #674, rules 1-4)."""

    def test_node_absent_package_empty_valid(self):
        from raes import parse_sdl

        parse_sdl(_scenario(node_arch=None, package_arch=None))

    def test_node_present_package_empty_valid(self):
        from raes import parse_sdl

        parse_sdl(_scenario(node_arch="x86_64", package_arch=None))

    def test_node_present_package_matching_valid(self):
        from raes import parse_sdl

        # aliases on either side normalize to the same canonical token
        parse_sdl(_scenario(node_arch="amd64", package_arch="x86_64"))

    def test_node_present_package_mismatch_invalid(self):
        from raes import SDLValidationError, parse_sdl

        scenario = _scenario(node_arch="x86_64", package_arch="aarch64")
        with pytest.raises(SDLValidationError, match="architecture"):
            parse_sdl(scenario)

    def test_node_absent_package_present_invalid(self):
        from raes import SDLValidationError, parse_sdl

        scenario = _scenario(node_arch=None, package_arch="x86_64")
        with pytest.raises(SDLValidationError, match="architecture"):
            parse_sdl(scenario)

    def test_variable_node_architecture_defers(self):
        from raes import parse_sdl

        # a variable-valued node architecture defers compatibility to binding
        parse_sdl(
            "name: arch-var\n"
            "variables:\n"
            "  arch: {type: string, default: aarch64, allowed_values: [aarch64]}\n"
            "nodes:\n"
            "  worker:\n"
            "    type: compute\n"
            "    architecture: '${arch}'\n"
            "    resources: {ram: 1 gib, cpu: 1}\n"
            "    runtime:\n"
            "      packages:\n"
            "        - {manager: apk, name: musl, version: '1', architecture: aarch64}\n"
        )


_ARCH_NODE_SCENARIO = "name: arch-compile\nnodes:\n  web:\n    type: compute\n    architecture: x86_64\n    resources: {ram: 1 gib, cpu: 1}\n"


class TestNodeArchitectureCompilation:
    def test_node_runtime_carries_architecture(self):
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model

        model = compile_runtime_model(parse_sdl(_ARCH_NODE_SCENARIO))
        node = next(iter(model.node_deployments.values()))
        assert node.architecture == "x86_64"

    def test_architecture_becomes_realization_requirement(self):
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model

        model = compile_runtime_model(parse_sdl(_ARCH_NODE_SCENARIO))
        by_field = {req.field_path: req for req in model.realization_requirements}
        assert "nodes.web.architecture" in by_field
        assert by_field["nodes.web.architecture"].requirement_kind == "node-architecture"

    def test_absent_architecture_emits_no_requirement(self):
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model

        model = compile_runtime_model(
            parse_sdl("name: no-arch\nnodes:\n  web:\n    type: compute\n    resources: {ram: 1 gib, cpu: 1}\n")
        )
        fields = {req.field_path for req in model.realization_requirements}
        assert "nodes.web.architecture" not in fields


def _architecture_manifest(supported_node_architectures: frozenset[str]):
    from raes_backend_protocols.capabilities import BackendManifest, ProvisionerCapabilities
    from raes_contracts.apparatus import ConceptBinding, RealizationSupportDeclaration
    from raes_contracts.vocabulary import RealizationSupportMode

    return BackendManifest(
        name="arch-limited",
        version="0.0.1",
        supported_contract_versions=frozenset({"backend-manifest-v2"}),
        compatible_processors=frozenset({"raes-reference-processor"}),
        realization_support=(
            RealizationSupportDeclaration(
                domain="runtime-realization",
                support_mode=RealizationSupportMode.CONSTRAINED,
                supported_constraint_kinds=frozenset({"node-type", "os-family", "node-architecture"}),
                supported_exact_requirement_kinds=frozenset({"declared-capability-match"}),
                disclosure_kinds=frozenset({"runtime-snapshot-v1"}),
            ),
        ),
        concept_bindings=(ConceptBinding(scope="capabilities.provisioner.supported_node_types", family="assets"),),
        provisioner=ProvisionerCapabilities(
            name="arch-limited-provisioner",
            supported_node_types=frozenset({"compute"}),
            supported_os_families=frozenset({"linux"}),
            supported_node_architectures=supported_node_architectures,
        ),
    )


class TestNodeArchitecturePlannerAdmission:
    def test_supported_architecture_passes(self):
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan

        model = compile_runtime_model(parse_sdl(_ARCH_NODE_SCENARIO))
        execution_plan = plan(model, _architecture_manifest(frozenset({"x86_64"})))
        codes = {d.code for d in execution_plan.diagnostics}
        assert "provisioner.unsupported-node-architecture" not in codes

    def test_unsupported_architecture_fails_closed(self):
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan

        model = compile_runtime_model(parse_sdl(_ARCH_NODE_SCENARIO))
        execution_plan = plan(model, _architecture_manifest(frozenset({"aarch64"})))
        codes = {d.code for d in execution_plan.diagnostics}
        assert "provisioner.unsupported-node-architecture" in codes
        assert not execution_plan.is_valid

    def test_empty_support_fails_architecture_requirement(self):
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan

        model = compile_runtime_model(parse_sdl(_ARCH_NODE_SCENARIO))
        execution_plan = plan(model, _architecture_manifest(frozenset()))
        codes = {d.code for d in execution_plan.diagnostics}
        assert "provisioner.unsupported-node-architecture" in codes


class TestNodeArchitectureSemanticDiff:
    """Semantic-comparison coverage (issue #674, criterion 5)."""

    @staticmethod
    def _digest(node_arch: str | None):
        from raes import parse_sdl
        from raes.canonical import canonical_sdl_digest

        arch_line = f"    architecture: {node_arch}\n" if node_arch is not None else ""
        return canonical_sdl_digest(
            parse_sdl(
                "name: arch-diff\nnodes:\n  web:\n    type: compute\n"
                + arch_line
                + "    resources: {ram: 1 gib, cpu: 1}\n"
            )
        )

    def test_alias_only_change_is_semantically_equal(self):
        assert self._digest("amd64") == self._digest("x86_64")

    def test_distinct_canonical_values_are_a_semantic_change(self):
        assert self._digest("x86_64") != self._digest("aarch64")

    def test_presence_versus_absence_is_a_semantic_change(self):
        assert self._digest("x86_64") != self._digest(None)


class TestNodeArchitectureSchemaGovernance:
    """The published schema encodes the governed vocabulary (issue #674, criterion 2/5).

    Regression guard: the ``Node.architecture`` schema must not carry an
    unrestricted string branch that would let a schema-only consumer bypass the
    governed CPU-architecture vocabulary.
    """

    @staticmethod
    def _node_architecture_schema():
        import jsonschema
        from raes.scenario import Scenario

        full = Scenario.model_json_schema()
        schema = full["$defs"]["Node"]["properties"]["architecture"]
        return {**schema, "$defs": full["$defs"]}, jsonschema

    def test_no_unrestricted_string_branch(self):
        schema, _ = self._node_architecture_schema()
        for branch in schema["anyOf"]:
            if branch.get("type") == "string":
                assert "pattern" in branch, "string branch must constrain to the governed vocabulary"

    @pytest.mark.parametrize("value", ["x86_64", "aarch64", "amd64", "arm64", "x-nvidia:grace", "${arch}"])
    def test_schema_accepts_governed_values(self, value):
        schema, jsonschema = self._node_architecture_schema()
        jsonschema.validate(value, schema)

    @pytest.mark.parametrize("value", ["sparc", "x86", "arm", "noarch", "anything"])
    def test_schema_rejects_ungoverned_values(self, value):
        schema, jsonschema = self._node_architecture_schema()
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(value, schema)


_ARCH_VAR_SCENARIO = (
    "name: arch-var-plan\n"
    "variables:\n"
    "  arch: {type: string, default: x86_64, allowed_values: [x86_64, aarch64]}\n"
    "nodes:\n"
    "  web: {type: compute, architecture: '${arch}', resources: {ram: 1 gib, cpu: 1}}\n"
)


class TestNodeArchitectureVariableDomain:
    """Finite-domain (variable-backed) planner admission (issue #674)."""

    def _plan(self, scenario_yaml: str, supported: frozenset[str]):
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan

        return plan(compile_runtime_model(parse_sdl(scenario_yaml)), _architecture_manifest(supported))

    def test_variable_domain_all_supported_passes(self):
        execution_plan = self._plan(_ARCH_VAR_SCENARIO, frozenset({"x86_64", "aarch64"}))
        codes = {d.code for d in execution_plan.diagnostics}
        assert "provisioner.unsupported-node-architecture" not in codes
        assert execution_plan.is_valid

    def test_variable_domain_unsupported_member_fails(self):
        execution_plan = self._plan(_ARCH_VAR_SCENARIO, frozenset({"x86_64"}))
        codes = {d.code for d in execution_plan.diagnostics}
        assert "provisioner.unsupported-node-architecture" in codes
        assert not execution_plan.is_valid


class TestNodeArchitecturePlannerBranches:
    """Direct coverage of the fail-closed planner branches (issue #674)."""

    @staticmethod
    def _node(architecture: str):
        from raes_processor.models import NodeRuntime

        return NodeRuntime(address="provision.node.web", name="web", spec={}, architecture=architecture)

    @staticmethod
    def _constraint(*allowed_values: str):
        from raes_processor.models import CompiledCapabilityConstraint

        return CompiledCapabilityConstraint(
            address="provision.node.web",
            concern="nodes.architecture",
            parameter=("arch",),
            allowed_values=allowed_values,
        )

    def test_without_constraint_unbound_variable(self):
        from raes_processor.planner.capability_domains import _node_architecture_without_constraint

        diagnostics = _node_architecture_without_constraint(self._node("${arch}"), frozenset({"x86_64"}))
        assert any(d.code == "provisioner.node-architecture-variable-ref-unbound" for d in diagnostics)

    def test_with_constraint_invalid_domain_member(self):
        from raes_processor.planner.capability_domains import _node_architecture_with_constraint

        diagnostics = _node_architecture_with_constraint(
            self._constraint("x86_64", "sparc"), self._node("x86_64"), frozenset({"x86_64", "aarch64"})
        )
        assert any(d.code == "provisioner.node-architecture-variable-domain-invalid" for d in diagnostics)

    def test_with_constraint_unsupported_member(self):
        from raes_processor.planner.capability_domains import _node_architecture_with_constraint

        diagnostics = _node_architecture_with_constraint(
            self._constraint("aarch64"), self._node("x86_64"), frozenset({"x86_64"})
        )
        assert any(d.code == "provisioner.unsupported-node-architecture" for d in diagnostics)

    def test_with_constraint_all_supported_clean(self):
        from raes_processor.planner.capability_domains import _node_architecture_with_constraint

        diagnostics = _node_architecture_with_constraint(
            self._constraint("x86_64", "aarch64"), self._node("x86_64"), frozenset({"x86_64", "aarch64"})
        )
        assert diagnostics == []

    def test_allowed_value_non_concrete_variable_rejected(self):
        from raes_processor.planner.capability_domains import _architecture_allowed_value

        token, error = _architecture_allowed_value("${arch}", "arch", "provision.node.web")
        assert token is None
        assert error is not None
        assert "non-concrete" in error.message

    def test_allowed_value_unvalidatable_rejected(self):
        from raes_processor.planner.capability_domains import _architecture_allowed_value

        token, error = _architecture_allowed_value(None, "arch", "provision.node.web")
        assert token is None
        assert error is not None
        assert "could not be validated" in error.message


class TestNodeArchitectureTargetDomain:
    """SAT finite-domain capture for `nodes.architecture` (issue #674)."""

    def test_architecture_address_captures_canonical_vocabulary(self):
        from raes_processor.satisfiability._translation import _target_domain
        from raes_processor.satisfiability.evidence import ConstraintSort, ConstraintSymbolModel

        symbol = ConstraintSymbolModel(
            symbol_id="symbol.web-arch",
            variable="arch",
            sort=ConstraintSort.STRING,
            domain=("aarch64", "sparc", "x86_64"),
        )
        domain = _target_domain("/nodes/web/architecture", symbol)
        assert domain == ("aarch64", "x86_64")


class TestRealizerConfigurationArchitecture:
    """`RealizerConfigurationModel.architecture` is a governed canonical term (issue #674)."""

    def _config(self, architecture: str):
        from raes_contracts.realization_envelope import RealizerConfigurationModel

        return RealizerConfigurationModel(
            mode="techvault-appliance",
            configuration_digest="sha256:" + "a" * 64,
            architecture=architecture,
            image_policy="pinned",
            network_policy="isolated",
            supported_node_types=["compute"],
            supported_os_families=["linux"],
            memory_mib={"minimum": 1024},
            vcpus={"minimum": 1},
        )

    def test_canonical_accepted(self):
        assert self._config("x86_64").architecture == "x86_64"

    def test_ungoverned_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="architecture"):
            self._config("sparc")


class TestProvisionerCapabilitiesArchitecture:
    """`supported_node_architectures` is validated against the governed vocabulary (issue #674)."""

    def test_governed_values_accepted(self):
        from raes_backend_protocols.capabilities import ProvisionerCapabilities

        caps = ProvisionerCapabilities(
            name="p",
            supported_node_types=frozenset({"compute"}),
            supported_os_families=frozenset({"linux"}),
            supported_node_architectures=frozenset({"x86_64", "aarch64"}),
        )
        assert "x86_64" in caps.supported_node_architectures

    def test_ungoverned_value_rejected(self):
        from raes_backend_protocols.capabilities import ProvisionerCapabilities

        node_types = frozenset({"compute"})
        os_families = frozenset({"linux"})
        architectures = frozenset({"sparc"})
        with pytest.raises(ValueError, match="architecture"):
            ProvisionerCapabilities(
                name="p",
                supported_node_types=node_types,
                supported_os_families=os_families,
                supported_node_architectures=architectures,
            )


class TestArchitecturesCompatible:
    def test_exact_canonical_equal(self):
        assert architectures_compatible(NodeArchitecture.X86_64, "x86_64") is True

    def test_alias_and_canonical_equal(self):
        # both sides are already normalized to canonical before comparison
        assert architectures_compatible(NodeArchitecture.AARCH64, "aarch64") is True

    def test_distinct_canonical_incompatible(self):
        assert architectures_compatible(NodeArchitecture.X86_64, "aarch64") is False

    def test_extension_tokens_exact_match(self):
        assert architectures_compatible("x-nvidia:grace", "x-nvidia:grace") is True
        assert architectures_compatible("x-nvidia:grace", "x86_64") is False

    def test_empty_package_is_compatible(self):
        assert architectures_compatible(NodeArchitecture.X86_64, "") is True
        assert architectures_compatible(None, "") is True

    def test_absent_node_with_present_package_incompatible(self):
        assert architectures_compatible(None, "x86_64") is False

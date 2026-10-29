"""Runtime registry tests."""

import pytest
from raes_backend_protocols.capabilities import BackendManifest, ProvisionerCapabilities
from raes_backend_stubs.stubs import create_stub_components, create_stub_manifest
from raes_contracts.apparatus import ConceptBinding, RealizationSupportDeclaration
from raes_contracts.errors import NotFoundError
from raes_contracts.vocabulary import RealizationSupportMode
from raes_runtime.registry import (
    BackendRegistry,
    RuntimeTarget,
    RuntimeTargetComponents,
)


class BadProvisioner:
    pass


class BadOrchestrator:
    def start(self, plan, snapshot):
        del plan, snapshot
        return None

    def status(self):
        return {}

    def stop(self, snapshot):
        del snapshot
        return None


class BadEvaluator:
    def start(self, plan, snapshot):
        del plan, snapshot
        return None

    def status(self):
        return {}


class WrongSigProvisioner:
    def validate(self):
        return []

    def apply(self):
        return None


class WrongSigOrchestrator:
    def start(self, plan):
        del plan
        return None

    def status(self, verbose):
        del verbose
        return {}

    def results(self, include_meta):
        del include_meta
        return {}

    def stop(self):
        return None


class WrongSigEvaluator:
    def start(self, plan):
        del plan
        return None

    def status(self, verbose):
        del verbose
        return {}

    def results(self, include_meta):
        del include_meta
        return {}

    def stop(self):
        return None


class OptionalArgProvisioner:
    def validate(self, plan, dry_run: bool = False):
        del plan, dry_run
        return []

    def apply(self, plan, snapshot, *, region: str = "test"):
        del plan, snapshot, region
        return None


class TestBackendRegistry:
    def test_manifest_introspection_happens_before_target_creation(self):
        calls: list[str] = []

        def manifest_factory(**config):
            calls.append("manifest")
            return create_stub_manifest(**config)

        def components_factory(*, manifest, **config):
            calls.append(f"components:{manifest.name}")
            return create_stub_components(manifest=manifest, **config)

        registry = BackendRegistry()
        registry.register("stub", manifest_factory, components_factory)

        manifest = registry.manifest("stub", region="test")

        assert manifest.name == "stub"
        assert calls == ["manifest"]

    def test_create_uses_manifest_factory_as_single_source_of_truth(self):
        registry = BackendRegistry()

        def manifest_factory(**config):
            return BackendManifest(
                name="manifest-a",
                version="0.0.1",
                supported_contract_versions=frozenset({"backend-manifest-v2"}),
                compatible_processors=frozenset({"raes-reference-processor"}),
                realization_support=(
                    RealizationSupportDeclaration(
                        domain="runtime-realization",
                        support_mode=RealizationSupportMode.CONSTRAINED,
                        supported_constraint_kinds=frozenset({"node-type"}),
                        disclosure_kinds=frozenset({"runtime-snapshot-v1"}),
                    ),
                ),
                concept_bindings=(
                    ConceptBinding(scope="capabilities.provisioner.supported_node_types", family="assets"),
                ),
                provisioner=ProvisionerCapabilities(
                    name="manifest-a-provisioner",
                    supported_node_types=frozenset({"compute"}),
                    supported_os_families=frozenset({"linux"}),
                ),
            )

        def components_factory(*, manifest, **config):
            assert manifest.name == "manifest-a"
            return RuntimeTargetComponents(
                provisioner=create_stub_components(manifest=manifest).provisioner,
            )

        registry.register("custom", manifest_factory, components_factory)

        target = registry.create("custom")

        assert target.name == "custom"
        assert target.manifest.name == "manifest-a"
        assert target.provisioner is not None

    def test_create_returns_fully_described_target(self):
        registry = BackendRegistry()
        registry.register("stub", create_stub_manifest, create_stub_components)

        target = registry.create("stub")

        assert target.name == "stub"
        assert target.manifest.name == "stub"
        assert target.orchestrator is not None
        assert target.evaluator is not None

    def test_shape_mismatch_raises_predictably(self):
        registry = BackendRegistry()

        def manifest_factory(**config):
            return create_stub_manifest(**config)

        def components_factory(*, manifest, **config):
            return RuntimeTargetComponents(
                provisioner=create_stub_components(manifest=manifest).provisioner,
                orchestrator=None,
                evaluator=None,
            )

        registry.register("broken", manifest_factory, components_factory)

        with pytest.raises(ValueError, match="registry.target-shape-mismatch"):
            registry.create("broken")

    def test_direct_runtime_target_construction_rejects_shape_mismatch(self):
        with pytest.raises(ValueError, match="registry.target-shape-mismatch"):
            RuntimeTarget(
                name="broken",
                manifest=create_stub_manifest(with_participant_runtime=False),
                provisioner=create_stub_components(
                    manifest=create_stub_manifest(with_participant_runtime=False)
                ).provisioner,
                orchestrator=None,
                evaluator=None,
            )

    def test_direct_runtime_target_construction_rejects_bad_provisioner_contract(self):
        components = create_stub_components(manifest=create_stub_manifest(with_participant_runtime=False))

        with pytest.raises(ValueError, match="registry.target-contract-mismatch"):
            RuntimeTarget(
                name="broken",
                manifest=create_stub_manifest(with_participant_runtime=False),
                provisioner=BadProvisioner(),
                orchestrator=components.orchestrator,
                evaluator=components.evaluator,
            )

    def test_direct_runtime_target_construction_rejects_bad_orchestrator_contract(self):
        components = create_stub_components(manifest=create_stub_manifest(with_participant_runtime=False))

        with pytest.raises(ValueError, match="registry.target-contract-mismatch"):
            RuntimeTarget(
                name="broken",
                manifest=create_stub_manifest(with_participant_runtime=False),
                provisioner=components.provisioner,
                orchestrator=BadOrchestrator(),
                evaluator=components.evaluator,
            )

    def test_direct_runtime_target_construction_rejects_bad_evaluator_contract(self):
        components = create_stub_components(manifest=create_stub_manifest(with_participant_runtime=False))

        with pytest.raises(ValueError, match="registry.target-contract-mismatch"):
            RuntimeTarget(
                name="broken",
                manifest=create_stub_manifest(with_participant_runtime=False),
                provisioner=components.provisioner,
                orchestrator=components.orchestrator,
                evaluator=BadEvaluator(),
            )

    def test_registry_create_rejects_bad_component_contract(self):
        registry = BackendRegistry()

        def manifest_factory(**config):
            return create_stub_manifest(with_participant_runtime=False, **config)

        def components_factory(*, manifest, **config):
            del manifest, config
            components = create_stub_components(manifest=create_stub_manifest(with_participant_runtime=False))
            return RuntimeTargetComponents(
                provisioner=BadProvisioner(),
                orchestrator=components.orchestrator,
                evaluator=components.evaluator,
            )

        registry.register("bad-contract", manifest_factory, components_factory)

        with pytest.raises(ValueError, match="registry.target-contract-mismatch"):
            registry.create("bad-contract")

    def test_registry_create_rejects_wrong_signature_component_contract(self):
        registry = BackendRegistry()

        def manifest_factory(**config):
            return create_stub_manifest(with_participant_runtime=False, **config)

        def components_factory(*, manifest, **config):
            del manifest, config
            components = create_stub_components(manifest=create_stub_manifest(with_participant_runtime=False))
            return RuntimeTargetComponents(
                provisioner=WrongSigProvisioner(),
                orchestrator=components.orchestrator,
                evaluator=components.evaluator,
            )

        registry.register("bad-signature", manifest_factory, components_factory)

        with pytest.raises(ValueError, match="registry.target-contract-mismatch"):
            registry.create("bad-signature")

    def test_direct_runtime_target_construction_rejects_wrong_signature_provisioner(self):
        components = create_stub_components(manifest=create_stub_manifest(with_participant_runtime=False))

        with pytest.raises(ValueError, match="registry.target-contract-mismatch"):
            RuntimeTarget(
                name="broken",
                manifest=create_stub_manifest(with_participant_runtime=False),
                provisioner=WrongSigProvisioner(),
                orchestrator=components.orchestrator,
                evaluator=components.evaluator,
            )

    def test_direct_runtime_target_construction_rejects_wrong_signature_orchestrator(self):
        components = create_stub_components(manifest=create_stub_manifest(with_participant_runtime=False))

        with pytest.raises(ValueError, match="registry.target-contract-mismatch"):
            RuntimeTarget(
                name="broken",
                manifest=create_stub_manifest(with_participant_runtime=False),
                provisioner=components.provisioner,
                orchestrator=WrongSigOrchestrator(),
                evaluator=components.evaluator,
            )

    def test_direct_runtime_target_construction_rejects_wrong_signature_evaluator(self):
        components = create_stub_components(manifest=create_stub_manifest(with_participant_runtime=False))

        with pytest.raises(ValueError, match="registry.target-contract-mismatch"):
            RuntimeTarget(
                name="broken",
                manifest=create_stub_manifest(with_participant_runtime=False),
                provisioner=components.provisioner,
                orchestrator=components.orchestrator,
                evaluator=WrongSigEvaluator(),
            )

    def test_direct_runtime_target_construction_accepts_optional_extra_parameters(self):
        components = create_stub_components(manifest=create_stub_manifest(with_participant_runtime=False))

        target = RuntimeTarget(
            name="optional",
            manifest=create_stub_manifest(with_participant_runtime=False),
            provisioner=OptionalArgProvisioner(),
            orchestrator=components.orchestrator,
            evaluator=components.evaluator,
        )

        assert target.provisioner is not None

    def test_legacy_evaluator_collections_are_rejected(self):
        registry = BackendRegistry()

        def manifest_factory(**config):
            return create_stub_manifest(**config)

        class LegacyComponents:
            def __init__(self) -> None:
                components = create_stub_components(manifest=create_stub_manifest(with_participant_runtime=False))
                self.provisioner = components.provisioner
                self.orchestrator = components.orchestrator
                self.evaluators = (components.evaluator,)

        def components_factory(*, manifest, **config):
            del manifest, config
            return LegacyComponents()

        registry.register("legacy", manifest_factory, components_factory)

        with pytest.raises(ValueError, match="registry.target-shape-mismatch"):
            registry.create("legacy")

    def test_unknown_backend_raises(self):
        registry = BackendRegistry()

        with pytest.raises(NotFoundError, match="Unknown backend"):
            registry.manifest("missing")

    def test_list_and_registration(self):
        registry = BackendRegistry()
        registry.register("beta", create_stub_manifest, create_stub_components)
        registry.register("alpha", create_stub_manifest, create_stub_components)

        assert registry.list_backends() == ["alpha", "beta"]
        assert registry.is_registered("alpha")
        assert not registry.is_registered("gamma")

    def test_duplicate_registration_is_rejected(self):
        registry = BackendRegistry()
        registry.register("stub", create_stub_manifest, create_stub_components)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("stub", create_stub_manifest, create_stub_components)

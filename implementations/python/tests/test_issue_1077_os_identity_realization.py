"""Issue #1077: authored OS identity admission and realization evidence."""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError


class TestAuthoredOperatingSystemIdentity:
    def test_distribution_vocabulary_and_release_normalization(self) -> None:
        from raes.nodes import Node
        from raes.operating_systems import OSDistribution

        node = Node(
            type="compute",
            os="linux",
            os_distribution="Ubuntu",
            os_version="22.04",
        )

        assert node.os_distribution is OSDistribution.UBUNTU
        assert node.os_version == "22.04"

    def test_governed_distribution_extension_is_canonicalized(self) -> None:
        from raes.nodes import Node

        node = Node(
            type="compute",
            os="other",
            os_distribution="X-Siemens:Simatic",
        )

        assert node.os_distribution == "x-siemens:simatic"

    @pytest.mark.parametrize("distribution", ["ubuntu latest", "unknown", "other", "kali"])
    def test_ungoverned_distribution_fails_closed(self, distribution: str) -> None:
        from raes.nodes import Node

        with pytest.raises(ValidationError, match="distribution"):
            Node(type="compute", os="linux", os_distribution=distribution)

    @pytest.mark.parametrize("version", [" latest", "latest ", "line\nbreak"])
    def test_invalid_explicit_release_fails_closed(self, version: str) -> None:
        from raes.nodes import Node

        with pytest.raises(ValidationError, match="version"):
            Node(
                type="compute",
                os="linux",
                os_distribution="ubuntu",
                os_version=version,
            )

    def test_distribution_requires_family(self) -> None:
        from raes import SDLValidationError, parse_sdl

        with pytest.raises(SDLValidationError, match="distribution.*family"):
            parse_sdl("name: invalid-os\nnodes:\n  web: {type: compute, os_distribution: ubuntu}\n")

    def test_version_requires_distribution(self) -> None:
        from raes import SDLValidationError, parse_sdl

        with pytest.raises(SDLValidationError, match="version.*distribution"):
            parse_sdl("name: invalid-os\nnodes:\n  web: {type: compute, os: linux, os_version: '22.04'}\n")

    def test_family_only_remains_valid(self) -> None:
        from raes import parse_sdl

        scenario = parse_sdl("name: family-only\nnodes:\n  web: {type: compute, os: linux}\n")

        assert scenario.nodes["web"].os_distribution is None
        assert scenario.nodes["web"].os_version == ""

    def test_public_node_schema_encodes_distribution_and_version_dependencies(self) -> None:
        from raes.nodes import Node

        validator = Draft202012Validator(Node.model_json_schema())

        assert list(validator.iter_errors({"type": "compute", "os_version": "22.04"}))
        assert list(validator.iter_errors({"type": "compute", "os_distribution": "ubuntu"}))
        assert not list(
            validator.iter_errors(
                {
                    "type": "compute",
                    "os": "linux",
                    "os_distribution": "ubuntu",
                    "os_version": "22.04",
                }
            )
        )


class TestCoupledOperatingSystemCapabilities:
    def test_capability_preserves_family_distribution_release_coupling(self) -> None:
        from raes_backend_protocols.capabilities import (
            OperatingSystemCompatibility,
            ProvisionerCapabilities,
        )

        capabilities = ProvisionerCapabilities(
            name="paired-os",
            supported_node_types=frozenset({"compute"}),
            supported_os_families=frozenset({"linux"}),
            operating_systems=(
                OperatingSystemCompatibility(
                    family="linux",
                    distribution="ubuntu",
                    versions=frozenset({"22.04", "24.04"}),
                ),
            ),
        )

        assert capabilities.supports_operating_system(
            family="linux",
            distribution="ubuntu",
            version="22.04",
        )
        assert not capabilities.supports_operating_system(
            family="linux",
            distribution="ubuntu",
            version="9",
        )

    def test_cross_pairing_between_rows_is_rejected(self) -> None:
        from raes_backend_protocols.capabilities import (
            OperatingSystemCompatibility,
            ProvisionerCapabilities,
        )

        capabilities = ProvisionerCapabilities(
            name="paired-os",
            supported_node_types=frozenset({"compute"}),
            supported_os_families=frozenset({"linux"}),
            operating_systems=(
                OperatingSystemCompatibility("linux", "ubuntu", frozenset({"22.04"})),
                OperatingSystemCompatibility("linux", "rocky-linux", frozenset({"9"})),
            ),
        )

        assert not capabilities.supports_operating_system(
            family="linux",
            distribution="ubuntu",
            version="9",
        )

    def test_row_family_must_match_coarse_family_capability(self) -> None:
        from raes_backend_protocols.capabilities import (
            OperatingSystemCompatibility,
            ProvisionerCapabilities,
        )

        compatibility = OperatingSystemCompatibility("windows", "windows-server", frozenset({"2022"}))
        kwargs = {
            "name": "mismatched-os",
            "supported_node_types": frozenset({"compute"}),
            "supported_os_families": frozenset({"linux"}),
            "operating_systems": (compatibility,),
        }
        with pytest.raises(ValueError, match="supported_os_families"):
            ProvisionerCapabilities(**kwargs)

    def test_core_distribution_cannot_be_paired_with_wrong_family(self) -> None:
        from raes_backend_protocols.capabilities import OperatingSystemCompatibility

        versions = frozenset({"22.04"})
        with pytest.raises(ValueError, match="requires family 'linux'"):
            OperatingSystemCompatibility("windows", "ubuntu", versions)

    def test_manifest_contract_roundtrip_preserves_coupled_rows(self) -> None:
        from raes_backend_protocols.capabilities import (
            OperatingSystemCompatibility,
            ProvisionerCapabilities,
        )
        from raes_backend_protocols.provisioner_manifest import (
            provisioner_capability_payload,
            provisioner_from_model,
        )
        from raes_contracts.contracts import ProvisionerCapabilitiesModel

        capabilities = ProvisionerCapabilities(
            name="roundtrip-os",
            supported_node_types=frozenset({"compute"}),
            supported_os_families=frozenset({"linux"}),
            operating_systems=(OperatingSystemCompatibility("linux", "ubuntu", frozenset({"22.04", "24.04"})),),
        )

        model = ProvisionerCapabilitiesModel.model_validate(provisioner_capability_payload(capabilities))

        assert provisioner_from_model(model).operating_systems == capabilities.operating_systems
        assert model.operating_systems[0].model_dump(mode="json") == {
            "family": "linux",
            "distribution": "ubuntu",
            "versions": ["22.04", "24.04"],
        }

    def test_realizer_configuration_validates_coupled_rows(self) -> None:
        from raes_contracts.realization_envelope import RealizerConfigurationModel

        payload = {
            "mode": "test",
            "configuration_digest": "sha256:" + "1" * 64,
            "architecture": "x86_64",
            "image_policy": "exact",
            "network_policy": "isolated",
            "supported_node_types": ["compute"],
            "supported_os_families": ["linux"],
            "operating_systems": [
                {
                    "family": "linux",
                    "distribution": "ubuntu",
                    "versions": ["22.04"],
                }
            ],
            "memory_mib": {"minimum": 128},
            "vcpus": {"minimum": 1},
        }
        configuration = RealizerConfigurationModel.model_validate(payload)

        assert configuration.operating_systems[0].distribution == "ubuntu"
        payload["operating_systems"] = [
            {
                "family": "windows",
                "distribution": "windows-server",
                "versions": ["2022"],
            }
        ]
        with pytest.raises(ValidationError, match="supported_os_families"):
            RealizerConfigurationModel.model_validate(payload)


_OS_NODE_SCENARIO = (
    "name: os-compile\n"
    "nodes:\n"
    "  web:\n"
    "    type: compute\n"
    "    os: linux\n"
    "    os_distribution: ubuntu\n"
    "    os_version: '22.04'\n"
    "    resources: {ram: 1 gib, cpu: 1}\n"
)


def _os_manifest(*versions: str):
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
    from raes_contracts.realization_envelope import ObservationStrength
    from raes_contracts.vocabulary import RealizationSupportMode, RealizationVerificationScope

    return BackendManifest(
        name="os-limited",
        version="0.0.1",
        supported_contract_versions=frozenset({"backend-manifest-v2"}),
        compatible_processors=frozenset({"raes-reference-processor"}),
        realization_support=(
            RealizationSupportDeclaration(
                domain="runtime-realization",
                support_mode=RealizationSupportMode.CONSTRAINED,
                supported_constraint_kinds=frozenset({"node-type", "os-family", "os-distribution", "os-version"}),
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
        concept_bindings=(ConceptBinding(scope="capabilities.provisioner.supported_node_types", family="assets"),),
        provisioner=ProvisionerCapabilities(
            name="os-limited-provisioner",
            supported_node_types=frozenset({"compute"}),
            supported_os_families=frozenset({"linux"}),
            operating_systems=(OperatingSystemCompatibility("linux", "ubuntu", frozenset(versions)),),
        ),
    )


def _bound_os_observation_context():
    from dataclasses import replace

    from raes import parse_sdl
    from raes_backend_libvirt.envelopes import LibvirtDriverMode, load_libvirt_realization_envelope
    from raes_contracts.realization_envelope import (
        BackendRealizationEnvelopeModel,
        ObservationStrength,
        RealizationConcern,
        realization_envelope_digest,
        realizer_configuration_digest,
    )
    from raes_contracts.realization_observation import (
        ObservedOperatingSystemIdentity,
        RealizationObservation,
    )
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan

    execution_plan = plan(compile_runtime_model(parse_sdl(_OS_NODE_SCENARIO)), _os_manifest("22.04"))
    envelope_payload = load_libvirt_realization_envelope(LibvirtDriverMode.GENERIC).model_dump(mode="json")
    envelope_payload["configuration"]["operating_systems"] = [
        {"family": "linux", "distribution": "ubuntu", "versions": ["22.04"]}
    ]
    envelope_payload["configuration"]["configuration_digest"] = realizer_configuration_digest(
        envelope_payload["configuration"]
    )
    os_concern = next(claim for claim in envelope_payload["concerns"] if claim["concern"] == "operating-system")
    os_concern.update(
        disposition="realized",
        observation_strength="guest-observed",
        mechanism="guest-os-release",
    )
    envelope_payload["digest"] = realization_envelope_digest(envelope_payload)
    envelope = BackendRealizationEnvelopeModel.model_validate(envelope_payload)
    provisioning = replace(
        execution_plan.provisioning,
        operation_id="op-os-bound",
        realization_envelope=envelope.identity,
    )
    native = RealizationObservation(
        address="provision.node.web",
        field_path="guest.os-release",
        concern=RealizationConcern.OPERATING_SYSTEM,
        source=ObservationStrength.GUEST_OBSERVED,
        value=ObservedOperatingSystemIdentity("linux", "ubuntu", "22.04"),
        operation_id="op-os-bound",
        envelope_digest=envelope.digest,
        configuration_digest=envelope.configuration.configuration_digest,
        observer_version="guest-os-release/v1",
        sequence=7,
        binding_verified=True,
    )
    return provisioning, envelope, native


class TestOperatingSystemCompilationAndAdmission:
    def test_compiled_runtime_and_plan_payload_carry_authored_identity(self) -> None:
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan

        model = compile_runtime_model(parse_sdl(_OS_NODE_SCENARIO))
        node = next(iter(model.node_deployments.values()))

        assert (node.os_family, node.os_distribution, node.os_version) == ("linux", "ubuntu", "22.04")
        execution_plan = plan(model, _os_manifest("22.04"))
        operation = next(
            operation for operation in execution_plan.provisioning.operations if operation.resource_type == "node"
        )
        assert operation.payload["os_distribution"] == "ubuntu"
        assert operation.payload["os_version"] == "22.04"

    def test_distribution_and_release_are_separate_realization_concerns(self) -> None:
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model

        model = compile_runtime_model(parse_sdl(_OS_NODE_SCENARIO))
        by_field = {requirement.field_path: requirement for requirement in model.realization_requirements}

        assert by_field["nodes.web.os_distribution"].requirement_kind == "os-distribution"
        assert by_field["nodes.web.os_version"].requirement_kind == "os-version"
        assert by_field["nodes.web.os_version"].required_observation_strength.value == "guest-observed"

    def test_exact_unsupported_release_fails_before_backend_execution(self) -> None:
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan

        execution_plan = plan(compile_runtime_model(parse_sdl(_OS_NODE_SCENARIO)), _os_manifest("24.04"))

        assert not execution_plan.is_valid
        assert any(
            diagnostic.code == "provisioner.unsupported-operating-system" for diagnostic in execution_plan.diagnostics
        )

    @pytest.mark.parametrize("backend", ["reference", "libvirt"])
    def test_existing_backends_reject_specific_os_without_selector_and_observer(self, backend: str) -> None:
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan

        if backend == "reference":
            from raes_reference_backend.manifest import create_reference_backend_manifest

            manifest = create_reference_backend_manifest()
        else:
            from raes_backend_libvirt.manifest import create_libvirt_manifest

            manifest = create_libvirt_manifest()

        execution_plan = plan(compile_runtime_model(parse_sdl(_OS_NODE_SCENARIO)), manifest)

        assert not execution_plan.is_valid
        assert any(d.code == "provisioner.unsupported-operating-system" for d in execution_plan.diagnostics)

    def test_finite_release_domain_retains_the_nonempty_supported_intersection(self) -> None:
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan

        scenario = parse_sdl(
            "name: os-version-domain\n"
            "variables:\n"
            "  release: {type: string, default: '22.04', allowed_values: ['22.04', '24.04']}\n"
            "nodes:\n"
            "  web:\n"
            "    type: compute\n"
            "    os: linux\n"
            "    os_distribution: ubuntu\n"
            "    os_version: '${release}'\n"
            "    resources: {ram: 1 gib, cpu: 1}\n"
        )

        partially_supported = plan(compile_runtime_model(scenario), _os_manifest("22.04"))
        fully_supported = plan(compile_runtime_model(scenario), _os_manifest("22.04", "24.04"))

        assert not any(d.code == "provisioner.unsupported-operating-system" for d in partially_supported.diagnostics)
        version_authority = next(
            entry
            for entry in partially_supported.provisioning.realization_authority
            if entry.requirement_kind == "os-version"
        )
        assert version_authority.bounds[0].domain.values == ["22.04"]
        assert not any(d.code == "provisioner.unsupported-operating-system" for d in fully_supported.diagnostics)

    def test_open_distribution_and_version_require_a_compatible_apparatus_row(self) -> None:
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan
        from raes_reference_backend.manifest import create_reference_backend_manifest

        scenario = parse_sdl(
            "name: open-os-details\n"
            "realization:\n"
            "  scopes:\n"
            "    - {field_pointer: /nodes/web/os_distribution, posture: open}\n"
            "    - {field_pointer: /nodes/web/os_version, posture: open}\n"
            "nodes:\n"
            "  web:\n"
            "    type: compute\n"
            "    os: linux\n"
            "    resources: {ram: 1 gib, cpu: 1}\n"
        )

        admitted = plan(compile_runtime_model(scenario), _os_manifest("22.04"))
        rejected = plan(compile_runtime_model(scenario), create_reference_backend_manifest())

        assert not any(d.code == "provisioner.unsupported-operating-system" for d in admitted.diagnostics)
        assert any(d.code == "provisioner.unsupported-operating-system" for d in rejected.diagnostics)


class TestBoundOperatingSystemObservation:
    @staticmethod
    def _snapshot(execution_plan, *, version: str, include_observation: bool = True):
        import copy

        from raes_contracts.planning import RuntimeDomain
        from raes_contracts.realization_envelope import ObservationStrength
        from raes_contracts.realization_observation import (
            ObservedOperatingSystemIdentity,
            RealizationObservationDisclosure,
        )
        from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
        from raes_contracts.vocabulary import RealizationVerificationScope

        operation = next(op for op in execution_plan.provisioning.operations if op.resource_type == "node")
        payload = copy.deepcopy(operation.payload)
        payload["os_version"] = "snapshot-echo-is-not-evidence"
        observations = (
            (
                RealizationObservationDisclosure(
                    address=operation.address,
                    field_path="nodes.web.operating-system",
                    domain="runtime-realization",
                    requirement_kind="operating-system",
                    verification_scope=RealizationVerificationScope.PRESENCE,
                    observation_strength=ObservationStrength.GUEST_OBSERVED,
                    operating_system=ObservedOperatingSystemIdentity(
                        family="linux",
                        distribution="ubuntu",
                        version=version,
                    ),
                    operation_id="op-os-1",
                    envelope_digest="sha256:" + "a" * 64,
                    configuration_digest="sha256:" + "b" * 64,
                    observer_version="guest-os-release/v1",
                    sequence=1,
                    binding_verified=True,
                ),
            )
            if include_observation
            else ()
        )
        return RuntimeSnapshot(
            entries={
                operation.address: SnapshotEntry(
                    address=operation.address,
                    domain=RuntimeDomain.PROVISIONING,
                    resource_type=operation.resource_type,
                    payload=payload,
                    ordering_dependencies=operation.ordering_dependencies,
                    refresh_dependencies=operation.refresh_dependencies,
                )
            },
            realization_observations=observations,
        )

    def test_one_typed_guest_observation_corroborates_all_os_leaves(self) -> None:
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan, realization_disclosure

        model = compile_runtime_model(parse_sdl(_OS_NODE_SCENARIO))
        manifest = _os_manifest("22.04")
        execution_plan = plan(model, manifest)
        requirements = tuple(
            requirement
            for requirement in model.realization_requirements
            if requirement.requirement_kind in {"os-family", "os-distribution", "os-version"}
        )

        diagnostics, provenance = realization_disclosure(
            requirements,
            execution_plan.provisioning,
            self._snapshot(execution_plan, version="22.04"),
            manifest=manifest,
        )

        assert diagnostics == []
        assert {entry.requirement_kind for entry in provenance} == {
            "os-family",
            "os-distribution",
            "os-version",
        }

    def test_family_only_requirement_cannot_use_snapshot_echo(self) -> None:
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan, realization_disclosure

        scenario = parse_sdl(
            "name: family-only\nnodes:\n  web: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}\n"
        )
        model = compile_runtime_model(scenario)
        manifest = _os_manifest("22.04")
        execution_plan = plan(model, manifest)
        family = next(
            requirement for requirement in model.realization_requirements if requirement.requirement_kind == "os-family"
        )

        missing, _ = realization_disclosure(
            (family,),
            execution_plan.provisioning,
            self._snapshot(execution_plan, version="22.04", include_observation=False),
            manifest=manifest,
        )
        observed, provenance = realization_disclosure(
            (family,),
            execution_plan.provisioning,
            self._snapshot(execution_plan, version="22.04"),
            manifest=manifest,
        )

        assert any(d.code == "runtime.backend-contract-invalid" for d in missing)
        assert observed == []
        assert [entry.requirement_kind for entry in provenance] == ["os-family"]

    def test_snapshot_echo_cannot_replace_or_override_guest_observation(self) -> None:
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan, realization_disclosure

        model = compile_runtime_model(parse_sdl(_OS_NODE_SCENARIO))
        manifest = _os_manifest("22.04", "24.04")
        execution_plan = plan(model, manifest)
        requirements = tuple(
            requirement
            for requirement in model.realization_requirements
            if requirement.requirement_kind in {"os-family", "os-distribution", "os-version"}
        )

        missing, _ = realization_disclosure(
            requirements,
            execution_plan.provisioning,
            self._snapshot(execution_plan, version="22.04", include_observation=False),
            manifest=manifest,
        )
        mismatched, _ = realization_disclosure(
            requirements,
            execution_plan.provisioning,
            self._snapshot(execution_plan, version="24.04"),
            manifest=manifest,
        )

        assert any(d.code == "runtime.backend-contract-invalid" for d in missing)
        assert any(d.code == "runtime.backend-contract-invalid" for d in mismatched)

    def test_constrained_release_rejects_observation_outside_authored_domain(self) -> None:
        from raes import parse_sdl
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan, realization_disclosure

        scenario = parse_sdl(
            "name: constrained-os-version\n"
            "variables:\n"
            "  release: {type: string, default: '22.04', allowed_values: ['22.04', '23.10']}\n"
            "nodes:\n"
            "  web:\n"
            "    type: compute\n"
            "    os: linux\n"
            "    os_distribution: ubuntu\n"
            "    os_version: '${release}'\n"
            "    resources: {ram: 1 gib, cpu: 1}\n"
        )
        model = compile_runtime_model(scenario)
        manifest = _os_manifest("22.04", "24.04")
        execution_plan = plan(model, manifest)
        version_requirement = next(
            requirement
            for requirement in model.realization_requirements
            if requirement.requirement_kind == "os-version"
        )

        diagnostics, provenance = realization_disclosure(
            (version_requirement,),
            execution_plan.provisioning,
            self._snapshot(execution_plan, version="24.04"),
            manifest=manifest,
        )

        assert version_requirement.explicitness.value == "constrained"
        assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
        assert provenance == ()

    def test_typed_observation_roundtrips_through_public_snapshot_contract(self) -> None:
        from raes import parse_sdl
        from raes_contracts.contracts import RuntimeSnapshotEnvelopeModel
        from raes_processor.compiler import compile_runtime_model
        from raes_processor.planner import plan
        from raes_runtime.control_plane_store import _snapshot_from_payload, _snapshot_payload

        execution_plan = plan(compile_runtime_model(parse_sdl(_OS_NODE_SCENARIO)), _os_manifest("22.04"))
        snapshot = self._snapshot(execution_plan, version="22.04")
        payload = _snapshot_payload(snapshot)

        assert _snapshot_from_payload(payload).realization_observations == snapshot.realization_observations
        public = RuntimeSnapshotEnvelopeModel.model_validate(payload)
        assert public.realization_observations[0].operating_system.version == "22.04"

    def test_binding_derives_verified_disclosure_from_operation_and_envelope(self) -> None:
        from raes_contracts.realization_observation import bind_operating_system_observations

        provisioning, envelope, native = _bound_os_observation_context()

        disclosures = bind_operating_system_observations(
            plan=provisioning,
            observations=(native,),
            envelope=envelope,
        )

        assert len(disclosures) == 1
        assert disclosures[0].operating_system == native.value
        assert disclosures[0].operation_id == "op-os-bound"
        assert disclosures[0].envelope_digest == envelope.digest

    @pytest.mark.parametrize(
        "invalid_binding",
        [
            "unsupported-version",
            "concern-not-realized",
            "concern-not-guest-observed",
            "observation-not-guest-observed",
            "operation-mismatch",
            "envelope-mismatch",
            "configuration-mismatch",
            "missing-observer-version",
            "missing-sequence",
            "negative-sequence",
            "unverified-binding",
        ],
    )
    def test_binding_rejects_each_invalid_native_os_observation_invariant(self, invalid_binding: str) -> None:
        from dataclasses import replace

        from raes_contracts.realization_envelope import (
            ConcernDisposition,
            ObservationStrength,
            RealizationConcern,
        )
        from raes_contracts.realization_observation import (
            ObservedOperatingSystemIdentity,
            bind_operating_system_observations,
        )

        provisioning, envelope, native = _bound_os_observation_context()
        if invalid_binding == "unsupported-version":
            native = replace(native, value=ObservedOperatingSystemIdentity("linux", "ubuntu", "24.04"))
        elif invalid_binding == "concern-not-realized":
            claims = [
                claim.model_copy(update={"disposition": ConcernDisposition.TRANSFORMED})
                if claim.concern is RealizationConcern.OPERATING_SYSTEM
                else claim
                for claim in envelope.concerns
            ]
            envelope = envelope.model_copy(update={"concerns": claims})
        elif invalid_binding == "concern-not-guest-observed":
            claims = [
                claim.model_copy(update={"observation_strength": ObservationStrength.DRIVER_REPORTED})
                if claim.concern is RealizationConcern.OPERATING_SYSTEM
                else claim
                for claim in envelope.concerns
            ]
            envelope = envelope.model_copy(update={"concerns": claims})
        elif invalid_binding == "observation-not-guest-observed":
            native = replace(native, source=ObservationStrength.DRIVER_REPORTED)
        elif invalid_binding == "operation-mismatch":
            native = replace(native, operation_id="op-other")
        elif invalid_binding == "envelope-mismatch":
            native = replace(native, envelope_digest="sha256:" + "c" * 64)
        elif invalid_binding == "configuration-mismatch":
            native = replace(native, configuration_digest="sha256:" + "c" * 64)
        elif invalid_binding == "missing-observer-version":
            native = replace(native, observer_version=None)
        elif invalid_binding == "missing-sequence":
            native = replace(native, sequence=None)
        elif invalid_binding == "negative-sequence":
            native = replace(native, sequence=-1)
        else:
            native = replace(native, binding_verified=False)

        disclosures = bind_operating_system_observations(
            plan=provisioning,
            observations=(native,),
            envelope=envelope,
        )

        assert disclosures == ()

"""A prepared OS identity is one coupled supported choice, not leaf overlap."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes_backend_protocols.capabilities import OperatingSystemCompatibility
from raes_backend_stubs.stubs import StubProvisioner
from raes_contracts.realization_observation import ObservedOperatingSystemIdentity, RealizationObservationDisclosure
from raes_contracts.realization_preparation import RealizationPreparation
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.vocabulary import ObservationStrength, RealizationSupportMode, RealizationVerificationScope
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from test_sem_218_realization_designation import _manifest, _scenario


def _request():
    manifest = _manifest(RealizationSupportMode.OPEN_REALIZATION)
    manifest = replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions | {"backend-realization-preparation-v1"},
        capabilities=replace(
            manifest.capabilities,
            provisioner=replace(
                manifest.provisioner,
                supported_os_families=frozenset({"linux", "windows"}),
                operating_systems=(
                    OperatingSystemCompatibility("linux", "ubuntu", frozenset({"22.04"})),
                    OperatingSystemCompatibility("windows", "windows-server", frozenset({"2022"})),
                ),
            ),
        ),
    )
    scenario = _scenario("realization:\n  default: open")
    # One node makes the existing observation test adapter's coverage complete.
    scenario = scenario.model_copy(update={"nodes": {"web": scenario.nodes["web"]}})
    execution = plan(compile_runtime_model(scenario), manifest)
    assert execution.is_valid, execution.diagnostics
    return execution.provisioning, manifest


class _PreparingOsBackend:
    def __init__(self, *, choice=("linux", "ubuntu", "22.04"), delivered_family="linux"):
        self.delivered_family = delivered_family
        self.choice = choice
        self.applies = 0

    def prepare(self, request, snapshot):
        operations = deepcopy(request.operations)
        for operation in operations:
            operation.payload.update(zip(("os_family", "os_distribution", "os_version"), self.choice, strict=True))
        return RealizationPreparation.for_request(request, snapshot, operations=tuple(operations))

    def apply(self, selected, snapshot):
        self.applies += 1
        result = StubProvisioner().apply(selected, snapshot)
        distribution, version = ("ubuntu", "22.04") if self.delivered_family == "linux" else ("windows-server", "2022")
        observation = RealizationObservationDisclosure(
            address=selected.operations[0].address,
            field_path="nodes.web.operating-system",
            domain="runtime-realization",
            requirement_kind="operating-system",
            verification_scope=RealizationVerificationScope.PRESENCE,
            observation_strength=ObservationStrength.GUEST_OBSERVED,
            operating_system=ObservedOperatingSystemIdentity(
                family=self.delivered_family, distribution=distribution, version=version
            ),
            operation_id=selected.operation_id,
            envelope_digest=selected.realization_envelope.digest,
            configuration_digest=selected.realization_envelope.configuration_digest,
            observer_version="test-guest-os/v1",
            sequence=1,
            binding_verified=True,
        )
        return replace(
            result,
            snapshot=result.snapshot.with_entries(
                result.snapshot.entries, realization_envelope=selected.realization_envelope
            ),
            operational_realization_observations=(observation,),
        )

    def validate(self, selected):
        return []


def _apply(backend):
    request, manifest = _request()
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.test.preparation-os",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    return previous, result


@pytest.mark.parametrize(
    "choice,accepted",
    [
        (("linux", "ubuntu", "22.04"), True),
        (("linux", "windows-server", "2022"), False),
        (("linux", "ubuntu", "2022"), False),
        (("unknown", "ubuntu", "22.04"), False),
    ],
)
def test_preparation_requires_a_joint_operating_system_row(choice, accepted):
    backend = _PreparingOsBackend(choice=choice)
    previous, result = _apply(backend)
    assert backend.applies == int(accepted), result.diagnostics
    assert result.success is accepted, result.diagnostics
    if not accepted:
        assert result.snapshot == previous
        assert result.diagnostics[0].code == "runtime.backend-preparation-invalid"


def test_observed_delivery_cannot_replace_the_prepared_operating_system():
    backend = _PreparingOsBackend(delivered_family="windows")
    previous, result = _apply(backend)
    assert backend.applies == 1, result.diagnostics
    assert not result.success
    assert result.snapshot == previous
    assert result.diagnostics[0].message == "Backend did not deliver its admitted realization completion."


def test_preparation_can_select_another_member_of_a_legacy_finite_domain():
    from raes_contracts.bounded_domains import EnumDomain
    from raes_contracts.planning import RealizationAuthorityBound, RealizationAuthorityMode, RealizationResolutionSource

    request, manifest = _request()
    operations = deepcopy(request.operations)
    operations[0].payload["os_family"] = "windows"
    authority = tuple(
        replace(
            item,
            mode=RealizationAuthorityMode.CONSTRAINED,
            source=RealizationResolutionSource.AUTHORED_LEAF,
            bounds=(RealizationAuthorityBound("", EnumDomain(values=["linux", "windows"])),),
            structure=None,
            constraint_document=None,
            constraint_binding=None,
        )
        if item.requirement_kind == "os-family"
        else item
        for item in request.realization_authority
    )
    request = replace(request, operations=operations, realization_authority=authority)
    backend = _PreparingOsBackend()
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.constrained-os",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert result.success, result.diagnostics
    assert backend.applies == 1


@pytest.mark.parametrize("owner", ["manager", "control-plane"])
def test_runtime_validates_the_prepared_completion_not_the_unselected_template(owner):
    from raes_contracts.diagnostics import Diagnostic
    from raes_runtime.manager import RuntimeManager
    from raes_runtime.registry import RuntimeTarget

    class ConcreteValidationBackend(_PreparingOsBackend):
        def __init__(self):
            super().__init__()
            self.validated = []

        def validate(self, selected):
            family = selected.operations[0].payload.get("os_family")
            self.validated.append(family)
            return (
                []
                if family == "linux"
                else [Diagnostic("test.unselected", "runtime", "runtime.prepare", "Not selected.")]
            )

    _, manifest = _request()
    backend = ConcreteValidationBackend()
    target = RuntimeTarget(name="preparation-test", manifest=manifest, provisioner=backend)
    manager = RuntimeManager(target)
    scenario = _scenario("realization:\n  default: open")
    scenario = scenario.model_copy(update={"nodes": {"web": scenario.nodes["web"]}})
    execution = manager.plan(scenario)
    if owner == "manager":
        result = manager.apply(execution)
        assert result.success, result.diagnostics
    else:
        from raes_contracts.runtime_state import OperationState
        from raes_runtime.control_plane import RuntimeControlPlane

        control_plane = RuntimeControlPlane(target)
        control_plane.register_planner_produced_plan(execution)
        receipt = control_plane.submit_provisioning(execution.provisioning)
        status = control_plane.get_operation(receipt.operation_id)
        assert status.state is OperationState.SUCCEEDED, status.diagnostics
        control_plane.close()
    assert backend.validated == ["linux"]

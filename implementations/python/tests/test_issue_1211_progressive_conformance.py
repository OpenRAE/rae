"""Integrated regression anchors for progressive specification (issue #1211)."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from raes import SDLParseError, canonical_sdl_bytes, instantiate_scenario, parse_sdl, parse_sdl_file
from raes._source_profile import SDLParserLimits
from raes.canonical import InstantiatedScenarioSnapshot, canonical_instantiated_sdl_bytes
from raes.explicitness import ExplicitnessClass
from raes_backend_protocols.capabilities import OperatingSystemCompatibility
from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.realization_observation import (
    ObservedOperatingSystemIdentity,
    RealizationObservationDisclosure,
)
from raes_contracts.realization_structure import (
    RealizationClosure,
    evaluate_realization_constraint,
    normalize_realization_literal,
)
from raes_contracts.runtime_state import OperationState
from raes_contracts.vocabulary import (
    ObservationStrength,
    RealizationSupportMode,
    RealizationVerificationScope,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_processor.semantics.realization_concerns import realization_concern_descriptors
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import InMemoryControlPlaneStore

FIXTURE = Path(__file__).parent / "fixtures/progressive-conformance.yaml"


class _ObservedStubProvisioner(StubProvisioner):
    """Hermetic stub that discloses exact values already present in its result."""

    def apply(self, submitted, snapshot):
        result = super().apply(submitted, snapshot)
        disclosures = []
        for sequence, operation in enumerate(submitted.operations, start=1):
            node = operation.payload["spec"]["node"]
            node_name = operation.address.removeprefix("provision.node.")
            disclosures.append(
                RealizationObservationDisclosure(
                    address=operation.address,
                    field_path=f"nodes.{node_name}.operating-system",
                    domain="runtime-realization",
                    requirement_kind="operating-system",
                    verification_scope=RealizationVerificationScope.PRESENCE,
                    observation_strength=ObservationStrength.GUEST_OBSERVED,
                    operating_system=ObservedOperatingSystemIdentity(
                        family=node["os"],
                        distribution=node["os_distribution"],
                        version=node["os_version"],
                    ),
                    operation_id=submitted.operation_id or "op-progressive-conformance",
                    envelope_digest="sha256:" + "a" * 64,
                    configuration_digest="sha256:" + "b" * 64,
                    observer_version="hermetic-progressive-conformance/v1",
                    sequence=sequence,
                    binding_verified=True,
                )
            )
        disclosures.extend(
            RealizationObservationDisclosure(
                address=authority.address,
                field_path=authority.field_path,
                domain=authority.domain,
                requirement_kind=authority.requirement_kind,
                verification_scope=RealizationVerificationScope.CONFIGURATION,
                observation_strength=ObservationStrength.GUEST_OBSERVED,
            )
            for authority in submitted.realization_authority
            if authority.requirement_kind in {"runtime-applications", "runtime-software-components"}
            and authority.mode.value != "closed"
        )
        return replace(result, snapshot=replace(result.snapshot, realization_observations=tuple(disclosures)))


class _PerturbedObservedStubProvisioner(_ObservedStubProvisioner):
    """Return a well-shaped snapshot whose private method identity has drifted."""

    def apply(self, submitted, snapshot):
        result = super().apply(submitted, snapshot)
        entries = dict(result.snapshot.entries)
        entry = entries["provision.node.private"]
        payload = deepcopy(entry.payload)
        payload["spec"]["node"]["runtime"]["applications"][0]["routes"][0]["methods"][2] = "Privatequery"
        entries[entry.address] = replace(entry, payload=payload)
        return replace(result, snapshot=result.snapshot.with_entries(entries))


class _RejectingObservationRuntime:
    """Fail loudly if a realization-only scenario attempts experimental observation."""

    capabilities = ()

    def collect(self, *args):
        raise AssertionError("observation collection must not run")

    def describe(self, *args):
        raise AssertionError("observation reporting must not run")

    def protect(self, *args):
        raise AssertionError("observation retention must not run")

    def verify_evidence(self, *args):
        raise AssertionError("observation evidence verification must not run")


def _hermetic_target(provisioner_type=_ObservedStubProvisioner):
    target = create_stub_target()
    manifest = target.manifest
    kinds = {descriptor.concern_kind for descriptor in realization_concern_descriptors()}
    configuration = RealizationObservationCapability(
        verification_scope=RealizationVerificationScope.CONFIGURATION,
        observation_strength=ObservationStrength.GUEST_OBSERVED,
    )
    operating_system = RealizationObservationCapability(
        verification_scope=RealizationVerificationScope.PRESENCE,
        observation_strength=ObservationStrength.GUEST_OBSERVED,
    )
    rows = tuple(
        OperatingSystemCompatibility(family, distribution, frozenset({version}))
        for family, distribution, version in (
            ("linux", "debian", "12"),
            ("linux", "x-fedoraproject:fedora", "42"),
            ("linux", "x-kali:kali", "2025.1"),
            ("linux", "x-acme:research-linux", "1.0"),
            ("linux", "ubuntu", "24.04"),
        )
    )
    provisioner = replace(manifest.provisioner, operating_systems=rows)
    declaration = manifest.realization_support[0]
    declaration = replace(
        declaration,
        support_mode=RealizationSupportMode.OPEN_REALIZATION,
        supported_exact_requirement_kinds=declaration.supported_exact_requirement_kinds | kinds,
        supported_constraint_kinds=declaration.supported_constraint_kinds | kinds,
        observation_capabilities={
            **declaration.observation_capabilities,
            **dict.fromkeys(kinds, configuration),
            "operating-system": operating_system,
        },
    )
    manifest = replace(
        manifest,
        capabilities=replace(manifest.capabilities, provisioner=provisioner),
        realization_support=(declaration,),
    )
    provisioner_runtime = provisioner_type(manifest.realization_envelope)
    return replace(
        target,
        manifest=manifest,
        provisioner=provisioner_runtime,
        observation_runtime=_RejectingObservationRuntime(),
    )


def test_private_five_linux_authoring_survives_the_semantic_lifecycle() -> None:
    scenario = parse_sdl_file(FIXTURE)
    assert tuple(scenario.nodes) == ("debian", "fedora", "kali", "private", "ubuntu")

    instantiated = instantiate_scenario(scenario)
    compiled = compile_runtime_model(instantiated)
    requirement = next(
        item
        for item in compiled.realization_requirements
        if item.address == "provision.node.private" and item.requirement_kind == "runtime-applications"
    )
    methods = requirement.constraint_document.root.items[0].fields["routes"].items[0].fields["methods"]
    assert [item.value for item in methods.items] == ["PROPFIND", "PrivateQuery", "privateQuery"]
    assert compiled.observation_demands == ()

    encoded = canonical_instantiated_sdl_bytes(instantiated)
    restored = InstantiatedScenarioSnapshot.model_validate_json(encoded).scenario
    assert canonical_instantiated_sdl_bytes(restored) == encoded
    assert canonical_sdl_bytes(scenario) == canonical_sdl_bytes(parse_sdl_file(FIXTURE))


def test_open_parents_keep_exact_siblings_and_do_not_invent_observation() -> None:
    compiled = compile_runtime_model(parse_sdl_file(FIXTURE))
    by_key = {(item.address, item.requirement_kind): item for item in compiled.realization_requirements}

    kali_distribution = by_key[("provision.node.kali", "os-distribution")]
    assert kali_distribution.explicitness is ExplicitnessClass.EXACT
    assert evaluate_realization_constraint(kali_distribution.constraint_document, "x-kali:kali").conformant
    assert not evaluate_realization_constraint(kali_distribution.constraint_document, "ubuntu").conformant

    applications = by_key[("provision.node.private", "runtime-applications")]
    assert applications.explicitness is ExplicitnessClass.OPEN
    route_scope = next(
        scope for scope in applications.constraint_document.scopes if scope.field_pointer == "/0/routes/0"
    )
    assert route_scope.closure.posture.value == "open"
    assert compiled.observation_demands == ()
    assert compiled.action_contracts == {}


def test_complete_abstract_model_needs_no_concrete_machine_catalog() -> None:
    abstract = {
        "computers": {
            "a": {"actions": ["increment", "send", "receive"]},
            "b": {"actions": ["increment", "send", "receive"]},
        },
        "links": {"mailbox": {"source": "a", "target": "b"}},
    }
    normalized = normalize_realization_literal(
        abstract,
        semantic_profile="abstract-transition-system/v1",
        default_closure=RealizationClosure(
            posture="open",
            universe="abstract-model/v1",
            profile="abstract-transition-system/v1",
        ),
    )
    assert normalized.document is not None
    assert evaluate_realization_constraint(normalized.document, abstract).conformant
    serialized = normalized.document.model_dump_json()
    assert all(term not in serialized for term in ("operating_system", "image", "packages", "observation"))


def test_negative_mutations_fail_at_source_or_identity_boundaries() -> None:
    source = FIXTURE.read_text()
    invalid_method_source = source.replace("PROPFIND", "BAD METHOD", 1)
    with pytest.raises(SDLParseError, match="HTTP method"):
        parse_sdl(invalid_method_source)

    low_node_limit = SDLParserLimits(max_nodes=2)
    with pytest.raises(SDLParseError, match="unique nodes"):
        parse_sdl(source, limits=low_node_limit)


def test_same_scenario_plans_executes_persists_and_recovers_without_collection() -> None:
    target = _hermetic_target()
    execution = plan(compile_runtime_model(parse_sdl_file(FIXTURE)), target.manifest)
    assert execution.is_valid, [(item.code, item.message) for item in execution.diagnostics]

    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(target, store=store)
    control_plane.register_planner_produced_plan(execution)
    receipt = control_plane.submit_provisioning(execution.provisioning)
    assert receipt.accepted
    status = control_plane.get_operation(receipt.operation_id)
    assert status.state is OperationState.SUCCEEDED, status.diagnostics
    assert set(control_plane.snapshot.entries) == {
        "provision.node.debian",
        "provision.node.fedora",
        "provision.node.kali",
        "provision.node.private",
        "provision.node.ubuntu",
    }
    assert control_plane.observation_execution(receipt.operation_id) is None
    assert all(record.result_payload is None for record in store.load_records().values())

    recovered = RuntimeControlPlane(target, store=store)
    assert recovered.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
    assert recovered.snapshot == control_plane.snapshot


def test_runtime_rejects_private_identity_drift_without_persisting_side_effects() -> None:
    target = _hermetic_target(_PerturbedObservedStubProvisioner)
    execution = plan(compile_runtime_model(parse_sdl_file(FIXTURE)), target.manifest)
    assert execution.is_valid, [(item.code, item.message) for item in execution.diagnostics]

    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(target, store=store)
    control_plane.register_planner_produced_plan(execution)
    receipt = control_plane.submit_provisioning(execution.provisioning)
    assert receipt.accepted
    status = control_plane.get_operation(receipt.operation_id)
    assert status.state is OperationState.FAILED
    assert status.changed_addresses == []
    assert status.diagnostics[0].code == "runtime.backend-contract-invalid"
    assert status.diagnostics[0].address == "/provision.node.private"
    assert control_plane.snapshot.entries == {}
    assert store.load_records()[receipt.operation_id].result_payload is None

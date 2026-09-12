"""Portable artifact requirement, capability, and satisfaction contracts (#920)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes.artifact_requirements import (
    ArtifactCandidate,
    ArtifactConstraint,
    ArtifactIdentity,
    ArtifactLockedInput,
    ArtifactMaterializationSpecification,
    ArtifactMechanismProfile,
    ArtifactRequirement,
    ArtifactSatisfactionRoute,
    Source,
)
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes.parser import parse_sdl
from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_stubs.stubs import create_stub_manifest
from raes_contracts.apparatus import ApparatusIdentity
from raes_contracts.artifact_requirements import (
    ARTIFACT_REQUIREMENT_SCHEMA_VERSION,
    ArtifactAvailabilityContext,
    ArtifactMechanismCapability,
    ArtifactRequirementAvailability,
    ArtifactRequirementContractModel,
    ArtifactSatisfactionDisclosureModel,
    artifact_requirement_invariant_violations,
)
from raes_contracts.contracts import schema_bundle
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.runtime_state import RealizationProvenanceEntry, RuntimeSnapshot, SnapshotEntry
from raes_contracts.vocabulary import RealizationSupportMode
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import CompiledRealizationRequirement
from raes_processor.planner.core import plan
from raes_processor.semantics.realization import (
    artifact_requirement_diagnostics,
    realization_disclosure,
)
from raes_runtime.control_plane_store import _snapshot_from_payload, _snapshot_payload

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_PROFILE_DIGEST = "sha256:" + "c" * 64
_ADDRESS = "provision.node.web"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_ROOT = _REPO_ROOT / "contracts" / "fixtures" / "artifact-requirements" / "artifact-requirement-v1"


def _identity(*, digest: str = _DIGEST_A) -> ArtifactIdentity:
    return ArtifactIdentity(
        artifact_id="ubuntu-server",
        version="24.04.1",
        digest=digest,
        media_type="application/vnd.oci.image.manifest.v1+json",
    )


def _mechanism(name: str = "exact-artifact") -> ArtifactMechanismProfile:
    return ArtifactMechanismProfile(
        mechanism=name,
        profile="raes-artifact-satisfaction",
        version="1",
        digest=_PROFILE_DIGEST,
    )


def _route(
    *,
    mechanism: ArtifactMechanismProfile | None = None,
    acquisition: str = "pull",
    timing: str = "realization",
) -> ArtifactSatisfactionRoute:
    return ArtifactSatisfactionRoute(
        mechanism=mechanism or _mechanism(),
        acquisition=acquisition,
        timing=timing,
    )


def _exact_requirement() -> ArtifactRequirement:
    return ArtifactRequirement(
        requirement_id="web-image",
        explicitness=ExplicitnessClass.EXACT,
        exact_artifact=_identity(),
        permitted_routes=[_route()],
        trust_policy_refs=["reusable-asset-trust-policy-v1#reusable_scenario"],
    )


def _compiled(
    requirement: ArtifactRequirement,
    *,
    address: str = _ADDRESS,
) -> CompiledRealizationRequirement:
    return CompiledRealizationRequirement(
        field_path="nodes.web.source.artifact_requirement",
        address=address,
        domain="runtime-realization",
        requirement_kind="source-artifact",
        explicitness=requirement.explicitness,
        provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
        governing_scope="#/nodes/web/source/artifact_requirement",
        artifact_requirement=requirement,
    )


def _availability(
    *,
    address: str = _ADDRESS,
    available_artifact_digests: list[str] | None = None,
    available_candidate_ids: list[str] | None = None,
    verified_locked_input_ids: list[str] | None = None,
    satisfied_constraint_ids: list[str] | None = None,
    available_materialization_specification_digests: list[str] | None = None,
    verified_integrity_refs: list[str] | None = None,
    verified_authenticity_refs: list[str] | None = None,
    verified_admission_refs: list[str] | None = None,
    verified_provenance_refs: list[str] | None = None,
    verified_evidence_refs: list[str] | None = None,
) -> ArtifactAvailabilityContext:
    return ArtifactAvailabilityContext(
        requirements=[
            ArtifactRequirementAvailability(
                address=address,
                available_artifact_digests=available_artifact_digests or [],
                available_candidate_ids=available_candidate_ids or [],
                verified_locked_input_ids=verified_locked_input_ids or [],
                satisfied_constraint_ids=satisfied_constraint_ids or [],
                available_materialization_specification_digests=(available_materialization_specification_digests or []),
                verified_integrity_refs=verified_integrity_refs or [],
                verified_authenticity_refs=verified_authenticity_refs or [],
                verified_admission_refs=verified_admission_refs or [],
                verified_provenance_refs=verified_provenance_refs or [],
                verified_evidence_refs=verified_evidence_refs or [],
            )
        ]
    )


def _capability(
    *,
    mechanism: ArtifactMechanismProfile | None = None,
    acquisition: str = "pull",
    timing: str = "realization",
) -> ArtifactMechanismCapability:
    return ArtifactMechanismCapability(
        mechanism=mechanism or _mechanism(),
        supported_requirement_kinds=["source-artifact"],
        supported_routes=[
            {
                "acquisition": acquisition,
                "timing": timing,
            }
        ],
    )


def _manifest(
    requirement: ArtifactRequirement,
    *,
    capability: ArtifactMechanismCapability | None = None,
) -> BackendManifest:
    manifest = create_stub_manifest()
    declarations = []
    for declaration in manifest.realization_support:
        if declaration.domain != "runtime-realization":
            declarations.append(declaration)
            continue
        declarations.append(
            replace(
                declaration,
                artifact_mechanisms=(capability or _capability(),),
                supported_constraint_kinds=declaration.supported_constraint_kinds | frozenset({"source-artifact"}),
            )
        )
    return replace(manifest, realization_support=tuple(declarations))


def test_exact_requirement_requires_one_immutable_identity_and_no_alternatives() -> None:
    source = Source(
        name="ubuntu-server",
        version="24.04.1",
        artifact_requirement=_exact_requirement(),
    )
    assert source.artifact_requirement is not None
    assert source.artifact_requirement.explicitness is ExplicitnessClass.EXACT

    exact_routes = [_route()]
    with pytest.raises(ValidationError, match="immutable|exact"):
        ArtifactRequirement(
            requirement_id="bad-exact",
            explicitness=ExplicitnessClass.EXACT,
            permitted_routes=exact_routes,
        )
    exact_identity = _identity()
    fallback_candidate = ArtifactCandidate(candidate_id="fallback", artifact=_identity(digest=_DIGEST_B))
    with pytest.raises(ValidationError, match="alternative|candidate|exact"):
        ArtifactRequirement(
            requirement_id="bad-fallback",
            explicitness=ExplicitnessClass.EXACT,
            exact_artifact=exact_identity,
            candidates=[fallback_candidate],
            permitted_routes=exact_routes,
        )
    exact_requirement = _exact_requirement()
    with pytest.raises(ValidationError, match="selector|identity|match"):
        Source(
            name="different-image",
            version="24.04.1",
            artifact_requirement=exact_requirement,
        )


def test_constrained_open_and_absent_postures_are_independent_of_transport() -> None:
    constrained = ArtifactRequirement(
        requirement_id="candidate-image",
        explicitness=ExplicitnessClass.CONSTRAINED,
        constraints=[
            ArtifactConstraint(
                constraint_id="linux-image",
                kind="artifact-class",
                allowed_values=["linux-vm-image"],
            )
        ],
        candidates=[ArtifactCandidate(candidate_id="candidate-a", artifact=_identity())],
        permitted_routes=[
            _route(acquisition="local-lookup", timing="backend-preparation"),
            _route(
                mechanism=_mechanism("published-candidate"),
                acquisition="import",
                timing="pack-ingestion",
            ),
        ],
    )
    opened = ArtifactRequirement(
        requirement_id="backend-selected",
        explicitness=ExplicitnessClass.OPEN,
        permitted_routes=[
            _route(
                mechanism=_mechanism("dynamic-composition"),
                acquisition="none",
                timing="realization",
            )
        ],
    )

    assert {route.acquisition for route in constrained.permitted_routes} == {
        "local-lookup",
        "import",
    }
    assert opened.permitted_routes[0].mechanism.mechanism == "dynamic-composition"
    assert Source(name="legacy", version="*").artifact_requirement is None


def test_materialization_and_locked_inputs_are_explicit_constrained_authority() -> None:
    locked = ArtifactLockedInput(
        input_id="rootfs",
        artifact=_identity(),
        associated_artifact_manifest_ref="associated-artifact-manifest-v1:rootfs",
        trust_policy_ref="reusable-asset-trust-policy-v1#associated_artifact_set",
    )
    specification = ArtifactMaterializationSpecification(
        specification_id="cloud-image",
        profile=_mechanism("materialization-specification"),
        digest=_PROFILE_DIGEST,
        locked_input_ids=["rootfs"],
    )
    requirement = ArtifactRequirement(
        requirement_id="materialized-image",
        explicitness=ExplicitnessClass.CONSTRAINED,
        locked_inputs=[locked],
        materialization_specifications=[specification],
        permitted_routes=[
            _route(
                mechanism=_mechanism("materialization-specification"),
                acquisition="none",
                timing="backend-preparation",
            )
        ],
    )
    assert requirement.materialization_specifications[0].locked_input_ids == ["rootfs"]

    materialization_routes = [_route(mechanism=_mechanism("materialization-specification"))]
    with pytest.raises(ValidationError, match="locked input"):
        ArtifactRequirement(
            requirement_id="missing-input-ref",
            explicitness=ExplicitnessClass.CONSTRAINED,
            materialization_specifications=[specification],
            permitted_routes=materialization_routes,
        )


def test_mechanisms_are_governed_extensible_profiles_not_a_closed_union() -> None:
    extension = _mechanism("x-acme:golden-image-compose")
    requirement = ArtifactRequirement(
        requirement_id="extension",
        explicitness=ExplicitnessClass.OPEN,
        permitted_routes=[_route(mechanism=extension, acquisition="none")],
    )
    assert requirement.permitted_routes[0].mechanism == extension

    with pytest.raises(ValidationError, match="mechanism"):
        _mechanism("arbitrary ungoverned mechanism")


@pytest.mark.parametrize(
    ("requirement", "context", "manifest_mutator", "expected_code"),
    [
        (
            _exact_requirement(),
            _availability(),
            None,
            "artifact.unavailable-exact-artifact",
        ),
        (
            ArtifactRequirement(
                requirement_id="constraint",
                explicitness=ExplicitnessClass.CONSTRAINED,
                constraints=[
                    ArtifactConstraint(
                        constraint_id="linux",
                        kind="artifact-class",
                        allowed_values=["linux-vm-image"],
                    )
                ],
                permitted_routes=[_route()],
            ),
            _availability(available_artifact_digests=[_DIGEST_A]),
            None,
            "artifact.unsatisfied-constraint",
        ),
        (
            ArtifactRequirement(
                requirement_id="open",
                explicitness=ExplicitnessClass.OPEN,
                permitted_routes=[_route(mechanism=_mechanism("dynamic-composition"))],
            ),
            _availability(),
            "exact-only",
            "artifact.unsupported-open-realization",
        ),
        (
            ArtifactRequirement(
                requirement_id="locked",
                explicitness=ExplicitnessClass.CONSTRAINED,
                locked_inputs=[
                    ArtifactLockedInput(
                        input_id="rootfs",
                        artifact=_identity(),
                        associated_artifact_manifest_ref="associated-artifact-manifest-v1:rootfs",
                        trust_policy_ref="reusable-asset-trust-policy-v1#associated_artifact_set",
                    )
                ],
                permitted_routes=[_route()],
            ),
            _availability(available_artifact_digests=[_DIGEST_A]),
            None,
            "artifact.missing-locked-input",
        ),
        (
            ArtifactRequirement(
                requirement_id="candidate",
                explicitness=ExplicitnessClass.CONSTRAINED,
                candidates=[ArtifactCandidate(candidate_id="candidate-a", artifact=_identity())],
                permitted_routes=[_route(mechanism=_mechanism("published-candidate"))],
            ),
            _availability(),
            None,
            "artifact.unavailable-candidate",
        ),
        (
            ArtifactRequirement(
                requirement_id="materialization",
                explicitness=ExplicitnessClass.CONSTRAINED,
                materialization_specifications=[
                    ArtifactMaterializationSpecification(
                        specification_id="cloud-image",
                        profile=_mechanism("materialization-specification"),
                        digest=_PROFILE_DIGEST,
                    )
                ],
                permitted_routes=[_route(mechanism=_mechanism("materialization-specification"))],
            ),
            _availability(),
            None,
            "artifact.unavailable-materialization-specification",
        ),
        (
            ArtifactRequirement(
                requirement_id="mechanism",
                explicitness=ExplicitnessClass.OPEN,
                permitted_routes=[_route(mechanism=_mechanism("x-acme:composer"), acquisition="none")],
            ),
            _availability(),
            "different-mechanism",
            "artifact.unsupported-backend-mechanism",
        ),
    ],
)
def test_realizability_failures_have_stable_distinct_diagnostics(
    requirement: ArtifactRequirement,
    context: ArtifactAvailabilityContext,
    manifest_mutator: str | None,
    expected_code: str,
) -> None:
    manifest = _manifest(requirement)
    if manifest_mutator == "exact-only":
        declarations = tuple(
            replace(
                declaration,
                support_mode=RealizationSupportMode.EXACT_ONLY,
                supported_constraint_kinds=frozenset(),
            )
            if declaration.domain == "runtime-realization"
            else declaration
            for declaration in manifest.realization_support
        )
        manifest = replace(manifest, realization_support=declarations)
    elif manifest_mutator == "different-mechanism":
        manifest = _manifest(requirement, capability=_capability(mechanism=_mechanism("dynamic-composition")))

    codes = {
        diagnostic.code
        for diagnostic in artifact_requirement_diagnostics(
            (_compiled(requirement),),
            manifest,
            availability=context,
        )
    }
    assert expected_code in codes


def test_backend_capability_matrix_does_not_claim_cartesian_product() -> None:
    requirement = ArtifactRequirement(
        requirement_id="prepared",
        explicitness=ExplicitnessClass.CONSTRAINED,
        candidates=[ArtifactCandidate(candidate_id="candidate-a", artifact=_identity())],
        permitted_routes=[
            _route(
                mechanism=_mechanism("published-candidate"),
                acquisition="import",
                timing="backend-preparation",
            )
        ],
    )
    capability = _capability(
        mechanism=_mechanism("published-candidate"),
        acquisition="pull",
        timing="publication",
    )
    diagnostics = artifact_requirement_diagnostics(
        (_compiled(requirement),),
        _manifest(requirement, capability=capability),
        availability=_availability(
            available_candidate_ids=["candidate-a"],
            available_artifact_digests=[_DIGEST_A],
        ),
    )
    assert {diagnostic.code for diagnostic in diagnostics} == {"artifact.unsupported-backend-mechanism"}


def test_requirement_local_availability_ids_cannot_collide_across_addresses() -> None:
    requirement = ArtifactRequirement(
        requirement_id="candidate",
        explicitness=ExplicitnessClass.CONSTRAINED,
        candidates=[ArtifactCandidate(candidate_id="fallback", artifact=_identity())],
        permitted_routes=[_route(mechanism=_mechanism("published-candidate"))],
    )
    first = _compiled(requirement, address="provision.node.first")
    second = _compiled(requirement, address="provision.node.second")
    facts = _availability(
        address=first.address,
        available_candidate_ids=["fallback"],
    )

    diagnostics = artifact_requirement_diagnostics(
        (first, second),
        _manifest(requirement),
        availability=facts,
    )

    assert [
        diagnostic.address for diagnostic in diagnostics if diagnostic.code == "artifact.unavailable-candidate"
    ] == [second.address]


def test_source_artifact_requirement_lowers_into_existing_compiled_demand() -> None:
    scenario = parse_sdl(
        f"""
name: portable-artifact
nodes:
  web:
    type: compute
    os: linux
    source:
      name: ubuntu-server
      version: 24.04.1
      artifact_requirement:
        requirement_id: web-image
        explicitness: exact
        exact_artifact:
          artifact_id: ubuntu-server
          version: 24.04.1
          digest: {_DIGEST_A}
          media_type: application/vnd.oci.image.manifest.v1+json
        permitted_routes:
          - mechanism:
              mechanism: exact-artifact
              profile: raes-artifact-satisfaction
              version: "1"
              digest: {_PROFILE_DIGEST}
            acquisition: pull
            timing: realization
        trust_policy_refs:
          - reusable-asset-trust-policy-v1#reusable_scenario
"""
    )
    compiled = compile_runtime_model(scenario)
    requirements = [
        requirement for requirement in compiled.realization_requirements if requirement.artifact_requirement is not None
    ]
    assert len(requirements) == 1
    assert requirements[0].address == _ADDRESS
    assert requirements[0].artifact_requirement == _exact_requirement()


def test_planner_threads_scoped_artifact_availability_into_admission() -> None:
    scenario = parse_sdl(
        f"""
name: portable-artifact-plan
nodes:
  web:
    type: compute
    os: linux
    source:
      name: ubuntu-server
      version: 24.04.1
      artifact_requirement:
        requirement_id: web-image
        explicitness: exact
        exact_artifact:
          artifact_id: ubuntu-server
          version: 24.04.1
          digest: {_DIGEST_A}
          media_type: application/vnd.oci.image.manifest.v1+json
        permitted_routes:
          - mechanism:
              mechanism: exact-artifact
              profile: raes-artifact-satisfaction
              version: "1"
              digest: {_PROFILE_DIGEST}
            acquisition: pull
            timing: realization
        trust_policy_refs:
          - reusable-asset-trust-policy-v1#reusable_scenario
"""
    )
    model = compile_runtime_model(scenario)
    manifest = _manifest(_exact_requirement())

    unavailable = plan(
        model,
        manifest,
        artifact_availability=_availability(),
    )
    available = plan(
        model,
        manifest,
        artifact_availability=_availability(
            available_artifact_digests=[_DIGEST_A],
        ),
    )

    assert "artifact.unavailable-exact-artifact" in {diagnostic.code for diagnostic in unavailable.diagnostics}
    assert "artifact.unavailable-exact-artifact" not in {diagnostic.code for diagnostic in available.diagnostics}


def test_exact_runtime_satisfaction_rejects_substitution_and_discloses_provenance() -> None:
    requirement = _exact_requirement()
    compiled = _compiled(requirement)
    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=_ADDRESS,
                resource_type="node",
                payload={"artifact_requirement": requirement.model_dump(mode="json")},
            )
        ]
    )
    manifest = _manifest(requirement)
    trust_policy_ref = "reusable-asset-trust-policy-v1#reusable_scenario"
    wrong = ArtifactSatisfactionDisclosureModel(
        requirement_id="web-image",
        artifact=_identity(digest=_DIGEST_B),
        mechanism=_mechanism(),
        acquisition="pull",
        timing="realization",
        backend=manifest.identity,
        integrity_refs=["sha256:" + "b" * 64],
        admission_refs=[trust_policy_ref],
        provenance_refs=["provenance:stub"],
    )
    snapshot = RuntimeSnapshot(
        entries={
            _ADDRESS: SnapshotEntry(
                address=_ADDRESS,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload={"artifact_satisfaction": wrong.model_dump(mode="json")},
            )
        }
    )

    availability = _availability(
        available_artifact_digests=[_DIGEST_A],
        verified_integrity_refs=[_DIGEST_A, _DIGEST_B],
        verified_admission_refs=[trust_policy_ref],
        verified_provenance_refs=["provenance:stub"],
    )
    diagnostics, provenance = realization_disclosure(
        (compiled,),
        plan,
        snapshot,
        manifest=manifest,
        artifact_availability=availability,
    )
    assert {diagnostic.code for diagnostic in diagnostics} == {"runtime.backend-contract-invalid"}
    assert provenance == ()

    correct = wrong.model_copy(
        update={
            "artifact": _identity(),
            "integrity_refs": [_DIGEST_A],
        }
    )
    snapshot.entries[_ADDRESS].payload["artifact_satisfaction"] = correct.model_dump(mode="json")
    diagnostics, provenance = realization_disclosure(
        (compiled,),
        plan,
        snapshot,
        manifest=manifest,
        artifact_availability=availability,
    )
    assert diagnostics == []
    assert len(provenance) == 1
    assert provenance[0].artifact_satisfaction == correct
    assert provenance[0].provenance is ExplicitnessProvenance.AUTHOR_DECLARED


def test_runtime_rejects_route_not_admitted_by_selected_manifest() -> None:
    requirement = _exact_requirement()
    compiled = _compiled(requirement)
    declared_plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=_ADDRESS,
                resource_type="node",
                payload={"artifact_requirement": requirement.model_dump(mode="json")},
            )
        ]
    )
    manifest = _manifest(
        requirement,
        capability=_capability(acquisition="copy"),
    )
    trust_policy_ref = "reusable-asset-trust-policy-v1#reusable_scenario"
    disclosure = ArtifactSatisfactionDisclosureModel(
        requirement_id=requirement.requirement_id,
        artifact=_identity(),
        mechanism=_mechanism(),
        acquisition="pull",
        timing="realization",
        backend=manifest.identity,
        integrity_refs=[_DIGEST_A],
        admission_refs=[trust_policy_ref],
        provenance_refs=["provenance:verified"],
    )
    snapshot = RuntimeSnapshot(
        entries={
            _ADDRESS: SnapshotEntry(
                address=_ADDRESS,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload={
                    "artifact_satisfaction": disclosure.model_dump(mode="json"),
                },
            )
        }
    )
    availability = _availability(
        available_artifact_digests=[_DIGEST_A],
        verified_integrity_refs=[_DIGEST_A],
        verified_admission_refs=[trust_policy_ref],
        verified_provenance_refs=["provenance:verified"],
    )

    diagnostics, provenance = realization_disclosure(
        (compiled,),
        declared_plan,
        snapshot,
        manifest=manifest,
        artifact_availability=availability,
    )

    assert {diagnostic.code for diagnostic in diagnostics} == {"runtime.backend-contract-invalid"}
    assert provenance == ()


def test_runtime_rejects_backend_claims_absent_from_verified_trust_context() -> None:
    requirement = _exact_requirement()
    compiled = _compiled(requirement)
    declared_plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=_ADDRESS,
                resource_type="node",
                payload={"artifact_requirement": requirement.model_dump(mode="json")},
            )
        ]
    )
    manifest = _manifest(requirement)
    trust_policy_ref = "reusable-asset-trust-policy-v1#reusable_scenario"
    disclosure = ArtifactSatisfactionDisclosureModel(
        requirement_id=requirement.requirement_id,
        artifact=_identity(),
        mechanism=_mechanism(),
        acquisition="pull",
        timing="realization",
        backend=manifest.identity,
        integrity_refs=[_DIGEST_A],
        admission_refs=[trust_policy_ref],
        provenance_refs=["provenance:unverified"],
    )
    snapshot = RuntimeSnapshot(
        entries={
            _ADDRESS: SnapshotEntry(
                address=_ADDRESS,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload={
                    "artifact_satisfaction": disclosure.model_dump(mode="json"),
                },
            )
        }
    )
    availability = _availability(
        available_artifact_digests=[_DIGEST_A],
        verified_integrity_refs=[_DIGEST_A],
        verified_admission_refs=[trust_policy_ref],
    )

    diagnostics, provenance = realization_disclosure(
        (compiled,),
        declared_plan,
        snapshot,
        manifest=manifest,
        artifact_availability=availability,
    )

    assert {diagnostic.code for diagnostic in diagnostics} == {"runtime.backend-contract-invalid"}
    assert provenance == ()


def test_runtime_binds_candidate_backend_route_and_verified_evidence() -> None:
    requirement = ArtifactRequirement(
        requirement_id="candidate-image",
        explicitness=ExplicitnessClass.CONSTRAINED,
        candidates=[ArtifactCandidate(candidate_id="candidate-a", artifact=_identity())],
        permitted_routes=[_route(mechanism=_mechanism("published-candidate"))],
    )
    compiled = _compiled(requirement)
    declared_plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=_ADDRESS,
                resource_type="node",
                payload={"artifact_requirement": requirement.model_dump(mode="json")},
            )
        ]
    )
    manifest = _manifest(
        requirement,
        capability=_capability(mechanism=_mechanism("published-candidate")),
    )
    disclosure = ArtifactSatisfactionDisclosureModel(
        requirement_id=requirement.requirement_id,
        artifact=_identity(digest=_DIGEST_B),
        mechanism=_mechanism("published-candidate"),
        acquisition="pull",
        timing="realization",
        backend=manifest.identity,
        candidate_id="candidate-a",
        integrity_refs=[_DIGEST_B],
        provenance_refs=["provenance:verified"],
    )
    snapshot = RuntimeSnapshot(
        entries={
            _ADDRESS: SnapshotEntry(
                address=_ADDRESS,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload={
                    "artifact_satisfaction": disclosure.model_dump(mode="json"),
                },
            )
        }
    )
    availability = _availability(
        available_candidate_ids=["candidate-a"],
        verified_integrity_refs=[_DIGEST_A, _DIGEST_B],
        verified_provenance_refs=["provenance:verified"],
    )

    diagnostics, _ = realization_disclosure(
        (compiled,),
        declared_plan,
        snapshot,
        manifest=manifest,
        artifact_availability=availability,
    )
    assert {diagnostic.code for diagnostic in diagnostics} == {"runtime.backend-contract-invalid"}

    valid = disclosure.model_copy(
        update={
            "artifact": _identity(),
            "integrity_refs": [_DIGEST_A],
        }
    )
    snapshot.entries[_ADDRESS].payload["artifact_satisfaction"] = valid.model_dump(mode="json")
    diagnostics, provenance = realization_disclosure(
        (compiled,),
        declared_plan,
        snapshot,
        manifest=manifest,
        artifact_availability=availability,
    )
    assert diagnostics == []
    assert provenance[0].artifact_satisfaction == valid

    wrong_backend = valid.model_copy(update={"backend": ApparatusIdentity(name="forged", version="1")})
    snapshot.entries[_ADDRESS].payload["artifact_satisfaction"] = wrong_backend.model_dump(mode="json")
    diagnostics, _ = realization_disclosure(
        (compiled,),
        declared_plan,
        snapshot,
        manifest=manifest,
        artifact_availability=availability,
    )
    assert {diagnostic.code for diagnostic in diagnostics} == {"runtime.backend-contract-invalid"}


def test_runtime_binds_materialization_selection_to_verified_specification_digest() -> None:
    trust_policy_ref = "reusable-asset-trust-policy-v1#associated_artifact_set"
    manifest_ref = "associated-artifact-manifest-v1:rootfs"
    requirement = ArtifactRequirement(
        requirement_id="materialized-image",
        explicitness=ExplicitnessClass.CONSTRAINED,
        locked_inputs=[
            ArtifactLockedInput(
                input_id="rootfs",
                artifact=_identity(),
                associated_artifact_manifest_ref=manifest_ref,
                trust_policy_ref=trust_policy_ref,
            )
        ],
        materialization_specifications=[
            ArtifactMaterializationSpecification(
                specification_id="cloud-image",
                profile=_mechanism("materialization-specification"),
                digest=_PROFILE_DIGEST,
                locked_input_ids=["rootfs"],
            )
        ],
        permitted_routes=[
            _route(
                mechanism=_mechanism("materialization-specification"),
                acquisition="none",
                timing="backend-preparation",
            )
        ],
    )
    compiled = _compiled(requirement)
    declared_plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=_ADDRESS,
                resource_type="node",
                payload={"artifact_requirement": requirement.model_dump(mode="json")},
            )
        ]
    )
    manifest = _manifest(
        requirement,
        capability=_capability(
            mechanism=_mechanism("materialization-specification"),
            acquisition="none",
            timing="backend-preparation",
        ),
    )
    disclosure = ArtifactSatisfactionDisclosureModel(
        requirement_id=requirement.requirement_id,
        artifact=_identity(),
        mechanism=_mechanism("materialization-specification"),
        acquisition="none",
        timing="backend-preparation",
        backend=manifest.identity,
        materialization_specification_id="cloud-image",
        materialization_specification_digest=_DIGEST_B,
        locked_input_ids=["rootfs"],
        integrity_refs=[_DIGEST_A],
        admission_refs=[trust_policy_ref],
        provenance_refs=["provenance:verified"],
        evidence_refs=[manifest_ref],
    )
    snapshot = RuntimeSnapshot(
        entries={
            _ADDRESS: SnapshotEntry(
                address=_ADDRESS,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload={
                    "artifact_satisfaction": disclosure.model_dump(mode="json"),
                },
            )
        }
    )
    availability = _availability(
        verified_locked_input_ids=["rootfs"],
        available_materialization_specification_digests=[_PROFILE_DIGEST],
        verified_integrity_refs=[_DIGEST_A],
        verified_admission_refs=[trust_policy_ref],
        verified_provenance_refs=["provenance:verified"],
        verified_evidence_refs=[manifest_ref],
    )

    diagnostics, provenance = realization_disclosure(
        (compiled,),
        declared_plan,
        snapshot,
        manifest=manifest,
        artifact_availability=availability,
    )
    assert {diagnostic.code for diagnostic in diagnostics} == {"runtime.backend-contract-invalid"}
    assert provenance == ()

    valid = disclosure.model_copy(update={"materialization_specification_digest": _PROFILE_DIGEST})
    snapshot.entries[_ADDRESS].payload["artifact_satisfaction"] = valid.model_dump(mode="json")
    diagnostics, provenance = realization_disclosure(
        (compiled,),
        declared_plan,
        snapshot,
        manifest=manifest,
        artifact_availability=availability,
    )
    assert diagnostics == []
    assert provenance[0].artifact_satisfaction == valid


def test_satisfaction_roundtrips_on_existing_provenance_carrier() -> None:
    disclosure = ArtifactSatisfactionDisclosureModel(
        requirement_id="web-image",
        artifact=_identity(),
        mechanism=_mechanism(),
        acquisition="local-lookup",
        timing="backend-preparation",
        backend={"name": "libvirt", "version": "1"},
        integrity_refs=[_DIGEST_A],
        authenticity_refs=["signature:rekor-entry"],
        admission_refs=["policy:reusable-asset-trust"],
        provenance_refs=["provenance:slsa"],
        evidence_refs=["evidence:artifact-resolution"],
    )
    entry = RealizationProvenanceEntry(
        address=_ADDRESS,
        field_path="nodes.web.source.artifact_requirement",
        domain="runtime-realization",
        requirement_kind="source-artifact",
        explicitness=ExplicitnessClass.EXACT,
        provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
        artifact_satisfaction=disclosure,
    )
    assert entry.artifact_satisfaction is disclosure
    restored = _snapshot_from_payload(_snapshot_payload(RuntimeSnapshot(realization_provenance=(entry,))))
    assert restored.realization_provenance[0].artifact_satisfaction == disclosure
    dumped = ArtifactSatisfactionDisclosureModel.model_validate(disclosure.model_dump(mode="json"))
    assert dumped == disclosure
    assert "location" not in ArtifactSatisfactionDisclosureModel.model_fields
    assert "channel" not in ArtifactSatisfactionDisclosureModel.model_fields


def test_contract_is_published_as_a_closed_schema() -> None:
    assert ARTIFACT_REQUIREMENT_SCHEMA_VERSION == "artifact-requirement/v1"
    model = ArtifactRequirementContractModel.model_validate(
        {
            "schema_version": ARTIFACT_REQUIREMENT_SCHEMA_VERSION,
            "source": Source(
                name="ubuntu-server",
                version="24.04.1",
                artifact_requirement=_exact_requirement(),
            ).model_dump(mode="json"),
        }
    )
    assert model.source.artifact_requirement is not None
    schema = schema_bundle()["artifact-requirement-v1"]
    assert schema["additionalProperties"] is False
    source_schema = schema["$defs"]["ArtifactRequirementSource"]
    assert "artifact_requirement" in source_schema["required"]
    assert {invariant["id"] for invariant in schema["x-raes-invariants"]} == {
        "exact-source-artifact-id-match",
        "exact-source-version-match",
        "materialization-locked-input-join",
    }


def test_published_fixtures_match_schema_and_typed_contract_validation() -> None:
    schema = schema_bundle()["artifact-requirement-v1"]
    validator = Draft202012Validator(schema)
    valid_paths = sorted((_FIXTURE_ROOT / "valid").glob("*.json"))
    invalid_paths = sorted((_FIXTURE_ROOT / "invalid").glob("*.json"))
    assert valid_paths
    assert invalid_paths
    for path in valid_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(payload)
        assert artifact_requirement_invariant_violations(payload) == ()
        ArtifactRequirementContractModel.model_validate(payload)
    for path in invalid_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema_errors = list(validator.iter_errors(payload))
        invariant_errors = artifact_requirement_invariant_violations(payload)
        assert schema_errors or invariant_errors, path
        with pytest.raises(ValidationError):
            ArtifactRequirementContractModel.model_validate(payload)

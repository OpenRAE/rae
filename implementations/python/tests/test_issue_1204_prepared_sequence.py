"""Prepared ordered choices must be delivered in the admitted order."""

from copy import deepcopy
from dataclasses import replace

import pytest
import yaml
from raes import instantiate_scenario, parse_sdl
from raes_contracts.contracts.realization_preparation import RealizationPreparation
from raes_contracts.realization_observation import RealizationObservationDisclosure
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_contracts.vocabulary import ObservationStrength
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_processor.planner.realization_preparation import preparation_authority
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from test_issue_1200_mixed_runtime_constraints import _fixture, _returned


@pytest.mark.parametrize("reverse", [False, True])
def test_prepared_delivery_preserves_sequence_order_with_overlapping_position_domains(reverse):
    runtime = {"container": {"dns": ["1.1.1.1", "8.8.8.8"]}}
    _, _, manifest = _fixture(runtime)
    manifest = replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions | {"backend-realization-preparation-v1"},
    )
    authored = deepcopy(runtime)
    authored["container"]["dns"] = ["${first}", "${second}"]
    source = yaml.safe_dump(
        {
            "name": "prepared-order",
            "variables": {
                "first": {"type": "string", "default": "1.1.1.1", "allowed_values": ["1.1.1.1", "8.8.8.8"]},
                "second": {"type": "string", "default": "8.8.8.8", "allowed_values": ["1.1.1.1", "8.8.8.8"]},
            },
            "nodes": {"host": {"type": "compute", "runtime": authored}},
        }
    )
    execution = plan(compile_runtime_model(instantiate_scenario(parse_sdl(source))), manifest)
    assert execution.is_valid, execution.diagnostics
    request = replace(execution.provisioning, preparation=preparation_authority(manifest))

    class Backend:
        prepares = applies = 0

        def prepare(self, selected, previous):
            self.prepares += 1
            return RealizationPreparation.for_request(selected, previous, operations=tuple(selected.operations))

        def validate(self, selected):
            return []

        def apply(self, selected, previous):
            self.applies += 1
            delivered = deepcopy(runtime)
            if reverse:
                delivered["container"]["dns"].reverse()
            snapshot = _returned(selected, delivered)
            snapshot.realization_observations = tuple(
                RealizationObservationDisclosure(
                    address=authority.address,
                    field_path=authority.field_path,
                    domain=authority.domain,
                    requirement_kind=authority.requirement_kind,
                    verification_scope=authority.verification_scope,
                    observation_strength=(
                        authority.required_observation_strength or ObservationStrength.GUEST_OBSERVED
                    ),
                )
                for authority in selected.realization_authority
                if authority.requirement_kind == "runtime-container-dns"
            )
            snapshot.metadata = deepcopy(previous.metadata)
            return ApplyResult(True, snapshot, changed_addresses=list(snapshot.entries))

    backend = Backend()
    previous = RuntimeSnapshot(metadata={"trusted": "predecessor"})
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.prepared-sequence",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert (backend.prepares, backend.applies) == (1, 1)
    assert result.success is not reverse, result.diagnostics
    if reverse:
        assert result.snapshot == previous
        assert result.changed_addresses == []
        assert result.details == {}
        assert result.diagnostics[0].code == "runtime.backend-contract-invalid"
        assert result.diagnostics[0].message == "Backend did not deliver its admitted realization completion."


def test_prepared_delivery_matches_keyed_collection_members_by_identity():
    from raes_processor.planner import prepared_delivery_violation

    runtime = {
        "packages": [
            {"name": "zsh", "version": "5.9", "manager": "apt"},
            {"name": "curl", "version": "8.5", "manager": "apt"},
        ]
    }
    _, request, _ = _fixture(runtime, scope="/nodes/host/runtime/packages")
    reordered = deepcopy(runtime)
    reordered["packages"].reverse()
    assert prepared_delivery_violation(request, _returned(request, reordered)) is None
    reordered["packages"][0]["version"] = "8.6"
    assert prepared_delivery_violation(request, _returned(request, reordered)) is not None


def test_identity_order_follows_records_sequences_references_and_conjunctions():
    from raes_contracts.realization_structure import (
        RealizationAllOf,
        RealizationCollectionMember,
        RealizationConstraintDocument,
        RealizationDefinitionReference,
        RealizationKeyedCollectionConstraint,
        RealizationLiteral,
        RealizationRecordConstraint,
        RealizationSequenceConstraint,
    )
    from raes_processor.planner.realization_preparation import _identity_order

    literal = RealizationLiteral(kind="literal", value="x")
    keyed = RealizationKeyedCollectionConstraint(
        kind="keyed-collection",
        collection_kind="test",
        identity_fields=("id",),
        members=(RealizationCollectionMember(identity=("a",), constraint=literal),),
    )
    document = RealizationConstraintDocument(
        semantic_profile="test",
        root=RealizationRecordConstraint(
            kind="recursive-record",
            fields={
                "sets": RealizationSequenceConstraint(
                    kind="sequence",
                    items=(
                        RealizationAllOf(
                            kind="all-of",
                            constraints=(
                                RealizationDefinitionReference(kind="definition-reference", target="keyed"),
                                literal,
                            ),
                        ),
                    ),
                ),
            },
        ),
        definitions={"keyed": keyed},
    )
    value = {"sets": [[{"id": "b"}, {"id": "a"}], ["kept"]], "other": [{"id": "z"}, {"id": "y"}]}
    ordered = _identity_order(value, document.root, document)
    # The keyed members are ordered; an unconstrained field and a second position keep their order.
    assert ordered == {"sets": [[{"id": "a"}, {"id": "b"}], ["kept"]], "other": [{"id": "z"}, {"id": "y"}]}
    missing = RealizationConstraintDocument(
        semantic_profile="test", root=RealizationDefinitionReference(kind="definition-reference", target="absent")
    )
    assert _identity_order([{"id": "b"}], missing.root, missing) == [{"id": "b"}]
    assert _identity_order("text", document.root, document) == "text"

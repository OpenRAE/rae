"""Resolved effect comparison; provenance remains in the sealed trial records."""

from collections.abc import Mapping

from raes.scenario import InstantiatedScenario
from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest
from raes_contracts.contracts import AdmittedTrialEntryModel

from .models import CompilationFailure


def _participant_effects(entry: AdmittedTrialEntryModel, scenario: InstantiatedScenario) -> list[object]:
    participants = []
    for result in sorted(entry.participant_configurations, key=lambda result: result.participant_address):
        values = []
        for value in result.configuration.values:
            effect = value.model_dump(mode="json", exclude={"origin"})
            context = value.control_context_selection
            if context is not None:
                # Owner admission already checked this exact pin on the concrete
                # scenario. Compare content and operative scope, never its label,
                # locator, descriptor digest, author, timestamp or retention data.
                declaration = context.declaration_ref.removeprefix("control_context_assets.")
                asset = scenario.control_context_assets[declaration]
                effect.pop("value")
                effect["control_context_selection"] = {
                    "slot_id": context.slot_id,
                    "kind": asset.kind,
                    "checksum": asset.content.checksum.model_dump(mode="json"),
                    "media_type": asset.content.media_type,
                    "size_bytes": asset.content.size_bytes,
                    "participant_addresses": sorted(asset.participant_addresses),
                    "role_refs": sorted(asset.role_refs),
                }
            values.append(effect)
        participants.append(
            {
                "participant_address": result.participant_address,
                "implementation": result.configuration.implementation_identity.model_dump(mode="json"),
                "values": values,
            }
        )
    return participants


def resolved_treatment_signature(entry: AdmittedTrialEntryModel, scenario: InstantiatedScenario) -> str:
    """Compare effective content while retaining operative realization metadata."""
    provenance = scenario.instantiation_provenance
    operational_provenance = {
        "capability_constraints": sorted(
            (
                {
                    "field_pointer": constraint.field_pointer,
                    "allowed_values": sorted(constraint.allowed_values, key=canonical_json_bytes),
                }
                for constraint in provenance.capability_constraints
            ),
            key=canonical_json_bytes,
        ),
        "parameter_derivations": [
            derivation.model_dump(mode="json") for derivation in provenance.parameter_derivations
        ],
        "explicitness": [
            {"model_path": record.model_path, "classification": record.classification}
            for record in provenance.explicitness
        ],
        "realization_designations": [record.model_dump(mode="json") for record in provenance.realization_designations],
        "realization_constraints": [
            record.model_dump(mode="json", exclude={"provenance"}) for record in provenance.realization_constraints
        ],
    }
    apparatus = sorted(
        (
            binding.descriptor.realization_payload()
            for binding in entry.bindings
            if binding.descriptor.target.plane == "apparatus"
        ),
        key=canonical_json_bytes,
    )
    return canonical_json_digest(
        [
            scenario.model_dump(mode="json", exclude={"instantiation_provenance"}),
            operational_provenance,
            _participant_effects(entry, scenario),
            apparatus,
        ]
    )


def validate_factorial_distinctness(
    entries: Mapping[str, AdmittedTrialEntryModel],
    resolved_signatures: Mapping[str, str],
) -> None:
    """Keep scalar comparison unchanged; typed designs compare selected effects."""
    conditions_by_signature = {}
    for entry_id, entry in entries.items():
        signature = resolved_signatures.get(entry_id)
        if signature is None:
            operational = sorted(
                (
                    binding.descriptor.realization_payload()
                    for binding in entry.bindings
                    if binding.descriptor.target.plane != "participant-implementation"
                ),
                key=canonical_json_bytes,
            )
            participant_values = [
                {
                    "participant_address": result.participant_address,
                    "configuration": result.configuration.model_dump(
                        mode="json", exclude={"values": {"__all__": {"origin"}}}
                    ),
                }
                for result in sorted(entry.participant_configurations, key=lambda result: result.participant_address)
            ]
            signature = canonical_json_digest([operational, participant_values])
        previous = conditions_by_signature.setdefault(signature, entry.coordinate.condition_id)
        if previous != entry.coordinate.condition_id:
            raise CompilationFailure(
                "factorial-conditions-indistinguishable",
                "/factorial_design",
                "distinct factorial conditions must remain operationally distinguishable after owner resolution",
            )

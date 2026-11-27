"""Added artifact concerns retain the existing satisfaction checks."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes_contracts.artifact_requirements import ArtifactSatisfactionDisclosureModel
from raes_contracts.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.planner import prepared_node_disclosure
from test_artifact_requirement_satisfaction import (
    _DIGEST_A,
    _DIGEST_B,
    _availability,
    _exact_requirement,
    _identity,
    _manifest,
    _mechanism,
)
from test_issue_1697_preparation_provenance import apply_prepared, prepared_target


@pytest.mark.parametrize("satisfaction", ["missing", "wrong", "valid"])
def test_prepared_artifact_provenance_requires_admitted_satisfaction(satisfaction):
    target, backend = prepared_target("{type: compute}")
    _, execution = apply_prepared(target)
    requirement = _exact_requirement()
    manifest = replace(target.manifest, realization_support=_manifest(requirement).realization_support)
    payload = deepcopy(backend.extra.payload)
    payload["spec"]["node"]["source"] = {
        "name": "ubuntu-server",
        "version": "24.04.1",
        "artifact_requirement": requirement.model_dump(mode="json"),
    }
    extra = replace(backend.extra, payload=payload)
    selected = replace(execution.provisioning, operations=[*execution.provisioning.operations, extra])
    snapshot = backend.apply(selected, RuntimeSnapshot()).snapshot
    trust = requirement.trust_policy_refs[0]
    disclosure = ArtifactSatisfactionDisclosureModel(
        requirement_id=requirement.requirement_id,
        artifact=_identity(digest=_DIGEST_B if satisfaction == "wrong" else _DIGEST_A),
        mechanism=_mechanism(),
        acquisition="pull",
        timing="realization",
        backend=manifest.identity,
        integrity_refs=[_DIGEST_A],
        admission_refs=[trust],
        provenance_refs=["provenance:stub"],
    )
    if satisfaction != "missing":
        snapshot.entries[extra.address].payload["artifact_satisfaction"] = disclosure.model_dump(mode="json")
    diagnostics, rows = prepared_node_disclosure(
        selected,
        snapshot,
        manifest=manifest,
        artifact_availability=_availability(
            address=extra.address,
            available_artifact_digests=[_DIGEST_A],
            verified_integrity_refs=[_DIGEST_A],
            verified_admission_refs=[trust],
            verified_provenance_refs=["provenance:stub"],
        ),
    )
    artifact_rows = [row for row in rows if row.requirement_kind == "source-artifact"]
    if satisfaction == "valid":
        assert diagnostics == []
        assert len(artifact_rows) == 1
        assert artifact_rows[0].artifact_satisfaction == disclosure
        assert artifact_rows[0].explicitness is ExplicitnessClass.OPEN
        assert artifact_rows[0].provenance is ExplicitnessProvenance.BACKEND_REALIZED
    else:
        assert diagnostics
        assert artifact_rows == []

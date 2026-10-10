"""Issue #1482: a mixed-runtime component binds when its target carries the admitted contract.

The capture is LilRAE's APTL manifest, produced by LilRAE's own functions (see the
provenance fields in the capture file). Its producer keeps the operating-system rows in
authored order and its artifact mechanisms in a list, so its manifest differs from the
manifest rebuilt from the published payload although both are the same contract.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_protocols.manifest import backend_manifest_from_v2_model_with_envelope, backend_manifest_v2_model
from raes_backend_stubs.stubs import create_stub_components
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import BackendManifestV2Model
from raes_contracts.contracts.mixed_composition import MixedCompositionComponentModel
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_runtime.mixed_runtime import MixedRuntimeComponent, _require_bound_component
from raes_runtime.registry import RuntimeTarget

_CAPTURE = json.loads(
    (Path(__file__).parent / "data" / "boundary_captures" / "lilrae-aptl-backend-manifest.json").read_text(
        encoding="utf-8"
    )
)
_PRODUCER_ROWS = _CAPTURE["producer_representation"]["operating_systems"]


def _published_payload() -> dict[str, Any]:
    return copy.deepcopy(_CAPTURE["backend_manifest"])


def _payload_in_producer_order() -> dict[str, Any]:
    """The same contract with its operating-system rows listed in the producer's order."""

    payload = _published_payload()
    provisioner = payload["capabilities"]["provisioner"]
    rows = {(row["family"], row["distribution"]): row for row in provisioner["operating_systems"]}
    provisioner["operating_systems"] = [rows[family, distribution] for family, distribution in _PRODUCER_ROWS]
    return payload


def _envelope() -> BackendRealizationEnvelopeModel:
    return BackendRealizationEnvelopeModel.model_validate(_CAPTURE["realization_envelope"])


def _rebuilt_manifest() -> BackendManifest:
    """The target manifest the #1016 fixtures build: the published payload rebuilt."""

    return backend_manifest_from_v2_model_with_envelope(
        BackendManifestV2Model.model_validate(_published_payload()), _envelope()
    )


def _producer_manifest() -> BackendManifest:
    """LilRAE's manifest as its producer holds it, from the capture's producer_representation."""

    manifest = _rebuilt_manifest()
    rows = {(row.family, row.distribution): row for row in manifest.provisioner.operating_systems}
    provisioner = replace(
        manifest.provisioner,
        operating_systems=tuple(rows[family, distribution] for family, distribution in _PRODUCER_ROWS),
    )
    container = {"list": list, "tuple": tuple}[_CAPTURE["producer_representation"]["artifact_mechanisms"]]
    support = tuple(
        replace(declaration, artifact_mechanisms=container(declaration.artifact_mechanisms))
        for declaration in manifest.realization_support
    )
    return replace(
        manifest, realization_support=support, capabilities=replace(manifest.capabilities, provisioner=provisioner)
    )


def _narrower_manifest() -> BackendManifest:
    """Another contract: the producer's manifest without its last operating-system row."""

    manifest = _producer_manifest()
    provisioner = replace(manifest.provisioner, operating_systems=manifest.provisioner.operating_systems[:-1])
    return replace(manifest, capabilities=replace(manifest.capabilities, provisioner=provisioner))


def _changed_envelope_manifest() -> BackendManifest:
    """The producer's manifest whose envelope lost a concern after validation and kept its identity."""

    manifest = _producer_manifest()
    envelope = manifest.realization_envelope.model_copy(deep=True)
    envelope.concerns = envelope.concerns[:-1]
    return replace(manifest, realization_envelope=envelope)


def _bind(target_manifest: BackendManifest, payload: dict[str, Any]) -> None:
    admitted, envelope = BackendManifestV2Model.model_validate(payload), _envelope()
    declaration = MixedCompositionComponentModel(
        component_id="aptl",
        apparatus_identity_ref="apparatus:aptl",
        realization_form="emulation-or-operation",
        manifest_ref={
            "ref_kind": "manifest",
            "ref_id": admitted.identity.name,
            "ref_version": admitted.schema_version,
            "ref_digest": canonical_json_digest(admitted.model_dump(mode="json")),
            "subject_ref": {
                "ref_kind": "backend",
                "ref_id": admitted.identity.name,
                "ref_version": admitted.identity.version,
            },
        },
        realization_envelope=envelope.identity,
    )
    parts = create_stub_components(manifest=target_manifest)
    target = RuntimeTarget(
        name="aptl",
        manifest=target_manifest,
        provisioner=parts.provisioner,
        orchestrator=parts.orchestrator,
        evaluator=parts.evaluator,
        participant_runtime=parts.participant_runtime,
        time_runtime=parts.time_runtime,
        observation_runtime=parts.observation_runtime,
    )
    _require_bound_component(MixedRuntimeComponent(target=target, manifest=admitted, envelope=envelope), declaration)


def test_capture_holds_the_published_contract_in_another_representation() -> None:
    producer = _producer_manifest()

    assert producer != _rebuilt_manifest()
    assert backend_manifest_v2_model(producer) == BackendManifestV2Model.model_validate(_published_payload())


@pytest.mark.parametrize(
    ("target_manifest", "payload"),
    [
        (_producer_manifest, _published_payload),
        (_rebuilt_manifest, _published_payload),
        (_producer_manifest, _payload_in_producer_order),
    ],
    ids=["lilrae-target", "rebuilt-target", "lilrae-target-unsorted-payload"],
)
def test_target_carrying_the_admitted_contract_is_bound(target_manifest, payload) -> None:
    _bind(target_manifest(), payload())


@pytest.mark.parametrize(
    "target_manifest",
    [_narrower_manifest, _changed_envelope_manifest],
    ids=["narrower-operating-systems", "envelope-changed-after-validation"],
)
def test_target_carrying_another_contract_is_refused(target_manifest) -> None:
    with pytest.raises(ValueError, match="mixed runtime target manifest differs from the admitted component"):
        _bind(target_manifest(), _published_payload())

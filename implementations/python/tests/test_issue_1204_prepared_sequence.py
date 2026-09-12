"""Prepared ordered choices must be delivered in the admitted order."""

from copy import deepcopy
from dataclasses import replace

import pytest
import yaml
from raes import instantiate_scenario, parse_sdl
from raes_contracts.realization_observation import RealizationObservationDisclosure
from raes_contracts.realization_preparation import RealizationPreparation
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
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
                    observation_strength=authority.required_observation_strength,
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

"""Prepared first-party records survive negotiated reporting and refresh."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from raes import admit_instantiated_scenario, parse_sdl
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.materialization_inventory import RUNTIME_DESCENDANTS_CONTRACT
from raes_contracts.planning import PlanScope
from raes_contracts.runtime_state import ApplyResult
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_processor.compiler import materialization_differences
from raes_runtime.manager import RuntimeManager
from test_issue_1241_materialization_runtime import ReportingProvisioner
from test_issue_1697_preparation_provenance import _SOURCE, AddingProvisioner, prepared_target


class PreparedReporter(AddingProvisioner):
    def __init__(self, manifest, *, descendants):
        super().__init__(manifest, "{type: compute}")
        self.manifest = manifest
        self.descendants = descendants
        self.sequence = 0
        self.creation = None

    def _describe_prepared(self, document):
        request = self.request
        source = request.materialization_source
        original = admit_instantiated_scenario(json.loads(source.snapshot)["scenario"])
        if self.extra.address in self.live:
            document["nodes"]["capture"] = deepcopy(self.extra.payload["spec"]["node"])
        bindings = document["materialization_provenance"]["resource_bindings"]
        bindings[:] = [binding for binding in bindings if binding["node_name"] == "host"]
        if self.extra.address in self.live:
            bindings.append({"address": self.extra.address, "node_name": "capture", "instance_index": 0})
        if self.descendants:
            self.sequence += 1
            document["materialization_provenance"]["attestation_id"] = f"prepared-{self.sequence}"
            if self.creation is None:
                self.creation = {
                    "run_id": source.run_id,
                    "operation_id": request.operation_id,
                    "attempt_id": request.inventory_attempt_id,
                    "evidence_digest": canonical_json_digest({"created": "leaf"}),
                }
            document["nodes"]["leaf"] = {"type": "compute"}
            bindings.append({"address": "provision.node.leaf", "node_name": "leaf", "instance_index": 0})
            document["materialization_provenance"]["inventory"] = {
                "contract_id": RUNTIME_DESCENDANTS_CONTRACT,
                "attempt_id": request.inventory_attempt_id,
                "sequence": self.sequence,
                "complete": True,
                "scope": "/nodes",
                "source_digest": source.instantiated_digest,
                "run_id": source.run_id,
                "target_scope": source.target_scope,
                "descendants": [
                    {
                        "address": "provision.node.leaf",
                        "parent_address": "provision.node.host",
                        "source_address": "provision.node.host",
                        "state": "active",
                        "native_identity_digest": canonical_json_digest({"native": "leaf"}),
                        "creation": self.creation,
                    }
                ],
                "backend_selections": [],
            }
        document["materialization_provenance"]["origins"] = []
        parsed = parse_sdl(json.dumps(document))
        document["materialization_provenance"]["origins"] = [
            origin.model_dump(mode="json") for origin in materialization_differences(original, parsed)
        ]

    def report(self, request, previous, result):
        self.request = request
        self.live = result.snapshot.entries
        return ReportingProvisioner(self.manifest, self._describe_prepared).report(request, previous, result)

    def apply(self, request, previous):
        return self.report(request, previous, super().apply(request, previous))

    def refresh_inventory(self, request, previous):
        return self.report(request, previous, ApplyResult(True, previous))


@pytest.mark.parametrize("descendants", [False, True])
def test_materialization_retains_first_party_prepared_records_without_descendant_ancestry(tmp_path, descendants):
    target, _ = prepared_target()
    contracts = {"backend-materialization-attestation-v1"}
    if descendants:
        contracts.add(RUNTIME_DESCENDANTS_CONTRACT)
    manifest = replace(
        target.manifest, supported_contract_versions=target.manifest.supported_contract_versions | contracts
    )
    backend = PreparedReporter(manifest, descendants=descendants)
    target = replace(target, manifest=manifest, provisioner=backend)
    archive = RunMaterializationArchive(tmp_path / "archive")
    with RuntimeManager(target, materialization_archive=archive, run_scope="run:reporting") as runtime:
        source = _SOURCE.replace("holder", "host").replace("type: switch", "type: compute")
        execution = runtime.plan(parse_sdl(source), run_scope=PlanScope(run_id="reporting"))
        assert execution.is_valid, execution.diagnostics
        applied = runtime.apply(execution)
        assert applied.success, applied.diagnostics
        expected = {row for row in applied.snapshot.realization_provenance if row.address == backend.extra.address}
        assert {row.requirement_kind for row in expected} >= {"node-type", "compute-substrate"}
        record = applied.snapshot.materialization_attestations[-1]
        assert (tmp_path / "archive" / record.reference.ref_path).is_file()
        bindings = parse_sdl(applied.materialization_attestation.sdl).materialization_provenance.resource_bindings
        binding = next(item for item in bindings if item.address == backend.extra.address)
        assert binding.source_node is None
        if descendants:
            assert {row.address for row in record.inventory.descendants} == {"provision.node.leaf"}
            assert any(row.address == "provision.node.leaf" for row in applied.snapshot.realization_provenance)
            refreshed = runtime.refresh_inventory(execution)
            assert refreshed.success, refreshed.diagnostics
            assert expected <= set(refreshed.snapshot.realization_provenance)
            from raes_contracts.planning import ChangeAction

            backend.extra = replace(backend.extra, action=ChangeAction.DELETE)
            next_plan = runtime.plan(parse_sdl(source), run_scope=PlanScope(run_id="reporting"))
            removed = runtime.apply(next_plan)
            assert removed.success, removed.diagnostics
            assert backend.extra.address not in removed.snapshot.entries
            assert not any(row.address == backend.extra.address for row in removed.snapshot.realization_provenance)

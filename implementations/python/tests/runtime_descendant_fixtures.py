"""A native producer reporting SDL without writing runtime-owned inventory."""

import json
from copy import deepcopy
from dataclasses import replace

from raes import admit_instantiated_scenario, parse_sdl
from raes_backend_stubs.stubs import StubProvisioner
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.planning import PlanScope
from raes_contracts.runtime_state import ApplyResult
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_processor.compiler import materialization_differences
from raes_runtime import RuntimeManager
from raes_runtime.registry import RuntimeTarget
from test_issue_1241_materialization_context import attesting_plan
from test_issue_1241_materialization_runtime import ReportingProvisioner

CONTRACT = "backend-runtime-descendants-v1"
ROOT = "provision.node.host"


class DescendantBackend:
    def __init__(self, manifest):
        self.manifest = manifest
        self.members = {"worker": ROOT, "leaf": "provision.node.worker"}
        self.states = {}
        self.selections = []
        self.node_values = {}
        self.observe_host_os = False
        self.records = {}
        self.sequence = 0
        self.applies = 0
        self.refreshes = 0
        self.mutate = None
        self.last_report = None

    def validate(self, request):
        return []

    def prepare_augmentation(self, request, previous):
        from raes.prospective_content import admit_prospective_content
        from raes_backend_protocols.augmentation import augmentation_preparation
        from raes_contracts.augmentation_preparation import AugmentationEffect

        original = admit_instantiated_scenario(json.loads(request.materialization_source.snapshot)["scenario"])
        document = json.loads(request.materialization_source.snapshot)["scenario"]
        document.pop("instantiation_provenance")
        for name in self.members:
            document["nodes"][name] = self.node_values.get(name, {"type": "compute"})
        prospective = admit_prospective_content(document)
        return augmentation_preparation(
            request,
            self.manifest,
            previous,
            content=json.dumps(document),
            effects=tuple(
                AugmentationEffect(
                    field_pointer=origin.field_pointer,
                    requirement_refs=("backend-operational",),
                    affected_scopes=(origin.field_pointer,),
                )
                for origin in materialization_differences(original, prospective)
            ),
        )

    def apply(self, request, previous):
        self.applies += 1
        result = StubProvisioner(self.manifest.realization_envelope).apply(request, previous)
        if request.materialization_source is None:
            return result
        if self.observe_host_os:
            from raes_contracts.realization_observation import (
                ObservedOperatingSystemIdentity,
                RealizationObservationDisclosure,
            )
            from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope

            observation = RealizationObservationDisclosure(
                address=ROOT,
                field_path="nodes.host.operating-system",
                domain="runtime-realization",
                requirement_kind="operating-system",
                verification_scope=RealizationVerificationScope.PRESENCE,
                observation_strength=ObservationStrength.GUEST_OBSERVED,
                operating_system=ObservedOperatingSystemIdentity(
                    family="linux", distribution="ubuntu", version="22.04"
                ),
                operation_id=request.operation_id,
                envelope_digest=request.realization_envelope.digest,
                configuration_digest=request.realization_envelope.configuration_digest,
                observer_version="test-guest-os/v1",
                sequence=1,
                binding_verified=True,
            )
            result = replace(
                result,
                snapshot=result.snapshot.with_entries(
                    dict(result.snapshot.entries),
                    realization_observations=(observation,),
                ),
            )
        return self.report(request, previous, result)

    def refresh_inventory(self, request, previous):
        self.refreshes += 1
        return self.report(request, previous, ApplyResult(True, previous))

    def report(self, request, previous, result):
        from raes_contracts.materialization import MaterializationSubmission

        self.last_request = request
        source = request.materialization_source
        original = admit_instantiated_scenario(json.loads(source.snapshot)["scenario"])
        document = json.loads(
            ReportingProvisioner(self.manifest).report(request, previous, result).materialization_attestation.sdl
        )
        document["materialization_provenance"]["resource_bindings"] = [
            {
                "address": resource.address,
                "node_name": resource.payload["name"],
                "source_node": resource.payload["name"],
                "instance_index": index,
            }
            for resource in request.operations
            if resource.resource_type in {"node", "network"} and resource.action != "delete"
            for index in range(resource.payload.get("count") or 1)
        ]
        self.sequence += 1
        for name, parent in self.members.items():
            address = f"provision.node.{name}"
            if address not in self.records:
                self.records[address] = {
                    "address": address,
                    "parent_address": parent,
                    "source_address": ROOT,
                    "native_identity_digest": canonical_json_digest({"native": name, "incarnation": 1}),
                    "creation": {
                        "run_id": source.run_id,
                        "operation_id": request.operation_id,
                        "attempt_id": request.inventory_attempt_id,
                        "evidence_digest": canonical_json_digest({"created": name}),
                    },
                    "state": "active",
                }
        for address, record in self.records.items():
            name = address.removeprefix("provision.node.")
            state = self.states.get(name, record["state"])
            if state != record["state"]:
                record["state"] = state
                record["lifecycle"] = {
                    "run_id": source.run_id,
                    "operation_id": request.operation_id,
                    "attempt_id": request.inventory_attempt_id,
                    "evidence_digest": canonical_json_digest({"state": state, "address": address}),
                }
            if record["state"] == "autoremoved":
                continue
            document["nodes"][name] = self.node_values.get(name, {"type": "compute"})
            document["materialization_provenance"]["resource_bindings"].append(
                {"address": address, "node_name": name, "instance_index": 0}
            )
        document["materialization_provenance"]["attestation_id"] = f"inventory-{self.sequence}"
        document["materialization_provenance"]["inventory"] = {
            "contract_id": CONTRACT,
            "attempt_id": request.inventory_attempt_id,
            "sequence": self.sequence,
            "complete": True,
            "scope": "/nodes",
            "source_digest": source.instantiated_digest,
            "run_id": source.run_id,
            "target_scope": source.target_scope,
            "descendants": deepcopy(list(self.records.values())),
            "backend_selections": self.selections,
        }
        parsed = parse_sdl(
            json.dumps(
                {
                    **document,
                    "materialization_provenance": {
                        **document["materialization_provenance"],
                        "origins": [],
                    },
                }
            )
        )
        document["materialization_provenance"]["origins"] = [
            origin.model_dump(mode="json") for origin in materialization_differences(original, parsed)
        ]
        if self.mutate is not None:
            self.mutate(document)
        self.last_report = deepcopy(document)
        return replace(result, materialization_attestation=MaterializationSubmission(sdl=json.dumps(document)))


def descendant_runtime(tmp_path, source=None, *, augmentation=None):
    execution, _ = attesting_plan()
    manifest = replace(
        execution.manifest, supported_contract_versions=execution.manifest.supported_contract_versions | {CONTRACT}
    )
    if augmentation is not None:
        manifest = replace(
            manifest,
            supported_contract_versions=manifest.supported_contract_versions | {"backend-augmentation-scope-v1"},
        )
    backend = DescendantBackend(manifest)
    target = RuntimeTarget(name="descendants", manifest=manifest, provisioner=backend)
    archive = RunMaterializationArchive(tmp_path / "archive")
    manager = RuntimeManager(target, materialization_archive=archive, run_scope="run:run-1")
    source = source or (
        "name: dynamic\nrealization:\n  default: open\n  scopes:\n"
        "    - {field_pointer: /nodes/host/runtime, posture: closed}\n"
        "nodes:\n  host: {type: compute}"
    )
    if augmentation is not None:
        import yaml

        source = json.dumps({**yaml.safe_load(source), "augmentation_scope": augmentation})
    plan = manager.plan(
        parse_sdl(source),
        run_scope=PlanScope(run_id="run-1"),
    )
    assert plan.is_valid, plan.diagnostics
    return manager, backend, plan, target, archive

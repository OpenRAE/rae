"""Bounded synthetic cloud inventory and in-memory preparation for issue #1885."""

import json
from copy import deepcopy
from dataclasses import replace

from cloud_resource_fixtures import authority, cloud_scenario, secret
from raes import parse_sdl
from raes_backend_stubs.manifest import load_stub_realization_envelope
from raes_backend_stubs.stubs import StubProvisioner, create_stub_manifest
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.contracts.backend_preparation import preparation_response_model
from raes_contracts.contracts.realization_preparation import RealizationPreparation
from raes_contracts.planning import BACKEND_PREPARATION_CONTRACT
from raes_contracts.runtime_state import RealizationObservationDisclosure, RuntimeSnapshot
from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext

CLOUD_KINDS = frozenset({"runtime-identity-authorities", "runtime-platform-applications"})


def inventory_source(count=500):
    raw = cloud_scenario()
    identity = authority(raw)
    identity["access_observations"] = []
    identity["resource_scopes"][0]["native_id"] = "synthetic-project"
    identity["subjects"].append(
        {"subject_id": "secret-reader-role", "kind": "role", "name": "roles/secretmanager.secretAccessor"}
    )
    identity["subjects"].append({"subject_id": "admin-role", "kind": "role", "name": "roles/owner"})
    identity["policies"][0]["resource_access"]["bindings"][0]["role_ref"] = (
        "nodes.iam.runtime.identity_authorities.cloud.subjects.secret-reader-role"
    )
    raw["content"] = {"fixture": {"type": "file", "target": "worker", "path": "/fixture", "text": "synthetic"}}
    raw["content"]["alternative"] = {"type": "file", "target": "worker", "path": "/alternative", "text": "other"}
    template = secret(raw)
    raw["nodes"]["secrets"]["runtime"]["platform_applications"][0]["secrets"] = [
        {
            **template,
            "secret_id": "database" if index == 0 else f"secret-{index}",
            "native_id": f"secret-{index}",
            "replication": {"provider": "gcp-secret-manager", "mode": "automatic"},
            "versions": [
                {"version_id": "v1", "native_id": "1", "state": "enabled", "payload_content_ref": "content.fixture"}
            ],
            "consumers": [],
        }
        for index in range(count)
    ]
    return raw


def inventory_plan(count=500, *, source=None):
    model = compile_runtime_model(parse_sdl(json.dumps(inventory_source(count) if source is None else source)))
    manifest = create_stub_manifest(with_realization_envelope=True)
    capability = RealizationObservationCapability(
        verification_scope=RealizationVerificationScope.CONFIGURATION,
        observation_strength=ObservationStrength.DAEMON_OBSERVED,
    )
    manifest = replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions | {BACKEND_PREPARATION_CONTRACT},
        realization_support=tuple(
            replace(
                declaration,
                supported_exact_requirement_kinds=declaration.supported_exact_requirement_kinds | CLOUD_KINDS,
                supported_constraint_kinds=declaration.supported_constraint_kinds | CLOUD_KINDS,
                observation_capabilities={
                    **declaration.observation_capabilities,
                    **dict.fromkeys(CLOUD_KINDS, capability),
                },
            )
            if declaration.domain == "runtime-realization"
            else declaration
            for declaration in manifest.realization_support
        ),
    )
    return plan(model, manifest), manifest


def cloud_value(operations, kind):
    node, field = ("iam", "identity_authorities") if kind == "iam" else ("secrets", "platform_applications")
    operation = next(item for item in operations if item.address == f"provision.node.{node}")
    return operation.payload["spec"]["node"]["runtime"][field][0]


def alter_inventory(operations, field):
    iam = cloud_value(operations, "iam")
    binding = iam["policies"][0]["resource_access"]["bindings"][0]
    version = cloud_value(operations, "secrets")["secrets"][-1]["versions"][0]
    if field == "role":
        binding["role_ref"] = "nodes.iam.runtime.identity_authorities.cloud.subjects.admin-role"
    elif field == "subject":
        binding["principal_refs"] = ["nodes.iam.runtime.identity_authorities.cloud.subjects.secret-reader-role"]
    elif field == "id":
        cloud_value(operations, "secrets")["secrets"][-1]["native_id"] = "changed-native-id"
    elif field == "payload":
        version["payload_content_ref"] = "content.alternative"
    else:
        raise ValueError("unknown test mutation")


class CloudPreparingProvisioner(StubProvisioner):
    def __init__(self, *, preparation_change=None, delivery_change=None):
        super().__init__(load_stub_realization_envelope())
        self.preparation_change = preparation_change
        self.delivery_change = delivery_change
        self.applies = 0

    def prepare(self, request, previous):
        operations = deepcopy(request.operations)
        if self.preparation_change is not None:
            alter_inventory(operations, self.preparation_change)
        response = RealizationPreparation.for_request(request, previous, operations=tuple(operations))
        return preparation_response_model(response).to_runtime()

    def apply(self, selected, previous):
        self.applies += 1
        result = super().apply(selected, previous)
        observations = tuple(
            RealizationObservationDisclosure(
                address=item.address,
                field_path=item.field_path,
                domain=item.domain,
                requirement_kind=item.requirement_kind,
                verification_scope=RealizationVerificationScope.CONFIGURATION,
                observation_strength=ObservationStrength.DAEMON_OBSERVED,
            )
            for item in selected.realization_authority
            if item.requirement_kind in CLOUD_KINDS
        )
        if self.delivery_change is not None:
            alter_inventory(list(result.snapshot.entries.values()), self.delivery_change)
        return replace(result, snapshot=replace(result.snapshot, realization_observations=observations))


def apply_inventory(request, manifest, backend):
    previous = RuntimeSnapshot(metadata={"trusted": "predecessor"})
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        address="runtime.test.cloud-budget",
        snapshot=previous,
        realization=_RealizationApplyContext(plan=deepcopy(request), manifest=manifest),
    )
    return previous, result

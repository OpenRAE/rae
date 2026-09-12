"""Authored software refinements reach generic preparation and effect gates."""

from copy import deepcopy
from dataclasses import replace

import pytest
import yaml
from raes import parse_sdl
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.domain_profiles import (
    DomainProfileBindingProvenanceModel,
    DomainProfileOperation,
    draft_domain_profile_definition,
    seal_domain_profile_definition,
)
from raes_contracts.realization_preparation import RealizationPreparation
from raes_contracts.realization_profiles import profile_context_digest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from test_issue_1200_mixed_runtime_constraints import _fixture, _returned
from test_issue_1202_domain_profiles import _context, _definition, _support


def _definition_for(context):
    initial = _definition(
        namespace="com.example.private", authority="urn:example:software", profile_id="correspondence"
    )
    return seal_domain_profile_definition(
        draft_domain_profile_definition(
            namespace=initial.coordinate.namespace,
            authority=initial.coordinate.authority,
            profile_id=initial.coordinate.profile_id,
            revision=initial.coordinate.revision,
            schema=initial.profile_schema,
            semantic_contract=initial.semantic_contract,
            allowed_contexts=(context,),
        )
    )


class _CorrespondenceBackend:
    """Installed fixture semantics, not a loader or an installation implementation."""

    def __init__(self, context, *, package_version):
        self.domain_profile_context = context
        self.package_version = package_version
        self.applies = 0
        self.validations = 0

    def prepare(self, request, snapshot):
        operations = deepcopy(request.operations)
        binding = request.profile_authority.bindings[0].model_copy(
            update={
                "provenance": DomainProfileBindingProvenanceModel(
                    basis="backend-selected", source_ref="urn:example:installed-selection"
                ),
            }
        )
        for operation in operations:
            component = operation.payload["spec"]["node"]["runtime"]["software_components"][0]
            component.update(version="1.2.0", package_version=self.package_version)
        operations = tuple(replace(operation, profile_bindings=(binding,)) for operation in operations)
        return RealizationPreparation.for_request(request, snapshot, operations=operations)

    def validate(self, selected):
        return []

    def validate_profiles(self, selected):
        self.validations += 1
        component = selected.operations[0].payload["spec"]["node"]["runtime"]["software_components"][0]
        suffix = selected.operations[0].profile_bindings[0].value["name"]
        if component["package_version"] == component["version"] + suffix:
            return []
        return [
            Diagnostic(
                "test.correspondence-mismatch",
                "runtime-realization",
                "provision.node.host",
                "Selected application and package versions violate the installed relation.",
                severity=Severity.ERROR,
            )
        ]

    def apply(self, selected, snapshot):
        self.applies += 1
        returned = _returned(selected, selected.operations[0].payload["spec"]["node"]["runtime"])
        returned.metadata = deepcopy(snapshot.metadata)
        entries = {
            operation.address: replace(returned.entries[operation.address], profile_bindings=operation.profile_bindings)
            for operation in selected.operations
        }
        return ApplyResult(True, returned.with_entries(entries), changed_addresses=list(entries))


@pytest.mark.parametrize("package_version,accepted", [("1.2.0-r1", True), ("1.2.0", False), ("9.0-r1", False)])
def test_profile_owned_version_correspondence_is_checked_before_effects(package_version, accepted):
    definition = _definition_for("software-version-correspondence")
    component = {
        "component_id": "tool",
        "name": "tool",
        "refinements": [
            {
                "refinement_id": "version-link",
                "purpose": "version-correspondence",
                "definition": definition.model_dump(mode="json"),
                "profile_value": {"name": "-r1"},
            }
        ],
    }
    source = {
        "name": "joint-software",
        "realization": {
            "default": "closed",
            "scopes": [{"field_pointer": "/nodes/host/runtime/software_components", "posture": "open"}],
        },
        "nodes": {"host": {"type": "compute", "runtime": {"software_components": [component]}}},
    }
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(source)))
    context = _context(definition, support_declarations=(_support(definition, *DomainProfileOperation),))
    _, _, base = _fixture({"software_components": [{"component_id": "tool", "name": "tool"}]})
    manifest = replace(
        base,
        supported_contract_versions=base.supported_contract_versions
        | {"plan-realization-profiles-v1", "backend-realization-preparation-v1"},
        domain_profile_context_digest=profile_context_digest(context),
    )
    execution = plan(model, manifest, profile_context=context)
    assert execution.is_valid, execution.diagnostics
    backend = _CorrespondenceBackend(context, package_version=package_version)
    previous = RuntimeSnapshot(metadata={"trusted": "predecessor"})
    request = execution.provisioning
    result = _call_backend_apply(
        backend.apply,
        request,
        previous,
        snapshot=previous,
        address="runtime.test.software",
        realization=_RealizationApplyContext(plan=request, manifest=manifest),
    )
    assert result.success is accepted, result.diagnostics
    assert backend.validations > 0
    assert backend.applies == int(accepted)
    if not accepted:
        assert result.snapshot == previous
        assert result.changed_addresses == []

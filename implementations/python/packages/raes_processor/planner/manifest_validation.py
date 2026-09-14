"""Backend-manifest capability validation for compiled runtime models."""

from raes_backend_protocols.capabilities import (
    BackendManifest,
    EvaluatorCapabilities,
    OrchestratorCapabilities,
    ProvisionerCapabilities,
)

from ..models import Diagnostic, PropositionRuntime, RuntimeModel
from .capability_domains import (
    _account_features,
    _resource_count_upper_bound,
    _validate_node_architecture,
    _validate_node_os_family,
)
from .operating_system_capability_domains import validate_node_operating_system
from .stateful_admission import generated_artifact_payload_diagnostic

_ORCHESTRATION_WORKFLOWS_ADDRESS = "orchestration.workflows"


def _validate_acls(model: RuntimeModel, provisioner: ProvisionerCapabilities) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for resource in [*model.networks.values(), *model.node_deployments.values()]:
        if resource.spec.get("infrastructure", {}).get("acls") and not provisioner.supports_acls:
            diagnostics.append(
                Diagnostic(
                    code="provisioner.acls-unsupported",
                    domain="provisioning",
                    address=resource.address,
                    message="Provisioner does not support ACL declarations.",
                )
            )
    return diagnostics


def _validate_switch_support(model: RuntimeModel, provisioner: ProvisionerCapabilities) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for network in model.networks.values():
        if "switch" not in provisioner.supported_node_types:
            diagnostics.append(
                Diagnostic(
                    code="provisioner.unsupported-node-type",
                    domain="provisioning",
                    address=network.address,
                    message="Provisioner does not support switch/network nodes.",
                )
            )
    return diagnostics


def _validate_node_kind_support(model: RuntimeModel, provisioner: ProvisionerCapabilities) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for node in model.node_deployments.values():
        if node.node_kind and node.node_kind not in provisioner.supported_node_types:
            diagnostics.append(
                Diagnostic(
                    code="provisioner.unsupported-node-type",
                    domain="provisioning",
                    address=node.address,
                    message=f"Provisioner does not support node kind '{node.node_kind}'.",
                )
            )
        diagnostics.extend(
            _validate_node_os_family(
                model,
                node,
                provisioner.supported_os_families,
            )
        )
        diagnostics.extend(validate_node_operating_system(model, node, provisioner))
        diagnostics.extend(
            _validate_node_architecture(
                model,
                node,
                provisioner.supported_node_architectures,
            )
        )
    return diagnostics


def _validate_total_node_count(model: RuntimeModel, provisioner: ProvisionerCapabilities) -> list[Diagnostic]:
    if provisioner.max_total_nodes is None:
        return []

    diagnostics: list[Diagnostic] = []
    total_nodes = 0
    for resource in [*model.networks.values(), *model.node_deployments.values()]:
        count_upper_bound, warning = _resource_count_upper_bound(model, resource)
        if warning is not None:
            diagnostics.append(warning)
        if count_upper_bound is not None:
            total_nodes += count_upper_bound

    if total_nodes > provisioner.max_total_nodes:
        diagnostics.append(
            Diagnostic(
                code="provisioner.max-total-nodes-exceeded",
                domain="provisioning",
                address="provision",
                message=(
                    f"Scenario requires {total_nodes} deployable nodes/networks, "
                    f"but provisioner maximum is {provisioner.max_total_nodes}."
                ),
            )
        )
    return diagnostics


def _validate_content_type_support(model: RuntimeModel, provisioner: ProvisionerCapabilities) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for content in model.content_placements.values():
        content_type = str(content.spec.get("type", ""))
        if content_type and content_type not in provisioner.supported_content_types:
            diagnostics.append(
                Diagnostic(
                    code="provisioner.unsupported-content-type",
                    domain="provisioning",
                    address=content.address,
                    message=f"Provisioner does not support content type '{content_type}'.",
                )
            )
    return diagnostics


def _validate_account_support(model: RuntimeModel, provisioner: ProvisionerCapabilities) -> list[Diagnostic]:
    if model.account_placements and not provisioner.supports_accounts:
        return [
            Diagnostic(
                code="provisioner.accounts-unsupported",
                domain="provisioning",
                address="provision.accounts",
                message="Provisioner does not support accounts.",
            )
        ]

    diagnostics: list[Diagnostic] = []
    if provisioner.supports_accounts:
        for account in model.account_placements.values():
            for feature in sorted(_account_features(account.spec)):
                if feature not in provisioner.supported_account_features:
                    diagnostics.append(
                        Diagnostic(
                            code="provisioner.unsupported-account-feature",
                            domain="provisioning",
                            address=account.address,
                            message=f"Provisioner does not support account feature '{feature}'.",
                        )
                    )
    return diagnostics


def _validate_artifact_and_volume_support(
    model: RuntimeModel, provisioner: ProvisionerCapabilities
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if model.generated_artifacts and not provisioner.supports_generated_artifacts:
        diagnostics.append(
            Diagnostic(
                code="provisioner.generated-artifacts-unsupported",
                domain="provisioning",
                address="provision.generated-artifacts",
                message="Provisioner does not support generated artifacts.",
            )
        )
    elif model.generated_artifacts:
        content_specs = {placement.address: {"spec": placement.spec} for placement in model.content_placements.values()}
        for artifact in model.generated_artifacts.values():
            diagnostic = generated_artifact_payload_diagnostic(
                address=artifact.address,
                spec=artifact.spec,
                provisioner=provisioner,
                node_specs={address: node.spec for address, node in model.node_deployments.items()},
                content_specs=content_specs,
            )
            if diagnostic is not None:
                diagnostics.append(diagnostic)
    if model.persistent_volumes and not provisioner.supports_persistent_volumes:
        diagnostics.append(
            Diagnostic(
                code="provisioner.persistent-volumes-unsupported",
                domain="provisioning",
                address="provision.persistent-volumes",
                message="Provisioner does not support persistent volumes.",
            )
        )
    return diagnostics


def _orchestrator_section_support(
    orchestration_sections: dict[str, bool], orchestrator: OrchestratorCapabilities
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for section, used in orchestration_sections.items():
        if used and section not in orchestrator.supported_sections:
            diagnostics.append(
                Diagnostic(
                    code="orchestrator.unsupported-section",
                    domain="orchestration",
                    address=f"orchestration.{section}",
                    message=f"Orchestrator does not support '{section}'.",
                )
            )
    return diagnostics


def _orchestrator_workflow_support(model: RuntimeModel, orchestrator: OrchestratorCapabilities) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if model.workflows and not orchestrator.supports_workflows:
        diagnostics.append(
            Diagnostic(
                code="orchestrator.workflows-unsupported",
                domain="orchestration",
                address=_ORCHESTRATION_WORKFLOWS_ADDRESS,
                message="Orchestrator does not support workflows.",
            )
        )
    workflow_features = sorted(
        {feature for workflow in model.workflows.values() for feature in workflow.required_features},
        key=lambda feature: feature.value,
    )
    for feature in workflow_features:
        if feature in orchestrator.supported_workflow_features:
            continue
        diagnostics.append(
            Diagnostic(
                code="orchestrator.workflow-feature-unsupported",
                domain="orchestration",
                address=_ORCHESTRATION_WORKFLOWS_ADDRESS,
                message=(f"Orchestrator does not support workflow feature '{feature.value}'."),
            )
        )
    return diagnostics


def _orchestrator_assertion_ref_support(
    model: RuntimeModel, orchestrator: OrchestratorCapabilities
) -> list[Diagnostic]:
    orchestration_uses_assertion_refs = any(event.assertion_addresses for event in model.events.values()) or any(
        addresses for workflow in model.workflows.values() for addresses in workflow.step_assertion_addresses.values()
    )
    if orchestration_uses_assertion_refs and not orchestrator.supports_assertion_refs:
        return [
            Diagnostic(
                code="orchestrator.assertion-refs-unsupported",
                domain="orchestration",
                address="orchestration.assertion-refs",
                message=("Orchestrator does not support assertion-gated events or workflow predicates."),
            )
        ]
    return []


def _orchestrator_state_predicate_support(
    model: RuntimeModel, orchestrator: OrchestratorCapabilities
) -> list[Diagnostic]:
    required_state_predicate_features = sorted(
        {feature for workflow in model.workflows.values() for feature in workflow.required_state_predicate_features},
        key=lambda feature: feature.value,
    )
    diagnostics: list[Diagnostic] = []
    for feature in required_state_predicate_features:
        if feature in orchestrator.supported_workflow_state_predicates:
            continue
        diagnostics.append(
            Diagnostic(
                code="orchestrator.step-state-predicate-feature-unsupported",
                domain="orchestration",
                address=_ORCHESTRATION_WORKFLOWS_ADDRESS,
                message=(f"Orchestrator does not support workflow state predicate feature '{feature.value}'."),
            )
        )
    return diagnostics


def _orchestrator_inject_binding_support(
    model: RuntimeModel, orchestrator: OrchestratorCapabilities
) -> list[Diagnostic]:
    if model.inject_bindings and not orchestrator.supports_inject_bindings:
        return [
            Diagnostic(
                code="orchestrator.inject-bindings-unsupported",
                domain="orchestration",
                address="orchestration.injects",
                message="Orchestrator does not support node-bound injects.",
            )
        ]
    return []


def _validate_orchestration_support(model: RuntimeModel, manifest: BackendManifest) -> list[Diagnostic]:
    orchestration_sections = {
        "injects": bool(model.injects or model.inject_bindings),
        "events": bool(model.events),
        "scripts": bool(model.scripts),
        "stories": bool(model.stories),
        "workflows": bool(model.workflows),
    }
    if not any(orchestration_sections.values()):
        return []

    orchestrator = manifest.orchestrator
    if orchestrator is None:
        return [
            Diagnostic(
                code="orchestrator.missing",
                domain="orchestration",
                address="orchestration",
                message="Scenario requires orchestration support, but no orchestrator is configured.",
            )
        ]

    diagnostics: list[Diagnostic] = []
    diagnostics.extend(_orchestrator_section_support(orchestration_sections, orchestrator))
    diagnostics.extend(_orchestrator_workflow_support(model, orchestrator))
    diagnostics.extend(_orchestrator_assertion_ref_support(model, orchestrator))
    diagnostics.extend(_orchestrator_state_predicate_support(model, orchestrator))
    diagnostics.extend(_orchestrator_inject_binding_support(model, orchestrator))
    return diagnostics


def _evaluator_section_support(
    evaluation_sections: dict[str, bool], supported_sections: frozenset[str]
) -> list[Diagnostic]:
    return [
        Diagnostic(
            code="evaluator.unsupported-section",
            domain="evaluation",
            address=f"evaluation.{section}",
            message=f"Evaluator does not support '{section}'.",
        )
        for section, used in evaluation_sections.items()
        if used and section not in supported_sections
    ]


def _proposition_evaluator_support(
    proposition: PropositionRuntime, evaluator: EvaluatorCapabilities
) -> list[Diagnostic]:
    predicate_spec = proposition.spec.get("predicate", {}) if isinstance(proposition.spec, dict) else {}
    # Order-preserving check table: emitted before the evidence-channel loop and
    # the trailing time-domain check so diagnostic ordering matches admission.
    scalar_checks = (
        (
            proposition.predicate_kind not in evaluator.supported_predicate_families,
            "evaluator.unsupported-predicate-family",
            f"Evaluator does not support proposition predicate family '{proposition.predicate_kind}'.",
        ),
        (
            predicate_spec.get("expected_from") is not None and not evaluator.supports_deferred_expected_comparison,
            "evaluator.unsupported-deferred-expected-comparison",
            "Evaluator does not support comparing a submission against a deferred generated value.",
        ),
        (
            proposition.quantifier not in evaluator.supported_quantifiers,
            "evaluator.unsupported-quantifier",
            f"Evaluator does not support proposition quantifier '{proposition.quantifier}'.",
        ),
        (
            bool(proposition.unresolved_evidence_channel_refs),
            "evaluator.evidence-channel-unresolved",
            "Evaluator admission requires every cited evidence requirement to declare a channel kind.",
        ),
    )
    diagnostics = [
        Diagnostic(code=code, domain="evaluation", address=proposition.address, message=message)
        for failed, code, message in scalar_checks
        if failed
    ]
    diagnostics.extend(
        Diagnostic(
            code="evaluator.unsupported-evidence-channel",
            domain="evaluation",
            address=proposition.address,
            message=f"Evaluator does not support evidence channel '{channel}'.",
        )
        for channel in proposition.evidence_channels
        if channel not in evaluator.supported_evidence_channels
    )
    if proposition.required_time_domain and proposition.required_time_domain not in evaluator.supported_time_domains:
        diagnostics.append(
            Diagnostic(
                code="evaluator.unsupported-time-domain",
                domain="evaluation",
                address=proposition.address,
                message=f"Evaluator does not support proposition time domain '{proposition.required_time_domain}'.",
            )
        )
    return diagnostics


def _evaluator_proposition_support(model: RuntimeModel, evaluator: EvaluatorCapabilities) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for proposition in model.propositions.values():
        diagnostics.extend(_proposition_evaluator_support(proposition, evaluator))
    return diagnostics


def _validate_evaluation_support(model: RuntimeModel, manifest: BackendManifest) -> list[Diagnostic]:
    evaluation_sections = {
        "conditions": bool(model.condition_bindings),
        "propositions": bool(model.propositions),
        "assertions": bool(model.assertions),
        "objectives": bool(model.objectives),
    }
    if not any(evaluation_sections.values()):
        return []

    if not manifest.has_evaluator:
        return [
            Diagnostic(
                code="evaluator.missing",
                domain="evaluation",
                address="evaluation",
                message="Scenario requires evaluation support, but no evaluator is configured.",
            )
        ]

    evaluator = manifest.evaluator
    assert evaluator is not None
    supported_sections = manifest.evaluator_supported_sections
    diagnostics = _evaluator_section_support(evaluation_sections, supported_sections)
    if model.objectives and not manifest.supports_objectives:
        diagnostics.append(
            Diagnostic(
                code="evaluator.objectives-unsupported",
                domain="evaluation",
                address="evaluation.objectives",
                message="Evaluator does not support objectives.",
            )
        )
    if "propositions" in supported_sections:
        diagnostics.extend(_evaluator_proposition_support(model, evaluator))
    return diagnostics


def _validate_manifest(model: RuntimeModel, manifest: BackendManifest) -> list[Diagnostic]:
    provisioner = manifest.provisioner
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(_validate_acls(model, provisioner))
    diagnostics.extend(_validate_switch_support(model, provisioner))
    diagnostics.extend(_validate_node_kind_support(model, provisioner))
    diagnostics.extend(_validate_total_node_count(model, provisioner))
    diagnostics.extend(_validate_content_type_support(model, provisioner))
    diagnostics.extend(_validate_account_support(model, provisioner))
    diagnostics.extend(_validate_artifact_and_volume_support(model, provisioner))
    diagnostics.extend(_validate_orchestration_support(model, manifest))
    diagnostics.extend(_validate_evaluation_support(model, manifest))
    return diagnostics

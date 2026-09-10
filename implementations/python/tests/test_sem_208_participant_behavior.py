"""SEM-208/209/210 participant behavior, interaction, and visibility tests."""

from __future__ import annotations

import textwrap

import pytest
from jsonschema import Draft202012Validator
from raes._declarations import build_declaration_index
from raes._errors import SDLInstantiationError, SDLParseError, SDLValidationError
from raes.instantiate import instantiate_scenario
from raes.parser import parse_sdl, parse_sdl_file
from raes.participant_behavior import ParticipantInteractionClass
from raes_contracts.contracts import schema_bundle
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import (
    ParticipantBehaviorHistoryEvent,
    ParticipantBehaviorHistoryEventType,
    ParticipantHistoryAddressScope,
    ParticipantObservationBoundaryRuntime,
    ParticipantObservationStatus,
    iter_participant_behavior_history_violations,
)

T0 = "2026-05-18T18:30:00Z"
T1 = "2026-05-18T18:30:05Z"
T2 = "2026-05-18T18:30:10Z"
T3 = "2026-05-18T18:30:15Z"
PARTICIPANT_ADDRESS = "participant.behavior.red-agent"
ACTION_ADDRESS = "participant.action-contract.scan"
OBSERVATION_ADDRESS = "participant.observation-boundary.red-view"
AFFORDANCE_ADDRESS = "participant.behavior-specification.red-scan-behavior.tool-affordance.network-scanner"
ACTION_INSTANCE = "scan-0001"
POST_STATE_DIGEST = "sha256:fb2f5a36c0d7d2a0"


def _complete_behavior_history_payloads(
    action_instance_id: str,
    *,
    realized_order: int | None = None,
    participant_address: str = PARTICIPANT_ADDRESS,
) -> list[dict[str, object]]:
    action_kwargs = {}
    if realized_order is not None:
        action_kwargs = {
            "joint_action_set_id": "joint-0001",
            "realized_order": realized_order,
            "interaction_class": ParticipantInteractionClass.SHARED_STATE_CHANGE,
            "shared_state_refs": ("nodes.web.services.http",),
        }
    action = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
        timestamp=T0,
        participant_address=participant_address,
        episode_id="episode-1",
        action_instance_id=action_instance_id,
        action_contract_address=ACTION_ADDRESS,
        actor_provenance=f"participant:{participant_address.rsplit('.', 1)[-1]}",
        **action_kwargs,
    )
    transition = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.STATE_TRANSITION_RECORDED,
        timestamp=T1,
        participant_address=participant_address,
        episode_id="episode-1",
        action_instance_id=action_instance_id,
        action_contract_address=ACTION_ADDRESS,
        state_transition_kind="participant_knowledge_expanded",
        post_state_digest=POST_STATE_DIGEST,
    )
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T2,
        participant_address=participant_address,
        episode_id="episode-1",
        action_instance_id=action_instance_id,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.TERMINAL,
        post_state_digest=POST_STATE_DIGEST,
    )
    return [action.to_payload(), transition.to_payload(), observation.to_payload()]


def _completed_episode_history_payloads(
    *,
    participant_address: str = PARTICIPANT_ADDRESS,
    episode_id: str = "episode-1",
) -> list[dict[str, object]]:
    return [
        {
            "event_type": "episode_initialized",
            "timestamp": T0,
            "participant_address": participant_address,
            "episode_id": episode_id,
            "sequence_number": 0,
            "terminal_reason": None,
            "control_action": "initialize",
            "details": {},
        },
        {
            "event_type": "episode_completed",
            "timestamp": T3,
            "participant_address": participant_address,
            "episode_id": episode_id,
            "sequence_number": 0,
            "terminal_reason": "completed",
            "control_action": None,
            "details": {},
        },
    ]


def _scenario_yaml(*, actions: str = "[scan]", boundaries: str = "[red-view]") -> str:
    return textwrap.dedent(
        f"""
        name: sem-208
        nodes:
          web:
            type: compute
            resources: {{ram: 1 GiB, cpu: 1}}
            services: [{{port: 80, name: http}}]
        entities:
          red-team:
            role: red
        action_contracts:
          scan:
            semantic_version: 1.0.0
            lifecycle_state: active
            behavioral_granularity: atomic
            procedure_basis: nmap service discovery
            realization_profile: backend-declared
            fidelity_claim: records participant discovery intent and terminal observation
            preconditions:
              - precondition_id: authority-in-scope
                precondition_class: authority
                description: red participant is authorized to scan the web service
                support_refs: [agents.red-agent, nodes.web.services.http]
              - precondition_id: target-service-present
                precondition_class: target
                description: target service exists in the participant action scope
                support_refs: [nodes.web.services.http]
              - precondition_id: backend-can-realize-scan
                precondition_class: realization
                description: backend can realize the scan action contract
                support_refs: [backend.participant-runtime]
            effects:
              - effect_id: discover-network-services
                effect_class: intended_effect
                description: discover network services
                target_refs: [nodes.web.services.http]
              - effect_id: participant-service-knowledge-update
                effect_class: side_effect
                description: participant-local service knowledge changes
                target_refs: [nodes.web.services.http]
              - effect_id: terminal-scan-observation
                effect_class: observation_effect
                description: terminal scan observation
                evidence_refs: [evidence.scan-output]
              - effect_id: participant-view-discovers-node
                effect_class: visibility_effect
                description: participant view marks the web node discovered
                target_refs: [nodes.web]
              - effect_id: scan-output-evidence
                effect_class: evidence_effect
                description: scan output is retained as evidence
                evidence_refs: [evidence.scan-output]
              - effect_id: no-hidden-truth-effect
                effect_class: no_effect
                description: scan does not disclose hidden adjudication material
            state_transition_effects: [participant knowledge expands]
            observation_expectations: [terminal scan result]
            evidence_expectations: [tool output]
            failure_classes: [target_unavailable, precondition_unsatisfied, backend_error, unknown]
            backend_failure_mappings:
              - backend_error_code: backend.target-unreachable
                failure_class: target_unavailable
                diagnostic: backend target unreachable
            interactions:
              - interaction_class: shared_state_change
                target: nodes.web.services.http
                rationale: scan reads and updates participant-visible service knowledge
                shared_state_refs: [nodes.web.services.http]
        observation_boundaries:
          red-view:
            projection_basis: participant-local projection over observed services
            observable_refs: []
            hidden_refs: [nodes.web, content.private-answer-key]
            evidence_refs: [evidence.scan-output]
            redaction_policy: hidden refs never project without explicit disclosure
            latency_profile: terminal observation emitted after state transition commit
            observer_effects: [tool execution may affect telemetry]
            realized_view_disclosure: backend reports terminal scan output only
            view_rules:
              - information_ref: nodes.web
                boundary_class: observable_resource
                disposition: hidden
                visibility_basis: service is not known before terminal scan output
                latency_profile: terminal observation latency
              - information_ref: content.private-answer-key
                boundary_class: private_answer_key
                disposition: hidden
                visibility_basis: adjudication-only hidden truth
              - information_ref: evidence.scan-output
                boundary_class: archival_evidence
                disposition: evidence_only
                visibility_basis: archival run evidence reference
                evidence_refs: [evidence.scan-output]
            view_transitions:
              - transition_id: discover-web-service
                transition_kind: discovery
                information_ref: nodes.web
                trigger: scan terminal observation
                effective_from: episode-step:scan-0001:terminal-observation
                effective_order: 30
                history_event_type: observation_emitted
                action_instance_id: scan-0001
                from_disposition: hidden
                to_disposition: discovered
                evidence_refs: [evidence.scan-output]
                certainty: high
                latency_profile: terminal observation latency
        agents:
          red-agent:
            entity: red-team
            actions: {actions}
            observation_boundaries: {boundaries}
        """
    )


def _sem219_scenario_yaml(*, actions: str = "[scan]", boundaries: str = "[red-view]") -> str:
    affordance_ref = "behavior_specifications.red-scan-behavior.tool_affordances.network-scanner"
    scenario = _scenario_yaml(actions=actions, boundaries=boundaries).replace(
        "action_contracts:\n",
        textwrap.dedent(
            """
        content:
          scanner-package:
            type: file
            target: web
            path: /opt/raes/tools/scanner
        action_contracts:
        """
        ),
        1,
    )
    scenario = scenario.replace(
        "    observable_refs: []\n",
        f"    observable_refs: [{affordance_ref}]\n",
        1,
    )
    scenario = scenario.replace(
        "    view_rules:\n",
        (
            "    view_rules:\n"
            f"      - information_ref: {affordance_ref}\n"
            "        boundary_class: observable_resource\n"
            "        disposition: observable\n"
            "        visibility_basis: authored participant-local affordance\n"
        ),
        1,
    )
    return scenario + textwrap.dedent(
        """
        behavior_specifications:
          red-scan-behavior:
            semantic_version: 1.0.0
            lifecycle_state: active
            participant_refs: [red-agent]
            action_contract_refs: [scan]
            observation_boundary_refs: [red-view]
            authority_scope_refs: [nodes.web.services.http]
            tool_affordances:
              network-scanner:
                tool_ref: scanner-package
                action_contract_refs: [scan]
                observation_boundary_refs: [red-view]
            extension_policy: governed-extension
        """
    )


def _act607_authority_scope_scenario_yaml() -> str:
    return textwrap.dedent(
        """
        name: act-607-authority-scope
        nodes:
          net:
            type: switch
          web:
            type: compute
            resources: {ram: 1 GiB, cpu: 1}
            services: [{port: 80, name: http}]
        infrastructure:
          net:
            count: 1
            properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}
          web:
            count: 1
            links: [net]
        entities:
          red-team:
            role: red
        accounts:
          operator:
            username: red
            node: web
        conditions:
          beacon-online:
            command: /usr/local/bin/check-beacon
            interval: 30
        propositions:
          beacon-online:
            description: The governed web host has declared beacon state.
            subjects: [nodes.web]
            basis: declared_state
            predicate: {kind: boolean, property: beacon-online, semantic_ref: urn:raes:declared-property:beacon-online, operator: equals, expected: true}
        assertions:
          beacon-online: {proposition: beacon-online, role: precondition, polarity: positive}
        relationships:
          red-controls-web:
            type: manages
            source: red-team
            target: web
        content:
          docs:
            type: dataset
            target: web
            items:
              - name: playbook
        action_contracts:
          scan:
            semantic_version: 1.0.0
            lifecycle_state: active
            behavioral_granularity: atomic
            procedure_basis: scan contract
            realization_profile: backend-declared
            fidelity_claim: records scan intent
            preconditions:
              - precondition_id: authority-in-scope
                precondition_class: authority
                description: participant authority is declared in SDL
            effects:
              - effect_id: no-effect
                effect_class: no_effect
                description: compilation-only contract
            failure_classes: [authority_denied, unknown]
        observation_boundaries:
          red-view:
            projection_basis: participant view
            evidence_refs: [evidence.scan-output]
            redaction_policy: hidden refs are not disclosed
            latency_profile: immediate
        agents:
          red-agent:
            entity: red-team
            actions: [scan]
            starting_accounts: [operator]
            initial_knowledge:
              hosts: [web]
              subnets: [net]
              services: [http]
              accounts: [operator]
            starting_assertions: [beacon-online]
            authority_anchors:
              - red-team
              - red-controls-web
              - operator
              - scan
              - red-view
              - docs
              - nodes.web.services.http
            operating_scope:
              - web
              - net
              - nodes.web.services.http
              - docs
              - playbook
            observation_boundaries: [red-view]
        behavior_specifications:
          red-scan-behavior:
            semantic_version: 1.0.0
            lifecycle_state: active
            participant_refs: [red-agent]
            action_contract_refs: [scan]
            observation_boundary_refs: [red-view]
            authority_scope_refs:
              - nodes.web.services.http
              - operator
              - scan
              - red-view
              - docs
              - playbook
              - red-controls-web
            extension_policy: governed-extension
        """
    )


def _act607_typed_ref_collision_scenario_yaml() -> str:
    return textwrap.dedent(
        """
        name: act-607-typed-ref-collisions
        nodes:
          web:
            type: compute
            resources: {ram: 1 GiB, cpu: 1}
            services: [{port: 80, name: http}]
        entities:
          red-team:
            role: red
        accounts:
          operator:
            username: red
            node: web
        conditions:
          beacon-online:
            command: /usr/local/bin/check-beacon
            interval: 30
        propositions:
          beacon-online:
            description: The governed web host has declared beacon state.
            subjects: [nodes.web]
            basis: declared_state
            predicate: {kind: boolean, property: beacon-online, semantic_ref: urn:raes:declared-property:beacon-online, operator: equals, expected: true}
        assertions:
          beacon-online: {proposition: beacon-online, role: precondition, polarity: positive}
        content:
          operator:
            type: dataset
            target: web
            source: file:///tmp/operator.txt
          beacon-online:
            type: dataset
            target: web
            source: file:///tmp/beacon-online.txt
          http:
            type: dataset
            target: web
            source: file:///tmp/http.txt
        agents:
          red-agent:
            entity: red-team
            starting_accounts: [operator]
            initial_knowledge:
              hosts: [web]
              services: [http]
              accounts: [operator]
            starting_assertions: [beacon-online]
        """
    )


def test_participant_behavior_contracts_parse_and_validate():
    scenario = parse_sdl(_scenario_yaml())

    assert scenario.action_contracts["scan"].semantic_version == "1.0.0"
    assert scenario.action_contracts["scan"].lifecycle_state.value == "active"
    assert scenario.action_contracts["scan"].interactions[0].interaction_class.value == "shared_state_change"
    assert scenario.observation_boundaries["red-view"].projection_basis.startswith("participant-local")
    assert scenario.observation_boundaries["red-view"].view_rules[1].disposition.value == "hidden"
    assert scenario.agents["red-agent"].observation_boundaries == ["red-view"]


def test_behavior_specifications_parse_validate_and_compile():
    scenario = parse_sdl(
        _scenario_yaml()
        + textwrap.dedent(
            """
        behavior_specifications:
          red-scan-behavior:
            semantic_version: 1.0.0
            lifecycle_state: active
            participant_refs: [red-agent]
            participant_role_refs: [red]
            action_contract_refs: [scan]
            observation_boundary_refs: [red-view]
            authority_scope_refs: [nodes.web.services.http]
            behavior_mode: policy-directed
            realization_profile_ref: participant-implementation-manifest:reference-red-agent
            backend_feature_support_refs: [action_contracts]
            evidence_contract_refs: [participant-behavior-history-event-stream-v1]
            extension_policy: governed-extension
            extensions:
              x-acme:review-note:
                owner: acme
                note: reference-only extension
        """
        )
    )

    spec = scenario.behavior_specifications["red-scan-behavior"]
    assert spec.semantic_version == "1.0.0"
    assert spec.participant_refs == ["red-agent"]
    assert spec.participant_role_refs == ["red"]
    assert spec.behavior_mode == "policy-directed"
    assert spec.extensions["x-acme:review-note"]["note"] == "reference-only extension"

    model = compile_runtime_model(scenario)
    compiled = model.behavior_specifications["participant.behavior-specification.red-scan-behavior"]
    assert compiled.participant_addresses == (PARTICIPANT_ADDRESS,)
    assert compiled.action_contract_addresses == (ACTION_ADDRESS,)
    assert compiled.observation_boundary_addresses == (OBSERVATION_ADDRESS,)
    assert compiled.authority_scope_refs == ("nodes.web.services.http",)
    assert compiled.behavior_mode == "policy-directed"
    assert compiled.spec["participant_refs"] == ["red-agent"]


def test_sem219_tool_affordance_parses_validates_and_compiles_typed_ir():
    scenario = parse_sdl(_sem219_scenario_yaml())

    binding = scenario.behavior_specifications["red-scan-behavior"].tool_affordances["network-scanner"]
    assert binding.tool_ref == "scanner-package"
    assert binding.action_contract_refs == ["scan"]
    assert binding.observation_boundary_refs == ["red-view"]

    model = compile_runtime_model(scenario)
    compiled = model.tool_affordances[AFFORDANCE_ADDRESS]
    assert compiled.behavior_specification_address == ("participant.behavior-specification.red-scan-behavior")
    assert compiled.tool_ref == "scanner-package"
    assert compiled.tool_address == "provision.content.scanner-package"
    assert compiled.action_contract_refs == ("scan",)
    assert compiled.action_contract_addresses == (ACTION_ADDRESS,)
    assert compiled.observation_boundary_refs == ("red-view",)
    assert compiled.observation_boundary_addresses == (OBSERVATION_ADDRESS,)
    assert compiled.refresh_dependencies == (
        "participant.behavior-specification.red-scan-behavior",
        "provision.content.scanner-package",
        ACTION_ADDRESS,
        OBSERVATION_ADDRESS,
    )
    assert model.behavior_specifications[
        "participant.behavior-specification.red-scan-behavior"
    ].tool_affordance_addresses == (AFFORDANCE_ADDRESS,)


def test_sem219_one_tool_identity_can_bind_multiple_distinct_affordances():
    scan_ref = "behavior_specifications.red-scan-behavior.tool_affordances.network-scanner"
    inspect_ref = "behavior_specifications.red-scan-behavior.tool_affordances.package-inspection"
    source = _sem219_scenario_yaml().replace(
        "action_contracts:\n  scan:\n",
        textwrap.dedent(
            """
            action_contracts:
              inspect:
                semantic_version: 1.0.0
                lifecycle_state: active
                behavioral_granularity: atomic
                procedure_basis: inspect a governed package
                realization_profile: backend-declared
                fidelity_claim: records participant package-inspection intent
                preconditions:
                  - precondition_id: authority-in-scope
                    precondition_class: authority
                    description: participant is authorized to inspect the package
                effects:
                  - effect_id: inspect-package
                    effect_class: observation_effect
                    description: inspect the governed package
                    evidence_refs: [evidence.scan-output]
                failure_classes: [precondition_unsatisfied, unknown]
              scan:
            """
        ).lstrip(),
        1,
    )
    source = source.replace("actions: [scan]", "actions: [scan, inspect]", 1)
    source = source.replace(
        "    action_contract_refs: [scan]\n    observation_boundary_refs: [red-view]\n    authority_scope_refs:",
        "    action_contract_refs: [scan, inspect]\n    observation_boundary_refs: [red-view]\n    authority_scope_refs:",
        1,
    )
    source = source.replace(
        "      network-scanner:\n",
        (
            "      package-inspection:\n"
            "        tool_ref: scanner-package\n"
            "        action_contract_refs: [inspect]\n"
            "        observation_boundary_refs: [red-view]\n"
            "      network-scanner:\n"
        ),
        1,
    )
    source = source.replace(
        f"    observable_refs: [{scan_ref}]",
        f"    observable_refs: [{scan_ref}, {inspect_ref}]",
        1,
    )
    source = source.replace(
        "    view_rules:\n",
        (
            "    view_rules:\n"
            f"      - information_ref: {inspect_ref}\n"
            "        boundary_class: observable_resource\n"
            "        disposition: observable\n"
            "        visibility_basis: authored participant-local affordance\n"
        ),
        1,
    )

    model = compile_runtime_model(parse_sdl(source))
    scan = model.tool_affordances[AFFORDANCE_ADDRESS]
    inspect = model.tool_affordances[
        "participant.behavior-specification.red-scan-behavior.tool-affordance.package-inspection"
    ]

    assert scan.tool_address == inspect.tool_address == "provision.content.scanner-package"
    assert scan.action_contract_addresses == (ACTION_ADDRESS,)
    assert inspect.action_contract_addresses == ("participant.action-contract.inspect",)


def test_sem219_tool_identity_is_revalidated_after_instantiation():
    source = (
        _sem219_scenario_yaml()
        .replace(
            "name: sem-208\n",
            textwrap.dedent(
                """
            name: sem-208
            variables:
              tool_identity:
                type: string
                default: scanner-package
                allowed_values: [scanner-package, missing-package]
            """
            ).lstrip(),
            1,
        )
        .replace("tool_ref: scanner-package", "tool_ref: ${tool_identity}", 1)
    )
    authored = parse_sdl(source)

    instantiated = instantiate_scenario(authored, parameters={"tool_identity": "scanner-package"})
    assert compile_runtime_model(instantiated).tool_affordances[AFFORDANCE_ADDRESS].tool_address == (
        "provision.content.scanner-package"
    )

    with pytest.raises(SDLInstantiationError, match="missing-package"):
        instantiate_scenario(authored, parameters={"tool_identity": "missing-package"})


def test_sem219_tool_affordance_is_closed_and_requires_non_empty_relations():
    invalid = _sem219_scenario_yaml().replace(
        "        tool_ref: scanner-package\n        action_contract_refs: [scan]\n        observation_boundary_refs: [red-view]",
        "        tool_ref: scanner-package\n        action_contract_refs: [scan]\n        observation_boundary_refs: []\n        visible: true",
        1,
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(invalid)

    rendered = str(excinfo.value)
    assert "observation_boundary_refs" in rendered
    assert "Extra inputs are not permitted" in rendered


def test_sem219_schemas_publish_closed_tool_affordance_shape():
    for contract_id in (
        "sdl-authoring-input-v1",
        "instantiated-scenario-v1",
        "instantiated-scenario-snapshot-v1",
    ):
        schema = schema_bundle()[contract_id]
        affordance = schema["$defs"]["ParticipantToolAffordance"]
        assert affordance["additionalProperties"] is False
        assert affordance["required"] == ["action_contract_refs", "observation_boundary_refs"]
        assert set(affordance["properties"]) == {
            "tool_ref",
            "action_contract_refs",
            "observation_boundary_refs",
        }


@pytest.mark.parametrize("relation_field", ("action_contract_refs", "observation_boundary_refs"))
@pytest.mark.parametrize("invalid_refs", (("",), ("scan", "scan")))
def test_sem219_schemas_reject_blank_and_duplicate_tool_affordance_relations(
    relation_field: str,
    invalid_refs: tuple[str, ...],
):
    payload = {
        "tool_ref": "scanner-package",
        "action_contract_refs": ["scan"],
        "observation_boundary_refs": ["red-view"],
    }
    payload[relation_field] = list(invalid_refs)

    for contract_id in (
        "sdl-authoring-input-v1",
        "instantiated-scenario-v1",
        "instantiated-scenario-snapshot-v1",
    ):
        affordance_schema = schema_bundle()[contract_id]["$defs"]["ParticipantToolAffordance"]
        assert list(Draft202012Validator(affordance_schema).iter_errors(payload)), contract_id


def test_sem219_tool_affordance_has_a_typed_authored_declaration():
    scenario = parse_sdl(_sem219_scenario_yaml())
    index = build_declaration_index(scenario)
    authored_ref = "behavior_specifications.red-scan-behavior.tool_affordances.network-scanner"

    declaration = index.declaration_for(authored_ref)
    assert declaration is not None
    assert declaration.kind == "tool-affordance"
    assert declaration.referenceable is True
    assert declaration.targetable is False
    assert index.resolve(authored_ref) == {authored_ref}


@pytest.mark.parametrize(
    ("scenario", "expected"),
    (
        (
            _sem219_scenario_yaml().replace("tool_ref: scanner-package", "tool_ref: shell", 1),
            "tool_ref 'shell' does not reference a declared scenario content identity",
        ),
        (
            _sem219_scenario_yaml().replace("tool_ref: scanner-package", "tool_ref: web", 1),
            "tool_ref 'web' must resolve through the scenario-content tools-and-artifacts reference model",
        ),
        (
            _sem219_scenario_yaml().replace(
                "    action_contract_refs: [scan]\n    observation_boundary_refs: [red-view]",
                "    action_contract_refs: []\n    observation_boundary_refs: [red-view]",
                1,
            ),
            "action_contract_ref 'scan' widens its owning behavior specification",
        ),
        (
            _sem219_scenario_yaml().replace(
                "    action_contract_refs: [scan]\n    observation_boundary_refs: [red-view]",
                "    action_contract_refs: [scan]\n    observation_boundary_refs: []",
                1,
            ),
            "observation_boundary_ref 'red-view' widens its owning behavior specification",
        ),
        (
            _sem219_scenario_yaml(actions="[]"),
            "action_contract_ref 'scan' is outside participant 'red-agent' actions",
        ),
        (
            _sem219_scenario_yaml(boundaries="[]"),
            "observation_boundary_ref 'red-view' is outside participant 'red-agent' observation boundaries",
        ),
    ),
)
def test_sem219_tool_affordance_references_fail_closed(scenario: str, expected: str):
    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(scenario)

    assert expected in str(excinfo.value)


def test_sem219_tool_affordance_rejects_cross_family_ambiguous_tool_identity():
    ambiguous = _sem219_scenario_yaml().replace(
        "entities:\n  red-team:\n",
        "entities:\n  scanner-package:\n    role: red\n  red-team:\n",
        1,
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(ambiguous)

    rendered = str(excinfo.value)
    assert "tool_ref 'scanner-package' is ambiguous" in rendered
    assert "content.scanner-package" in rendered
    assert "entities.scanner-package" in rendered


def test_sem219_tool_affordance_requires_explicit_view_classification():
    affordance_ref = "behavior_specifications.red-scan-behavior.tool_affordances.network-scanner"
    invalid = _sem219_scenario_yaml().replace(
        f"    observable_refs: [{affordance_ref}]",
        "    observable_refs: []",
        1,
    )
    invalid = invalid.replace(
        (
            f"      - information_ref: {affordance_ref}\n"
            "        boundary_class: observable_resource\n"
            "        disposition: observable\n"
            "        visibility_basis: authored participant-local affordance\n"
        ),
        "",
        1,
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(invalid)

    assert "must be explicitly classified by observation boundary 'red-view'" in str(excinfo.value)


def test_sem219_tool_affordance_rejects_duplicate_relations():
    duplicate = _sem219_scenario_yaml().replace(
        "      network-scanner:\n",
        (
            "      alternate-scanner:\n"
            "        tool_ref: scanner-package\n"
            "        action_contract_refs: [scan]\n"
            "        observation_boundary_refs: [red-view]\n"
            "      network-scanner:\n"
        ),
        1,
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(duplicate)

    assert "duplicate tool affordance relation" in str(excinfo.value)


def test_sem219_role_scoped_affordance_resolves_each_matching_participant():
    role_scoped = _sem219_scenario_yaml().replace(
        "    participant_refs: [red-agent]\n",
        "    participant_refs: []\n    participant_role_refs: [red]\n",
        1,
    )

    scenario = parse_sdl(role_scoped)

    assert scenario.behavior_specifications["red-scan-behavior"].participant_role_refs == ["red"]
    assert AFFORDANCE_ADDRESS in compile_runtime_model(scenario).tool_affordances


@pytest.mark.parametrize(
    ("actions", "boundaries", "expected"),
    (
        ("[]", "[red-view]", "action_contract_ref 'scan' is outside participant 'red-observer' actions"),
        (
            "[scan]",
            "[]",
            "observation_boundary_ref 'red-view' is outside participant 'red-observer' observation boundaries",
        ),
    ),
)
def test_sem219_role_scoped_affordance_enforces_each_matching_participant(
    actions: str,
    boundaries: str,
    expected: str,
):
    role_scoped = _sem219_scenario_yaml().replace(
        "    participant_refs: [red-agent]\n",
        "    participant_refs: []\n    participant_role_refs: [red]\n",
        1,
    )
    role_scoped = role_scoped.replace(
        "    observation_boundaries: [red-view]\n\nbehavior_specifications:\n",
        (
            "    observation_boundaries: [red-view]\n"
            "  red-observer:\n"
            "    entity: red-team\n"
            f"    actions: {actions}\n"
            f"    observation_boundaries: {boundaries}\n\n"
            "behavior_specifications:\n"
        ),
        1,
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(role_scoped)

    assert expected in str(excinfo.value)


def test_sem219_hidden_affordance_remains_authored_without_becoming_visible():
    affordance_ref = "behavior_specifications.red-scan-behavior.tool_affordances.network-scanner"
    hidden = (
        _sem219_scenario_yaml()
        .replace(
            f"    observable_refs: [{affordance_ref}]",
            f"    observable_refs: []\n    hidden_refs: [{affordance_ref}, nodes.web, content.private-answer-key]",
            1,
        )
        .replace(
            "    hidden_refs: [nodes.web, content.private-answer-key]\n",
            "",
            1,
        )
        .replace(
            "        disposition: observable\n",
            "        disposition: hidden\n",
            1,
        )
    )

    model = compile_runtime_model(parse_sdl(hidden))

    assert AFFORDANCE_ADDRESS in model.tool_affordances
    assert affordance_ref in model.observation_boundaries[OBSERVATION_ADDRESS].hidden_refs
    assert affordance_ref not in model.observation_boundaries[OBSERVATION_ADDRESS].observable_refs


def test_sem219_optional_tool_identity_does_not_weaken_affordance_meaning():
    identity_free = _sem219_scenario_yaml().replace(
        "        tool_ref: scanner-package\n",
        "",
        1,
    )

    compiled = compile_runtime_model(parse_sdl(identity_free)).tool_affordances[AFFORDANCE_ADDRESS]

    assert compiled.tool_ref == ""
    assert compiled.tool_address == ""
    assert compiled.action_contract_addresses == (ACTION_ADDRESS,)
    assert compiled.observation_boundary_addresses == (OBSERVATION_ADDRESS,)


def test_sem219_global_tool_identity_does_not_synthesize_participant_availability():
    globally_present = _scenario_yaml().replace(
        "action_contracts:\n",
        textwrap.dedent(
            """
            content:
              scanner-package:
                type: file
                target: web
                path: /opt/raes/tools/scanner
            action_contracts:
            """
        ),
        1,
    )

    model = compile_runtime_model(parse_sdl(globally_present))

    assert "provision.content.scanner-package" in model.content_placements
    assert model.tool_affordances == {}


def test_sem219_backend_support_does_not_synthesize_participant_authority():
    source = _scenario_yaml() + textwrap.dedent(
        """
        behavior_specifications:
          red-scan-behavior:
            semantic_version: 1.0.0
            lifecycle_state: active
            participant_refs: [red-agent]
            action_contract_refs: [scan]
            backend_feature_support_refs: [action_contracts]
            extension_policy: governed-extension
        """
    )

    model = compile_runtime_model(parse_sdl(source))
    behavior_spec = model.behavior_specifications["participant.behavior-specification.red-scan-behavior"]

    assert behavior_spec.backend_feature_support_refs == ("action_contracts",)
    assert behavior_spec.tool_affordance_addresses == ()
    assert model.tool_affordances == {}


def test_sem219_constraints_and_failure_classes_remain_on_action_contract():
    model = compile_runtime_model(parse_sdl(_sem219_scenario_yaml()))
    affordance = model.tool_affordances[AFFORDANCE_ADDRESS]
    action_contract = model.action_contracts[ACTION_ADDRESS]

    assert affordance.action_contract_addresses == (ACTION_ADDRESS,)
    assert action_contract.precondition_classes == ("authority", "target", "realization")
    assert "precondition_unsatisfied" in action_contract.failure_classes
    assert "preconditions" not in affordance.spec
    assert "failure_classes" not in affordance.spec


def test_participant_behavior_runtime_carries_act607_authority_scope_metadata():
    model = compile_runtime_model(parse_sdl(_act607_authority_scope_scenario_yaml()))

    compiled = model.participant_behaviors[PARTICIPANT_ADDRESS]

    assert compiled.starting_account_refs == ("operator",)
    assert compiled.starting_account_addresses == ("provision.account.operator",)
    assert compiled.initial_knowledge_addresses == (
        "provision.node.web",
        "provision.network.net",
        "provision.node.web.service.http",
        "provision.account.operator",
    )
    assert compiled.starting_assertion_refs == ("beacon-online",)
    assert compiled.starting_assertion_addresses == ("evaluation.assertion.beacon-online",)
    assert compiled.authority_anchor_refs == (
        "red-team",
        "red-controls-web",
        "operator",
        "scan",
        "red-view",
        "docs",
        "nodes.web.services.http",
    )
    assert compiled.authority_anchor_addresses == (
        "provision.account.operator",
        ACTION_ADDRESS,
        OBSERVATION_ADDRESS,
        "provision.content.docs",
        "provision.node.web.service.http",
    )
    assert compiled.operating_scope_refs == (
        "web",
        "net",
        "nodes.web.services.http",
        "docs",
        "playbook",
    )
    assert compiled.operating_scope_addresses == (
        "provision.node.web",
        "provision.network.net",
        "provision.node.web.service.http",
        "provision.content.docs",
        "provision.content.docs.items.playbook",
    )
    assert compiled.refresh_dependencies == (
        ACTION_ADDRESS,
        OBSERVATION_ADDRESS,
        "provision.account.operator",
        "provision.node.web",
        "provision.network.net",
        "provision.node.web.service.http",
        "evaluation.assertion.beacon-online",
        "provision.content.docs",
        "provision.content.docs.items.playbook",
    )


def test_participant_typed_authority_refs_ignore_global_alias_collisions():
    model = compile_runtime_model(parse_sdl(_act607_typed_ref_collision_scenario_yaml()))

    compiled = model.participant_behaviors[PARTICIPANT_ADDRESS]

    assert compiled.starting_account_addresses == ("provision.account.operator",)
    assert compiled.initial_knowledge_addresses == (
        "provision.node.web",
        "provision.node.web.service.http",
        "provision.account.operator",
    )
    assert compiled.starting_assertion_addresses == ("evaluation.assertion.beacon-online",)
    assert compiled.refresh_dependencies == (
        "provision.account.operator",
        "provision.node.web",
        "provision.node.web.service.http",
        "evaluation.assertion.beacon-online",
    )


def test_behavior_specification_runtime_carries_authority_scope_addresses():
    model = compile_runtime_model(parse_sdl(_act607_authority_scope_scenario_yaml()))

    compiled = model.behavior_specifications["participant.behavior-specification.red-scan-behavior"]

    assert compiled.authority_scope_refs == (
        "nodes.web.services.http",
        "operator",
        "scan",
        "red-view",
        "docs",
        "playbook",
        "red-controls-web",
    )
    assert compiled.authority_scope_addresses == (
        "provision.node.web.service.http",
        "provision.account.operator",
        ACTION_ADDRESS,
        OBSERVATION_ADDRESS,
        "provision.content.docs",
        "provision.content.docs.items.playbook",
    )
    assert compiled.refresh_dependencies == (
        PARTICIPANT_ADDRESS,
        ACTION_ADDRESS,
        OBSERVATION_ADDRESS,
        "provision.node.web.service.http",
        "provision.account.operator",
        "provision.content.docs",
        "provision.content.docs.items.playbook",
    )


def test_behavior_specification_refs_are_namespaced_during_module_composition(tmp_path):
    module = tmp_path / "shared.yaml"
    module.write_text(
        textwrap.dedent(
            """
            name: shared
            module:
              id: acme/shared
              version: 1.0.0
              exports:
                entities: [red-team]
                content: [scanner-package]
                agents: [red-agent]
                action_contracts: [scan]
                observation_boundaries: [red-view]
                behavior_specifications: [red-scan-behavior]
            entities:
              red-team:
                role: red
            agents:
              red-agent:
                entity: red-team
                actions: [scan]
                observation_boundaries: [red-view]
            content:
              scanner-package:
                type: file
                target: web
                path: /opt/raes/tools/scanner
            nodes:
              web:
                type: compute
                resources: {ram: 1 GiB, cpu: 1}
            action_contracts:
              scan:
                semantic_version: 1.0.0
                lifecycle_state: active
                behavioral_granularity: atomic
                procedure_basis: scan contract
                realization_profile: backend-declared
                fidelity_claim: records scan intent
                preconditions:
                  - precondition_id: authority-in-scope
                    precondition_class: authority
                    description: participant has authority
                effects:
                  - effect_id: no-effect
                    effect_class: no_effect
                    description: composition-only contract
                failure_classes: [unknown]
            observation_boundaries:
              red-view:
                projection_basis: participant view
                observable_refs:
                  - behavior_specifications.red-scan-behavior.tool_affordances.network-scanner
                evidence_refs: [evidence.scan-output]
                redaction_policy: no hidden refs are disclosed
                latency_profile: immediate
                view_rules:
                  - information_ref: behavior_specifications.red-scan-behavior.tool_affordances.network-scanner
                    boundary_class: observable_resource
                    disposition: observable
                    visibility_basis: authored participant-local affordance
            behavior_specifications:
              red-scan-behavior:
                semantic_version: 1.0.0
                lifecycle_state: active
                participant_refs: [red-agent]
                action_contract_refs: [scan]
                observation_boundary_refs: [red-view]
                tool_affordances:
                  network-scanner:
                    tool_ref: scanner-package
                    action_contract_refs: [scan]
                    observation_boundary_refs: [red-view]
                extension_policy: governed-extension
            """
        ).lstrip(),
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: root
            imports:
              - source: local:shared.yaml
                namespace: shared
            """
        ).lstrip(),
        encoding="utf-8",
    )

    scenario = parse_sdl_file(root)
    spec = scenario.behavior_specifications["shared.red-scan-behavior"]
    assert spec.participant_refs == ["shared.red-agent"]
    assert spec.action_contract_refs == ["shared.scan"]
    assert spec.observation_boundary_refs == ["shared.red-view"]
    binding = spec.tool_affordances["network-scanner"]
    assert binding.tool_ref == "shared.scanner-package"
    assert binding.action_contract_refs == ["shared.scan"]
    assert binding.observation_boundary_refs == ["shared.red-view"]
    affordance_ref = "behavior_specifications.shared.red-scan-behavior.tool_affordances.network-scanner"
    boundary = scenario.observation_boundaries["shared.red-view"]
    assert affordance_ref in boundary.observable_refs
    assert boundary.view_rules[0].information_ref == affordance_ref

    compiled = compile_runtime_model(scenario).behavior_specifications[
        "participant.behavior-specification.shared.red-scan-behavior"
    ]
    assert compiled.participant_addresses == ("participant.behavior.shared.red-agent",)
    assert compiled.action_contract_addresses == ("participant.action-contract.shared.scan",)
    assert compiled.observation_boundary_addresses == ("participant.observation-boundary.shared.red-view",)
    affordance = compile_runtime_model(scenario).tool_affordances[
        "participant.behavior-specification.shared.red-scan-behavior.tool-affordance.network-scanner"
    ]
    assert affordance.tool_address == "provision.content.shared.scanner-package"
    assert affordance.action_contract_addresses == ("participant.action-contract.shared.scan",)


def test_behavior_specification_optional_fields_compile_empty_when_omitted():
    scenario = parse_sdl(
        _scenario_yaml()
        + textwrap.dedent(
            """
        behavior_specifications:
          red-scan-behavior:
            semantic_version: 1.0.0
            lifecycle_state: active
            participant_refs: [red-agent]
            action_contract_refs: [scan]
            extension_policy: governed-extension
        """
        )
    )

    compiled = compile_runtime_model(scenario).behavior_specifications[
        "participant.behavior-specification.red-scan-behavior"
    ]
    assert compiled.behavior_mode == ""
    assert compiled.realization_profile_ref == ""


@pytest.mark.parametrize(
    "behavior_mode",
    [
        "autonomous",
        "scripted",
        "policy-directed",
        "replayed",
        "human-supervised",
    ],
)
def test_act_608_behavior_modes_parse_validate_and_compile(behavior_mode: str):
    scenario = parse_sdl(
        _scenario_yaml()
        + textwrap.dedent(
            f"""
        behavior_specifications:
          red-scan-behavior:
            semantic_version: 1.0.0
            lifecycle_state: active
            participant_refs: [red-agent]
            action_contract_refs: [scan]
            behavior_mode: {behavior_mode}
            extension_policy: governed-extension
        """
        )
    )

    spec = scenario.behavior_specifications["red-scan-behavior"]
    assert spec.behavior_mode == behavior_mode

    compiled = compile_runtime_model(scenario).behavior_specifications[
        "participant.behavior-specification.red-scan-behavior"
    ]
    assert compiled.behavior_mode == behavior_mode


def test_behavior_specification_behavior_mode_allows_governed_extensions():
    scenario = parse_sdl(
        _scenario_yaml()
        + textwrap.dedent(
            """
        behavior_specifications:
          red-scan-behavior:
            semantic_version: 1.0.0
            lifecycle_state: active
            participant_refs: [red-agent]
            action_contract_refs: [scan]
            behavior_mode: x-acme:swarm-control
            extension_policy: governed-extension
        """
        )
    )

    compiled = compile_runtime_model(scenario).behavior_specifications[
        "participant.behavior-specification.red-scan-behavior"
    ]
    assert compiled.behavior_mode == "x-acme:swarm-control"


@pytest.mark.parametrize("field", ["offensive_behavior_refs", "ai_offensive_behavior_refs", "defensive_behavior_refs"])
def test_behavior_classifications_require_external_binding_migration(field):
    source = _scenario_yaml() + textwrap.dedent(
        f"""
        behavior_specifications:
          legacy:
            semantic_version: 1.0.0
            participant_refs: [red-agent]
            action_contract_refs: [scan]
            {field}: [x-acme:custom-term]
        """
    )
    with pytest.raises(SDLParseError, match="classification migration"):
        parse_sdl(source)


@pytest.mark.parametrize(
    ("field", "replacement", "expected"),
    [
        (
            "participant_refs: [red-agent]",
            "participant_refs: [blue-agent]",
            "Behavior specification 'red-scan-behavior' participant_ref 'blue-agent' "
            "does not reference a declared agent",
        ),
        (
            "action_contract_refs: [scan]",
            "action_contract_refs: [exploit]",
            "Behavior specification 'red-scan-behavior' action_contract_ref 'exploit' "
            "does not reference a declared action_contract",
        ),
        (
            "observation_boundary_refs: [red-view]",
            "observation_boundary_refs: [leaked-view]",
            "Behavior specification 'red-scan-behavior' observation_boundary_ref 'leaked-view' "
            "does not reference a declared observation_boundary",
        ),
        (
            "authority_scope_refs: [nodes.web.services.http]",
            "authority_scope_refs: [nodes.missing.services.http]",
            "Behavior specification 'red-scan-behavior' authority_scope_ref 'nodes.missing.services.http' "
            "does not reference any defined targetable element",
        ),
    ],
)
def test_behavior_specification_references_fail_closed(field: str, replacement: str, expected: str):
    behavior_spec = textwrap.dedent(
        """
        behavior_specifications:
          red-scan-behavior:
            semantic_version: 1.0.0
            lifecycle_state: active
            participant_refs: [red-agent]
            participant_role_refs: [red]
            action_contract_refs: [scan]
            observation_boundary_refs: [red-view]
            authority_scope_refs: [nodes.web.services.http]
            behavior_mode: policy-directed
            extension_policy: governed-extension
        """
    )
    scenario = _scenario_yaml() + behavior_spec.replace(field, replacement)

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(scenario)

    assert expected in str(excinfo.value)


def test_behavior_specification_behavior_mode_uses_governed_vocabulary():
    scenario = _scenario_yaml() + textwrap.dedent(
        """
        behavior_specifications:
          red-scan-behavior:
            semantic_version: 1.0.0
            lifecycle_state: active
            participant_refs: [red-agent]
            action_contract_refs: [scan]
            behavior_mode: supervised
            extension_policy: governed-extension
        """
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(scenario)

    assert "participant-decision-surface-modes" in str(excinfo.value)


def test_behavior_specification_backend_feature_refs_use_governed_vocabulary():
    scenario = _scenario_yaml() + textwrap.dedent(
        """
        behavior_specifications:
          red-scan-behavior:
            semantic_version: 1.0.0
            lifecycle_state: active
            participant_refs: [red-agent]
            action_contract_refs: [scan]
            backend_feature_support_refs: [participant-behavior-history]
            extension_policy: governed-extension
        """
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(scenario)

    assert (
        "backend_feature_support_ref 'participant-behavior-history' is not a governed participant runtime feature"
        in str(excinfo.value)
    )


def test_behavior_specification_evidence_contract_refs_use_published_contract_ids():
    scenario = _scenario_yaml() + textwrap.dedent(
        """
        behavior_specifications:
          red-scan-behavior:
            semantic_version: 1.0.0
            lifecycle_state: active
            participant_refs: [red-agent]
            action_contract_refs: [scan]
            evidence_contract_refs: [raw-terminal-log-v1]
            extension_policy: governed-extension
        """
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(scenario)

    assert (
        "Behavior specification 'red-scan-behavior' evidence_contract_ref 'raw-terminal-log-v1' "
        "does not reference a published contract"
    ) in str(excinfo.value)


def test_behavior_specification_extension_keys_are_governed():
    scenario = _scenario_yaml() + textwrap.dedent(
        """
        behavior_specifications:
          red-scan-behavior:
            semantic_version: 1.0.0
            lifecycle_state: active
            participant_refs: [red-agent]
            action_contract_refs: [scan]
            extension_policy: governed-extension
            extensions:
              custom-mode:
                note: ungoverned
        """
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "behavior specification extension keys must match" in str(excinfo.value)


def test_agent_actions_must_resolve_to_governed_action_contracts():
    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(_scenario_yaml(actions="[scan, exploit]"))

    assert "Agent 'red-agent' action 'exploit' does not reference a declared action_contract" in str(excinfo.value)


def test_agent_observation_boundaries_must_resolve_to_declared_boundaries():
    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(_scenario_yaml(boundaries="[red-view, leaked-view]"))

    assert (
        "Agent 'red-agent' observation_boundary 'leaked-view' does not reference a declared observation_boundary"
        in str(excinfo.value)
    )


def test_participant_interactions_must_resolve_related_action_contracts():
    scenario = _scenario_yaml().replace(
        "        shared_state_refs: [nodes.web.services.http]",
        ("        related_actions: [coordinate]\n        shared_state_refs: [nodes.web.services.http]"),
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(scenario)

    assert (
        "Action contract 'scan' interaction related_action 'coordinate' does not reference a declared action_contract"
    ) in str(excinfo.value)


def test_participant_interactions_must_resolve_targets():
    scenario = _scenario_yaml().replace(
        "target: nodes.web.services.http",
        "target: nodes.missing.services.http",
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(scenario)

    assert (
        "Action contract 'scan' interaction[0] target 'nodes.missing.services.http' "
        "does not reference any defined targetable element"
    ) in str(excinfo.value)


def test_participant_interactions_must_resolve_shared_state_refs():
    scenario = _scenario_yaml().replace(
        "shared_state_refs: [nodes.web.services.http]",
        "shared_state_refs: [nodes.missing.services.http]",
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(scenario)

    assert (
        "Action contract 'scan' interaction[0] shared_state_ref 'nodes.missing.services.http' "
        "does not reference any defined targetable element"
    ) in str(excinfo.value)


def test_compiler_maps_participant_behavior_to_runtime_addresses():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))

    assert set(model.action_contracts) == {ACTION_ADDRESS}
    assert set(model.observation_boundaries) == {OBSERVATION_ADDRESS}
    contract = model.action_contracts[ACTION_ADDRESS]
    assert contract.interaction_classes == ("shared_state_change",)
    assert contract.shared_state_refs == ("nodes.web.services.http",)
    boundary = model.observation_boundaries[OBSERVATION_ADDRESS]
    assert boundary.hidden_refs == ("nodes.web", "content.private-answer-key")
    assert boundary.observable_refs == ()
    assert boundary.evidence_only_refs == ("evidence.scan-output",)
    assert boundary.discovered_refs == ()
    assert boundary.view_transitions[0]["transition_id"] == "discover-web-service"
    assert boundary.view_transitions[0]["effective_from"] == "episode-step:scan-0001:terminal-observation"
    assert boundary.view_transitions[0]["effective_order"] == 30
    assert boundary.view_transitions[0]["history_event_type"] == "observation_emitted"
    assert boundary.view_relation_timeline[0]["view_relation"]["nodes.web"] == "hidden"
    assert "nodes.web" not in boundary.view_relation_timeline[0]["visible_refs"]
    assert boundary.view_relation_timeline[1]["view_relation"]["nodes.web"] == "discovered"
    assert "nodes.web" in boundary.view_relation_timeline[1]["visible_refs"]
    assert boundary.realized_view_disclosure == "backend reports terminal scan output only"

    binding = model.participant_behaviors[PARTICIPANT_ADDRESS]
    assert binding.participant_name == "red-agent"
    assert binding.entity_name == "red-team"
    assert binding.action_contract_addresses == (ACTION_ADDRESS,)
    assert binding.observation_boundary_addresses == (OBSERVATION_ADDRESS,)
    assert binding.interpretation_mode == "role-neutral-projection"
    assert binding.spec["interpretation_mode"] == "role-neutral-projection"


def test_view_relation_timeline_tracks_inference_and_concealment_transitions():
    scenario = (
        _scenario_yaml()
        .replace(
            "hidden_refs: [nodes.web, content.private-answer-key]",
            "hidden_refs: [nodes.web, content.private-answer-key, nodes.web.services.http]",
        )
        .replace(
            "      - information_ref: evidence.scan-output\n"
            "        boundary_class: archival_evidence\n"
            "        disposition: evidence_only\n"
            "        visibility_basis: archival run evidence reference\n"
            "        evidence_refs: [evidence.scan-output]",
            "      - information_ref: nodes.web.services.http\n"
            "        boundary_class: observable_resource\n"
            "        disposition: hidden\n"
            "        visibility_basis: service is not known before scan output inference\n"
            "      - information_ref: evidence.scan-output\n"
            "        boundary_class: archival_evidence\n"
            "        disposition: evidence_only\n"
            "        visibility_basis: archival run evidence reference\n"
            "        evidence_refs: [evidence.scan-output]",
        )
        .replace(
            "        evidence_refs: [evidence.scan-output]\n"
            "        certainty: high\n"
            "        latency_profile: terminal observation latency",
            "        evidence_refs: [evidence.scan-output]\n"
            "        certainty: high\n"
            "        latency_profile: terminal observation latency\n"
            "      - transition_id: infer-http-service\n"
            "        transition_kind: inference\n"
            "        information_ref: nodes.web.services.http\n"
            "        trigger: interpret scan output\n"
            "        effective_from: episode-step:scan-0001:analysis\n"
            "        effective_order: 40\n"
            "        history_event_type: observation_emitted\n"
            "        action_instance_id: scan-0001\n"
            "        from_disposition: hidden\n"
            "        to_disposition: inferred\n"
            "        evidence_refs: [evidence.scan-output]\n"
            "        certainty: medium\n"
            "        latency_profile: participant analysis latency\n"
            "      - transition_id: conceal-http-service\n"
            "        transition_kind: concealment\n"
            "        information_ref: nodes.web.services.http\n"
            "        trigger: redacted follow-up observation\n"
            "        effective_from: episode-step:scan-0001:redacted-observation\n"
            "        effective_order: 50\n"
            "        history_event_type: observation_emitted\n"
            "        action_instance_id: scan-0001\n"
            "        from_disposition: inferred\n"
            "        to_disposition: concealed\n"
            "        evidence_refs: [evidence.scan-output]\n"
            "        certainty: medium\n"
            "        latency_profile: redaction latency",
        )
    )

    model = compile_runtime_model(parse_sdl(scenario))

    boundary = model.observation_boundaries[OBSERVATION_ADDRESS]
    assert boundary.inferred_refs == ()
    assert boundary.concealed_refs == ()
    assert boundary.view_relation_timeline[2]["transition_id"] == "infer-http-service"
    assert boundary.view_relation_timeline[2]["view_relation"]["nodes.web.services.http"] == "inferred"
    assert boundary.view_relation_timeline[3]["transition_id"] == "conceal-http-service"
    assert boundary.view_relation_timeline[3]["view_relation"]["nodes.web.services.http"] == "concealed"


def test_hidden_truth_cannot_be_observed_without_explicit_disclosure_rule():
    scenario = _scenario_yaml().replace(
        "observable_refs: []",
        "observable_refs: [content.private-answer-key]",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert (
        "hidden_refs must not also be observable_refs; use a disclosed view_rule instead: content.private-answer-key"
    ) in str(excinfo.value)


def test_evidence_only_refs_cannot_be_boundary_observable_refs():
    scenario = _scenario_yaml().replace(
        "observable_refs: []",
        "observable_refs: [evidence.scan-output]",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert (
        "evidence_only refs must not also be observable_refs; use evidence_refs instead: evidence.scan-output"
        in str(excinfo.value)
    )


def test_hidden_truth_disclosure_is_separate_from_observable_projection():
    scenario = _scenario_yaml().replace(
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency",
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency\n"
        "      - transition_id: disclose-answer-key\n"
        "        transition_kind: disclosure\n"
        "        information_ref: content.private-answer-key\n"
        "        trigger: episode close adjudication\n"
        "        effective_from: episode-close\n"
        "        effective_order: 100\n"
        "        history_event_type: episode_close\n"
        "        from_disposition: hidden\n"
        "        to_disposition: disclosed\n"
        "        disclosure_rule: reveal answer key after episode close\n"
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: post-run adjudication latency\n"
        "        realized_backend_disclosure: emitted only in post-run adjudication view",
    )

    model = compile_runtime_model(parse_sdl(scenario))

    boundary = model.observation_boundaries[OBSERVATION_ADDRESS]
    assert "content.private-answer-key" not in boundary.observable_refs
    assert boundary.disclosed_refs == ()
    assert boundary.view_transitions[1]["transition_kind"] == "disclosure"
    assert boundary.view_relation_timeline[2]["view_relation"]["content.private-answer-key"] == "disclosed"
    assert "content.private-answer-key" in boundary.view_relation_timeline[2]["disclosed_refs"]


def test_hidden_truth_disclosure_does_not_make_observable_refs_safe():
    scenario = _scenario_yaml()
    scenario = scenario.replace(
        "observable_refs: []",
        "observable_refs: [content.private-answer-key]",
    ).replace(
        "      - information_ref: content.private-answer-key\n"
        "        boundary_class: private_answer_key\n"
        "        disposition: hidden\n"
        "        visibility_basis: adjudication-only hidden truth",
        "      - information_ref: content.private-answer-key\n"
        "        boundary_class: private_answer_key\n"
        "        disposition: disclosed\n"
        "        visibility_basis: explicit evaluator disclosure\n"
        "        disclosure_rule: reveal answer key after episode close",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "hidden_refs must not also be observable_refs" in str(excinfo.value)


def test_private_answer_key_view_rule_requires_disclosure_rule_when_exposed():
    scenario = _scenario_yaml().replace(
        "      - information_ref: content.private-answer-key\n"
        "        boundary_class: private_answer_key\n"
        "        disposition: hidden\n"
        "        visibility_basis: adjudication-only hidden truth",
        "      - information_ref: content.private-answer-key\n"
        "        boundary_class: private_answer_key\n"
        "        disposition: disclosed\n"
        "        visibility_basis: explicit evaluator disclosure",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "disclosed view rules require an explicit disclosure_rule" in str(excinfo.value)


def test_disclosure_transition_requires_disclosure_rule():
    scenario = _scenario_yaml().replace(
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency",
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency\n"
        "      - transition_id: disclose-answer-key\n"
        "        transition_kind: disclosure\n"
        "        information_ref: content.private-answer-key\n"
        "        trigger: episode close adjudication\n"
        "        effective_from: episode-close\n"
        "        effective_order: 100\n"
        "        history_event_type: episode_close\n"
        "        from_disposition: hidden\n"
        "        to_disposition: disclosed\n"
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: post-run adjudication latency",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "disclosure transitions require disclosure_rule" in str(excinfo.value)


def test_transition_from_disposition_must_match_initial_view_rule():
    scenario = _scenario_yaml().replace(
        "      - information_ref: nodes.web\n"
        "        boundary_class: observable_resource\n"
        "        disposition: hidden\n"
        "        visibility_basis: service is not known before terminal scan output",
        "      - information_ref: nodes.web\n"
        "        boundary_class: observable_resource\n"
        "        disposition: observable\n"
        "        visibility_basis: incorrectly declared initially visible",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert (
        "view_transition 'discover-web-service' from_disposition does not match current disposition for nodes.web"
        in str(excinfo.value)
    )


def test_sensitive_view_rule_cannot_be_directly_observable():
    scenario = _scenario_yaml().replace(
        "      - information_ref: content.private-answer-key\n"
        "        boundary_class: private_answer_key\n"
        "        disposition: hidden\n"
        "        visibility_basis: adjudication-only hidden truth",
        "      - information_ref: content.private-answer-key\n"
        "        boundary_class: private_answer_key\n"
        "        disposition: observable\n"
        "        visibility_basis: adjudication-only hidden truth",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "private_answer_key must use disposition disclosed, not observable" in str(excinfo.value)


def test_hidden_truth_view_rule_cannot_be_directly_observable():
    scenario = (
        _scenario_yaml()
        .replace(
            "        boundary_class: private_answer_key",
            "        boundary_class: hidden_truth",
        )
        .replace(
            "        disposition: hidden",
            "        disposition: observable",
        )
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "hidden_truth must use disposition disclosed, not observable" in str(excinfo.value)


def test_sensitive_inference_transition_requires_disclosure_rule():
    scenario = _scenario_yaml().replace(
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency",
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency\n"
        "      - transition_id: infer-answer-key\n"
        "        transition_kind: inference\n"
        "        information_ref: content.private-answer-key\n"
        "        trigger: leaked benchmark clue\n"
        "        effective_from: episode-step:scan-0001:leak\n"
        "        effective_order: 40\n"
        "        history_event_type: observation_emitted\n"
        "        action_instance_id: scan-0001\n"
        "        from_disposition: hidden\n"
        "        to_disposition: inferred\n"
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: low\n"
        "        latency_profile: terminal observation latency",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "inference transitions exposing private_answer_key require disclosure_rule" in str(excinfo.value)


def test_hidden_truth_evidence_reference_requires_evidence_only_rule():
    scenario = _scenario_yaml().replace(
        "evidence_refs: [evidence.scan-output]",
        "evidence_refs: [evidence.scan-output, content.private-answer-key]",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert (
        "hidden_refs may only appear in evidence_refs through evidence_only view_rules: content.private-answer-key"
    ) in str(excinfo.value)


def test_view_rule_information_ref_must_be_declared_by_boundary_refs():
    scenario = _scenario_yaml().replace(
        "information_ref: nodes.web",
        "information_ref: nodes.db",
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(scenario)

    assert (
        "Observation boundary 'red-view' view_rule information_ref 'nodes.db' "
        "is not declared by observable_refs, hidden_refs, or evidence_refs"
    ) in str(excinfo.value)
    assert (
        "Observation boundary 'red-view' view_transition 'discover-web-service' "
        "information_ref 'nodes.db' is not declared by observable_refs, hidden_refs, or evidence_refs"
    ) in str(excinfo.value)


def test_view_rule_evidence_ref_must_be_declared_by_boundary_evidence_refs():
    scenario = _scenario_yaml().replace(
        "      - information_ref: evidence.scan-output\n"
        "        boundary_class: archival_evidence\n"
        "        disposition: evidence_only\n"
        "        visibility_basis: archival run evidence reference\n"
        "        evidence_refs: [evidence.scan-output]",
        "      - information_ref: evidence.scan-output\n"
        "        boundary_class: archival_evidence\n"
        "        disposition: evidence_only\n"
        "        visibility_basis: archival run evidence reference\n"
        "        evidence_refs: [evidence.missing]",
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(scenario)

    assert (
        "Observation boundary 'red-view' view_rule evidence_ref 'evidence.missing' is not declared by evidence_refs"
    ) in str(excinfo.value)


def test_view_transition_evidence_ref_must_be_declared_by_boundary_evidence_refs():
    scenario = _scenario_yaml().replace(
        "        evidence_refs: [evidence.scan-output]\n        certainty: high",
        "        evidence_refs: [evidence.missing]\n        certainty: high",
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(scenario)

    assert (
        "Observation boundary 'red-view' view_transition 'discover-web-service' "
        "evidence_ref 'evidence.missing' is not declared by evidence_refs"
    ) in str(excinfo.value)


def test_view_transition_to_disposition_must_match_transition_kind():
    scenario = _scenario_yaml().replace(
        "        to_disposition: discovered",
        "        to_disposition: inferred",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "discovery transitions require to_disposition in: discovered" in str(excinfo.value)


def test_view_transition_requires_matching_view_rule():
    scenario = (
        _scenario_yaml()
        .replace(
            "hidden_refs: [nodes.web, content.private-answer-key]",
            "hidden_refs: [nodes.web, content.private-answer-key, nodes.web.services.http]",
        )
        .replace(
            "        evidence_refs: [evidence.scan-output]\n"
            "        certainty: high\n"
            "        latency_profile: terminal observation latency",
            "        evidence_refs: [evidence.scan-output]\n"
            "        certainty: high\n"
            "        latency_profile: terminal observation latency\n"
            "      - transition_id: infer-http-service\n"
            "        transition_kind: inference\n"
            "        information_ref: nodes.web.services.http\n"
            "        trigger: interpret scan output\n"
            "        effective_from: episode-step:scan-0001:analysis\n"
            "        effective_order: 40\n"
            "        history_event_type: observation_emitted\n"
            "        action_instance_id: scan-0001\n"
            "        from_disposition: hidden\n"
            "        to_disposition: inferred\n"
            "        evidence_refs: [evidence.scan-output]\n"
            "        certainty: medium\n"
            "        latency_profile: participant analysis latency",
        )
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "view_transitions require matching view_rules: infer-http-service" in str(excinfo.value)


def test_view_rules_require_unique_information_refs():
    scenario = _scenario_yaml().replace(
        "      - information_ref: evidence.scan-output\n"
        "        boundary_class: archival_evidence\n"
        "        disposition: evidence_only\n"
        "        visibility_basis: archival run evidence reference\n"
        "        evidence_refs: [evidence.scan-output]",
        "      - information_ref: nodes.web\n"
        "        boundary_class: archival_evidence\n"
        "        disposition: evidence_only\n"
        "        visibility_basis: archival run evidence reference\n"
        "        evidence_refs: [evidence.scan-output]",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "view_rules require unique information_ref values: nodes.web" in str(excinfo.value)


def test_view_transitions_require_unique_transition_ids():
    scenario = _scenario_yaml().replace(
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency",
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency\n"
        "      - transition_id: discover-web-service\n"
        "        transition_kind: discovery\n"
        "        information_ref: nodes.web\n"
        "        trigger: duplicate scan terminal observation\n"
        "        effective_from: episode-step:scan-0001:duplicate-terminal-observation\n"
        "        effective_order: 31\n"
        "        history_event_type: observation_emitted\n"
        "        action_instance_id: scan-0001\n"
        "        from_disposition: hidden\n"
        "        to_disposition: discovered\n"
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "view_transitions require unique transition_id values: discover-web-service" in str(excinfo.value)


def test_view_transition_from_and_to_dispositions_must_differ():
    scenario = _scenario_yaml().replace(
        "        from_disposition: hidden\n        to_disposition: discovered",
        "        from_disposition: discovered\n        to_disposition: discovered",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "participant view transitions must alter disposition" in str(excinfo.value)


def test_view_transition_from_disposition_must_match_current_relation():
    scenario = _scenario_yaml().replace(
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency",
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency\n"
        "      - transition_id: conceal-web-service\n"
        "        transition_kind: concealment\n"
        "        information_ref: nodes.web\n"
        "        trigger: redacted scan follow-up\n"
        "        effective_from: episode-step:scan-0001:redacted-observation\n"
        "        effective_order: 40\n"
        "        history_event_type: observation_emitted\n"
        "        action_instance_id: scan-0001\n"
        "        from_disposition: hidden\n"
        "        to_disposition: concealed\n"
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: medium\n"
        "        latency_profile: redaction latency",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert (
        "view_transition 'conceal-web-service' from_disposition does not match current disposition for nodes.web"
        in str(excinfo.value)
    )


def test_view_transition_effective_order_drives_timeline_not_declaration_order():
    scenario = _scenario_yaml().replace(
        "      - transition_id: discover-web-service\n",
        "      - transition_id: infer-web-service\n"
        "        transition_kind: inference\n"
        "        information_ref: nodes.web\n"
        "        trigger: participant interprets terminal scan observation\n"
        "        effective_from: episode-step:scan-0001:analysis\n"
        "        effective_order: 40\n"
        "        history_event_type: observation_emitted\n"
        "        action_instance_id: scan-0001\n"
        "        from_disposition: discovered\n"
        "        to_disposition: inferred\n"
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: medium\n"
        "        latency_profile: participant analysis latency\n"
        "      - transition_id: discover-web-service\n",
    )

    model = compile_runtime_model(parse_sdl(scenario))

    boundary = model.observation_boundaries[OBSERVATION_ADDRESS]
    assert [transition["transition_id"] for transition in boundary.view_transitions] == [
        "discover-web-service",
        "infer-web-service",
    ]
    assert [snapshot["transition_id"] for snapshot in boundary.view_relation_timeline] == [
        "initial",
        "discover-web-service",
        "infer-web-service",
    ]


def test_view_transitions_require_unique_effective_order_values():
    scenario = _scenario_yaml().replace(
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency",
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency\n"
        "      - transition_id: duplicate-effective-order\n"
        "        transition_kind: discovery\n"
        "        information_ref: nodes.web\n"
        "        trigger: duplicate scan terminal observation\n"
        "        effective_from: episode-step:scan-0001:duplicate-terminal-observation\n"
        "        effective_order: 30\n"
        "        history_event_type: observation_emitted\n"
        "        action_instance_id: scan-0001\n"
        "        from_disposition: hidden\n"
        "        to_disposition: discovered\n"
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "view_transitions require unique effective_order values: 30" in str(excinfo.value)


def test_view_transitions_require_evidence_certainty_and_latency():
    scenario = _scenario_yaml().replace(
        "        to_disposition: discovered\n"
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency",
        "        to_disposition: discovered\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency",
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "participant view transitions require evidence_refs" in str(excinfo.value)


def test_coordination_interactions_require_related_actions():
    scenario = (
        _scenario_yaml()
        .replace(
            "interaction_class: shared_state_change",
            "interaction_class: coordination",
        )
        .replace(
            "        shared_state_refs: [nodes.web.services.http]\n",
            "",
        )
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "coordination interactions require related_actions" in str(excinfo.value)


def test_contention_interactions_require_shared_state_refs():
    scenario = (
        _scenario_yaml()
        .replace(
            "interaction_class: shared_state_change",
            "interaction_class: contention",
        )
        .replace(
            "        shared_state_refs: [nodes.web.services.http]\n",
            "",
        )
    )

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "contention interactions require shared_state_refs" in str(excinfo.value)


def test_behavior_history_events_round_trip_with_compiled_addresses():
    event = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        actor_provenance="participant:red-agent",
        joint_action_set_id="joint-0001",
        realized_order=0,
        interaction_class=ParticipantInteractionClass.SHARED_STATE_CHANGE,
        shared_state_refs=("nodes.web.services.http",),
    )

    assert ParticipantBehaviorHistoryEvent.from_payload(event.to_payload()) == event

    with pytest.raises(ValueError, match="compiled participant action contract address"):
        ParticipantBehaviorHistoryEvent(
            event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
            timestamp=T0,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id="episode-1",
            action_instance_id=ACTION_INSTANCE,
            action_contract_address="scan",
            actor_provenance="participant:red-agent",
        )


def test_behavior_history_requires_realized_order_for_joint_action_sets():
    with pytest.raises(ValueError, match="joint_action_set_id requires realized_order"):
        ParticipantBehaviorHistoryEvent(
            event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
            timestamp=T0,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id="episode-1",
            action_instance_id=ACTION_INSTANCE,
            action_contract_address=ACTION_ADDRESS,
            actor_provenance="participant:red-agent",
            joint_action_set_id="joint-0001",
        )


def test_behavior_history_requires_shared_state_refs_for_shared_state_interactions():
    with pytest.raises(ValueError, match="shared_state_change events require shared_state_refs"):
        ParticipantBehaviorHistoryEvent(
            event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
            timestamp=T0,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id="episode-1",
            action_instance_id=ACTION_INSTANCE,
            action_contract_address=ACTION_ADDRESS,
            actor_provenance="participant:red-agent",
            joint_action_set_id="joint-0001",
            realized_order=0,
            interaction_class=ParticipantInteractionClass.SHARED_STATE_CHANGE,
        )


def test_behavior_history_payload_rejects_string_shared_state_refs():
    payload = {
        "event_type": "action_attempted",
        "timestamp": T0,
        "participant_address": PARTICIPANT_ADDRESS,
        "episode_id": "episode-1",
        "action_instance_id": ACTION_INSTANCE,
        "action_contract_address": ACTION_ADDRESS,
        "actor_provenance": "participant:red-agent",
        "joint_action_set_id": "joint-0001",
        "realized_order": 0,
        "interaction_class": "shared_state_change",
        "shared_state_refs": "nodes.web.services.http",
    }

    with pytest.raises(TypeError, match="shared_state_refs must be a list of strings"):
        ParticipantBehaviorHistoryEvent.from_payload(payload)


def test_behavior_history_requires_terminal_observation_for_action_instance():
    action = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        actor_provenance="participant:red-agent",
    )

    violations = list(
        iter_participant_behavior_history_violations(
            [action.to_payload()],
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses={ACTION_ADDRESS},
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
        )
    )

    assert violations == [
        (
            ACTION_INSTANCE,
            "participant action instance requires exactly one terminal observation or orphaned-action observation",
        )
    ]


def test_behavior_history_pairs_state_transition_and_terminal_observation():
    action = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        actor_provenance="participant:red-agent",
    )
    transition = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.STATE_TRANSITION_RECORDED,
        timestamp=T1,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        state_transition_kind="participant_knowledge_expanded",
        post_state_digest=POST_STATE_DIGEST,
    )
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T2,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.TERMINAL,
        post_state_digest=POST_STATE_DIGEST,
    )

    assert (
        list(
            iter_participant_behavior_history_violations(
                [action.to_payload(), transition.to_payload(), observation.to_payload()],
                address_scope=ParticipantHistoryAddressScope(
                    action_contract_addresses={ACTION_ADDRESS},
                    observation_boundary_addresses={OBSERVATION_ADDRESS},
                ),
            )
        )
        == []
    )


def test_behavior_history_rejects_observation_details_that_expose_hidden_truth():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    events = _complete_behavior_history_payloads(ACTION_INSTANCE)
    events[2]["details"] = {
        "visible_refs": ["nodes.web", "content.private-answer-key"],
        "evidence_refs": ["evidence.scan-output"],
    }

    violations = list(
        iter_participant_behavior_history_violations(
            events,
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses={ACTION_ADDRESS},
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            observation_boundaries=model.observation_boundaries,
            participant_episode_history=_completed_episode_history_payloads(),
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            (
                "observation visible_refs may only contain participant-visible refs at effective_order 30: "
                "'content.private-answer-key' has disposition 'hidden'"
            ),
        )
    ]


def test_behavior_history_rejects_future_episode_close_disclosure_in_observation_details():
    scenario = _scenario_yaml().replace(
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency",
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency\n"
        "      - transition_id: disclose-answer-key\n"
        "        transition_kind: disclosure\n"
        "        information_ref: content.private-answer-key\n"
        "        trigger: episode close adjudication\n"
        "        effective_from: episode-close\n"
        "        effective_order: 100\n"
        "        history_event_type: episode_close\n"
        "        from_disposition: hidden\n"
        "        to_disposition: disclosed\n"
        "        disclosure_rule: reveal answer key after episode close\n"
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: post-run adjudication latency",
    )
    model = compile_runtime_model(parse_sdl(scenario))
    events = _complete_behavior_history_payloads(ACTION_INSTANCE)
    events[2]["details"] = {"visible_refs": ["content.private-answer-key"]}

    violations = list(
        iter_participant_behavior_history_violations(
            events,
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses={ACTION_ADDRESS},
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            observation_boundaries=model.observation_boundaries,
            participant_episode_history=_completed_episode_history_payloads(),
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            (
                "observation visible_refs may only contain participant-visible refs at effective_order 30: "
                "'content.private-answer-key' has disposition 'hidden'"
            ),
        )
    ]


def test_behavior_history_rejects_unresolved_episode_close_transition_anchor():
    scenario = _scenario_yaml().replace(
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency",
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: terminal observation latency\n"
        "      - transition_id: disclose-answer-key\n"
        "        transition_kind: disclosure\n"
        "        information_ref: content.private-answer-key\n"
        "        trigger: episode close adjudication\n"
        "        effective_from: episode-close\n"
        "        effective_order: 100\n"
        "        history_event_type: episode_close\n"
        "        from_disposition: hidden\n"
        "        to_disposition: disclosed\n"
        "        disclosure_rule: reveal answer key after episode close\n"
        "        evidence_refs: [evidence.scan-output]\n"
        "        certainty: high\n"
        "        latency_profile: post-run adjudication latency",
    )
    model = compile_runtime_model(parse_sdl(scenario))

    violations = list(
        iter_participant_behavior_history_violations(
            _complete_behavior_history_payloads(ACTION_INSTANCE),
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses={ACTION_ADDRESS},
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            observation_boundaries=model.observation_boundaries,
            participant_episode_history=[],
        )
    )

    assert violations == [
        (
            "participant.observation-boundary.red-view.view_transitions.disclose-answer-key",
            "visibility transition anchor does not resolve to a terminal participant episode history event",
        )
    ]


def test_behavior_history_does_not_import_unanchored_lower_order_transition_snapshot():
    boundary = ParticipantObservationBoundaryRuntime(
        address=OBSERVATION_ADDRESS,
        name="red-view",
        boundary_name="red-view",
        projection_basis="participant-local projection over observed services",
        hidden_refs=("content.private-answer-key", "nodes.web"),
        evidence_refs=("evidence.scan-output",),
        view_transitions=(
            {
                "transition_id": "disclose-answer-key",
                "history_event_type": "observation_emitted",
                "action_instance_id": "late-scan",
                "information_ref": "content.private-answer-key",
                "from_disposition": "hidden",
                "to_disposition": "disclosed",
                "effective_order": 10,
            },
            {
                "transition_id": "discover-web-service",
                "history_event_type": "observation_emitted",
                "action_instance_id": "early-scan",
                "information_ref": "nodes.web",
                "from_disposition": "hidden",
                "to_disposition": "discovered",
                "effective_order": 20,
            },
        ),
        view_relation_timeline=(
            {
                "transition_id": "initial",
                "effective_order": -1,
                "view_relation": {
                    "content.private-answer-key": "hidden",
                    "nodes.web": "hidden",
                },
            },
            {
                "transition_id": "disclose-answer-key",
                "effective_order": 10,
                "view_relation": {
                    "content.private-answer-key": "disclosed",
                    "nodes.web": "hidden",
                },
            },
            {
                "transition_id": "discover-web-service",
                "effective_order": 20,
                "view_relation": {
                    "content.private-answer-key": "disclosed",
                    "nodes.web": "discovered",
                },
            },
        ),
        spec={},
    )
    events = [
        *_complete_behavior_history_payloads("early-scan"),
        *_complete_behavior_history_payloads("late-scan"),
    ]
    events[2]["details"] = {"visible_refs": ["content.private-answer-key", "nodes.web"]}

    violations = list(
        iter_participant_behavior_history_violations(
            events,
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses={ACTION_ADDRESS},
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            observation_boundaries={OBSERVATION_ADDRESS: boundary},
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            (
                "observation visible_refs may only contain participant-visible refs at effective_order 20: "
                "'content.private-answer-key' has disposition 'hidden'"
            ),
        )
    ]


def test_behavior_history_rejects_nested_observation_details_payload_side_channel():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    events = _complete_behavior_history_payloads(ACTION_INSTANCE)
    events[2]["details"] = {"payload": {"visible_refs": ["content.private-answer-key"]}}

    violations = list(
        iter_participant_behavior_history_violations(
            events,
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses={ACTION_ADDRESS},
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            observation_boundaries=model.observation_boundaries,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "observation details may only contain visible_refs, disclosed_refs, evidence_refs; unsupported fields: payload",
        )
    ]


def test_behavior_history_rejects_caller_supplied_observation_effective_order():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    events = _complete_behavior_history_payloads(ACTION_INSTANCE)
    events[2]["details"] = {
        "effective_order": 100,
        "visible_refs": ["nodes.web"],
    }

    violations = list(
        iter_participant_behavior_history_violations(
            events,
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses={ACTION_ADDRESS},
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            observation_boundaries=model.observation_boundaries,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            (
                "observation details may only contain visible_refs, disclosed_refs, evidence_refs; "
                "unsupported fields: effective_order"
            ),
        )
    ]


def test_behavior_history_rejects_details_on_non_observation_events():
    events = _complete_behavior_history_payloads(ACTION_INSTANCE)
    events[0]["details"] = {"visible_refs": ["nodes.web"]}

    violations = list(
        iter_participant_behavior_history_violations(
            events,
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses={ACTION_ADDRESS},
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[0]",
            "participant behavior details are only allowed on observation_emitted events",
        )
    ]


def test_behavior_history_rejects_unresolved_visibility_transition_anchor():
    scenario = _scenario_yaml().replace("action_instance_id: scan-0001", "action_instance_id: scan-9999")
    model = compile_runtime_model(parse_sdl(scenario))

    violations = list(
        iter_participant_behavior_history_violations(
            _complete_behavior_history_payloads(ACTION_INSTANCE),
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses={ACTION_ADDRESS},
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            observation_boundaries=model.observation_boundaries,
        )
    )

    assert violations == [
        (
            "participant.observation-boundary.red-view.view_transitions.discover-web-service",
            "visibility transition anchor does not resolve to an observation_emitted event",
        )
    ]


def test_behavior_history_rejects_duplicate_realized_order_in_joint_action_set():
    events = [
        *_complete_behavior_history_payloads("scan-0001", realized_order=0),
        *_complete_behavior_history_payloads("scan-0002", realized_order=0),
    ]

    violations = list(
        iter_participant_behavior_history_violations(
            events,
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses={ACTION_ADDRESS},
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
        )
    )

    assert violations == [
        (
            "joint-action-set.joint-0001",
            (
                "joint action set realized_order 0 is assigned to multiple action_attempted events: "
                f"{PARTICIPANT_ADDRESS}/scan-0001, {PARTICIPANT_ADDRESS}/scan-0002"
            ),
        )
    ]


def test_behavior_history_rejects_state_transition_observation_digest_mismatch():
    action = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        actor_provenance="participant:red-agent",
    )
    transition = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.STATE_TRANSITION_RECORDED,
        timestamp=T1,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        state_transition_kind="participant_knowledge_expanded",
        post_state_digest=POST_STATE_DIGEST,
    )
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T2,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.TERMINAL,
        post_state_digest="sha256:different",
    )

    violations = list(
        iter_participant_behavior_history_violations(
            [action.to_payload(), transition.to_payload(), observation.to_payload()],
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses={ACTION_ADDRESS},
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
        )
    )

    assert violations == [
        (
            ACTION_INSTANCE,
            "terminal observation post_state_digest must match the state transition post_state_digest",
        )
    ]


def test_behavior_history_allows_orphaned_action_observation_without_state_digest():
    action = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        actor_provenance="participant:red-agent",
    )
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T2,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.ORPHANED_ACTION,
    )

    assert (
        list(
            iter_participant_behavior_history_violations(
                [action.to_payload(), observation.to_payload()],
                address_scope=ParticipantHistoryAddressScope(
                    action_contract_addresses={ACTION_ADDRESS},
                    observation_boundary_addresses={OBSERVATION_ADDRESS},
                ),
            )
        )
        == []
    )


def test_behavior_history_schema_is_published_as_closed_world_contract():
    generated = schema_bundle()

    schema = generated["participant-behavior-history-event-stream-v1"]
    event_schema = schema["items"]
    schema_defs = event_schema.get("$defs", schema.get("$defs", {}))
    details_schema = event_schema["properties"]["details"]
    if "$ref" in details_schema:
        details_schema = schema_defs[details_schema["$ref"].rsplit("/", 1)[-1]]

    assert event_schema["additionalProperties"] is False
    assert "ParticipantBehaviorHistoryEventModel" in event_schema["title"]
    assert "action_result" in event_schema["properties"]
    assert "ParticipantActionResultModel" in schema_defs
    assert details_schema["additionalProperties"] is False
    assert set(details_schema["properties"]) == {"visible_refs", "disclosed_refs", "evidence_refs"}

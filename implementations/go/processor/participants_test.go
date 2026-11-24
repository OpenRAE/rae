package processor_test

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestCompileActionContractCarriesGovernedShape(t *testing.T) {
	scenario, err := sdl.Parse([]byte(`name: actions
action_contracts:
  probe:
    semantic_version: 1.0.0
    lifecycle_state: active
    behavioral_granularity: atomic
    procedure_basis: declared probe
    realization_profile: backend-declared
    fidelity_claim: records declared intent
    preconditions:
      - {precondition_id: available, precondition_class: target, description: target available, support_refs: [backend.target]}
    effects:
      - {effect_id: observe, effect_class: observation_effect, description: emits observation, evidence_refs: [evidence.output]}
    failure_classes: [unknown, timeout]
`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	resources := compiled.Model().View().ParticipantResources
	if len(resources) != 1 {
		t.Fatalf("participant resources = %d", len(resources))
	}
	if resources[0].Kind != "action-contract" || resources[0].Address != "participant.action-contract.probe" {
		t.Fatalf("action identity = %#v", resources[0])
	}
	var action struct {
		ArgumentShapeRef    string   `json:"argument_shape_ref"`
		PreconditionClasses []string `json:"precondition_classes"`
		EffectClasses       []string `json:"effect_classes"`
		FailureClasses      []string `json:"failure_classes"`
	}
	if err := json.Unmarshal(resources[0].Payload.JSON(), &action); err != nil {
		t.Fatal(err)
	}
	const expected = "participant.action-contract.probe.argument-shape.sha256-44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
	if action.ArgumentShapeRef != expected || len(action.PreconditionClasses) != 1 || action.PreconditionClasses[0] != "target" || action.EffectClasses[0] != "observation_effect" || len(action.FailureClasses) != 2 {
		t.Fatalf("action projection = %#v", action)
	}
}

func TestCompileObservationTimelinePreservesCanonicalVisibility(t *testing.T) {
	scenario, err := sdl.Parse([]byte(`name: visibility
nodes:
  server: {type: compute}
observation_boundaries:
  view:
    projection_basis: participant-local projection
    observable_refs: []
    hidden_refs: [nodes.server]
    evidence_refs: [evidence.output]
    redaction_policy: explicit disclosure
    latency_profile: terminal observation
    view_rules:
      - {information_ref: nodes.server, boundary_class: observable_resource, disposition: hidden, visibility_basis: initially concealed}
    view_transitions:
      - transition_id: discover
        transition_kind: discovery
        information_ref: nodes.server
        trigger: terminal observation
        effective_from: episode-step:probe:terminal-observation
        effective_order: 30
        history_event_type: observation_emitted
        action_instance_id: probe
        from_disposition: hidden
        to_disposition: discovered
        evidence_refs: [evidence.output]
        certainty: high
        latency_profile: terminal observation
`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	resources := compiled.Model().View().ParticipantResources
	if len(resources) != 1 {
		t.Fatalf("participant resources = %d", len(resources))
	}
	var boundary struct {
		HiddenRefs           []string            `json:"hidden_refs"`
		ReferenceAliases     map[string][]string `json:"reference_aliases"`
		ViewRelationTimeline []struct {
			TransitionID string            `json:"transition_id"`
			ViewRelation map[string]string `json:"view_relation"`
			VisibleRefs  []string          `json:"visible_refs"`
		} `json:"view_relation_timeline"`
	}
	if err := json.Unmarshal(resources[0].Payload.JSON(), &boundary); err != nil {
		t.Fatal(err)
	}
	if len(boundary.HiddenRefs) != 1 || boundary.HiddenRefs[0] != "provision.node.server" || len(boundary.ViewRelationTimeline) != 2 {
		t.Fatalf("boundary = %#v", boundary)
	}
	if len(boundary.ViewRelationTimeline[0].VisibleRefs) != 0 || boundary.ViewRelationTimeline[1].ViewRelation["provision.node.server"] != "discovered" || boundary.ViewRelationTimeline[1].VisibleRefs[0] != "provision.node.server" {
		t.Fatal("view transition changed initial visibility or canonical identity")
	}
	if boundary.ReferenceAliases["nodes.server"][0] != "provision.node.server" {
		t.Fatal("missing canonical visibility alias")
	}
}

func TestCompileParticipantUsesOwnerScopeAndRole(t *testing.T) {
	scenario, err := sdl.Parse([]byte(`name: participant
nodes:
  server: {type: compute, services: [{name: http, port: 80}]}
entities:
  team: {role: red}
agents:
  actor:
    affiliations: [team]
    authority_anchors: [nodes.server]
    operating_scope: [http]
    initial_knowledge: {hosts: [server], services: [http]}
    interactive_access:
      terminal: {target_ref: server, channel: ssh}
`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	var participant processor.Resource
	for _, resource := range compiled.Model().View().ParticipantResources {
		if resource.Kind == "participant-behavior" {
			participant = resource
		}
	}
	var payload struct {
		Role                      string   `json:"role"`
		OperatingScopeAddresses   []string `json:"operating_scope_addresses"`
		AuthorityAnchorAddresses  []string `json:"authority_anchor_addresses"`
		InitialKnowledgeAddresses []string `json:"initial_knowledge_addresses"`
	}
	if err := json.Unmarshal(participant.Payload.JSON(), &payload); err != nil {
		t.Fatal(err)
	}
	if payload.Role != "red" || len(payload.OperatingScopeAddresses) != 1 || payload.OperatingScopeAddresses[0] != "provision.node.server.service.http" || len(payload.AuthorityAnchorAddresses) != 1 || len(payload.InitialKnowledgeAddresses) != 2 {
		t.Fatalf("participant facts = %#v", payload)
	}
	if len(participant.OrderingDependencies) != 0 || len(participant.RefreshDependencies) != 2 {
		t.Fatalf("participant dependencies = %v / %v", participant.OrderingDependencies, participant.RefreshDependencies)
	}
}

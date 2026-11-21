package runtime_test

import (
	"encoding/json"
	"maps"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
)

func participantInput(t *testing.T) runtimecontract.ParticipantActionInput {
	t.Helper()
	raw, err := os.ReadFile("testdata/participant-binding.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Manifest  binding.ParticipantImplementationManifestV1 `json:"manifest"`
		Selection map[string]any                              `json:"selection"`
	}
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	selection, err := admission.AdmitFragment(owner, admission.ParticipantImplementationSelection, fixture.Selection, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	return runtimecontract.ParticipantActionInput{ParticipantAddress: "participant.behavior.agent", ActionContractAddress: "participant.action-contract.scan", ObservationBoundaryAddress: "participant.observation-boundary.agent", ActionInstanceID: "action-1", ImplementationManifest: fixture.Manifest, ImplementationSelection: selection, StateTransitionKind: "participant_action_admitted"}
}

func TestParticipantBindingOwnsInputAndEnforcesExposure(t *testing.T) {
	input := participantInput(t)
	input.TargetAddresses = []string{"provision.node.vm"}
	request, err := runtimecontract.BindParticipantAction(input)
	if err != nil {
		t.Fatal(err)
	}
	input.TargetAddresses[0] = "changed"
	first := request.Input()
	if first.TargetAddresses[0] != "provision.node.vm" {
		t.Fatal("input alias retained")
	}
	first.TargetAddresses[0] = "changed-again"
	if request.Input().TargetAddresses[0] != "provision.node.vm" {
		t.Fatal("readback alias retained")
	}
	for _, alter := range []func(*runtimecontract.ParticipantActionInput){
		func(x *runtimecontract.ParticipantActionInput) { x.ParticipantAddress = "other" },
		func(x *runtimecontract.ParticipantActionInput) { x.ActionContractAddress = "scan" },
		func(x *runtimecontract.ParticipantActionInput) {
			x.EvidenceRefs = []string{"content.evaluator-notes"}
			x.ObservationBoundaryEvidenceRefs = []string{"content.evaluator-notes"}
		},
		func(x *runtimecontract.ParticipantActionInput) { x.VisibleRefs = []string{"private"} },
		func(x *runtimecontract.ParticipantActionInput) { x.DisclosedRefs = []string{"private"} },
		func(x *runtimecontract.ParticipantActionInput) { s := "scope"; x.ExecutionScopeRef = &s },
		func(x *runtimecontract.ParticipantActionInput) { x.TargetAddresses = []string{"same", "same"} },
	} {
		candidate := request.Input()
		alter(&candidate)
		if _, err := runtimecontract.BindParticipantAction(candidate); err == nil {
			t.Fatal("invalid binding accepted")
		}
	}
}

type foreignSelection struct{ admission.Fragment }

func (foreignSelection) Document() any { panic("foreign selection invoked") }
func TestParticipantBindingRejectsForeignFragmentsBeforeCallbacks(t *testing.T) {
	input := participantInput(t)
	input.ImplementationSelection = foreignSelection{input.ImplementationSelection}
	if _, err := runtimecontract.BindParticipantAction(input); err == nil {
		t.Fatal("foreign selection accepted")
	}
}

type foreignAction struct {
	runtimecontract.ParticipantActionRequest
}

func (foreignAction) Input() runtimecontract.ParticipantActionInput { panic("foreign action invoked") }
func TestParticipantActionReaderRejectsForeignHandles(t *testing.T) {
	if _, err := runtimecontract.ParticipantActionInputFor(foreignAction{}); err == nil {
		t.Fatal("foreign request accepted")
	}
	request, err := runtimecontract.BindParticipantAction(participantInput(t))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := runtimecontract.ParticipantActionInputFor(request); err != nil {
		t.Fatal(err)
	}
}

func TestParticipantBindingChecksNestedEvidenceAndTemporalIdentity(t *testing.T) {
	input := participantInput(t)
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	result := map[string]any{"status": "succeeded", "participant_address": input.ParticipantAddress, "episode_id": "episode", "action_instance_id": input.ActionInstanceID, "action_contract_address": input.ActionContractAddress, "observation_point": "observed"}
	input.ActionResult = admitParticipantFragment(t, owner, admission.ParticipantActionResult, result)
	if _, err := runtimecontract.BindParticipantAction(input); err != nil {
		t.Fatal(err)
	}
	for _, field := range []string{"participant_address", "action_instance_id", "action_contract_address"} {
		candidate := maps.Clone(result)
		candidate[field] = "different"
		altered := input
		altered.ActionResult = admitParticipantFragment(t, owner, admission.ParticipantActionResult, candidate)
		if _, err := runtimecontract.BindParticipantAction(altered); err == nil {
			t.Fatal("mismatched action identity accepted", field)
		}
	}
	result["evidence_refs"] = []any{"unbound-evidence"}
	input.ActionResult = admitParticipantFragment(t, owner, admission.ParticipantActionResult, result)
	if _, err := runtimecontract.BindParticipantAction(input); err == nil {
		t.Fatal("unbound nested evidence accepted")
	}
	input.ActionResult = nil
	context := admitParticipantFragment(t, owner, admission.ParticipantTemporalContext, map[string]any{"temporal_contract_id": "temporal", "time_domain": "simulation_time", "clock_authority": "runtime", "event_points": []any{"observed"}, "observation_point": "observed"})
	input.TemporalContexts = []admission.Fragment{context, context}
	if _, err := runtimecontract.BindParticipantAction(input); err == nil {
		t.Fatal("duplicate temporal identity accepted")
	}
}

func admitParticipantFragment(t *testing.T, owner *admission.Validator, profile admission.FragmentProfile, document map[string]any) admission.Fragment { //nolint:ireturn // Test construction exercises the sealed public fragment boundary.
	t.Helper()
	fragment, err := admission.AdmitFragment(owner, profile, document, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	return fragment
}

package runtime

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func TestOperationOwnershipRejectsInvalidAuthorityAndBudgets(t *testing.T) {
	for _, operation := range []ProvisionOperation{
		{Address: "invalid", Action: "create"},
		{Address: "provision.node.vm", Action: "invoke"},
		{Address: "provision.node.vm", Action: "create", ExecutionPolicyScopes: make([]admission.Fragment, value.Runtime().MaxMembers+1)},
		{Address: "provision.node.vm", Action: "create", ExecutionPolicyScopes: []admission.Fragment{nil}},
		{Address: "provision.node.vm", Action: "create", Payload: map[string]any{"private": make(chan int)}},
	} {
		if _, err := ownOperations([]ProvisionOperation{operation}); err == nil {
			t.Fatal("invalid operation accepted", operation.Action)
		}
	}
	if _, err := ownOperations(make([]ProvisionOperation, value.Runtime().MaxMembers+1)); err == nil {
		t.Fatal("operation count budget bypassed")
	}
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	wrong, err := admission.AdmitFragment(owner, admission.RealizationValue, map[string]any{}, ingress.Limits{MaxBytes: 1024, MaxDepth: 8})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ownOperations([]ProvisionOperation{{Address: "provision.node.vm", Action: "create", ExecutionPolicy: wrong}}); err == nil {
		t.Fatal("wrong execution-policy profile accepted")
	}
	if _, err := ownedObject(map[string]any{"unsupported": make(chan int)}); err == nil {
		t.Fatal("foreign carrier accepted")
	}
}

func TestDiagnosticOwnershipCopiesRangesAndBoundsText(t *testing.T) {
	source := []diagnostic.Diagnostic{{Code: "refused", Message: "safe", Range: &diagnostic.Range{StartLine: 1, EndLine: 1}}}
	owned, err := ownDiagnostics(source)
	if err != nil {
		t.Fatal(err)
	}
	source[0].Range.StartLine = 9
	source[0].Message = "changed"
	if owned[0].Range.StartLine != 1 || owned[0].Message != "safe" {
		t.Fatal("diagnostic alias retained", owned)
	}
	if _, err := ownDiagnostics(make([]diagnostic.Diagnostic, value.Runtime().MaxMembers+1)); err == nil {
		t.Fatal("diagnostic count budget bypassed")
	}
	if _, err := ownDiagnostics([]diagnostic.Diagnostic{{Message: strings.Repeat("a", (8<<20)+1)}}); err == nil {
		t.Fatal("diagnostic text budget bypassed")
	}
}

func TestParticipantProofGroupsRequireMatchingContextAndBoundary(t *testing.T) {
	shared := map[string]any{"binding": map[string]any{"temporal_id": "time"}, "clock": "runtime"}
	proof := map[string]any{"context": shared, "observation_boundary_address": "participant.observation-boundary.agent"}
	if !participantProofGroupValid([]any{proof}, []map[string]any{shared}, "participant.observation-boundary.agent") {
		t.Fatal("matching temporal proof refused")
	}
	for _, test := range []struct {
		proofs   []any
		contexts []map[string]any
		boundary string
	}{
		{[]any{proof, proof}, []map[string]any{shared}, "participant.observation-boundary.agent"},
		{[]any{proof}, nil, "participant.observation-boundary.agent"},
		{[]any{proof}, []map[string]any{shared}, "participant.observation-boundary.other"},
	} {
		if participantProofGroupValid(test.proofs, test.contexts, test.boundary) {
			t.Fatal("unbound temporal proof accepted")
		}
	}
	result := map[string]any{"evidence_refs": []any{"outer"}, "preconditions": []any{map[string]any{"evidence_refs": []any{"pre"}}}, "effects": []any{map[string]any{"evidence_refs": []any{"effect"}}}, "temporal_evidence": []any{map[string]any{"evidence_refs": []any{"temporal"}}}}
	if refs := resultEvidence(result); len(refs) != 4 {
		t.Fatal("nested evidence omitted", refs)
	}
	input := ParticipantActionInput{VisibleRefs: []string{"visible"}, DisclosedRefs: []string{"disclosed"}, EvidenceRefs: []string{"proof"}, ObservationBoundaryEvidenceRefs: []string{"proof"}}
	selection := map[string]any{"exposure_policy": map[string]any{"disclosed_refs": []any{"disclosed"}, "visibility_scope_refs": []any{"visible"}}}
	if !participantExposureValid(input, selection) {
		t.Fatal("explicit exposure refused")
	}
	input.ObservationBoundaryEvidenceRefs = nil
	if participantExposureValid(input, selection) {
		t.Fatal("unbound evidence exposed")
	}
	input = ParticipantActionInput{ExecutionScopeRef: new(string), ExecutionGeneration: new(int64), PostStateDigest: new(string)}
	*input.ExecutionScopeRef, *input.ExecutionGeneration, *input.PostStateDigest = "scope", 5, "digest"
	retained := copyParticipantInput(input)
	*input.ExecutionScopeRef, *input.ExecutionGeneration, *input.PostStateDigest = "changed", 6, "changed"
	if *retained.ExecutionScopeRef != "scope" || *retained.ExecutionGeneration != 5 || *retained.PostStateDigest != "digest" {
		t.Fatal("generation or commitment pointers alias input")
	}
	if got := resultEvidence(map[string]any{"effects": []any{json.Number("1")}}); len(got) != 0 {
		t.Fatal("malformed row supplied evidence", got)
	}
}

func TestParticipantFragmentProfilesAndTemporalJoins(t *testing.T) {
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	admit := func(profile admission.FragmentProfile, document map[string]any) admission.Fragment {
		t.Helper()
		fragment, admitErr := admission.AdmitFragment(owner, profile, document, ingress.Limits{MaxBytes: 4096, MaxDepth: 32})
		if admitErr != nil {
			t.Fatal(admitErr)
		}
		return fragment
	}
	context := admit(admission.ParticipantTemporalContext, map[string]any{"temporal_contract_id": "temporal", "time_domain": "simulation_time", "clock_authority": "runtime", "event_points": []any{"observed"}, "observation_point": "observed"})
	input := ParticipantActionInput{TemporalContexts: []admission.Fragment{context}}
	if !participantTemporalValid(input) {
		t.Fatal("unambiguous temporal context refused")
	}
	input.ActionResult = admit(admission.ParticipantActionResult, map[string]any{"status": "succeeded", "participant_address": "participant.behavior.agent", "episode_id": "episode", "action_instance_id": "action", "action_contract_address": "participant.action-contract.scan", "observation_point": "end"})
	if participantTemporalValid(input) {
		t.Fatal("result from a different observation point accepted")
	}
	input.ActionResult = nil
	measurement := admit(admission.ParticipantResourceMeasurement, map[string]any{"budget_state_ref": "budget", "resource_kind": "inference_tokens", "unit": "tokens", "meter_profile_ref": "meter", "reserved": json.Number("1")})
	input.ResourceMeasurementRequirements = []admission.Fragment{measurement}
	if !participantTemporalValid(input) {
		t.Fatal("unique resource measurement refused")
	}
	input.ResourceMeasurementRequirements = append(input.ResourceMeasurementRequirements, measurement)
	if participantTemporalValid(input) {
		t.Fatal("duplicate budget identity accepted")
	}
	for _, candidate := range []ParticipantActionInput{
		{ImplementationSelection: context},
		{ImplementationSelection: nil, ActionResult: context},
	} {
		if checkParticipantFragments(candidate) == nil {
			t.Fatal("wrong-profile request accepted")
		}
	}
	if participantReferencesValid(ParticipantActionInput{VisibleRefs: make([]string, value.Runtime().MaxMembers+1)}) {
		t.Fatal("reference count budget bypassed")
	}
	empty := ""
	if participantIdentityValid(ParticipantActionInput{ParticipantAddress: "participant.behavior.agent", ActionContractAddress: "participant.action-contract.scan", ObservationBoundaryAddress: "participant.observation-boundary.agent", ActionInstanceID: "action", StateTransitionKind: "commit", PostStateDigest: &empty}) {
		t.Fatal("empty state commitment accepted")
	}
}

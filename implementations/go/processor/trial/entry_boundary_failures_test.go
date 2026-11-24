package trial

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestTrialEntryConstructionRefusesIncompleteSelectionAndCleanupAuthorities(t *testing.T) {
	for _, field := range []string{"assignment", "outcome", "family", "envelope", "capture-relations", "backend", "cleanup-bytes", "cleanup-shape", "factorial-shape", "cleanup-capability"} {
		t.Run(field, func(t *testing.T) { checkEntryConstructionBoundary(t, field) })
	}
}
func checkEntryConstructionBoundary(t *testing.T, field string) {
	t.Helper()
	request := compilerRequest(t, referenceCompilations(t)[0].Request)
	input, err := prepareInputs(request)
	if err != nil {
		t.Fatal(err)
	}
	coordinates, err := coordinates(input.spec, request.Limits)
	if err != nil {
		t.Fatal(err)
	}
	rows, err := selectionRows(request, input.spec, coordinates, input.family.Points)
	if err != nil {
		t.Fatal(err)
	}
	row := rows[0]
	switch field {
	case "assignment":
		request.RealizationAssignments = map[string]admission.Fragment{"foreign": nil}
	case "outcome":
		row.selections[0].Outcome = selectionOutcome{Kind: "literal", Value: json.RawMessage(`{`)}
	case "family":
		request.Family = nil
	case "envelope":
		input.envelope = binding.RealizationEnvelopeV1{}
	case "capture-relations":
		input.spec.RunPlan.EvidenceRelations = []json.RawMessage{json.RawMessage(`{`)}
	case "backend":
		for key := range input.backends {
			input.backends[key] = binding.BackendManifestV2{}
		}
	case "cleanup-bytes":
		input.authority.Cleanup = json.RawMessage(`{`)
	case "cleanup-shape":
		input.authority.Cleanup = json.RawMessage(`[]`)
	case "factorial-shape":
		input.spec.Factorial = json.RawMessage(`{`)
	case "cleanup-capability":
		removeEntryCleanupCapability(t, &input)
	}
	if _, _, _, err := compileEntry(t.Context(), request, input, "plan", coordinates[0], row); err == nil {
		t.Fatal("incomplete entry authority admitted")
	}
}
func removeEntryCleanupCapability(t *testing.T, input *compilationInputs) {
	t.Helper()
	for key, backend := range input.backends {
		raw, err := encoded(backend)
		if err != nil {
			t.Fatal(err)
		}
		var document map[string]any
		if decode(raw, &document) != nil {
			t.Fatal("backend fixture")
		}
		capabilities, ok := document["capabilities"].(map[string]any)
		if !ok {
			t.Fatal("backend capabilities missing")
		}
		capabilities["cleanup"] = nil
		raw, err = encoded(document)
		if err != nil {
			t.Fatal(err)
		}
		if decode(raw, &backend) != nil {
			t.Fatal("changed backend fixture")
		}
		input.backends[key] = backend
	}
}
func TestParallelScheduleAndAssignmentKeysRetainExactSealedAuthority(t *testing.T) {
	raw, err := readSealedFixture("../../../../contracts/fixtures/plans/admitted-trial-plan-v1/valid/two-entry.json")
	if err != nil {
		t.Fatal(err)
	}
	var plan binding.AdmittedTrialPlanV1
	if json.Unmarshal(raw, &plan) != nil {
		t.Fatal("parallel plan fixture")
	}
	schedule, err := PlanBatchSchedule(plan)
	if err != nil || schedule.AdmittedParallelismCeiling != 2 || len(schedule.Entries) != 2 {
		t.Fatal("sealed isolation ceiling lost", schedule, err)
	}
	owner, err := trialOwner()
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct{ input, expected string }{
		{`{"replicate_id":"replicate-000001"}`, `{"replicate_id":"replicate-000001"}`},
		{`{"block_id":null,"condition_id":"c","replicate_id":"replicate-000001"}`, `{"condition_id":"c","replicate_id":"replicate-000001"}`},
	} {
		var document any
		if decode([]byte(test.input), &document) != nil {
			t.Fatal("coordinate fixture")
		}
		fragment, admitErr := admission.AdmitFragment(owner, admission.RealizationValue, document, trialIngress())
		if admitErr != nil {
			t.Fatal(admitErr)
		}
		key, keyErr := RealizationAssignmentKey(fragment)
		if keyErr != nil || key != test.expected {
			t.Fatal("assignment key changed coordinate authority", key, keyErr)
		}
	}
}

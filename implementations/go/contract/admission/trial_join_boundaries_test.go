package admission

import (
	"context"
	"encoding/json"
	"maps"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestTrialRunJoinRefusesEveryForeignProvenancePin(t *testing.T) {
	owner := boundTestOwner(t)
	var reference struct {
		Plan  json.RawMessage
		Cases []trialRunReferenceCase
	}
	readFullReferenceJSON(t, "testdata/trial-run-reconciliation.json", &reference)
	for _, test := range []struct {
		name, target, field string
		value               any
	}{
		{"exact", "", "", nil},
		{"missing-provenance", "run", "trial_provenance", nil},
		{"plan", "provenance", "plan_id", "foreign"},
		{"plan-digest", "provenance", "plan_digest", "sha256:" + strings.Repeat("0", 64)},
		{"entry", "provenance", "plan_entry_id", "foreign"},
		{"admitted-run", "provenance", "admitted_run_id", "foreign"},
		{"run", "run", "run_id", "foreign"},
		{"snapshot", "snapshot", "ref_digest", "sha256:" + strings.Repeat("0", 64)},
		{"terminal-attempt", "provenance", "terminal_attempt_id", "foreign"},
		{"missing-controls", "run", "stochastic_controls", []any{}},
		{"extra-treatment", "run", "realized_selections", []any{map[string]any{"selection_id": "foreign"}}},
		{"terminal-status", "run", "run_status", "failed"},
	} {
		t.Run(test.name, func(t *testing.T) {
			plan := decodeRuleObject(t, string(reference.Plan))
			run := decodeRuleObject(t, string(reference.Cases[0].Run))
			targets := map[string]any{"run": run, "provenance": at(run, "trial_provenance"), "snapshot": at(run, "scenario_snapshot_ref")}
			if test.target != "" {
				object(targets[test.target])[test.field] = test.value
			}
			receipts := make([]any, len(reference.Cases[0].Receipts))
			for index, raw := range reference.Cases[0].Receipts {
				receipts[index] = decodeRuleObject(t, string(raw))
			}
			if err := owner.trialRunJoin(plan, run, receipts); (err == nil) != (test.name == "exact") {
				t.Fatal("provenance admission", err)
			}
		})
	}
}

func TestTrialParticipantReconciliationKeepsConfigurationAndBindingPins(t *testing.T) {
	owner := boundTestOwner(t)
	result, err := RealizeParticipantConfiguration(context.Background(), configurationRequestFixture(t))
	if err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	configuration := decodeRuleObject(t, string(raw))
	var reference struct {
		Cases []experimentEvidenceReferenceCase
	}
	readFullReferenceJSON(t, "testdata/experiment-evidence-reference.json", &reference)
	base := object(array(at(decodeRuleObject(t, string(reference.Cases[0].Run)), "participant_implementation_provenance", "participant_implementations"))[0])
	for _, field := range []string{"", "binding", "origin", "digest", "selection", "selection-authority"} {
		t.Run("pin-"+field, func(t *testing.T) {
			selection := maps.Clone(base)
			for _, key := range []string{"participant_address", "manifest_ref", "manifest_digest", "configuration_digest"} {
				selection[key] = at(configuration, key)
			}
			selection["configuration_ref"] = "configuration:reference"
			selection["implementation_identity"] = at(configuration, "configuration", "implementation_identity")
			descriptor := map[string]any{"binding_id": "binding", "target": map[string]any{"plane": "participant-implementation", "participant_address": at(configuration, "participant_address")}}
			binding := map[string]any{"descriptor": descriptor, "origin": "selection"}
			realized := map[string]any{"descriptor": descriptor, "origin": "selection", "configuration_digest": at(configuration, "configuration_digest")}
			entry := map[string]any{"participant_configurations": []any{configuration}, "bindings": []any{binding}}
			run := map[string]any{"realized_bindings": []any{realized}, "participant_implementation_provenance": map[string]any{"participant_implementations": []any{selection}}}
			switch field {
			case "binding":
				run["realized_bindings"] = []any{}
			case "origin":
				realized["origin"] = "foreign"
			case "digest":
				realized["configuration_digest"] = "sha256:" + strings.Repeat("0", 64)
			case "selection":
				run["participant_implementation_provenance"] = nil
			case "selection-authority":
				selection["selected_decision_surface_mode"] = "foreign"
			}
			if err := owner.trialRunBindings(entry, run); (err == nil) != (field == "") {
				t.Fatal("participant binding reconciliation", err)
			}
		})
	}
}

func TestTrialRandomnessAndTreatmentSetsRequireExactRecordedValues(t *testing.T) {
	control := map[string]any{"control_id": "random", "role": "other"}
	draw := map[string]any{"control_id": "random", "value": json.Number("1")}
	treatment := map[string]any{"selection_id": "selection", "outcome": map[string]any{"kind": "literal", "value": true}}
	plan := map[string]any{"stochastic_controls": map[string]any{"random": control}, "allocation": map[string]any{"policy": map[string]any{"stochastic_control_ref": "random"}}}
	entry := map[string]any{"stochastic_draws": []any{draw}, "selections": []any{map[string]any{"treatment": treatment}}}
	for _, field := range []string{"", "controls", "draws", "treatments"} {
		t.Run("set-"+field, func(t *testing.T) {
			run := map[string]any{"stochastic_controls": []any{control}, "stochastic_draws": []any{draw}, "realized_selections": []any{treatment}}
			switch field {
			case "controls":
				run["stochastic_controls"] = []any{}
			case "draws":
				run["stochastic_draws"] = []any{}
			case "treatments":
				run["realized_selections"] = []any{}
			}
			if err := trialRunRandomness(plan, entry, run); (err == nil) != (field == "") {
				t.Fatal("recorded randomness/treatment reconciliation", err)
			}
		})
	}
}

func TestTrialPublicBoundariesRefuseUnownedAndMalformedArtifacts(t *testing.T) {
	owner := boundTestOwner(t)
	for _, test := range []struct {
		name  string
		check func() error
	}{
		{"seal-owner", func() error { _, err := SealTrialPlan(nil, []byte(`{}`), experimentProjectionLimits()); return err }},
		{"seal-json", func() error { _, err := SealTrialPlan(owner, []byte(`{`), experimentProjectionLimits()); return err }},
		{"seal-shape", func() error { _, err := SealTrialPlan(owner, []byte(`[]`), experimentProjectionLimits()); return err }},
		{"projection-owner", func() error {
			_, err := TrialPlanProjection(nil, validation.Value{}, experimentProjectionLimits())
			return err
		}},
		{"order-owner", func() error { _, err := TrialEntryOrder(nil, validation.Value{}); return err }},
		{"run-owner", func() error { return ValidateTrialRun(nil, TrialRunInputs{}) }},
		{"run-json-owner", func() error { return ValidateTrialRunJSON(nil, validation.Value{}, nil, nil) }},
		{"study-owner", func() error { return ValidateTrialStudy(nil, TrialStudyInputs{}) }},
		{"supersession-owner", func() error { _, err := SupersedeTrialRunJSON(nil, nil, validation.Value{}); return err }},
		{"experiment-projection-owner", func() error { _, err := ExperimentProjection(nil, validation.Value{}); return err }},
		{"model-projection-owner", func() error { _, err := ExperimentModelProjection(nil, termExperimentRunV1, nil); return err }},
		{"manifest-projection-owner", func() error { _, err := ManifestModelProjection(nil, "backend-manifest-v2", nil); return err }},
		{"manifest-projection-contract", func() error { _, err := ManifestModelProjection(owner, "foreign", []byte(`{}`)); return err }},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := test.check(); err == nil {
				t.Fatal("unowned or malformed artifact admitted")
			}
		})
	}
	var reference struct {
		Plan  json.RawMessage
		Cases []trialRunReferenceCase
	}
	readFullReferenceJSON(t, "testdata/trial-run-reconciliation.json", &reference)
	plan, err := owner.Validate(trialPlanContract, reference.Plan, experimentProjectionLimits(), nil)
	if err != nil {
		t.Fatal(err)
	}
	if checkErr := ValidateTrialRunJSON(owner, plan, []byte(`{`), nil); checkErr == nil {
		t.Fatal("malformed archival bytes admitted")
	}
	if checkErr := ValidateTrialRunJSON(owner, plan, reference.Cases[0].Run, [][]byte{[]byte(`{`)}); checkErr == nil {
		t.Fatal("malformed cleanup bytes admitted")
	}
	structural := schemaOnlyTestOwner(t, owner)
	run, err := structural.Validate(termExperimentRunV1, reference.Cases[0].Run, experimentProjectionLimits(), nil)
	if err != nil {
		t.Fatal(err)
	}
	if err := ValidateTrialRun(owner, TrialRunInputs{Plan: plan, Run: run, CleanupReceipts: []validation.Value{{}}}); err == nil {
		t.Fatal("unowned receipt admitted")
	}
	if err := ValidateTrialRun(owner, TrialRunInputs{Plan: plan, Run: run, Task: run}); err == nil {
		t.Fatal("wrong task artifact admitted")
	}
}

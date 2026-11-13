package processor_test

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

type participantRelationVector struct {
	Name     string          `json:"name"`
	Source   string          `json:"source"`
	Address  string          `json:"address"`
	Shape    string          `json:"shape"`
	Proposal string          `json:"proposal"`
	Input    json.RawMessage `json:"input"`
	Expected json.RawMessage `json:"expected"`
	Valid    bool            `json:"valid"`
}
type participantRelationVectors struct {
	Sources   map[string]string           `json:"sources"`
	Arguments []participantRelationVector `json:"arguments"`
	Actions   []participantRelationVector `json:"actions"`
	Outcomes  []participantRelationVector `json:"outcomes"`
	Temporal  []participantRelationVector `json:"temporal"`
}

func participantRelations(t *testing.T) participantRelationVectors {
	t.Helper()
	raw, err := os.ReadFile("testdata/participant-relations-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var result participantRelationVectors
	if err := json.Unmarshal(raw, &result); err != nil {
		t.Fatal(err)
	}
	if len(result.Arguments) != 25 || len(result.Actions) != 26 || len(result.Outcomes) != 20 || len(result.Temporal) != 13 {
		t.Fatal("participant relation reference inventory changed")
	}
	return result
}
func participantFragment(t *testing.T, profile admission.FragmentProfile, raw []byte) (admission.Fragment, error) { //nolint:ireturn // The test exercises the sealed fragment owner.
	t.Helper()
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var input any
	if err := decoder.Decode(&input); err != nil {
		t.Fatal(err)
	}
	return admission.AdmitFragment(owner, profile, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
}
func participantFindings(findings []diagnostic.Diagnostic) []string {
	result := make([]string, len(findings))
	for index, finding := range findings {
		result[index] = finding.Message
	}
	return result
}
func TestParticipantArgumentsMatchPureReference(t *testing.T) {
	vectors := participantRelations(t)
	for _, test := range vectors.Arguments {
		t.Run(test.Name, func(t *testing.T) {
			model := toolSupportModel(t, toolSupportSource{Text: vectors.Sources[test.Source]})
			input, err := participantFragment(t, admission.RealizationValue, test.Input)
			if err != nil {
				t.Fatal(err)
			}
			result, err := processor.ResolveParticipantActionArguments(model, test.Address, test.Shape, test.Proposal, input)
			if (err == nil) != test.Valid {
				t.Fatalf("valid=%v err=%v", test.Valid, err)
			}
			if err == nil {
				assertReferenceJSON(t, "normalized arguments", requireJSON(t, result.Document()), test.Expected)
			}
		})
	}
}
func TestParticipantActionResultsMatchPureReference(t *testing.T) {
	vectors := participantRelations(t)
	model := toolSupportModel(t, toolSupportSource{Text: vectors.Sources["action"]})
	for _, test := range vectors.Actions {
		t.Run(test.Name, func(t *testing.T) {
			input, err := participantFragment(t, admission.ParticipantActionResult, test.Input)
			var findings []diagnostic.Diagnostic
			if err == nil {
				findings, err = processor.ParticipantActionResultViolations(model, test.Address, input)
			}
			if (err == nil) != test.Valid {
				t.Fatalf("valid=%v err=%v", test.Valid, err)
			}
			if err == nil {
				assertReferenceJSON(t, "action violations", requireJSON(t, participantFindings(findings)), test.Expected)
			}
		})
	}
	for code, want := range map[string]string{"backend.timeout": "timeout", "backend.unmapped": "backend_error", "": "unknown"} {
		got, err := processor.ParticipantFailureClass(model, "participant.action-contract.scan", code)
		if err != nil || got != want {
			t.Fatalf("failure class=%s err=%v", got, err)
		}
	}
}
func TestParticipantOutcomesMatchPureReference(t *testing.T) {
	vectors := participantRelations(t)
	model := toolSupportModel(t, toolSupportSource{Text: vectors.Sources["outcome"]})
	for _, test := range vectors.Outcomes {
		t.Run(test.Name, func(t *testing.T) {
			input, err := participantFragment(t, admission.ParticipantOutcomeInterpretationRecord, test.Input)
			var findings []diagnostic.Diagnostic
			if err == nil {
				findings, err = processor.ParticipantOutcomeInterpretationViolations(model, test.Address, input)
			}
			if (err == nil) != test.Valid {
				t.Fatalf("valid=%v err=%v", test.Valid, err)
			}
			if err == nil {
				assertReferenceJSON(t, "outcome violations", requireJSON(t, participantFindings(findings)), test.Expected)
			}
		})
	}
}
func TestParticipantTemporalStateMachinesMatchPureReference(t *testing.T) {
	vectors := participantRelations(t)
	for _, test := range vectors.Temporal {
		t.Run(test.Name, func(t *testing.T) {
			input, err := participantFragment(t, admission.RealizationValue, test.Input)
			if err != nil {
				t.Fatal(err)
			}
			findings, err := processor.ParticipantTemporalStateMachineViolations(input)
			if err != nil {
				t.Fatal(err)
			}
			pairs := make([][2]string, len(findings))
			for index, finding := range findings {
				pairs[index] = [2]string{finding.Pointer, finding.Message}
			}
			assertReferenceJSON(t, "temporal violations", requireJSON(t, pairs), test.Expected)
		})
	}
}
func TestParticipantRelationsRefuseForeignModelsBeforeMethods(t *testing.T) {
	for _, check := range []func() error{
		func() error {
			_, err := processor.ParticipantFailureClass(foreignModel{}, "participant.action-contract.scan", "private-canary")
			return err
		},
		func() error {
			_, err := processor.ResolveParticipantActionArguments(foreignModel{}, "action", "shape", "proposal", nil)
			return err
		},
		func() error {
			_, err := processor.ParticipantActionResultViolations(foreignModel{}, "action", nil)
			return err
		},
		func() error {
			_, err := processor.ParticipantOutcomeInterpretationViolations(foreignModel{}, "rule", nil)
			return err
		},
		func() error {
			_, err := processor.ParticipantBehaviorHistoryViolations(foreignModel{}, "participant", nil, nil)
			return err
		},
	} {
		err := check()
		if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
			t.Fatalf("foreign model=%v", err)
		}
	}
}

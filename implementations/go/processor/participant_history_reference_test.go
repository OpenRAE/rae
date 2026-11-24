package processor_test

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

type participantHistoryCase struct {
	Name        string          `json:"name"`
	Source      string          `json:"source"`
	Participant string          `json:"participant"`
	Input       json.RawMessage `json:"input"`
	Episodes    json.RawMessage `json:"episodes"`
	Expected    json.RawMessage `json:"expected"`
}
type participantHistoryVectors struct {
	Sources map[string]string        `json:"sources"`
	History []participantHistoryCase `json:"history"`
	Joint   []participantHistoryCase `json:"joint"`
}

func participantHistoryReference(t *testing.T) participantHistoryVectors {
	t.Helper()
	var result participantHistoryVectors
	for _, raw := range referenceParts(t, []string{"testdata/participant-history-reference.json", "testdata/participant-history-reference-2.json", "testdata/participant-history-reference-3.json"}) {
		if err := json.Unmarshal(raw, &result); err != nil {
			t.Fatal(err)
		}
	}
	if len(result.Sources) != 42 || len(result.History) != 114 || len(result.Joint) != 6 {
		t.Fatal("participant history reference inventory changed")
	}
	return result
}
func participantHistoryPairs(findings []diagnostic.Diagnostic) [][2]string {
	result := make([][2]string, len(findings))
	for index, finding := range findings {
		result[index] = [2]string{finding.Pointer, finding.Message}
	}
	return result
}
func TestParticipantBehaviorHistoriesMatchPureReference(t *testing.T) {
	vectors := participantHistoryReference(t)
	models := map[string]processor.RuntimeModel{}
	for _, test := range vectors.History {
		t.Run(test.Name, func(t *testing.T) {
			model := models[test.Source]
			if model == nil {
				model = toolSupportModel(t, toolSupportSource{Text: vectors.Sources[test.Source]})
				models[test.Source] = model
			}
			input, err := participantFragment(t, admission.RealizationValue, test.Input)
			if err != nil {
				t.Fatal(err)
			}
			episodes := participantHistoryEpisodeInput(t, test.Episodes)
			findings, err := processor.ParticipantBehaviorHistoryViolations(model, test.Participant, input, episodes)
			if err != nil {
				t.Fatal(err)
			}
			assertReferenceJSON(t, "history violations", requireJSON(t, participantHistoryPairs(findings)), test.Expected)
		})
	}
}
func TestParticipantJointActionsMatchPureReference(t *testing.T) {
	vectors := participantHistoryReference(t)
	for _, test := range vectors.Joint {
		t.Run(test.Name, func(t *testing.T) {
			input, err := participantFragment(t, admission.RealizationValue, test.Input)
			if err != nil {
				t.Fatal(err)
			}
			findings, err := processor.ParticipantJointActionViolations(input)
			if err != nil {
				t.Fatal(err)
			}
			assertReferenceJSON(t, "joint action violations", requireJSON(t, participantHistoryPairs(findings)), test.Expected)
		})
	}
}

func participantHistoryEpisodeInput(t *testing.T, raw json.RawMessage) admission.Fragment { //nolint:ireturn // The SDK boundary consumes the existing sealed optional fragment.
	t.Helper()
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	input, err := participantFragment(t, admission.RealizationValue, raw)
	if err != nil {
		t.Fatal(err)
	}
	return input
}

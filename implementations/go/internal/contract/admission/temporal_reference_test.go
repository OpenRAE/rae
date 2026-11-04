package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

type temporalReferenceCase struct {
	Kind     string            `json:"kind"`
	Name     string            `json:"name"`
	Baseline string            `json:"baseline"`
	Changes  []referenceChange `json:"changes"`
	Admitted bool              `json:"admitted"`
	Context  json.RawMessage   `json:"context"`
	Proofs   json.RawMessage   `json:"proofs"`
	Clock    json.RawMessage   `json:"clock"`
	Native   string            `json:"native"`
	Boundary string            `json:"boundary"`
	Status   string            `json:"status"`
	Reason   string            `json:"reason"`
}

func TestTemporalHistoriesAndAssessmentsMatchPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Baselines map[string]json.RawMessage `json:"baselines"`
		Cases     []temporalReferenceCase    `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/temporal-verdicts.json", &reference)
	if len(reference.Cases) != 77 || len(reference.Baselines) != 2 {
		t.Fatal("independent temporal inventory changed")
	}
	e := boundTestOwner(t)
	for _, c := range reference.Cases {
		t.Run(c.Baseline+"/"+c.Kind+"/"+c.Name, func(t *testing.T) {
			switch c.Kind {
			case "history":
				checkTemporalReferenceHistory(t, e, reference.Baselines[c.Baseline], c)
			case "assessment":
				checkTemporalReferenceAssessment(t, e, c)
			default:
				t.Fatal("unknown temporal reference owner")
			}
		})
	}
}

func checkTemporalReferenceHistory(t *testing.T, e *Validator, baseline json.RawMessage, c temporalReferenceCase) {
	t.Helper()
	value := decodeRuleObject(t, string(baseline))
	for _, change := range c.Changes {
		applyReferenceChange(t, value, change)
	}
	history, clocks, err := temporalTypedHistory(e, value)
	if err == nil {
		err = temporalParticipantHistory(stringAt(value, "participant"), history, clocks)
	}
	if (err == nil) != c.Admitted {
		t.Fatalf("temporal history differs from Python (admitted=%v): %v", c.Admitted, err)
	}
}

func checkTemporalReferenceAssessment(t *testing.T, e *Validator, c temporalReferenceCase) {
	t.Helper()
	context := decodeRuleObject(t, string(c.Context))
	proofs := array(decodeRuleObject(t, string(c.Proofs)))
	clock := decodeRuleObject(t, string(c.Clock))
	context = typedTemporalReference(t, e, "ParticipantTemporalExecutionContextModel", context)
	clock = typedTemporalReference(t, e, "RuntimeClockStateModel", clock)
	for index, proof := range proofs {
		proofs[index] = typedTemporalReference(t, e, "ParticipantTemporalEvidenceModel", proof)
	}
	var status, reason string
	if c.Baseline == "deadline" {
		status, reason = temporalDeadline(context, proofs, c.Boundary, clock, c.Native)
	} else {
		status, reason = temporalDwell(context, proofs, clock)
	}
	if status != c.Status || reason != c.Reason {
		t.Fatalf("assessment=(%s,%s), Python=(%s,%s)", status, reason, c.Status, c.Reason)
	}
}

func typedTemporalReference(t *testing.T, e *Validator, model string, value any) any {
	t.Helper()
	view, err := temporalTypedFragment(e, model, value)
	if err != nil {
		t.Fatal(err)
	}
	return view
}

func temporalTypedFragment(e *Validator, model string, value any) (map[string]any, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	return e.low.DefaultedObjectFragment(termRuntimeSnapshotV1, "#/$defs/"+model, raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
}

func temporalTypedHistory(e *Validator, value any) ([]any, map[string]any, error) {
	history := []any{}
	for _, event := range array(at(value, "history")) {
		view, err := temporalTypedFragment(e, "ParticipantBehaviorHistoryEventModel", event)
		if err != nil {
			return nil, nil, err
		}
		history = append(history, view)
	}
	clocks := map[string]any{}
	for key, clock := range object(at(value, "clocks")) {
		view, err := temporalTypedFragment(e, "RuntimeClockStateModel", clock)
		if err != nil {
			return nil, nil, err
		}
		clocks[key] = view
	}
	return history, clocks, nil
}

package experiment

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
)

func TestDecisionMatchesIndependentIdentitiesAndDefaults(t *testing.T) {
	raw, err := os.ReadFile("testdata/decisions-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Cases []struct {
			Document json.RawMessage `json:"document"`
			ID       string          `json:"id"`
		} `json:"cases"`
	}
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("bad fixture")
	}
	for _, item := range reference.Cases {
		decision, decodeErr := DecodeDecision(item.Document)
		if decodeErr != nil {
			t.Fatal(decodeErr)
		}
		if decision.ID() != item.ID {
			t.Fatalf("identity differs: %s", decision.SchemaVersion())
		}
		want, _ := canonjson.JCS(item.Document)
		got, _ := canonjson.JCS(decision.JSON())
		if !bytes.Equal(want, got) {
			t.Fatalf("projection differs: %s\n%s\n%s", decision.SchemaVersion(), want, got)
		}
		copyJSON := decision.JSON()
		copyJSON[0] = 'x'
		if decision.JSON()[0] != '{' {
			t.Fatal("mutable decision")
		}
	}
}
func TestDecisionRejectsAmbiguousAndForgedShapes(t *testing.T) {
	for _, raw := range []string{`{}`, `{"schema_version":"runtime-trial-observation/v1","execution_attempt_id":"a","observation":{"kind":"execution","state":"succeeded","ceased":true,"evidence":[],"secret":"marker"}}`, `{"schema_version":"runtime-experiment-cancel/v1","experiment_id":"a","experiment_id":"b","actor_id":"c"}`, `{"schema_version":"runtime-trial-attempt/v1","experiment_id":"a","plan_entry_id":"b","run_id":"c","attempt":1.0,"execution_attempt_id":"d","started_at":"bad","deadline":"bad"}`} {
		if _, err := DecodeDecision([]byte(raw)); err == nil {
			t.Fatalf("accepted %s", raw)
		}
	}
}

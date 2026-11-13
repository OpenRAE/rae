package processor_test

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestParticipantBudgetRetainsPinnedResourceKind(t *testing.T) {
	// Reference: issue 1208 private resource measure through the issue 899
	// complete budget vector. This is authored SDL, not a compiled payload.
	raw, err := os.ReadFile("testdata/participant-resource-profile.json")
	if err != nil {
		t.Fatal(err)
	}
	scenario, err := sdl.Parse(raw, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, resource := range compiled.Model().View().ParticipantResources {
		if resource.Kind != "behavior-specification" {
			continue
		}
		if compiledPacketMeasurePresent(t, resource.Payload) {
			return
		}
	}
	t.Fatal("missing profile-backed budget demand")
}

func compiledPacketMeasurePresent(t *testing.T, payload processor.ResourcePayload) bool {
	t.Helper()
	var record struct {
		Execution struct {
			Demands []struct {
				ID   string          `json:"budget_id"`
				Kind json.RawMessage `json:"resource_kind"`
			} `json:"resource_demands"`
		} `json:"autonomous_execution"`
	}
	if err := json.Unmarshal(payload.JSON(), &record); err != nil {
		t.Fatal(err)
	}
	for _, demand := range record.Execution.Demands {
		if demand.ID != "packets" {
			continue
		}
		if !bytes.Contains(demand.Kind, []byte(`"profile_id":"packet-counter"`)) || !bytes.Contains(demand.Kind, []byte(`"definition_digest":"sha256:`)) {
			t.Fatalf("lost pinned measure: %s", demand.Kind)
		}
		return true
	}
	return false
}

package admission_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestResourceMeasureRequiresExactIndependentSemantics(t *testing.T) {
	raw, err := os.ReadFile("../../processor/testdata/participant-resource-context.json")
	if err != nil {
		t.Fatal(err)
	}
	var context binding.DomainProfileResolutionContextV1
	if checkErr := json.Unmarshal(raw, &context); checkErr != nil {
		t.Fatal(checkErr)
	}
	var source struct {
		Definitions []struct {
			Definition struct {
				Coordinate map[string]any `json:"coordinate"`
			} `json:"definition"`
		} `json:"definitions"`
	}
	if checkErr := json.Unmarshal(raw, &source); checkErr != nil {
		t.Fatal(checkErr)
	}
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	kind, err := admission.AdmitFragment(owner, admission.RealizationValue, source.Definitions[0].Definition.Coordinate, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	for _, change := range []string{"", "unit", "accounting", "meter", "reset", "context"} {
		t.Run(change, func(t *testing.T) {
			unit, accounting, meter, reset := "packets", "cumulative_counter", "urn:example:packet-meter:1", "run"
			selected := &context
			switch change {
			case "unit":
				unit = "bytes"
			case "accounting":
				accounting = "lease"
			case "meter":
				meter = "urn:wrong"
			case "reset":
				reset = "episode"
			case "context":
				selected = nil
			}
			valid, err := admission.ParticipantResourceMeasureSupported(owner, kind, unit, accounting, meter, reset, selected)
			if err != nil || valid != (change == "") {
				t.Fatalf("valid=%v err=%v", valid, err)
			}
		})
	}
}

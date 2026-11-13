package processor_test

import (
	"encoding/json"
	"os"
	"slices"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func autonomousSupportModels(t *testing.T) map[string]processor.RuntimeModel {
	t.Helper()
	v1, err := os.ReadFile("testdata/autonomous-v1.sdl.yaml")
	if err != nil {
		t.Fatal(err)
	}
	v2, err := os.ReadFile("testdata/autonomous-v2.sdl.yaml")
	if err != nil {
		t.Fatal(err)
	}
	models := map[string]processor.RuntimeModel{}
	for name, raw := range map[string][]byte{"v1": v1, "v2": v2} {
		scenario, err := sdl.Parse(raw, sdl.DefaultParseOptions())
		if err != nil {
			t.Fatal(err)
		}
		compiled, err := processor.Compile(scenario, nil)
		if err != nil {
			t.Fatal(err)
		}
		models[name] = compiled.Model()
	}
	return models
}

func TestAutonomousSupportKeepsReferenceCapacityAndResetGaps(t *testing.T) {
	models := autonomousSupportModels(t)
	raw, err := os.ReadFile("testdata/autonomous-support.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name     string                    `json:"name"`
		Source   string                    `json:"source_id"`
		Manifest binding.BackendManifestV2 `json:"manifest"`
		Gaps     []string                  `json:"gaps"`
	}
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			result, err := processor.ParticipantSupport(models[test.Source], test.Manifest, nil)
			if err != nil {
				t.Fatal(err)
			}
			gaps := autonomousTestMessages(result.Execution)
			if !slices.Equal(gaps, test.Gaps) {
				t.Fatalf("autonomous capability gaps=%v want=%v", gaps, test.Gaps)
			}
		})
	}
}

func autonomousTestMessages(findings []diagnostic.Diagnostic) []string {
	gaps := []string{}
	for _, finding := range findings {
		if finding.Code == "participant.autonomous-execution-unsupported" {
			gaps = append(gaps, finding.Message)
		}
	}
	return gaps
}

func TestAutonomousV3SupportKeepsCompleteBudgetAndPinnedMeasure(t *testing.T) {
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
	vector, err := os.ReadFile("testdata/autonomous-v3-support.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name     string                    `json:"name"`
		Manifest binding.BackendManifestV2 `json:"manifest"`
		Gaps     []string                  `json:"gaps"`
	}
	if err := json.Unmarshal(vector, &cases); err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			result, err := processor.ParticipantSupport(compiled.Model(), test.Manifest, nil)
			if err != nil {
				t.Fatal(err)
			}
			if gaps := autonomousTestMessages(result.Execution); !slices.Equal(gaps, test.Gaps) {
				t.Fatalf("autonomous budget gaps=%v want=%v", gaps, test.Gaps)
			}
		})
	}
}

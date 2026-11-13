package processor

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type captureRelationReference struct {
	Scenario json.RawMessage       `json:"scenario"`
	Cases    []captureRelationCase `json:"cases"`
}

type captureRelationCase struct {
	Name      string                            `json:"name"`
	Specs     []binding.ExperimentCaptureSpecV1 `json:"specs"`
	Relations []map[string]any                  `json:"relations"`
	Valid     bool                              `json:"valid"`
	Demands   []map[string]any                  `json:"demands"`
}

func readCaptureFixture(t *testing.T, path string, result any) {
	t.Helper()
	root, err := os.OpenRoot("testdata")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if closeErr := root.Close(); closeErr != nil {
			t.Error(closeErr)
		}
	})
	raw, err := root.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if decodeErr := json.Unmarshal(raw, result); decodeErr != nil {
		t.Fatal(decodeErr)
	}
}

//nolint:ireturn // Test helper returns the existing sealed scenario interface.
func captureScenario(t *testing.T, raw json.RawMessage) sdl.Scenario {
	t.Helper()
	if string(raw) == "null" {
		return nil
	}
	scenario, err := sdl.Parse(raw, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	return scenario
}

func captureRelationTestInputs(t *testing.T, owner *admission.Validator, test captureRelationCase) CaptureInputs {
	t.Helper()
	inputs := CaptureInputs{CaptureSpecs: test.Specs}
	for _, document := range test.Relations {
		relation, err := admission.AdmitFragment(owner, admission.ExperimentEvidenceRequirementRelation, document, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
		if err != nil {
			t.Fatal(err)
		}
		inputs.EvidenceRelations = append(inputs.EvidenceRelations, relation)
	}
	return inputs
}

func TestCaptureSpecAndScenarioDemandsMatchIndependentReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/capture-projection-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Scenario json.RawMessage                 `json:"scenario"`
		Spec     binding.ExperimentCaptureSpecV1 `json:"spec"`
		SDL      []map[string]any                `json:"sdl_demands"`
		Capture  []map[string]any                `json:"capture_demands"`
	}
	if decodeErr := json.Unmarshal(raw, &fixture); decodeErr != nil {
		t.Fatal(decodeErr)
	}
	scenario, err := sdl.Parse(fixture.Scenario, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name     string
		scenario sdl.Scenario
		inputs   CaptureInputs
		expected []map[string]any
	}{
		{"sdl", scenario, CaptureInputs{}, fixture.SDL},
		{"capture", nil, CaptureInputs{CaptureSpecs: []binding.ExperimentCaptureSpecV1{fixture.Spec}}, fixture.Capture},
	} {
		t.Run(test.name, func(t *testing.T) {
			demands, err := CompileCaptureDemands(test.scenario, test.inputs)
			if err != nil {
				t.Fatal(err)
			}
			if diff := cmp.Diff(test.expected, captureReferenceProjection(t, demands)); diff != "" {
				t.Fatalf("capture projection differs (-reference +native):\n%s", diff)
			}
		})
	}
}

func TestScopedCaptureRelationsMatchIndependentConjunctionReference(t *testing.T) {
	var fixture captureRelationReference
	readCaptureFixture(t, "capture-relations-reference.json", &fixture)
	scenario := captureScenario(t, fixture.Scenario)
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range fixture.Cases {
		t.Run(test.Name, func(t *testing.T) {
			inputs := captureRelationTestInputs(t, owner, test)
			demands, captureErr := CompileCaptureDemands(scenario, inputs)
			if (captureErr == nil) != test.Valid {
				t.Fatalf("valid=%v, error=%v", test.Valid, captureErr)
			}
			if captureErr == nil {
				if diff := cmp.Diff(test.Demands, captureReferenceProjection(t, demands)); diff != "" {
					t.Fatalf("capture conjunction differs (-reference +native):\n%s", diff)
				}
			}
		})
	}
}

func TestCaptureInputsAreBoundedBeforeTransportSerialization(t *testing.T) {
	for _, count := range []int{16385} {
		if _, err := CompileCaptureDemands(nil, CaptureInputs{CaptureSpecs: make([]binding.ExperimentCaptureSpecV1, count)}); err == nil {
			t.Fatal("unbounded capture-spec batch admitted")
		}
	}
	var spec binding.ExperimentCaptureSpecV1
	canary := "private-capture-canary"
	raw := []byte(`{"title":"` + canary + strings.Repeat("x", 8<<20) + `"}`)
	if err := json.Unmarshal(raw, &spec); err != nil {
		t.Fatal(err)
	}
	result, err := CompileCaptureDemands(nil, CaptureInputs{CaptureSpecs: []binding.ExperimentCaptureSpecV1{spec}})
	if err == nil || result != nil || strings.Contains(err.Error(), canary) {
		t.Fatal("oversized capture payload was accepted or exposed input")
	}
}

func TestCaptureOrderingRequirednessAndUnresolvedReferencesMatchReference(t *testing.T) {
	var cases []struct {
		Name     string                            `json:"name"`
		Scenario json.RawMessage                   `json:"scenario"`
		Specs    []binding.ExperimentCaptureSpecV1 `json:"specs"`
		Demands  []map[string]any                  `json:"demands"`
	}
	readCaptureFixture(t, "capture-order-reference.json", &cases)
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			scenario := captureScenario(t, test.Scenario)
			demands, captureErr := CompileCaptureDemands(scenario, CaptureInputs{CaptureSpecs: test.Specs})
			if captureErr != nil {
				t.Fatal(captureErr)
			}
			if diff := cmp.Diff(test.Demands, captureReferenceProjection(t, demands)); diff != "" {
				t.Fatalf("capture values differ (-reference +native):\n%s", diff)
			}
		})
	}
}

func TestCaptureCompileRetainsExplicitAuthoredRelationAuthority(t *testing.T) {
	var fixture captureRelationReference
	readCaptureFixture(t, "capture-relations-reference.json", &fixture)
	scenario := captureScenario(t, fixture.Scenario)
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	inputs := captureRelationTestInputs(t, owner, fixture.Cases[0])
	compiled, err := CompileWithOptions(scenario, CompileOptions{Capture: inputs})
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(fixture.Cases[0].Demands, captureReferenceProjection(t, compiled.Model().View().CaptureDemands)); diff != "" {
		t.Fatalf("compile discarded supplied capture authority (-reference +native):\n%s", diff)
	}
	concrete, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, compileErr := CompileWithOptions(concrete, CompileOptions{Capture: inputs}); compileErr == nil {
		t.Fatal("concrete scenario invented an authored relation owner")
	}
	inputs.RelationScenario = scenario
	if _, captureErr := CompileCaptureDemands(nil, inputs); captureErr == nil {
		t.Fatal("capture relation dropped every authored base obligation")
	}
	if _, compileErr := CompileWithOptions(concrete, CompileOptions{Capture: inputs}); compileErr != nil {
		t.Fatal(compileErr)
	}
	view := compiled.Model().View()
	view.CaptureDemands[0].FieldSelectors[0] = "changed"
	if cmp.Diff(fixture.Cases[0].Demands, captureReferenceProjection(t, compiled.Model().View().CaptureDemands)) != "" {
		t.Fatal("returned capture dimensions changed sealed compilation")
	}
}

func TestMaterializedCaptureCompilationRequiresTheExplicitAuthoredRelationOwner(t *testing.T) {
	var fixture captureRelationReference
	readCaptureFixture(t, "capture-relations-reference.json", &fixture)
	authored := captureScenario(t, fixture.Scenario)
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	inputs := captureRelationTestInputs(t, owner, fixture.Cases[0])
	raw, err := os.ReadFile("../../../contracts/fixtures/sdl/materialized-scenario-v1/valid/reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var materialized map[string]any
	if decodeErr := json.Unmarshal(raw, &materialized); decodeErr != nil {
		t.Fatal(decodeErr)
	}
	materialized["evidence_requirements"] = authored.Document()["evidence_requirements"]
	scenario := captureScenario(t, rawJSON(materialized))
	baseline, err := CompileMaterialized(scenario, CompileOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if !baseline.Model().View().Descriptive || len(baseline.Model().View().CaptureDemands) != 0 || len(baseline.Model().View().ObservationDemands) != 0 {
		t.Fatal("zero capture options changed descriptive compilation")
	}
	if _, compileErr := CompileWithOptions(scenario, CompileOptions{Capture: inputs}); compileErr == nil {
		t.Fatal("materialized compilation silently discarded capture relation inputs")
	}
	inputs.RelationScenario = authored
	compiled, err := CompileMaterialized(scenario, CompileOptions{Capture: inputs})
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(fixture.Cases[0].Demands, captureReferenceProjection(t, compiled.Model().View().CaptureDemands)); diff != "" {
		t.Fatalf("materialized capture dimensions differ (-reference +native):\n%s", diff)
	}
	if !compiled.Model().View().Descriptive || len(compiled.Model().View().ObservationDemands) != 0 {
		t.Fatal("explicit capture compilation changed materialized phase authority")
	}
}

func captureReferenceProjection(t *testing.T, input []CaptureDemand) []map[string]any {
	t.Helper()
	result := make([]map[string]any, len(input))
	for index, demand := range input {
		raw, err := json.Marshal(captureDemandProjection(demand))
		if err != nil {
			t.Fatal(err)
		}
		if err := json.Unmarshal(raw, &result[index]); err != nil {
			t.Fatal(err)
		}
	}
	return result
}

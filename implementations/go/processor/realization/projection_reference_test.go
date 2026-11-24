package realization

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type projectionReference struct {
	Name      string          `json:"name"`
	Kind      string          `json:"kind"`
	Input     json.RawMessage `json:"input"`
	Observed  bool            `json:"observed"`
	Recursive bool            `json:"recursive"`
	Rejected  bool            `json:"rejected"`
	Output    json.RawMessage `json:"output"`
}

func TestRealizationInputModelsUseExistingNativeConstructionOwner(t *testing.T) {
	raw, err := os.ReadFile("testdata/construction-reference.json")
	requireNoError(t, err)
	var cases []struct {
		Name     string          `json:"name"`
		Model    string          `json:"model"`
		Input    json.RawMessage `json:"input"`
		Accepted bool            `json:"accepted"`
	}
	requireNoError(t, json.Unmarshal(raw, &cases))
	owner, err := realizationOwner()
	requireNoError(t, err)
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			err := owner.CheckSDLConstruction("sdl-authoring-input-v1", "#/$defs/"+test.Model, test.Input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
			if test.Model == "Node" {
				input, inputErr := nativeValue(test.Input)
				requireNoError(t, inputErr)
				_, _, err = sdl.NormalizeNodeValue(selectionTestValue(t, input))
			}
			if (err == nil) != test.Accepted {
				t.Fatalf("native %s construction admitted=%v want=%v: %v", test.Model, err == nil, test.Accepted, err)
			}
		})
	}
}

type referenceConstraintLimits struct {
	MaxDepth            int `json:"max_depth"`
	MaxNodes            int `json:"max_nodes"`
	MaxOperations       int `json:"max_operations"`
	MaxMembers          int `json:"max_members"`
	MaxIdentityChecks   int `json:"max_identity_checks"`
	MaxScalarBytes      int `json:"max_scalar_bytes"`
	MaxTotalScalarBytes int `json:"max_total_scalar_bytes"`
}

func referenceConstraintBudget(input *referenceConstraintLimits) admission.ConstraintLimits {
	result := admission.DefaultConstraintLimits()
	if input == nil {
		return result
	}
	for _, bound := range []struct {
		source int
		target *int
	}{
		{input.MaxDepth, &result.MaxDepth}, {input.MaxNodes, &result.MaxNodes}, {input.MaxOperations, &result.MaxOperations}, {input.MaxMembers, &result.MaxMembers},
		{input.MaxIdentityChecks, &result.MaxIdentityChecks}, {input.MaxScalarBytes, &result.MaxScalarBytes}, {input.MaxTotalScalarBytes, &result.MaxTotalScalarBytes},
	} {
		if bound.source > 0 {
			*bound.target = bound.source
		}
	}
	return result
}

func TestProjectedConstraintsKeepReferencePrivateAndPartialRelations(t *testing.T) {
	raw, err := os.ReadFile("testdata/constraint-reference.json")
	requireNoError(t, err)
	var cases []struct {
		Name        string                     `json:"name"`
		Constraint  json.RawMessage            `json:"constraint"`
		Actual      json.RawMessage            `json:"actual"`
		Status      string                     `json:"status"`
		Diagnostics []referenceDiagnostic      `json:"diagnostics"`
		Limits      *referenceConstraintLimits `json:"limits"`
	}
	requireNoError(t, json.Unmarshal(raw, &cases))
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			constraint := relationFragment(t, test.Constraint, admission.RealizationConstraint)
			actual, err := nativeValue(test.Actual)
			requireNoError(t, err)
			limits := referenceConstraintBudget(test.Limits)
			result, err := admission.EvaluateRealizationConstraint(constraint, selectionTestValue(t, actual), limits)
			requireNoError(t, err)
			var got struct {
				Status      string                `json:"status"`
				Diagnostics []referenceDiagnostic `json:"diagnostics"`
			}
			requireNoError(t, json.Unmarshal(requireJSON(t, result.Document()), &got))
			if got.Status != test.Status || cmp.Diff(test.Diagnostics, got.Diagnostics) != "" {
				t.Fatalf("constraint result=%+v want status=%s diagnostics=%+v", got, test.Status, test.Diagnostics)
			}
		})
	}
}

func TestConcernProjectionsKeepReferenceSecurityAndPresenceCases(t *testing.T) {
	raw, err := os.ReadFile("testdata/projection-reference.json")
	requireNoError(t, err)
	var cases []projectionReference
	requireNoError(t, json.Unmarshal(raw, &cases))
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			input, err := nativeValue(test.Input)
			requireNoError(t, err)
			result, err := ProjectConcern(test.Kind, selectionTestValue(t, input), test.Observed, test.Recursive)
			if test.Rejected {
				if err == nil {
					t.Fatal("invalid reference concern accepted")
				}
				return
			}
			requireNoError(t, err)
			expected, err := nativeValue(test.Output)
			requireNoError(t, err)
			if diff := cmp.Diff(expected, result.Document()); diff != "" {
				t.Fatalf("projection differs (-reference +native):\n%s", diff)
			}
		})
	}
}

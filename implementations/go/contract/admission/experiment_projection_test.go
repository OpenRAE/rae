package admission

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestExperimentProjectionsMatchNativeConstructors(t *testing.T) {
	t.Parallel()
	raw, err := os.ReadFile("testdata/experiment-constructor-projections.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Cases []experimentConstructorReferenceCase `json:"cases"`
	}
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("invalid constructor reference")
	}
	owner := boundTestOwner(t)
	structural := schemaOnlyTestOwner(t, owner)
	if len(reference.Cases) != 28 {
		t.Fatal("constructor case count =", len(reference.Cases), "want 28")
	}
	for _, c := range reference.Cases {
		t.Run(c.Path, func(t *testing.T) { checkExperimentConstructorReference(t, c, owner, structural) })
	}
	if _, err := ExperimentProjection(owner, validation.Value{}); err == nil {
		t.Fatal("zero handle projected")
	}
	if _, err := ExperimentProjection(nil, validation.Value{}); err == nil {
		t.Fatal("nil owner projected")
	}
}

func assertExperimentJSON(t *testing.T, actual, expected []byte) {
	t.Helper()
	a, err := canonjson.JCS(actual)
	if err != nil {
		t.Fatal(err)
	}
	e, err := canonjson.JCS(expected)
	if err != nil {
		t.Fatal(err)
	}
	if string(a) != string(e) {
		var actualValue, expectedValue any
		if decodeExact(a, &actualValue) != nil || decodeExact(e, &expectedValue) != nil {
			t.Fatal("invalid canonical model JSON")
		}
		t.Fatalf("model projection differs (-actual +expected):\n%s", cmp.Diff(actualValue, expectedValue))
	}
}

type experimentConstructorReferenceCase struct {
	Path       string          `json:"path"`
	ContractID string          `json:"contract_id"`
	Result     json.RawMessage `json:"result"`
}

func checkExperimentConstructorReference(t *testing.T, c experimentConstructorReferenceCase, owner *Validator, structural *validation.Validator) {
	t.Helper()

	input, err := os.ReadFile("../../../../" + c.Path)
	if err != nil {
		t.Fatal(err)
	}
	admitted, err := structural.Validate(c.ContractID, input, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatal(err)
	}
	actual, err := ExperimentProjection(owner, admitted)
	if err != nil {
		t.Fatal(err)
	}
	assertExperimentJSON(t, actual, c.Result)
}

func TestTrialJoinsReconstructExperimentModelDefaults(t *testing.T) {
	owner := boundTestOwner(t)
	raw, err := os.ReadFile("../../../../contracts/fixtures/experiment-core/experiment-task-v1/valid/reference.json")
	if err != nil {
		t.Fatal(err)
	}
	expected, err := owner.experimentProjection("experiment-task-v1", raw)
	if err != nil {
		t.Fatal(err)
	}
	var input map[string]any
	if decodeExact(expected, &input) != nil {
		t.Fatal("fixture")
	}
	delete(input, "evidence_requirement_relations")
	delete(input, "validation_basis_disclosures")
	stripped, err := json.Marshal(input)
	if err != nil {
		t.Fatal(err)
	}
	structural := schemaOnlyTestOwner(t, owner)
	value, err := structural.Validate("experiment-task-v1", stripped, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatal(err)
	}
	actual, err := owner.experimentValue(value, "experiment-task-v1")
	if err != nil {
		t.Fatal(err)
	}
	projected, err := json.Marshal(actual)
	if err != nil {
		t.Fatal(err)
	}
	assertExperimentJSON(t, projected, expected)
}

func schemaOnlyTestOwner(t *testing.T, owner *Validator) *validation.Validator {
	t.Helper()
	rules := make([]validation.Rule, 0, len(owner.low.Keys()))
	for _, key := range owner.low.Keys() {
		rules = append(rules, validation.Rule{Key: key, Check: func(validation.Invocation) error { return nil }})
	}
	structural, err := validation.New(rules)
	if err != nil {
		t.Fatal(err)
	}
	return structural
}

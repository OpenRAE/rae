package admission

import (
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

type foreignEvidenceRelation struct{ Fragment }

func (foreignEvidenceRelation) Document() any { panic("foreign relation projection called") }

func TestCaptureRelationInputsUseClosedNativeArtifacts(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile("../../../../contracts/fixtures/experiment-core/experiment-capture-spec-v1/valid/reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var spec binding.ExperimentCaptureSpecV1
	if decodeErr := json.Unmarshal(raw, &spec); decodeErr != nil {
		t.Fatal(decodeErr)
	}
	if err := CheckEvidenceRequirementRelations(owner, nil, nil, []binding.ExperimentCaptureSpecV1{spec}); err != nil {
		t.Fatal(err)
	}
	if err := CheckEvidenceRequirementRelations(owner, []Fragment{foreignEvidenceRelation{}}, nil, nil); err == nil {
		t.Fatal("foreign relation input accepted")
	}
}

func TestCaptureRelationBatchGuardsAggregateWorkBeforeModelValidation(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	var spec binding.ExperimentCaptureSpecV1
	canary := "private-capture-spec"
	if decodeErr := json.Unmarshal([]byte(`{"title":"`+canary+strings.Repeat("x", 600000)+`"}`), &spec); decodeErr != nil {
		t.Fatal(decodeErr)
	}
	specs := make([]binding.ExperimentCaptureSpecV1, 15)
	for index := range specs {
		specs[index] = spec
	}
	err = CheckEvidenceRequirementRelations(owner, nil, nil, specs)
	if !errors.Is(err, value.ErrLimit) || strings.Contains(err.Error(), canary) {
		t.Fatalf("aggregate generated input did not fail at the shared work boundary: %v", err)
	}
	if err = CheckEvidenceRequirementRelations(owner, nil, nil, nil); err != nil {
		t.Fatal("a refused batch poisoned the next independent call")
	}
}

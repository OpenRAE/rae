package admission

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func TestSupplementalProfileAndEvidenceModelsMatchPython(t *testing.T) {
	raw, err := os.ReadFile("testdata/supplemental-model-verdicts.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Cases []supplementalModelCase `json:"cases"`
	}
	if err := json.Unmarshal(raw, &reference); err != nil {
		t.Fatal(err)
	}
	if len(reference.Cases) != 50 {
		t.Fatal("supplemental model inventory changed")
	}
	e := boundTestOwner(t)
	for _, c := range reference.Cases {
		t.Run(c.Contract+"/"+c.Name, func(t *testing.T) {
			checkSupplementalModelCase(t, e, c)
		})
	}
}

type supplementalModelCase struct {
	Contract string          `json:"contract"`
	Name     string          `json:"name"`
	Input    json.RawMessage `json:"input"`
	Admitted bool            `json:"admitted"`
	Schema   bool            `json:"schema_admitted"`
}

func checkSupplementalModelCase(t *testing.T, e *Validator, c supplementalModelCase) {
	t.Helper()
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if err := e.low.CheckSchema(c.Contract, c.Input, limits); (err == nil) != c.Schema {
		t.Fatalf("schema result differs from Python: %v", err)
	}
	admitted, err := e.Validate(c.Contract, c.Input, limits, nil)
	if (err == nil) != c.Admitted {
		t.Fatalf("Python admitted=%v: %v", c.Admitted, err)
	}
	if err == nil && !bytes.Equal(admitted.JSON(), c.Input) {
		t.Fatal("model comparison changed evidence")
	}
	if err != nil && admitted.ContractID() != "" {
		t.Fatal("refusal returned admission")
	}
}

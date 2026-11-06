package admission

import (
	"encoding/json"
	"io/fs"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

func TestReferenceModelPublishedBindingVerdicts(t *testing.T) {
	recordedCatalogVerdicts(t, boundTestOwner(t), "reference-models-v1", "testdata/reference-model-verdicts.json", 6)
}
func TestUCOCatalogReferenceVerdicts(t *testing.T) {
	recordedCatalogVerdicts(t, boundTestOwner(t), "uco-alignment-v1", "testdata/uco-verdicts.json", 8)
}
func recordedCatalogVerdicts(t *testing.T, e *Validator, id, file string, count int) {
	t.Helper()
	source, err := corpus.Open()
	if err != nil {
		t.Fatal(err)
	}
	rawVerdicts, readErr := fs.ReadFile(os.DirFS("."), file)
	if readErr != nil {
		t.Fatal(readErr)
	}
	var recorded struct {
		ContractID string `json:"contract_id"`
		Cases      []struct {
			Fixture string `json:"fixture"`
			Valid   bool   `json:"valid"`
		} `json:"cases"`
	}
	if err = json.Unmarshal(rawVerdicts, &recorded); err != nil {
		t.Fatal(err)
	}
	if recorded.ContractID != id || len(recorded.Cases) != count {
		t.Fatal("missing reference verdicts")
	}
	for _, test := range recorded.Cases {
		t.Run(test.Fixture, func(t *testing.T) {
			raw, err := fs.ReadFile(source, test.Fixture)
			if err != nil {
				t.Fatal(err)
			}
			limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
			_, err = e.Validate(id, raw, limits, nil)
			if (err == nil) != test.Valid {
				t.Fatalf("admitted=%v, reference=%v", err == nil, test.Valid)
			}
			portableErr := e.CheckPortable(id, raw, limits)
			if (portableErr == nil) != test.Valid {
				t.Fatalf("portable admitted=%v, reference=%v", portableErr == nil, test.Valid)
			}
		})
	}
}

func TestReferenceModelDuplicateBindingsAndKeyFields(t *testing.T) {
	e := boundTestOwner(t)
	for _, name := range []string{"keys", "reused", "authoritative"} {
		t.Run(name, func(t *testing.T) {
			root := fixtureObject(t, "fixtures/concept-authority/reference-models-v1/valid/reference.json")
			model := at(root, "models", "scenario-node")
			switch name {
			case "keys":
				object(model)["key_fields"] = []any{"type", "type"}
			case "reused":
				rows := array(at(model, "reused_schemas"))
				object(model)["reused_schemas"] = append(rows, rows[0])
			case "authoritative":
				object(model)["reused_schemas"] = []any{at(model, "authoritative_schema")}
			}
			raw := controlJSON(t, root)
			limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
			if err := e.low.CheckSchema("reference-models-v1", raw, limits); err != nil {
				t.Fatalf("mutation must pass shape: %v", err)
			}
			if _, err := e.Validate("reference-models-v1", raw, limits, nil); err == nil {
				t.Fatal("accepted duplicate reference binding")
			}
		})
	}
}

func TestConceptFamilyKeysRequireNonblankIdentity(t *testing.T) {
	e := boundTestOwner(t)
	v := fixtureObject(t, "fixtures/concept-authority/concept-families-v1/valid/reference.json")
	for _, family := range object(at(v, "families")) {
		v["families"] = map[string]any{" ": family}
		break
	}
	raw := controlJSON(t, v)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if err := e.low.CheckSchema("concept-families-v1", raw, limits); err != nil {
		t.Fatal(err)
	}
	if _, err := e.Validate("concept-families-v1", raw, limits, nil); err == nil {
		t.Fatal("accepted blank family identity")
	}
}

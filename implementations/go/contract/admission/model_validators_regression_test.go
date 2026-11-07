package admission

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// Regression: each nested reference model validator applies where its
// definition occurs. Before the definition-level rules, these definitions were
// checked only from some containing documents, so a native fragment or another
// containing document accepted what the reference model refuses. The vectors
// also cover nested union members without their discriminator tag.
func TestModelRulesMatchTheReferenceModels(t *testing.T) {
	data, err := os.ReadFile("testdata/model-rule-vectors.json")
	if err != nil {
		t.Fatalf("ReadFile() error = %v", err)
	}
	var recording struct {
		Cases []struct {
			Model    string          `json:"model"`
			Contract string          `json:"contract"`
			Name     string          `json:"name"`
			Valid    bool            `json:"valid"`
			Document json.RawMessage `json:"document"`
		} `json:"cases"`
	}
	decodeJSON(t, data, &recording)
	v := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}
	models := map[string]bool{}
	for _, c := range recording.Cases {
		models[c.Model] = true
		canonical, err := json.Marshal(exactDocument(t, c.Document))
		if err != nil {
			t.Fatalf("Marshal() error = %v", err)
		}
		err = v.checkModelFragment(c.Contract, schemaDefinitionsPrefix+c.Model, canonical, limits)
		if (err == nil) != c.Valid {
			t.Errorf("%s %s: error = %v, want valid %t", c.Model, c.Name, err, c.Valid)
		}
	}
	for _, c := range sdlConstructorVectors(t) {
		models[strings.TrimPrefix(c.Pointer, schemaDefinitionsPrefix)] = true
	}
	for name := range definitionRules() {
		if !models[name] {
			t.Errorf("definition rule %s has no reference vector", name)
		}
	}
}

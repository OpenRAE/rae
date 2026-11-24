package admission

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestControlledVocabularyPublishedVerdicts(t *testing.T) {
	recordedCatalogVerdicts(t, boundTestOwner(t), "controlled-vocabularies-v1", "testdata/controlled-vocabulary-verdicts.json", 4)
}

func TestControlledVocabularyModelVerdicts(t *testing.T) {
	e := boundTestOwner(t)
	raw, err := os.ReadFile("testdata/controlled-vocabulary-model-verdicts.json")
	if err != nil {
		t.Fatal(err)
	}
	var recorded struct {
		Cases []struct {
			Name    string          `json:"name"`
			Payload json.RawMessage `json:"payload"`
			Valid   bool            `json:"valid"`
		} `json:"cases"`
	}
	if err = json.Unmarshal(raw, &recorded); err != nil {
		t.Fatal(err)
	}
	if len(recorded.Cases) != 16 {
		t.Fatal("controlled vocabulary model inventory changed")
	}
	for _, c := range recorded.Cases {
		t.Run(c.Name, func(t *testing.T) {
			limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
			_, err := e.Validate("controlled-vocabularies-v1", c.Payload, limits, nil)
			if (err == nil) != c.Valid {
				t.Fatalf("catalog admission=%v reference=%v error=%v", err == nil, c.Valid, err)
			}
		})
	}
}

package analysis

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestAuthoringIndependentAxes(t *testing.T) {
	for _, name := range []string{"editorial-difference", "declaration-difference"} {
		t.Run(name, func(t *testing.T) {
			raw := readTestFile(t, "../../../../contracts/fixtures/authoring-adapters-v1/cases/"+name+".json")
			vector := testAdmission(t, "authoring-adapter-vector-v1", raw, nil)
			doc := testObject(t, vector.JSON())
			source := text(doc["input_source"])
			contrast := object(doc["contrast"])
			other := text(contrast["output_source"])
			for _, same := range []bool{true, false} {
				checkAuthoringAxes(t, vector, source, other, contrast, same)
			}
		})
	}
}

func checkAuthoringAxes(t *testing.T, vector validation.Value, source, other string, contrast map[string]any, same bool) {
	t.Helper()
	right := other
	if same {
		right = source
	}
	got, err := Analyze(Request{Kind: "authoring-adapter-comparison", Authoring: &AuthoringInput{Vector: vector, Left: AuthoringOutput{InputSource: source, OutputSource: &source}, Right: AuthoringOutput{InputSource: source, OutputSource: &right}}})
	if err != nil {
		t.Fatal(err)
	}
	wantArtifact, wantSemantic := "equivalent", "equivalent"
	if !same {
		wantArtifact = text(contrast["artifact_relation"])
		wantSemantic = text(contrast["semantic_relation"])
	}
	if got.Document["artifact_relation"] != wantArtifact || got.Document["semantic_relation"] != wantSemantic || got.Document["left_matches_expected"] != true || got.Document["right_matches_expected"] != same || got.SemanticResult.ContractID() != "semantic-comparison-result-v1" {
		t.Fatalf("%v", got.Document)
	}
}

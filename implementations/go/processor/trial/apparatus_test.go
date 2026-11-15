package trial

import (
	"encoding/json"
	"os"
	"testing"
)

func TestCompilerRequiresSelectedApparatusIntentAndCompatibility(t *testing.T) {
	raw, err := os.ReadFile("testdata/apparatus-refusals.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Cases []struct {
			Name       string              `json:"name"`
			Request    referenceRequest    `json:"request"`
			Diagnostic referenceDiagnostic `json:"diagnostic"`
		} `json:"cases"`
	}
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("invalid apparatus reference")
	}
	for _, test := range reference.Cases {
		t.Run(test.Name, func(t *testing.T) {
			result, err := Compile(compilerRequest(t, test.Request))
			if err != nil {
				t.Fatal(err)
			}
			if result.Plan != nil || len(result.Diagnostics) != 1 {
				t.Fatal("apparatus intent was not enforced", result.Diagnostics)
			}
			if got := referenceDiagnosticOf(result.Diagnostics[0]); got != test.Diagnostic {
				t.Fatal("apparatus refusal differs", got, "want", test.Diagnostic)
			}
		})
	}
}

func TestCompilerReconstructsOmittedManifestDefaultsBeforeDigestComparison(t *testing.T) {
	raw, err := os.ReadFile("testdata/manifest-defaults-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var ref struct {
		Request referenceRequest `json:"request"`
		Plan    json.RawMessage  `json:"plan"`
	}
	if json.Unmarshal(raw, &ref) != nil {
		t.Fatal("invalid manifest default reference")
	}
	result, err := Compile(compilerRequest(t, ref.Request))
	if err != nil {
		t.Fatal(err)
	}
	if result.Plan == nil {
		t.Fatal("valid constructor defaults were refused", result.Diagnostics)
	}
	actual, err := encoded(result.Plan)
	if err != nil {
		t.Fatal(err)
	}
	if !sameJSON(actual, ref.Plan) {
		t.Fatal("manifest constructor defaults changed the admitted plan")
	}
}

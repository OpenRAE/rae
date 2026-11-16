package trial

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

// referenceDiagnostic is the Python diagnostic wire shape.
// Native diagnostic source-location fields have separate owner tests.
type referenceDiagnostic struct {
	Code     string `json:"code"`
	Domain   string `json:"domain"`
	Address  string `json:"address"`
	Message  string `json:"message"`
	Severity string `json:"severity"`
}

func (d referenceDiagnostic) native() diagnostic.Diagnostic {
	return diagnostic.Diagnostic{Code: d.Code, Domain: d.Domain, Address: d.Address, Message: d.Message, Severity: d.Severity}
}
func referenceDiagnosticOf(d diagnostic.Diagnostic) referenceDiagnostic {
	return referenceDiagnostic{d.Code, d.Domain, d.Address, d.Message, d.Severity}
}

func TestCompilerPreservesIndependentCaptureDiagnostics(t *testing.T) {
	raw, err := os.ReadFile("testdata/capture-refusals.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Cases []struct {
			Name        string                `json:"name"`
			Request     referenceRequest      `json:"request"`
			Diagnostics []referenceDiagnostic `json:"diagnostics"`
		} `json:"cases"`
	}
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("fixture")
	}
	for _, item := range reference.Cases {
		t.Run(item.Name, func(t *testing.T) {
			result, compileErr := Compile(compilerRequest(t, item.Request))
			if compileErr != nil {
				t.Fatal(compileErr)
			}
			want := make([]diagnostic.Diagnostic, len(item.Diagnostics))
			for index, d := range item.Diagnostics {
				want[index] = d.native()
			}
			if result.Plan != nil || !cmp.Equal(result.Diagnostics, want) {
				t.Fatal("diagnostics differ", result.Diagnostics, want)
			}
		})
	}
}

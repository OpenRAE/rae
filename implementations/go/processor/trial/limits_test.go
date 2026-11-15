package trial

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type compilerLimitReferenceCase struct {
	Name        string                `json:"name"`
	Request     referenceRequest      `json:"request"`
	Limits      map[string]int        `json:"limits"`
	Diagnostics []referenceDiagnostic `json:"diagnostics"`
}

func TestCompilerLimitsPreserveIndependentAtomicRefusals(t *testing.T) {
	raw, err := os.ReadFile("testdata/compiler-limit-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var ref struct {
		Cases []compilerLimitReferenceCase `json:"cases"`
	}
	if json.Unmarshal(raw, &ref) != nil {
		t.Fatal("fixture")
	}
	for _, test := range ref.Cases {
		t.Run(test.Name, func(t *testing.T) { checkCompilerLimit(t, test) })
	}
}
func checkCompilerLimit(t *testing.T, test compilerLimitReferenceCase) {
	t.Helper()
	request := compilerRequest(t, test.Request)
	request.Limits = Limits{test.Limits["max_coordinates"], test.Limits["max_domain_values_per_point"], test.Limits["max_product_outputs"], test.Limits["max_bindings_per_entry"], test.Limits["max_draws_per_entry"], test.Limits["max_diagnostics"], test.Limits["max_mixed_profiles"], test.Limits["max_mixed_context_work"], test.Limits["max_plan_bytes"]}
	result, err := Compile(request)
	if err != nil {
		t.Fatal(err)
	}
	actual := make([]referenceDiagnostic, len(result.Diagnostics))
	for index, d := range result.Diagnostics {
		actual[index] = referenceDiagnosticOf(d)
	}
	if result.Plan != nil || !cmp.Equal(actual, test.Diagnostics) {
		t.Fatal("limit refusal differs", cmp.Diff(test.Diagnostics, actual))
	}
}

func TestEntryDrawLimitPrecedesConfigurationConstruction(t *testing.T) {
	calls := 0
	work := drawLimitedEntryFixture(t, &calls)
	err := work.configure(t.Context())
	var refusal *compilationRefusalError
	if !errors.As(err, &refusal) || refusal.code != "draw-limit-exceeded" || calls != 0 {
		t.Fatal("draw limit did not precede configuration", err, calls)
	}
}

type countingTypedFactory struct{ calls *int }

//nolint:ireturn // The installed factory uses the public validator interface.
func (f countingTypedFactory) ForScenario(ctx context.Context, scenario sdl.Scenario) (admission.ParticipantControlContextValidator, error) {
	*f.calls++
	return typedContextFactory{}.ForScenario(ctx, scenario)
}
func drawLimitedEntryFixture(t *testing.T, calls *int) entryCompilation {
	t.Helper()
	request := typedCompilerRequest(t, typedReferences(t).Cases[1])
	request.Limits.MaxDrawsPerEntry = 1
	request.ParticipantControlContextFactories = map[ConfigurationValidatorKey]ControlContextFactory{{"participant-config", "1"}: countingTypedFactory{calls}}
	input, err := prepareInputs(request)
	if err != nil {
		t.Fatal(err)
	}
	work := planCompilation{request: request, input: input}
	if err = work.prepareRows(t.Context()); err != nil {
		t.Fatal(err)
	}
	entry := entryCompilation{request: request, input: input, coordinate: work.coordinates[0], row: work.rows[0]}
	entry.row.draws = []json.RawMessage{json.RawMessage(`{}`), json.RawMessage(`{}`)}
	if err = entry.selectScenario(); err != nil {
		t.Fatal(err)
	}
	return entry
}

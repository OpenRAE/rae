package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestRealizedTimeModelAndDeclarationJoins(t *testing.T) {
	e := boundTestOwner(t)
	model := fixtureObject(t, "fixtures/time/realized-time-model-v1/valid/reference.json")
	run := map[string]any{"run_id": model["run_id"], "realized_time_model": model}
	if err := e.runTimeModel(validation.Invocation{Instance: run}); err != nil {
		t.Fatal(err)
	}
	run["run_id"] = "foreign-run"
	if err := e.runTimeModel(validation.Invocation{Instance: run}); err == nil {
		t.Error("accepted foreign run timing provenance")
	}
	for _, raw := range []string{
		`{"domains":{"domain":{"address":"domain","kind":"wall_clock","epoch":"scenario","tick_period_seconds":{"numerator":1,"denominator":1}}}}`,
		`{"domains":{"domain":{"address":"domain","tick_period_seconds":{"numerator":2,"denominator":4}}}}`,
		`{"domains":{"one":{"address":"one"},"two":{"address":"two"}},"mappings":{"one-two":{"address":"one-two","source_domain_address":"one","target_domain_address":"two"},"two-one":{"address":"two-one","source_domain_address":"two","target_domain_address":"one"}}}`,
	} {
		if err := timeDeclaration(decodeRuleObject(t, raw)); err == nil {
			t.Error("accepted invalid time declaration")
		}
	}
}

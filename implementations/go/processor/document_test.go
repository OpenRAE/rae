package processor_test

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestCompiledDocumentProjectsTypedTimeAndCapabilityFacts(t *testing.T) {
	scenario, err := sdl.Parse([]byte(`name: example
variables:
  count: {type: integer, default: 1, allowed_values: [1,2]}
nodes:
  server: {type: compute}
infrastructure:
  server: {count: '${count}'}
time_domains:
  scenario: {kind: simulated, tick_period_seconds: {numerator: 1, denominator: 1000}, epoch: scenario_start, description: milliseconds}
`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	document := compiled.Document()
	time, ok := document["time_model"].(map[string]any)
	if !ok {
		t.Fatal("compiled time model missing")
	}
	domains := requireType[[]any](t, time["domains"])
	if len(domains) != 1 || requireType[map[string]any](t, domains[0])["tick_period_denominator"] != json.Number("1000") {
		t.Fatalf("time projection=%v", time)
	}
	constraints := requireType[[]any](t, document["capability_constraints"])
	if len(constraints) != 1 || requireType[map[string]any](t, constraints[0])["concern"] != "infrastructure.count" {
		t.Fatalf("capability projection=%v", constraints)
	}
}

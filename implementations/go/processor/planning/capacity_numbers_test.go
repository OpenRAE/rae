package planning_test

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

func requireSufficientCapacity(t *testing.T, compiled processor.Compilation, target binding.BackendManifestV2) {
	t.Helper()
	result, err := planning.PlanWithManifest(compiled, target, planning.Options{})
	if err != nil {
		t.Fatal(err)
	}
	if !result.Plan.Valid() || len(result.Diagnostics) != 0 {
		t.Fatalf("sufficient capacity refused: %+v", result.Diagnostics)
	}
}

func TestPlanningCapacityAcceptsIntegralJSONNumbers(t *testing.T) {
	compiled := compile(t, basicScenario)
	for _, number := range []string{"10", "10.0", "1e1", "9007199254740993", "9007199254740993.0", "9.007199254740993e15"} {
		t.Run("nodes/"+number, func(t *testing.T) {
			target := changeManifest(t, func(record map[string]any) {
				requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])["max_total_nodes"] = json.Number(number)
			})
			requireSufficientCapacity(t, compiled, target)
		})
	}
	withTime := compile(t, `name: example
time_domains:
  scenario: {kind: simulated, epoch: scenario_start, tick_period_seconds: {numerator: 1, denominator: 1}, description: scenario}
`)
	for _, field := range []string{"max_time_domains", "max_clocks"} {
		for _, number := range []string{"10", "10.0", "1e1"} {
			t.Run(field+"/"+number, func(t *testing.T) {
				target := timeCapacityManifest(t, field, number)
				requireSufficientCapacity(t, withTime, target)
			})
		}
	}
}

func timeCapacityManifest(t *testing.T, fieldName, number string) binding.BackendManifestV2 {
	t.Helper()
	raw, err := os.ReadFile("../testdata/autonomous-support.json")
	if err != nil {
		t.Fatal(err)
	}
	var vectors []struct {
		Manifest binding.BackendManifestV2 `json:"manifest"`
	}
	if err = json.Unmarshal(raw, &vectors); err != nil {
		t.Fatal(err)
	}
	capabilities := field(vectors[0].Manifest.Capabilities)
	var time map[string]json.RawMessage
	if err = json.Unmarshal(field(capabilities.Time), &time); err != nil {
		t.Fatal(err)
	}
	time[fieldName] = json.RawMessage(number)
	timeRaw, err := json.Marshal(time)
	if err != nil {
		t.Fatal(err)
	}
	if err = capabilities.Time.UnmarshalJSON(timeRaw); err != nil {
		t.Fatal(err)
	}
	capabilitiesRaw, err := json.Marshal(capabilities)
	if err != nil {
		t.Fatal(err)
	}
	if err = vectors[0].Manifest.Capabilities.UnmarshalJSON(capabilitiesRaw); err != nil {
		t.Fatal(err)
	}
	return vectors[0].Manifest
}

func TestPlanningCapacityKeepsHugeIntegerThresholdExact(t *testing.T) {
	compiled := compile(t, "name: example\nnodes:\n  first: {type: compute}\n  second: {type: compute}\n  third: {type: compute}\ninfrastructure:\n  first: {count: 9007199254740991}\n  second: {count: 9007199254740991}\n  third: {count: 2}\n")
	expected := []diagnostic.Diagnostic{{Code: "provisioner.max-total-nodes-exceeded", Severity: "error", Domain: "provisioning", Address: "provision", Message: "Scenario requires 18014398509481984 deployable nodes/networks, but provisioner maximum is 18014398509481983."}}
	for _, number := range []string{"18014398509481983", "18014398509481983.0", "1.8014398509481983e16"} {
		t.Run(number, func(t *testing.T) {
			target := changeManifest(t, func(record map[string]any) {
				requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])["max_total_nodes"] = json.Number(number)
			})
			result, err := planning.PlanWithManifest(compiled, target, planning.Options{})
			if err != nil {
				t.Fatal(err)
			}
			if diff := cmp.Diff(expected, result.Diagnostics); diff != "" {
				t.Fatalf("equivalent capacity changed diagnostics (-integer +equivalent):\n%s", diff)
			}
			if result.Plan.Valid() {
				t.Fatal("insufficient exact capacity was accepted")
			}
		})
	}
}

func TestPlanningCapacityRetainsNumericInputBounds(t *testing.T) {
	compiled := compile(t, basicScenario)
	for _, number := range []string{"1e999999999", "0e999999999", "1e-999999999", strings.Repeat("1", 4301)} {
		t.Run(number[:min(24, len(number))], func(t *testing.T) {
			target := changeManifest(t, func(record map[string]any) {
				requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])["max_total_nodes"] = json.Number(number)
			})
			result, err := planning.PlanWithManifest(compiled, target, planning.Options{})
			if err == nil || result.Plan != nil || len(result.Diagnostics) != 0 {
				t.Fatalf("out-of-budget capacity returned a plan: error=%v", err)
			}
		})
	}
}

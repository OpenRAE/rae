package processor

import (
	"encoding/json"
	"os"
	"slices"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func governedResourceFixture(t *testing.T) (*participantAutonomous, []byte, binding.BackendManifestV2) {
	t.Helper()
	raw, err := os.ReadFile("testdata/participant-resource-profile.json")
	if err != nil {
		t.Fatal(err)
	}
	scenario, err := sdl.Parse(raw, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	model, ok := compiled.Model().(*runtimeModel)
	if !ok {
		t.Fatal("native model")
	}
	var policy *participantAutonomous
	for _, spec := range model.participants.specifications {
		if spec.AutonomousExecution != nil {
			policy = spec.AutonomousExecution
		}
	}
	if policy == nil {
		t.Fatal("missing policy")
	}
	caps, err := os.ReadFile("testdata/participant-resource-capabilities.json")
	if err != nil {
		t.Fatal(err)
	}
	var manifest binding.BackendManifestV2
	if checkErr := json.Unmarshal([]byte(`{"supported_contract_versions":["participant-resource-budget-policy-v1","participant-resource-pool-capacity-v1","participant-resource-budget-state-v1","participant-resource-budget-event-v1"]}`), &manifest); checkErr != nil {
		t.Fatal(checkErr)
	}
	return policy, caps, manifest
}

func TestResourceSupportChecksChosenResetAgainstPinnedSemantics(t *testing.T) {
	policy, caps, manifest := governedResourceFixture(t)
	gaps, err := participantResourceSupportGaps(manifest, caps, []*participantAutonomous{policy})
	if err != nil || len(gaps) != 0 {
		t.Fatalf("supported measure: %v %v", gaps, err)
	}
	for i := range policy.ResourceDemands {
		if policy.ResourceDemands[i].BudgetID == "packets" {
			policy.ResourceDemands[i].Reset = "time_segment"
		}
	}
	gaps, err = participantResourceSupportGaps(manifest, caps, []*participantAutonomous{policy})
	if err != nil || !slices.Contains(gaps, "participant resource budget packets lacks supported profile semantics") {
		t.Fatalf("changed reset admitted: %v %v", gaps, err)
	}
}

func TestResourcePoolAliasDoesNotRepeatPoolDiagnostics(t *testing.T) {
	policy, raw, manifest := governedResourceFixture(t)
	demand := resourceTestDemand(t, policy, "packets")
	alias := demand
	alias.BudgetID = "packet-alias"
	policy.ResourceDemands = []participantResourceDemand{demand, alias}
	var caps resourceBudgetSupport
	if err := json.Unmarshal(raw, &caps); err != nil {
		t.Fatal(err)
	}
	for i := range caps.Pools {
		if caps.Pools[i].PoolRef == "packet-pool" {
			caps.Pools[i].Capacity = "8"
		}
	}
	encoded, err := json.Marshal(caps)
	if err != nil {
		t.Fatal(err)
	}
	gaps, err := participantResourceSupportGaps(manifest, encoded, []*participantAutonomous{policy})
	if err != nil {
		t.Fatal(err)
	}
	capacityFailures := 0
	for _, gap := range gaps {
		if strings.Contains(gap, "requires capacity 12; configured capacity is 8") {
			capacityFailures++
		}
	}
	if capacityFailures != 1 || len(gaps) != 3 {
		t.Fatalf("pool alias repeated capacity/fairness checks: %v", gaps)
	}
	if gaps[1] != "participant policy "+policy.Address+" aliases canonical resource pool packet-pool" || gaps[2] != "participant resource pool packet-pool aggregate policy limits require 12; configured capacity is 8" {
		t.Fatalf("pool diagnostic order=%v", gaps)
	}
}

func resourceTestDemand(t *testing.T, policy *participantAutonomous, id string) participantResourceDemand {
	t.Helper()
	for _, demand := range policy.ResourceDemands {
		if demand.BudgetID == id {
			return demand
		}
	}
	t.Fatal("missing resource demand")
	return participantResourceDemand{}
}

func TestResourceSupportAggregatesCompetingPolicyLimits(t *testing.T) {
	policy, caps, manifest := governedResourceFixture(t)
	competing := *policy
	competing.Address += ".competing"
	gaps, err := participantResourceSupportGaps(manifest, caps, []*participantAutonomous{policy, &competing})
	if err != nil {
		t.Fatal(err)
	}
	want := "participant resource pool inference-pool aggregate policy limits require 40000; configured capacity is 20000"
	if !slices.Contains(gaps, want) {
		t.Fatalf("competing policies borrowed pool capacity: %v", gaps)
	}
}

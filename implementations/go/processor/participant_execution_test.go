package processor_test

import (
	"encoding/json"
	"os"
	"slices"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestCompileAutonomousParticipantRetainsBindings(t *testing.T) {
	raw, err := os.ReadFile("../../../examples/scenarios/temporal-profiles/user-deadline.sdl.yaml")
	if err != nil {
		t.Fatal(err)
	}
	scenario, err := sdl.Parse(raw, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	result, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, resource := range result.Model().View().ParticipantResources {
		if resource.Kind != "behavior-specification" {
			continue
		}
		var output struct {
			ParticipantAddresses []string `json:"participant_addresses"`
			AutonomousExecution  struct {
				TargetAddresses   []string    `json:"target_addresses"`
				MaxActionAttempts json.Number `json:"max_action_attempts"`
				TemporalBindings  []struct {
					ClockAddress   string `json:"clock_address"`
					ContractDigest string `json:"contract_digest"`
				} `json:"temporal_bindings"`
				ResourceDemands []struct {
					Limit json.Number `json:"limit"`
				} `json:"resource_demands"`
			} `json:"autonomous_execution"`
		}
		if err := json.Unmarshal(resource.Payload.JSON(), &output); err != nil {
			t.Fatal(err)
		}
		policy := output.AutonomousExecution
		if !slices.Equal(output.ParticipantAddresses, []string{"participant.behavior.participant-agent"}) || policy.MaxActionAttempts != "1" || !slices.Contains(policy.TargetAddresses, "provision.node.customer-portal.service.http") || len(policy.TemporalBindings) != 1 || policy.TemporalBindings[0].ClockAddress != "time.clock.scenario-clock" || len(policy.TemporalBindings[0].ContractDigest) != 71 || len(policy.ResourceDemands) != 2 || policy.ResourceDemands[0].Limit != "1" {
			t.Fatalf("lost autonomous authority, target, budget or time: %#v", output)
		}
		return
	}
	t.Fatal("missing behavior specification")
}

package processor

import (
	"os"
	"slices"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestInvocationToolRelationRetainsExactParticipantsAndInteraction(t *testing.T) {
	raw, err := os.ReadFile("testdata/invocation-tools.sdl.yaml")
	if err != nil {
		t.Fatal(err)
	}
	source, err := sdl.Parse(raw, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := Compile(source, nil)
	if err != nil {
		t.Fatal(err)
	}
	model, err := nativeRuntimeModel(compiled.Model())
	if err != nil {
		t.Fatal(err)
	}
	policy := model.participants.specifications["participant.behavior-specification.participant-behavior"].AutonomousExecution
	if policy == nil || len(policy.InvocationToolBindings) != 1 {
		t.Fatal("expected one compiled invocation relation")
	}
	binding := policy.InvocationToolBindings[0]
	if binding.ToolAffordanceAddress != "participant.behavior-specification.participant-behavior.tool-affordance.portal-client" || binding.ActionContractAddress != "participant.action-contract.probe-customer-portal-login" {
		t.Fatalf("tool identity=%+v", binding)
	}
	if !slices.Equal(binding.ObservationBoundaryAddresses, []string{"participant.observation-boundary.participant-view"}) || !slices.Equal(binding.ParticipantAddresses, []string{"participant.behavior.participant-agent", "participant.behavior.second-agent"}) {
		t.Fatalf("tool scope=%+v", binding)
	}
	if !slices.Contains(binding.TargetAddresses, "provision.node.customer-portal.service.http") || binding.SharedTimeBound {
		t.Fatalf("tool target/time=%+v", binding)
	}
	if binding.Interaction == nil || binding.Interaction.ActionContractAddress != binding.ActionContractAddress || binding.Interaction.ParticipantImplementationRef != policy.ParticipantImplementationRef || !slices.Equal(binding.Interaction.TargetAddresses, binding.TargetAddresses) {
		t.Fatal("invocation relation lost its execution interaction")
	}
}

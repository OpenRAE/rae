package processor

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestParticipantTemporalBindingsUseDeclaredSharedTime(t *testing.T) {
	for _, fixture := range []string{"user-deadline", "automation-dwell"} {
		t.Run(fixture, func(t *testing.T) {
			binding := declaredTemporalBinding(t, fixture)
			assertDeclaredTemporalRelation(t, fixture, binding)
		})
	}
}
func declaredTemporalBinding(t *testing.T, fixture string) participantTemporalBinding {
	t.Helper()
	raw, err := os.ReadFile("../../../examples/scenarios/temporal-profiles/" + fixture + ".sdl.yaml") //nolint:gosec // fixture is selected from the fixed two-element test table.
	if err != nil {
		t.Fatal(err)
	}
	scenario, err := sdl.Parse(raw, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	model, err := sdl.ModelBytes(instance)
	if err != nil {
		t.Fatal(err)
	}
	state := compilerState{}
	if err := json.Unmarshal(model, &state.input.model); err != nil {
		t.Fatal(err)
	}
	bindings := state.participantTemporalBindings([]string{"probe-customer-portal-login", "probe-customer-portal-login"})
	if state.err != nil || len(bindings) != 1 {
		t.Fatalf("bindings=%#v,%v", bindings, state.err)
	}
	return bindings[0]
}
func assertDeclaredTemporalRelation(t *testing.T, fixture string, binding participantTemporalBinding) {
	t.Helper()
	if binding.Profile != "participant-shared-time/v1" || binding.ClockAddress != "time.clock.scenario-clock" || binding.End.Segment != "0" || binding.End.Microstep != "0" || !strings.HasPrefix(binding.ContractDigest, "sha256:") || len(binding.ContractDigest) != 71 {
		t.Fatalf("lost shared-time authority or coordinates: %#v", binding)
	}
	if fixture == "automation-dwell" && (binding.Start == nil || binding.ConditionPreconditionID == nil || binding.ObservationBoundaryAddress == nil) {
		t.Fatalf("lost dwell coverage relation: %#v", binding)
	}
	if fixture == "user-deadline" && (binding.Start != nil || binding.ConditionPreconditionID != nil || binding.ObservationBoundaryAddress != nil) {
		t.Fatalf("inferred deadline coverage relation: %#v", binding)
	}
}
func TestLegacyTemporalStringsDoNotGrantSharedTimeBinding(t *testing.T) {
	state := compilerState{}
	if err := json.Unmarshal([]byte(`{"action_contracts":{"legacy":{"temporal_contracts":[{"clock_authority":"clock","duration_ref":"deadline","temporal_id":"legacy"}]}}}`), &state.input.model); err != nil {
		t.Fatal(err)
	}
	if bindings := state.participantTemporalBindings([]string{"legacy"}); state.err != nil || len(bindings) != 0 {
		t.Fatalf("inferred a binding from legacy strings: %#v %v", bindings, state.err)
	}
}

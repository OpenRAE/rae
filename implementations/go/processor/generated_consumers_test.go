package processor_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

func TestGeneratedArtifactConsumersDerivesDeliveryWithoutGrantingIt(t *testing.T) {
	raw := []byte(`{"name":"prepared-node-context","nodes":{"host":{"type":"compute","runtime":{"environment":[{"name":"MODE","value_classification":"plain","provenance":"runtime","value_from":{"generated_artifact":"generated_artifacts.token","output":"value"}}]}}},"generated_artifacts":{"token":{"generator":"random_value","lifecycle":"reuse_valid","provenance":"test","regeneration_scope":"once","random_value":{"alphabet":"hex_lower","length":32},"outputs":[{"name":"value","path":"token","sensitivity":"public"}]}}}`)
	input, err := participantFragment(t, admission.RealizationValue, raw)
	if err != nil {
		t.Fatal(err)
	}
	consumers, err := processor.GeneratedArtifactConsumers(input)
	if err != nil {
		t.Fatal(err)
	}
	entries := consumers["token"]
	if len(entries) != 1 || entries[0].Node != "host" || entries[0].TargetAddress != "provision.node.host" || entries[0].DeliveryMode != "environment" || entries[0].Output != "value" || entries[0].EnvironmentVariable != "MODE" || entries[0].Classification != "plain" {
		t.Fatalf("consumer derivation=%v", consumers)
	}
	consumers["token"][0].Node = "changed"
	again, err := processor.GeneratedArtifactConsumers(input)
	if err != nil || again["token"][0].Node != "host" {
		t.Fatalf("caller mutated facts: %v", err)
	}
	if _, err := processor.GeneratedArtifactConsumers(foreignParticipantFragment{input}); err == nil {
		t.Fatal("foreign context admitted")
	}
}
func TestGeneratedArtifactConsumersRefusesUnboundReferences(t *testing.T) {
	input, err := participantFragment(t, admission.RealizationValue, []byte(`{"name":"prepared-node-context","nodes":{"host":{"type":"compute","runtime":{"environment":[{"name":"MODE","value_classification":"plain","provenance":"runtime","value_from":{"generated_artifact":"generated_artifacts.absent","output":"value"}}]}}}}`))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := processor.GeneratedArtifactConsumers(input); err == nil {
		t.Fatal("unbound delivery accepted")
	}
}

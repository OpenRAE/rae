package runtime_test

import (
	"strings"
	"testing"

	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
)

func TestToolRequestPreservesCallGrammarAndGenerationBounds(t *testing.T) {
	request := runtimecontract.ToolActionRequest{ToolCallID: "call-1", InvocationActionInstanceID: "outer", ParticipantAddress: "participant", EpisodeID: "episode", ParticipantImplementationRef: "implementation", ToolAffordanceAddress: "tool", ActionContractAddress: "action", ObservationBoundaryAddress: "boundary", TargetAddresses: []string{"target"}, ExecutionScopeRef: "scope", ExecutionGeneration: 0}
	if request.Validate() != nil {
		t.Fatal("valid request refused")
	}
	for _, call := range []string{"", strings.Repeat("a", 129), "call/1", "é", "call\n"} {
		candidate := request
		candidate.ToolCallID = call
		if candidate.Validate() == nil {
			t.Fatal("invalid tool call accepted")
		}
	}
	candidate := request
	candidate.ExecutionGeneration = -1
	if candidate.Validate() == nil {
		t.Fatal("negative generation")
	}
	candidate = request
	candidate.TargetAddresses = []string{"target", "target"}
	if candidate.Validate() == nil {
		t.Fatal("duplicate target")
	}
}

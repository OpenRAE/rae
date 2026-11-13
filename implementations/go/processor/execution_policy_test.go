package processor_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestCompileRetainsCompleteLexicalExecutionPolicy(t *testing.T) {
	scenario, err := sdl.Parse([]byte(`name: example
nodes:
  server: {type: compute}
execution_policy:
  default: {policy_id: stop, response: terminate}
`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	policies := compiled.Model().View().ExecutionPolicies
	if len(policies) != 1 || policies[0].Address != "provision.node.server" || policies[0].Policy == nil {
		t.Fatalf("effective policies=%+v", policies)
	}
	document := requireType[map[string]any](t, policies[0].Policy.Document())
	if document["scope"] != "/nodes/server" || document["governing_scope"] != "#/" {
		t.Fatalf("lexical owner lost: %+v", document)
	}
}

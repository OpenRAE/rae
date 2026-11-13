package processor_test

import (
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestCompileBindingExecutionPoliciesUseConstructedResourceIdentities(t *testing.T) {
	for _, explicit := range []bool{false, true} {
		t.Run(map[bool]string{false: "default", true: "application"}[explicit], func(t *testing.T) {
			view := compileBindingPolicyFixture(t, explicit)
			for _, binding := range []struct{ address, section, name string }{
				{"provision.feature.host.setup", "features", "setup"},
				{"evaluation.condition.host.healthy", "conditions", "healthy"},
				{"orchestration.inject-binding.host.announce", "injects", "announce"},
			} {
				t.Run(binding.section, func(t *testing.T) {
					compiledTestResource(t, view.Resources, binding.address)
					scope, governing, id := "/"+binding.section+"/"+binding.name, "#/", "ambient"
					if explicit {
						scope = "/nodes/host" + scope
						governing, id = "#"+scope, "application"
					}
					requireCompiledBindingPolicy(t, view, binding.address, scope, governing, id)
				})
			}
		})
	}
}

func compileBindingPolicyFixture(t *testing.T, explicit bool) processor.CompiledScenario {
	t.Helper()
	raw, err := os.ReadFile("testdata/node-binding-execution-policy.yaml")
	if err != nil {
		t.Fatal(err)
	}
	if explicit {
		raw = append(raw, []byte(`  scopes:
    - {scope: /nodes/host/features/setup, policy: {policy_id: application, response: terminate}}
    - {scope: /nodes/host/conditions/healthy, policy: {policy_id: application, response: terminate}}
    - {scope: /nodes/host/injects/announce, policy: {policy_id: application, response: terminate}}
`)...)
	}
	scenario, err := sdl.Parse(raw, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	return compiled.Model().View()
}

func requireCompiledBindingPolicy(t *testing.T, view processor.CompiledScenario, address, scope, governing, id string) {
	t.Helper()
	for _, entry := range view.ExecutionPolicies {
		if entry.Address != address {
			continue
		}
		document := requireType[map[string]any](t, entry.Policy.Document())
		policy := requireType[map[string]any](t, document["policy"])
		if document["scope"] != scope || document["governing_scope"] != governing || policy["policy_id"] != id {
			t.Fatalf("binding policy %s lost its lexical owner: %+v", address, document)
		}
		return
	}
	t.Fatalf("compiled binding %s has no execution policy", address)
}

package authoring

import (
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestImportedPoliciesKeepLexicalScopes(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	c := composition{parser: parser}
	incoming := map[string]any{
		"nodes":                 map[string]any{"n": map[string]any{}},
		"features":              map[string]any{"f": map[string]any{}},
		"clocks":                map[string]any{"clock": map[string]any{}},
		"evidence_requirements": map[string]any{"e": map[string]any{}},
		"augmentation_scope":    map[string]any{"default": "closed", "scopes": []any{map[string]any{"scope": "/nodes/n", "permission": "open"}}},
		"execution_policy":      map[string]any{"default": map[string]any{"policy_id": "p", "response": "terminate"}, "scopes": []any{map[string]any{"scope": "/nodes/n/features/f", "policy": map[string]any{"policy_id": "q", "response": "hold", "clock_basis": "semantic", "clock_ref": "clock", "evidence_refs": []any{"e"}}}}},
	}
	parent := map[string]any{"augmentation_scope": map[string]any{"default": "closed"}}
	if err = c.composePolicies(parent, incoming, "m", nil); err != nil {
		t.Fatal(err)
	}
	augmentation := object(parent["augmentation_scope"])
	if augmentation["default"] != "closed" {
		t.Fatal("parent default changed")
	}
	rules := array(augmentation["scopes"])
	if len(rules) != 2 || object(rules[0])["permission"] != "closed" || object(rules[1])["scope"] != "/nodes/m.__private.n" {
		t.Fatalf("augmentation=%v", augmentation)
	}
	execution := object(parent["execution_policy"])
	rules = array(execution["scopes"])
	if len(rules) != 2 || object(rules[1])["scope"] != "/nodes/m.__private.n/features/m.__private.f" {
		t.Fatalf("execution=%v", execution)
	}
	policy := object(object(rules[1])["policy"])
	if policy["clock_ref"] != "m.__private.clock" || array(policy["evidence_refs"])[0] != "m.__private.e" {
		t.Fatalf("policy=%v", policy)
	}
}

func TestImportedPoliciesPreserveNestedNamespaceOwners(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, scope := range []string{"/nodes", "/nodes/inner.n"} {
		t.Run(scope, func(t *testing.T) {
			incoming := map[string]any{
				"nodes": map[string]any{"inner.n": map[string]any{}, "inner.other": map[string]any{}},
				"execution_policy": map[string]any{"scopes": []any{map[string]any{
					"scope": scope, "namespace": []any{"inner"}, "policy": map[string]any{"policy_id": "p", "response": "terminate"},
				}}},
			}
			parent := map[string]any{}
			c := composition{parser: parser}
			if err := c.composePolicies(parent, incoming, "m", nil); err != nil {
				t.Fatal(err)
			}
			rules := array(object(parent["execution_policy"])["scopes"])
			if len(rules) != 1 {
				t.Fatalf("namespace owner was duplicated: %v", rules)
			}
			if diff := cmp.Diff([]any{"m", "__private", "inner"}, array(object(rules[0])["namespace"])); diff != "" {
				t.Fatalf("nested namespace (-want +got): %s", diff)
			}
		})
	}
}

func TestImportedAugmentationRenamesStableAgentIdentity(t *testing.T) {
	value := map[string]any{"forwarding_agents": []any{map[string]any{"forwarding_agent_id": "a", "nested": []any{map[string]any{"text": "x"}}}}}
	symbols := importSymbols{"forwarding_agents": map[string]string{"a": "m.__private.a"}}
	_, canonical, err := admission.ResolveSDLObservationScope(value, "/forwarding_agents/0/nested/0/text")
	if err != nil {
		t.Fatal(err)
	}
	expected := map[string]any{"forwarding_agents": []any{map[string]any{"forwarding_agent_id": "m.__private.a", "nested": []any{map[string]any{"text": "x"}}}}}
	_, want, err := admission.ResolveSDLObservationScope(expected, "/forwarding_agents/0/nested/0/text")
	if err != nil {
		t.Fatal(err)
	}
	for _, pointer := range []string{"/forwarding_agents/0/nested/0/text", canonical} {
		got, err := augmentationPointer(pointer, value, symbols)
		if err != nil || got != want || !strings.Contains(got, "/@sha256:") {
			t.Fatalf("%s %v", got, err)
		}
	}
}

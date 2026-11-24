package authoring

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestScopeQueriesPreserveInputAndReuseContainers(t *testing.T) {
	p, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	value := map[string]any{"name": "example", nodesSection: map[string]any{"n": map[string]any{"type": computeType}}, "execution_policy": map[string]any{"default": map[string]any{"policy_id": "p", "response": "terminate"}}}
	value[forwardingSection] = []any{map[string]any{"forwarding_agent_id": "a"}}
	before, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	queries := newScopeQueries(p, materializedContract, value)
	for _, pointer := range []string{"", "/nodes/n/description", "/nodes/n/features", "/nodes/n/runtime", "/execution_policy", "/execution_policy/default", "/execution_policy/default/retry", "/execution_policy/default/retry/max_attempts"} {
		canonical, scopeErr := queries.resolve(pointer)
		if scopeErr != nil || canonical != pointer {
			t.Fatalf("%s resolved to %s: %v", pointer, canonical, scopeErr)
		}
	}
	containers := len(queries.copied)
	if _, scopeErr := queries.resolve("/nodes/n/description"); scopeErr != nil || len(queries.copied) != containers {
		t.Fatalf("repeated scope copied containers: %v", scopeErr)
	}
	for _, pointer := range []string{"/nodes/n/runtime/nope", "/nodes/n/missing", "/nodes/missing", "nodes/n"} {
		if _, scopeErr := queries.resolve(pointer); scopeErr == nil {
			t.Fatalf("unresolved scope %s accepted", pointer)
		}
	}
	checkStableScopeQueries(t, queries)
	after, err := json.Marshal(value)
	if err != nil || !bytes.Equal(before, after) {
		t.Fatal("scope query changed semantic input")
	}
}

func checkStableScopeQueries(t *testing.T, queries *scopeQueries) {
	t.Helper()
	const stable = "/forwarding_agents/@sha256:0eb5b8d6f81bc677da8a08567cc4fa9a06a57e9ec8da85ed73a7f62727996002/description"
	for _, pointer := range []string{"/forwarding_agents/0/description", stable} {
		canonical, scopeErr := queries.resolve(pointer)
		if scopeErr != nil || canonical != stable {
			t.Fatalf("stable identity scope %s resolved to %s: %v", pointer, canonical, scopeErr)
		}
	}
}

func TestFactoryDefaultsRejectUnknownFields(t *testing.T) {
	p, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	row := p.layouts[materializedContract]["#"]
	row.FactoryDefaults["future-unknown-field"] = json.RawMessage(`{}`)
	if err := p.checkLayout(materializedContract); err == nil {
		t.Fatal("unknown factory-default target accepted")
	}
}

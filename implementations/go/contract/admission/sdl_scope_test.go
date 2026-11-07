package admission

import (
	"strings"
	"testing"
)

func TestSDLObservationScopeUsesStableIdentity(t *testing.T) {
	value := map[string]any{"forwarding_agents": []any{map[string]any{"forwarding_agent_id": "a", "nested": []any{map[string]any{"text": "x"}}}}}
	const canonical = "/forwarding_agents/@sha256:0eb5b8d6f81bc677da8a08567cc4fa9a06a57e9ec8da85ed73a7f62727996002/nested/0/text"
	for _, pointer := range []string{"/forwarding_agents/0/nested/0/text", canonical} {
		source, address, err := ResolveSDLObservationScope(value, pointer)
		if err != nil || source != "/forwarding_agents/0/nested/0/text" || address != canonical {
			t.Fatalf("%s %s %v", source, address, err)
		}
	}
	for _, pointer := range []string{"/forwarding_agents/1", "/forwarding_agents/00", "/forwarding_agents/0/missing", "/forwarding_agents/~2", strings.Repeat("/x", 33), strings.Repeat("x", 4097)} {
		if _, _, err := ResolveSDLObservationScope(value, pointer); err == nil {
			t.Fatalf("accepted %q", pointer)
		}
	}
	duplicate := map[string]any{"forwarding_agents": []any{map[string]any{"forwarding_agent_id": "a"}, map[string]any{"forwarding_agent_id": "a"}}}
	if _, _, err := ResolveSDLObservationScope(duplicate, "/forwarding_agents/0"); err == nil {
		t.Fatal("duplicate identity accepted")
	}
}

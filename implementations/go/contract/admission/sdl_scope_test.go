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

func TestSDLObservationScopeReusesRegisteredCollectionIdentity(t *testing.T) {
	value := map[string]any{"nodes": map[string]any{"server": map[string]any{"runtime": map[string]any{"environment": []any{map[string]any{"name": "PUBLIC", "value": "example"}}}}}}
	profiles := []RealizationCollectionProfile{{FieldPointer: "/nodes/server/runtime/environment", CollectionKind: "runtime-environment", IdentityFields: []string{"name"}, Closure: RealizationClosure{Posture: "closed", Universe: "sdl-collection-members/v1", Profile: "recursive-realization-constraint/v1"}}}
	source, scope, err := ResolveSDLObservationScopeWithProfiles(value, "/nodes/server/runtime/environment/0/value", profiles)
	if err != nil || source != "/nodes/server/runtime/environment/0/value" || !strings.Contains(scope, "/@sha256:") {
		t.Fatalf("%s %s %v", source, scope, err)
	}
	again, canonical, err := ResolveSDLObservationScopeWithProfiles(value, scope, profiles)
	if err != nil || again != source || canonical != scope {
		t.Fatalf("unstable identity: %s %s %v", again, canonical, err)
	}
	profiles = append(profiles, profiles[0])
	if _, _, err := ResolveSDLObservationScopeWithProfiles(value, source, profiles); err == nil {
		t.Fatal("duplicate profile accepted")
	}
}

package admission

import "testing"

func TestMaterializationContentMatchesNativeIdentitiesWithoutClaimingActualAuthority(t *testing.T) {
	original := map[string]any{"name": "original", "port": 80}
	listener := map[string]any{"name": "listener", "port": 9090}
	before := compositionServices(t, []any{original, listener})
	after := compositionServices(t, []any{listener, original})
	matches, err := MaterializationContentMatches(before, after)
	if err != nil || !matches {
		t.Fatalf("reordered native identities mismatch: %v", err)
	}
	after = compositionServices(t, []any{listener})
	matches, err = MaterializationContentMatches(before, after)
	if err != nil || matches {
		t.Fatalf("missing admitted content matched=%v err=%v", matches, err)
	}
	if _, err := MaterializationContentMatches(before, MaterializationCompilation{}); err == nil {
		t.Fatal("malformed phase data admitted")
	}
}

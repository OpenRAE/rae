package admission

import (
	"strings"
	"testing"
)

func compositionInput(t *testing.T, input any) MaterializationCompilation {
	t.Helper()
	raw := projectionTestJSON(t, input)
	return MaterializationCompilation{Document: raw, FullDocument: raw}
}

func compositionServices(t *testing.T, services []any) MaterializationCompilation {
	t.Helper()
	return compositionInput(t, map[string]any{"name": "scope", "nodes": map[string]any{"host": map[string]any{"type": "compute", "services": services}}})
}

func TestMaterializationCompositionKeepsNativeIdentityAndProducerOwnership(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	original := map[string]any{"name": "original", "port": 80}
	collector := map[string]any{"name": "collector", "port": 9000}
	listener := map[string]any{"name": "listener", "port": 9090}
	base := compositionServices(t, []any{original})
	prior := compositionServices(t, []any{collector, original})
	local := compositionServices(t, []any{listener, original})
	combined, err := ComposeMaterializationContent(owner, base, prior, local)
	if err != nil {
		t.Fatal(err)
	}
	services := array(at(combined.Document(), "nodes", "host", "services"))
	if len(services) != 3 || stringAt(services[0], "name") != "collector" || stringAt(services[1], "name") != "original" || stringAt(services[2], "name") != "listener" {
		t.Fatalf("native service membership/order changed: %v", services)
	}
	if _, err := ComposeMaterializationContent(owner, base, prior, prior); err == nil {
		t.Fatal("two producers claimed the same added member")
	}
	removed := compositionInput(t, map[string]any{"name": "scope", "nodes": map[string]any{}})
	if _, err := ComposeMaterializationContent(owner, base, prior, removed); err == nil {
		t.Fatal("producer removed another producer's changed subtree")
	}
}

func TestMaterializationCompositionRefusesMalformedAndUnboundedPhaseData(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	base := compositionServices(t, []any{})
	oversized := compositionInput(t, map[string]any{"name": "scope", "description": strings.Repeat("x", (1<<20)+1), "nodes": map[string]any{}})
	if _, err := ComposeMaterializationContent(owner, base, base, oversized); err == nil {
		t.Fatal("oversized native scalar admitted")
	}
	if _, err := ComposeMaterializationContent(nil, base, base, base); err == nil {
		t.Fatal("missing owner admitted")
	}
}

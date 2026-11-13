package realization

import (
	"maps"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestObservedMountMarkersRoundTripWithoutRestoringProtectedSources(t *testing.T) {
	input := map[string]any{"target": "/data", "source": "", "source_kind": "bind", "source_sensitivity": "operator_secret", "options": []any{}, "backend_generated": false}
	projected, err := projectMountRecord(input, false)
	if err != nil {
		t.Fatal(err)
	}
	restored, err := restoreRuntimeMount(projected)
	if err != nil || restored["source"] != "" || restored["source_present"] != nil {
		t.Fatalf("mount reconstruction exposed a source: %+v %v", restored, err)
	}
	if projected["source_present"] != true || projected["options_present"] != false {
		t.Fatal("mount markers lost protected presence")
	}
	for _, test := range []struct {
		field string
		value any
	}{
		{"source_present", false}, {"source_present", "true"}, {"options_present", true}, {"options", true}, {"source_kind", "invented"},
	} {
		changed := maps.Clone(projected)
		changed[test.field] = test.value
		if _, err := restoreRuntimeMount(changed); err == nil {
			t.Fatalf("changed mount marker accepted: %s", test.field)
		}
	}
	if _, err := restoreRuntimeMount(map[string]any{"source_present": true}); err == nil {
		t.Fatal("incomplete protected mount accepted")
	}
}

func TestMountProjectionRefusesInvalidTargetsAndRawProtectedFields(t *testing.T) {
	for _, input := range []map[string]any{
		{}, {"target": "/data", "source": true},
		{"target": "/data", "source": "fixture-only", "source_sensitivity": "operator_secret"},
		{"target": "/data", "options": true},
		{"target": "/data", "options": []any{"secret"}, "options_sensitivity": "operator_secret"},
	} {
		if _, err := projectMounts([]any{input}, true, true); err == nil {
			t.Fatal("malformed or protected mount was projected")
		}
	}
	if _, err := mountMarkerExpected(map[string]any{"source": true}, "source"); err == nil {
		t.Fatal("non-string source produced a presence marker")
	}
	if _, err := mountMarkerExpected(map[string]any{"source_sensitivity": map[string]any{}}, "source"); err == nil {
		t.Fatal("invalid classification produced a presence marker")
	}
}

func TestCapabilityProjectionsRefuseInvalidOverridesAndKeepCanonicalScalarOrder(t *testing.T) {
	for _, input := range []any{nil, map[string]any{"required": true}, map[string]any{"process_overrides": true}, map[string]any{"process_overrides": []any{false}}, map[string]any{"process_overrides": []any{map[string]any{"subject": true}}}} {
		if _, err := projectCapabilities(input, false); err == nil {
			t.Fatal("malformed capability declaration accepted")
		}
	}
	projected, err := projectCapabilities(map[string]any{"required": []any{"CAP_Z", "CAP_A"}}, false)
	if err != nil || !cmp.Equal(projected["required"], []any{"CAP_A", "CAP_Z"}) {
		t.Fatalf("capability scalar order changed: %+v %v", projected, err)
	}
	for _, input := range []any{true, []any{true}} {
		if sortTypedScalarSequence(input) == nil {
			t.Fatal("non-string scalar collection accepted")
		}
	}
	if _, err := projectPorts([]any{map[string]any{"host_ip": []any{}}}, false); err == nil {
		t.Fatal("non-scalar port identity accepted")
	}
	if _, err := sharedProcessProjection(func() {}, false); err == nil {
		t.Fatal("non-JSON process identity accepted")
	}
	if checkObservedProcessBounds(map[string]any{"soft": "${limit}"}) == nil {
		t.Fatal("unbound observed process limit accepted")
	}
}

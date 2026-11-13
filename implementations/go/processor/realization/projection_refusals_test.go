package realization

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestRuntimeProjectionListsRefuseScalarAndUnownedMembers(t *testing.T) {
	projectors := []struct {
		name    string
		project func(any) ([]any, error)
	}{
		{"environment", func(v any) ([]any, error) { return projectEnvironment(v, true, true) }},
		{"forwarding", func(v any) ([]any, error) { return projectForwarding(v, true, true) }},
		{"forwarding settings", func(v any) ([]any, error) { return projectForwardingSettings(v, "agent", true, true) }},
		{"restore forwarding", restoreForwardingSettings},
		{"nested records", func(v any) ([]any, error) { return projectNestedRecords(v, "name", true) }},
		{"listeners", func(v any) ([]any, error) { return projectListeners(v, true) }},
		{"ports", func(v any) ([]any, error) { return projectPorts(v, true) }},
		{"mounts", func(v any) ([]any, error) { return projectMounts(v, true, true) }},
		{"process limits", func(v any) ([]any, error) { return projectProcessLimits(v, true, true) }},
		{"string list", stringSequence},
	}
	for _, projector := range projectors {
		t.Run(projector.name, func(t *testing.T) {
			for _, input := range []any{nil, true, []any{false}} {
				result, err := projector.project(input)
				if err == nil || result != nil {
					t.Fatalf("malformed runtime list produced a projection: %+v %v", result, err)
				}
			}
		})
	}
}

func TestProtectedRuntimeMarkersRefuseUnknownFieldsAndInvalidCommitments(t *testing.T) {
	commitment := runtimeValueCommitment + strings.Repeat("a", 64)
	for _, input := range []map[string]any{
		{"other_present": true}, {"value_present": "true"}, {"value_commitment": commitment},
		{"value_present": false, "value_commitment": commitment}, {"value_present": true, "value_commitment": "invalid"},
	} {
		if _, err := restoreRuntimeMarkers([]any{map[string]any{"nested": input}}); err == nil {
			t.Fatalf("invalid runtime marker restored: %+v", input)
		}
	}
	input := map[string]any{"values_present": true, "values_commitment": commitment}
	restored, err := restoreRuntimeRecord(input)
	if err != nil || !cmp.Equal(restored, map[string]any{"values": []any{}}) {
		t.Fatalf("marker reconstruction changed: %+v %v", restored, err)
	}
	if _, err := overlayRuntimeMarkers([]any{[]any{}}, []any{[]any{true}}); err == nil {
		t.Fatal("marker overlay accepted a changed collection shape")
	}
	for _, invalid := range []any{true, runtimeValueCommitment + "abc", runtimeValueCommitment + strings.Repeat("g", 64)} {
		if validCommitment(invalid) {
			t.Fatal("noncanonical commitment accepted")
		}
	}
}

func TestSensitiveFieldProjectionNeverAcceptsRawProtectedValues(t *testing.T) {
	for _, test := range []struct {
		classification any
		record         map[string]any
	}{
		{map[string]any{}, map[string]any{}},
		{"operator_secret", map[string]any{"value": "fixture-only"}},
		{"plain", map[string]any{"value": "fixture-only", "value_commitment": "invalid"}},
		{"plain", map[string]any{"value": func() {}}},
	} {
		if _, err := projectSensitiveField(test.record, "value", test.classification, "runtime-environment", "example", true); err == nil {
			t.Fatal("invalid protected-field projection accepted")
		}
	}
	for _, value := range []any{nil, "", []any{}} {
		if hasSensitiveValue(value) {
			t.Fatal("empty field produced a value commitment")
		}
	}
	if identity := runtimeLocalIdentity(map[string]any{"custom_id": true}); identity != "custom_id:True" {
		t.Fatalf("boolean native identity changed: %q", identity)
	}
	if identity := runtimeLocalIdentity(map[string]any{"custom_id": json.Number("7")}); identity != "custom_id:7" {
		t.Fatalf("integer native identity changed: %q", identity)
	}
}

func TestForwardingProjectionKeepsBufferPolicyAndRefusesMalformedChildren(t *testing.T) {
	input := map[string]any{"forwarding_agent_id": "agent", "buffer_policy": map[string]any{"description": "editorial", "capacity": json.Number("7")}}
	projected, err := projectForwardingAgent(input, false, false)
	if err != nil || !cmp.Equal(projected["buffer_policy"], map[string]any{"capacity": json.Number("7")}) {
		t.Fatalf("forwarding buffer projection changed: %+v %v", projected, err)
	}
	for _, field := range []string{"sources", "transforms", "ship_targets", "reload_channels", "settings", "buffer_policy"} {
		t.Run(field, func(t *testing.T) {
			if _, err := projectForwardingAgent(map[string]any{"forwarding_agent_id": "agent", field: true}, true, true); err == nil {
				t.Fatal("malformed forwarding child accepted")
			}
		})
	}
	if _, err := projectForwarding([]any{map[string]any{}}, false, false); err == nil {
		t.Fatal("forwarder without identity accepted")
	}
	if _, err := projectForwardingSettings([]any{map[string]any{}}, "agent", true, true); err == nil {
		t.Fatal("setting without identity accepted")
	}
}

func TestRuntimeObservationListsCannotSmuggleMalformedOrUncommittedFields(t *testing.T) {
	for _, input := range []any{true, []any{true}, []any{map[string]any{"settings": true}}, []any{map[string]any{"settings": []any{map[string]any{"value_present": true}}}}} {
		if validateForwardingObservation(input) == nil {
			t.Fatal("malformed forwarding observation accepted")
		}
	}
	for _, input := range []any{true, []any{true}, []any{map[string]any{"value_present": true}}} {
		if validateEnvironmentObservation(input) == nil {
			t.Fatal("malformed environment observation accepted")
		}
	}
	for _, record := range []map[string]any{
		{}, {"name": "TOKEN", "value_from": true}, {"name": "TOKEN", "value_classification": []any{}},
	} {
		if _, err := projectEnvironment([]any{record}, true, true); err == nil {
			t.Fatal("invalid environment source or classification accepted")
		}
	}
	if _, err := restoreCommittedRecord(map[string]any{"classification": "redacted", "value_present": true, "extra": true}, []string{"classification"}, "classification"); err == nil {
		t.Fatal("value-free observation carried an extra field")
	}
	if checkCommittedPresence(map[string]any{"value_present": "true"}, "classification") == nil {
		t.Fatal("non-boolean commitment presence accepted")
	}
}

func TestArtifactAvailabilityCannotRepeatAddressesOrClaimMalformedFacts(t *testing.T) {
	for _, input := range [][]ArtifactAvailability{
		{{}}, {{Address: "node"}, {Address: "node"}},
		{{Address: "node", AvailableArtifactDigests: []string{"same", "same"}}},
		{{Address: "node", AvailableMaterializationSpecificationDigests: []string{"invalid"}}},
		make([]ArtifactAvailability, 16385),
	} {
		if _, err := artifactAvailabilityIndex(input); err == nil {
			t.Fatal("unbounded or ambiguous artifact availability accepted")
		}
	}
}

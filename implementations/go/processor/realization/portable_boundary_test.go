package realization

import (
	"encoding/json"
	"maps"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestPortableRealizationGuardsTransportBeforeSemanticViews(t *testing.T) {
	canary := "private-portable-authority-canary"
	var plan binding.ProvisioningPlanV1
	raw := []byte(`{"operations":[{"action":"create","address":"provision.node.host","resource_type":"node","payload":{"private":"` + canary + strings.Repeat("x", 8<<20) + `"}}],"realization_authority":[]}`)
	requireNoError(t, json.Unmarshal(raw, &plan))
	snapshot := evaluationTestSnapshot(t, map[string]any{})
	for _, test := range []struct {
		name string
		call func() error
	}{
		{"diagnostics", func() error { _, err := PlannedAuthorityDiagnostics(plan, EvaluationOptions{}); return err }},
		{"requirements", func() error { _, err := PlannedRequirements(plan); return err }},
		{"readback", func() error { _, err := EvaluatePlanned(plan, snapshot, EvaluationOptions{}); return err }},
		{"cleanup", func() error {
			_, err := CleanupPlannedDiagnostics(plan, snapshot, nil, EvaluationOptions{})
			return err
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			err := test.call()
			if err == nil || strings.Contains(err.Error(), canary) {
				t.Fatal("portable work boundary accepted or exposed the oversized value")
			}
		})
	}
	empty := binding.ProvisioningPlanV1{}
	requireNoError(t, json.Unmarshal([]byte(`{"operations":[],"realization_authority":[]}`), &empty))
	result, err := EvaluatePlanned(empty, snapshot, EvaluationOptions{})
	requireNoError(t, err)
	if len(result.Diagnostics)+len(result.Provenance) != 0 {
		t.Fatal("refused portable input poisoned the next independent call")
	}
}

func TestPortableRequirementsComposeWithTheExistingSnapshotSanitizer(t *testing.T) {
	library := portableReferenceLibrary(t)
	plan := portablePlanForOpenKind(t, library, "runtime-environment")
	requirements, err := PlannedRequirements(plan)
	requireNoError(t, err)
	var decoded evaluatedPlan
	requireNoError(t, json.Unmarshal(requireJSON(t, plan), &decoded))
	operation := decoded.Operations[0]
	node := requireType[map[string]any](t, requireType[map[string]any](t, operation.Payload["spec"])["node"])
	canary := "capture-only-public-value"
	node["runtime"] = map[string]any{"environment": []any{map[string]any{"name": "TOKEN", "value": canary, "value_classification": "plain", "provenance": "runtime", "source": ""}}}
	document := map[string]any{"schema_version": "runtime-snapshot/v1", "entries": map[string]any{operation.Address: map[string]any{"address": operation.Address, "domain": "provisioning", "resource_type": "node", "payload": operation.Payload}}}
	var snapshot binding.RuntimeSnapshotV1
	requireNoError(t, json.Unmarshal(requireJSON(t, document), &snapshot))
	sanitized, err := SanitizeSnapshot(requirements, snapshot)
	requireNoError(t, err)
	raw := string(requireJSON(t, sanitized))
	if strings.Contains(raw, canary) || !strings.Contains(raw, "value_commitment") || !strings.Contains(raw, "value_present") {
		t.Fatal("portable concern recovery lost the existing privacy projection")
	}
	if !strings.Contains(string(requireJSON(t, snapshot)), canary) {
		t.Fatal("sanitization changed the caller-owned snapshot")
	}
	if len(requirements) == 0 {
		t.Fatal("missing recovered native requirement")
	}
	requirements[0].Kind = "changed"
	fresh, err := PlannedRequirements(plan)
	requireNoError(t, err)
	if len(fresh) == 0 || fresh[0].Kind == "changed" {
		t.Fatal("recovered portable views retained caller mutation")
	}
}

func portablePlanForOpenKind(t *testing.T, library portableRelationLibrary, kind string) binding.ProvisioningPlanV1 {
	t.Helper()
	for _, test := range library.Cases {
		plan := library.Plans[test.Plan]
		var decoded evaluatedPlan
		requireNoError(t, json.Unmarshal(requireJSON(t, plan), &decoded))
		for _, authority := range decoded.Authority {
			if authority.Kind == kind && authority.Mode == termOpen {
				return plan
			}
		}
	}
	t.Fatalf("no independent portable plan for %s", kind)
	return binding.ProvisioningPlanV1{}
}

func TestPortableProcessBoundLookupKeepsTheReferenceFirstMatch(t *testing.T) {
	// This identity is independently recorded from the Python contract owner.
	const identity = "sha256:dc85f90a20c69056ee15fafe7f81d302de8144ea98b877928364c107bc52b984"
	first, err := nativeValue([]byte(`{"resource":"open_file_descriptors","scope":"process","subject":{"name":"worker","pid":null,"parent_pid":null,"command":"","command_redacted":false,"role":"unknown","user":"","group":"","working_directory":""},"soft":100,"hard":200}`))
	requireNoError(t, err)
	second := maps.Clone(requireType[map[string]any](t, first))
	second[termSoft] = json.Number("200")
	lookup := plannedBoundLookup{input: []any{first, second}}
	for range 3 {
		if got := lookup.value(plannedBound{Identity: identity, Pointer: "/soft"}); got != json.Number("100") {
			t.Fatal("portable duplicate identity changed the reference first-match rule")
		}
	}
}

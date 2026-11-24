package realization

import (
	"slices"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestPreparedNodeUsesSharedRuntimeOwnerAndBackendRequirements(t *testing.T) {
	input := selectionTestValue(t, map[string]any{"type": "compute", "runtime": map[string]any{"processes": []any{map[string]any{"name": "worker"}}}})
	normalized, requirements, presence, err := CompilePreparedNode(input, "worker", "provision.node.worker")
	if err != nil {
		t.Fatal(err)
	}
	if admission.CheckFragment(normalized, admission.RealizationValue) != nil {
		t.Fatal("prepared node lost native value owner")
	}
	if !slices.Contains(presence["runtime.processes[0]"], "name") {
		t.Fatalf("typed required presence lost: %v", presence)
	}
	found := false
	for _, requirement := range requirements {
		if requirement.Kind != "runtime-processes" {
			continue
		}
		found = true
		if requirement.Posture == nil || *requirement.Posture != "exact" || requirement.Provenance != "backend-realized" || requirement.Constraint != nil {
			t.Fatalf("prepared authority=%+v", requirement)
		}
	}
	if !found {
		t.Fatal("prepared runtime concern did not become exact backend requirement")
	}
}
func TestPreparedNodeRefusesForeignHandleAndMismatchedIdentity(t *testing.T) {
	if _, _, _, err := CompilePreparedNode(replacedValue{}, "worker", "provision.node.worker"); err == nil {
		t.Fatal("foreign node accepted")
	}
	input := selectionTestValue(t, map[string]any{"type": "compute"})
	if _, _, _, err := CompilePreparedNode(input, "worker", "provision.node.other"); err == nil {
		t.Fatal("prepared node identity mismatch accepted")
	}
}

func TestPreparedNodeRetainsProtectedLogicalPresence(t *testing.T) {
	input := selectionTestValue(t, map[string]any{"type": "compute", "runtime": map[string]any{"environment": []any{map[string]any{"name": "TOKEN", "value_classification": "redacted", "provenance": "runtime", "source": "", "value_present": true}}}})
	_, requirements, presence, err := CompilePreparedNode(input, "worker", "provision.node.worker")
	if err != nil {
		t.Fatal(err)
	}
	if !slices.Contains(presence["runtime.environment[0]"], "value") {
		t.Fatal("restored blank erased protected logical presence")
	}
	if len(requirements) == 0 {
		t.Fatal("protected concern lost backend requirement")
	}
}

func TestPreparedLogicalMarkersCannotCreatePresenceForDataMaps(t *testing.T) {
	input := map[string]any{"runtime": map[string]any{"environment": []any{map[string]any{"name": "TOKEN", "value_present": true}}}, "data": map[string]any{"value_present": true}}
	presence := map[string][]string{"runtime.environment[0]": {"name"}}
	mergePreparedPresence(input, presence, "")
	if !slices.Contains(presence["runtime.environment[0]"], "value") {
		t.Fatal("native protected field lost logical presence")
	}
	if _, granted := presence["data"]; granted {
		t.Fatal("literal dictionary created typed child authority")
	}
}

func TestPreparedNodeRefusesBackendSecretMaterial(t *testing.T) {
	for _, classification := range []string{"secret_fixture", "operator_secret"} {
		t.Run(classification, func(t *testing.T) {
			input := selectionTestValue(t, map[string]any{"type": "compute", "runtime": map[string]any{"environment": []any{map[string]any{"name": "TOKEN", "value": "fixture-secret-material", "value_classification": classification}}}})
			if _, _, _, err := CompilePreparedNode(input, "worker", "provision.node.worker"); err == nil {
				t.Fatal("backend raw secret material accepted")
			} else if strings.Contains(err.Error(), "fixture-secret-material") {
				t.Fatal("rejected secret appeared in the error")
			}
		})
	}
}

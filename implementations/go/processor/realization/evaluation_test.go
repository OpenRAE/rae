package realization

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type evaluationReferenceCase struct {
	Name        string                `json:"name"`
	Source      string                `json:"source"`
	Plan        string                `json:"plan"`
	Snapshot    string                `json:"snapshot"`
	Manifest    string                `json:"manifest"`
	Envelope    string                `json:"envelope"`
	Kinds       []string              `json:"kinds"`
	Diagnostics []referenceDiagnostic `json:"diagnostics"`
	Provenance  []map[string]string   `json:"provenance"`
}
type evaluationReferenceLibrary struct {
	Sources   map[string]string                         `json:"sources"`
	Plans     map[string]binding.ProvisioningPlanV1     `json:"plans"`
	Snapshots map[string]binding.RuntimeSnapshotV1      `json:"snapshots"`
	Manifests map[string]binding.BackendManifestV2      `json:"manifests"`
	Envelopes map[string]*binding.RealizationEnvelopeV1 `json:"envelopes"`
	Cases     []evaluationReferenceCase                 `json:"cases"`
}

func TestEvaluationMatchesReferenceCases(t *testing.T) {
	raw, err := os.ReadFile("testdata/evaluation-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var library evaluationReferenceLibrary
	if err := json.Unmarshal(raw, &library); err != nil {
		t.Fatal(err)
	}
	for _, test := range library.Cases {
		t.Run(test.Name, func(t *testing.T) { checkReferenceEvaluation(t, library, test) })
	}
}
func checkReferenceEvaluation(t *testing.T, library evaluationReferenceLibrary, test evaluationReferenceCase) {
	t.Helper()
	compiled := compileRealizationFixture(t, library.Sources[test.Source])
	requirements := []Requirement{}
	for _, requirement := range compiled.Requirements {
		if containsString(test.Kinds, requirement.Kind) {
			requirements = append(requirements, requirement)
		}
	}
	if len(requirements) == 0 {
		t.Fatal("missing reference requirement")
	}
	manifest := library.Manifests[test.Manifest]
	got, err := Evaluate(requirements, library.Plans[test.Plan], library.Snapshots[test.Snapshot], EvaluationOptions{Manifest: &manifest, Envelope: library.Envelopes[test.Envelope]})
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(test.Diagnostics, referenceDiagnostics(got.Diagnostics)); diff != "" {
		t.Fatalf("diagnostics differ (-reference +native): %s", diff)
	}
	projected := make([]map[string]string, len(got.Provenance))
	for index, p := range got.Provenance {
		projected[index] = map[string]string{"Address": p.Address, "FieldPath": p.FieldPath, "Domain": p.Domain, "Kind": p.Kind, "Posture": p.Posture, "Provenance": p.Provenance, "GoverningScope": p.GoverningScope}
	}
	if diff := cmp.Diff(test.Provenance, projected); diff != "" {
		t.Fatalf("provenance differs (-reference +native): %s", diff)
	}
}

func evaluationTestPlan(t *testing.T, action string, payload map[string]any) binding.ProvisioningPlanV1 {
	t.Helper()
	document := map[string]any{"operations": []any{map[string]any{"address": "provision.node.server", "action": action, "resource_type": "node", "payload": payload}}, "diagnostics": []any{}, "realization_authority": []any{}}
	var result binding.ProvisioningPlanV1
	if err := json.Unmarshal(requireJSON(t, document), &result); err != nil {
		t.Fatal(err)
	}
	return result
}
func evaluationTestSnapshot(t *testing.T, payload map[string]any) binding.RuntimeSnapshotV1 {
	t.Helper()
	document := map[string]any{"schema_version": "runtime-snapshot/v1", "entries": map[string]any{"provision.node.server": map[string]any{"address": "provision.node.server", "domain": "provisioning", "resource_type": "node", "payload": payload}}}
	var result binding.RuntimeSnapshotV1
	if err := json.Unmarshal(requireJSON(t, document), &result); err != nil {
		t.Fatal(err)
	}
	return result
}
func TestEvaluationRetainsAbsenceDeletionAndValueFreeProvenance(t *testing.T) {
	requirement := exactRequirement("provision.node.server", "nodes.server.type", "node-type", "author-declared", "#/nodes/server/type")
	tests := []struct {
		name, action         string
		payload              map[string]any
		findings, provenance int
	}{
		{"honoured", "create", map[string]any{"node_kind": "compute"}, 0, 1},
		{"changed", "create", map[string]any{"node_kind": "switch"}, 1, 0},
		{"omitted", "create", map[string]any{}, 1, 0},
		{"deleted", "delete", map[string]any{}, 0, 0},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got, err := Evaluate([]Requirement{requirement}, evaluationTestPlan(t, test.action, map[string]any{"node_kind": "compute"}), evaluationTestSnapshot(t, test.payload), EvaluationOptions{})
			if err != nil {
				t.Fatal(err)
			}
			if len(got.Diagnostics) != test.findings || len(got.Provenance) != test.provenance {
				t.Fatalf("evaluation=%+v", got)
			}
			if len(got.Provenance) > 0 && got.Provenance[0].Provenance != "author-declared" {
				t.Fatalf("provenance=%+v", got.Provenance)
			}
		})
	}
}

func TestEvaluationKeepsEqualSelectionOriginSeparateFromConstraintAuthority(t *testing.T) {
	for _, test := range []struct{ posture, declared, expected string }{
		{"constrained", "author-declared", "backend-realized"},
		{"constrained", "processor-derived", "processor-derived"},
		{"exact", "author-declared", "author-declared"},
	} {
		t.Run(test.posture+"-"+test.declared, func(t *testing.T) {
			requirement := exactRequirement("provision.node.server", "nodes.server.type", "node-type", test.declared, "#/nodes/server/type")
			requirement.Posture = &test.posture
			payload := map[string]any{"node_kind": "compute"}
			result, err := Evaluate([]Requirement{requirement}, evaluationTestPlan(t, "create", payload), evaluationTestSnapshot(t, payload), EvaluationOptions{})
			if err != nil || len(result.Diagnostics) != 0 || len(result.Provenance) != 1 {
				t.Fatalf("evaluation=%+v,error=%v", result, err)
			}
			if result.Provenance[0].Provenance != test.expected {
				t.Fatalf("value origin=%s,expected=%s", result.Provenance[0].Provenance, test.expected)
			}
		})
	}
}

func TestEvaluationRefusesUnverifiedSubstrateDisclosureAtInputBoundary(t *testing.T) {
	raw, err := os.ReadFile("testdata/evaluation-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var library evaluationReferenceLibrary
	if err := json.Unmarshal(raw, &library); err != nil {
		t.Fatal(err)
	}
	for _, test := range library.Cases {
		if test.Name != "bound-independent-observation" {
			continue
		}
		var document map[string]any
		if err := json.Unmarshal(requireJSON(t, library.Snapshots[test.Snapshot]), &document); err != nil {
			t.Fatal(err)
		}
		observations := requireType[[]any](t, document["realization_observations"])
		requireType[map[string]any](t, observations[0])["binding_verified"] = false
		var snapshot binding.RuntimeSnapshotV1
		if err := json.Unmarshal(requireJSON(t, document), &snapshot); err != nil {
			t.Fatal(err)
		}
		manifest := library.Manifests[test.Manifest]
		if _, err := Evaluate(nil, library.Plans[test.Plan], snapshot, EvaluationOptions{Manifest: &manifest, Envelope: library.Envelopes[test.Envelope]}); err == nil {
			t.Fatal("unverified substrate disclosure admitted before semantic evaluation")
		}
		return
	}
	t.Fatal("missing bound observation fixture")
}

func TestEvaluationBoundsAggregateRequirementScalarsBeforePhaseChecks(t *testing.T) {
	requirement := exactRequirement("provision.node.server", strings.Repeat("x", 4096), "node-type", "author-declared", "#/nodes/server/type")
	batch := make([]Requirement, 2100)
	for index := range batch {
		batch[index] = requirement
	}
	planned := evaluationTestPlan(t, "delete", map[string]any{})
	snapshot := evaluationTestSnapshot(t, map[string]any{})
	if _, err := Evaluate(batch, planned, snapshot, EvaluationOptions{}); err == nil {
		t.Fatal("individually bounded requirements exceeded shared aggregate budget")
	}
}

package realization

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestArtifactEvaluationMatchesReferenceChoicesAndTrust(t *testing.T) {
	raw, err := os.ReadFile("testdata/artifact-evaluation.json")
	requireNoError(t, err)
	var cases []struct {
		Name         string                        `json:"name"`
		Posture      string                        `json:"posture"`
		Contract     binding.ArtifactRequirementV1 `json:"contract"`
		Manifest     binding.BackendManifestV2     `json:"manifest"`
		Availability []referenceAvailability       `json:"availability"`
		Plan         binding.ProvisioningPlanV1    `json:"plan"`
		Snapshot     binding.RuntimeSnapshotV1     `json:"snapshot"`
		Diagnostics  []referenceDiagnostic         `json:"diagnostics"`
		Provenance   []map[string]any              `json:"provenance"`
	}
	requireNoError(t, json.Unmarshal(raw, &cases))
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			requirement := exactRequirement("provision.node.web", "nodes.web.source.artifact_requirement", "source-artifact", "author-declared", "#/nodes/web/source/artifact_requirement")
			requirement.Posture = &test.Posture
			requirement.ArtifactRequirement = &test.Contract
			got, err := Evaluate([]Requirement{requirement}, test.Plan, test.Snapshot, EvaluationOptions{Manifest: &test.Manifest, ArtifactAvailability: referenceFacts(test.Availability)})
			requireNoError(t, err)
			if diff := cmp.Diff(test.Diagnostics, referenceDiagnostics(got.Diagnostics)); diff != "" {
				t.Fatalf("diagnostics differ (-reference +native): %s", diff)
			}
			if diff := cmp.Diff(test.Provenance, referenceArtifactProvenance(t, got.Provenance)); diff != "" {
				t.Fatalf("provenance differs (-reference +native): %s", diff)
			}
		})
	}
}
func referenceArtifactProvenance(t *testing.T, input []Provenance) []map[string]any {
	t.Helper()
	result := make([]map[string]any, len(input))
	for index, p := range input {
		if admission.CheckFragment(p.ArtifactSatisfaction, admission.ArtifactSatisfaction) != nil {
			t.Fatal("artifact provenance lost native satisfaction owner")
		}
		result[index] = map[string]any{"Address": p.Address, "FieldPath": p.FieldPath, "Domain": p.Domain, "Kind": p.Kind, "Posture": p.Posture, "Provenance": p.Provenance, "GoverningScope": p.GoverningScope, "artifact_satisfaction": p.ArtifactSatisfaction.Document()}
	}
	return result
}

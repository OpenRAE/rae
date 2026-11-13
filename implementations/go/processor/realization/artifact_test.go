package realization

import (
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"slices"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func artifactTestFixture(t *testing.T) (Requirement, binding.BackendManifestV2, []ArtifactAvailability, map[string]any) {
	t.Helper()
	var contract binding.ArtifactRequirementV1
	var manifest binding.BackendManifestV2
	var satisfaction map[string]any
	for name, output := range map[string]any{"artifact-contract.json": &contract, "artifact-manifest.json": &manifest, "artifact-satisfaction.json": &satisfaction} {
		raw, err := fs.ReadFile(os.DirFS("testdata"), name)
		if err != nil {
			t.Fatal(err)
		}
		if err := json.Unmarshal(raw, output); err != nil {
			t.Fatal(err)
		}
	}
	requirement := exactRequirement("provision.node.server", "nodes.server.source.artifact_requirement", "source-artifact", "author-declared", "#/nodes/server/source/artifact_requirement")
	requirement.ArtifactRequirement = &contract
	facts := []ArtifactAvailability{{Address: requirement.Address, AvailableArtifactDigests: []string{"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}, VerifiedIntegrityRefs: []string{"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}, VerifiedAdmissionRefs: []string{"reusable-asset-trust-policy-v1#reusable_scenario"}, VerifiedProvenanceRefs: []string{"provenance:stub"}}}
	return requirement, manifest, facts, satisfaction
}
func TestArtifactSupportKeepsAddressLocalFacts(t *testing.T) {
	requirement, manifest, facts, _ := artifactTestFixture(t)
	findings, err := ArtifactSupport([]Requirement{requirement}, manifest, facts)
	if err != nil || len(findings) != 0 {
		t.Fatalf("supported artifact: %v %v", findings, err)
	}
	facts[0].Address = "provision.node.other"
	findings, err = ArtifactSupport([]Requirement{requirement}, manifest, facts)
	if err != nil || len(findings) != 1 || findings[0].Code != "artifact.unavailable-exact-artifact" {
		t.Fatalf("foreign facts admitted: %v %v", findings, err)
	}
}
func TestArtifactEvaluationRequiresVerifiedTrustAndExactIdentity(t *testing.T) {
	requirement, manifest, facts, satisfaction := artifactTestFixture(t)
	planned := evaluationTestPlan(t, "create", map[string]any{})
	snapshot := evaluationTestSnapshot(t, map[string]any{"artifact_satisfaction": satisfaction})
	result, err := Evaluate([]Requirement{requirement}, planned, snapshot, EvaluationOptions{Manifest: &manifest, ArtifactAvailability: facts})
	if err != nil || len(result.Diagnostics) != 0 || len(result.Provenance) != 1 {
		t.Fatalf("valid artifact: %+v %v", result, err)
	}
	if admission.CheckFragment(result.Provenance[0].ArtifactSatisfaction, admission.ArtifactSatisfaction) != nil {
		t.Fatal("satisfaction lost native owner")
	}
	facts[0].VerifiedProvenanceRefs = nil
	result, err = Evaluate([]Requirement{requirement}, planned, snapshot, EvaluationOptions{Manifest: &manifest, ArtifactAvailability: facts})
	if err != nil || len(result.Diagnostics) != 1 || len(result.Provenance) != 0 {
		t.Fatalf("unverified provenance admitted: %+v %v", result, err)
	}
}

func TestArtifactAvailabilityRefusesMalformedSpecificationDigest(t *testing.T) {
	requirement, manifest, facts, _ := artifactTestFixture(t)
	facts[0].AvailableMaterializationSpecificationDigests = []string{"not-a-digest"}
	if _, err := ArtifactSupport([]Requirement{requirement}, manifest, facts); err == nil {
		t.Fatal("untyped materialization digest accepted")
	}
}

func TestArtifactSupportKeepsReferenceDiagnosticOrder(t *testing.T) {
	raw, err := os.ReadFile("testdata/artifact-support.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name         string                        `json:"name"`
		Posture      string                        `json:"posture"`
		Contract     binding.ArtifactRequirementV1 `json:"contract"`
		Manifest     binding.BackendManifestV2     `json:"manifest"`
		Availability []referenceAvailability       `json:"availability"`
		Diagnostics  []referenceDiagnostic         `json:"diagnostics"`
	}
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			requirement := exactRequirement("provision.node.web", "nodes.web.source.artifact_requirement", "source-artifact", "author-declared", "#/nodes/web/source/artifact_requirement")
			requirement.Posture = &test.Posture
			requirement.ArtifactRequirement = &test.Contract
			findings, err := ArtifactSupport([]Requirement{requirement}, test.Manifest, referenceFacts(test.Availability))
			if err != nil {
				t.Fatal(err)
			}
			if diff := cmp.Diff(test.Diagnostics, referenceDiagnostics(findings)); diff != "" {
				t.Fatalf("diagnostics differ (-reference +native): %s", diff)
			}
		})
	}
}

func TestSourceArtifactsUseBoundDeclarationNamesAndOrder(t *testing.T) {
	raw, err := os.ReadFile("testdata/artifact-contract.json")
	if err != nil {
		t.Fatal(err)
	}
	var contract map[string]json.RawMessage
	if err := json.Unmarshal(raw, &contract); err != nil {
		t.Fatal(err)
	}
	source := fmt.Sprintf(`name: bound-artifacts
nodes:
  server:
    type: compute
    roles: {operator: {username: operator}}
    features: {z-asset: operator, a-asset: operator}
features:
  z-asset: {type: artifact, source: %s}
  a-asset: {type: artifact, source: %s}
`, contract["source"], contract["source"])
	compiled := compileRealizationFixture(t, source)
	addresses := []string{}
	for _, requirement := range compiled.Requirements {
		if requirement.Kind == "source-artifact" {
			addresses = append(addresses, requirement.Address)
		}
	}
	if !slices.Equal(addresses, []string{"provision.feature.server.z-asset", "provision.feature.server.a-asset"}) {
		t.Fatalf("source artifact declarations lost identity/order: %v", addresses)
	}
}

func TestArtifactCandidateIDsStayLocalToEachRequirementAddress(t *testing.T) {
	raw, err := os.ReadFile("testdata/artifact-support.json")
	requireNoError(t, err)
	var cases []struct {
		Name     string                        `json:"name"`
		Contract binding.ArtifactRequirementV1 `json:"contract"`
		Manifest binding.BackendManifestV2     `json:"manifest"`
	}
	requireNoError(t, json.Unmarshal(raw, &cases))
	for _, test := range cases {
		if !strings.Contains(test.Name, "unavailable-candidate") {
			continue
		}
		first := exactRequirement("provision.node.first", "nodes.web.source.artifact_requirement", "source-artifact", "author-declared", "#/nodes/web/source/artifact_requirement")
		posture := "constrained"
		first.Posture = &posture
		first.ArtifactRequirement = &test.Contract
		second := first
		second.Address = "provision.node.second"
		facts := []ArtifactAvailability{{Address: first.Address, AvailableCandidateIDs: []string{"candidate-a"}}}
		findings, err := ArtifactSupport([]Requirement{first, second}, test.Manifest, facts)
		requireNoError(t, err)
		refused := []string{}
		for _, finding := range findings {
			if finding.Code == "artifact.unavailable-candidate" {
				refused = append(refused, finding.Address)
			}
		}
		if !slices.Equal(refused, []string{second.Address}) {
			t.Fatalf("candidate ID leaked across addresses: %v", refused)
		}
		return
	}
	t.Fatal("candidate reference fixture missing")
}

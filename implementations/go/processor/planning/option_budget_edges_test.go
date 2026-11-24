package planning

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

func TestPlanningOptionTextBudgetsRefuseInvalidAndAggregateAuthority(t *testing.T) {
	for _, text := range []string{string([]byte{255}), strings.Repeat("x", 1<<20+1)} {
		if err := checkNativeOptions(Options{ArtifactAvailability: []ArtifactAvailability{{Address: text}}}); err == nil {
			t.Fatal("invalid planning availability address accepted")
		}
	}
	for _, availability := range [][]ArtifactAvailability{
		make([]ArtifactAvailability, 16385),
		{{AvailableCandidateIDs: make([]string, 16385)}},
		{{AvailableCandidateIDs: []string{string([]byte{255})}}},
		{{AvailableCandidateIDs: make([]string, 16384), VerifiedIntegrityRefs: make([]string, 16384), VerifiedAdmissionRefs: make([]string, 16384), VerifiedEvidenceRefs: make([]string, 16384)}},
	} {
		if err := checkNativeOptions(Options{ArtifactAvailability: availability}); err == nil {
			t.Fatal("unbounded planning availability accepted")
		}
	}
	budget := optionTextBudget{bytes: 8 << 20}
	if budget.check("x") {
		t.Fatal("aggregate text budget ignored")
	}
}

func TestPlanningProfilesRefuseUnpinnedTargetsAndInvalidAuthoredOwners(t *testing.T) {
	selection := privateServiceProfile(t)
	view := processor.CompiledScenario{Resources: []processor.Resource{{Address: "provision.node.host", Kind: "node", SelectedProfiles: []binding.DomainProfileBindingV1{selection}}}}
	_, findings, err := prepareProfiles(view, binding.BackendManifestV2{}, nil, nil, nil)
	if err != nil || len(findings) != 1 || findings[0].Code != "realization.profile-unsupported" {
		t.Fatalf("invalid authored profile owner accepted: %+v %v", findings, err)
	}
	if _, _, err := prepareProfiles(processor.CompiledScenario{}, binding.BackendManifestV2{}, &binding.DomainProfileResolutionContextV1{}, nil, nil); err == nil {
		t.Fatal("invalid independent profile context accepted")
	}
	var manifest binding.BackendManifestV2
	if err := json.Unmarshal([]byte(`{"supported_contract_versions":["backend-realization-preparation-v1"]}`), &manifest); err != nil {
		t.Fatal(err)
	}
	plan := executionPlan{manifest: manifest}
	if _, err := plan.attachPreparation(processor.CompiledScenario{}, nil); err == nil {
		t.Fatal("invalid backend manifest issued preparation authority")
	}
}

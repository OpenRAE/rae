package analysis

import (
	"encoding/json"
	"fmt"
	"maps"
	"os"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestOpacityModelCheckReferenceAndReleaseIdentity(t *testing.T) {
	root := "../../../../"
	input := readTestFile(t, root+"contracts/fixtures/formal-analysis/participant-opacity-model-check-input-v1/valid/opaque-transition-model.json")
	expected := readTestFile(t, root+"contracts/fixtures/formal-analysis/participant-opacity-model-check-evidence-v1/valid/opaque-transition-model.json")
	var want map[string]any
	if err := json.Unmarshal(expected, &want); err != nil {
		t.Fatal(err)
	}
	// This static published fixture predates the current product release. Rebind
	// its checker release identity to the release authority, without changing it.
	raw, err := os.ReadFile(root + ".release-please-manifest.json")
	if err != nil {
		t.Fatal(err)
	}
	var releases map[string]string
	if err = json.Unmarshal(raw, &releases); err != nil {
		t.Fatal(err)
	}
	if analysisPackageVersion != releases["."] {
		t.Fatal("checker package version differs from the release manifest")
	}
	if err = referenceReleaseMetadata(want); err != nil {
		t.Fatal(err)
	}
	got, err := Analyze(Request{Kind: "participant-opacity-model-check", Input: &JSONInput{Data: input}})
	if err != nil {
		t.Fatal(err)
	}
	raw, err = json.Marshal(got.Document)
	if err != nil {
		t.Fatal(err)
	}
	var actual map[string]any
	if err = json.Unmarshal(raw, &actual); err != nil {
		t.Fatal(err)
	}
	if difference := cmp.Diff(want, actual); difference != "" {
		t.Fatalf("-want +got:\n%s", difference)
	}
}

func TestOpacityModelResourceLimitProducesEvidence(t *testing.T) {
	input := testObject(t, readTestFile(t, "../../../../contracts/fixtures/formal-analysis/participant-opacity-model-check-input-v1/valid/opaque-transition-model.json"))
	governed, err := loadOpacityProfile(input)
	if err != nil {
		t.Fatal(err)
	}
	object(object(governed["parameters"])["bounds"])["max_points"] = 16384
	profile := testAdmission(t, "behavioral-relation-profile-v1", testJSON(t, governed), opacityClaimContext{claim: testJSON(t, input["claim"])})
	input["profile_digest"], err = hash(governed)
	if err != nil {
		t.Fatal(err)
	}
	seed := object(array(input["states"])[0])
	states := make([]any, 8193)
	for index := range states {
		state := maps.Clone(seed)
		state["ordinal"] = index
		state["state_ref"] = fmt.Sprintf("model-state:bounded-%05d", index)
		states[index] = state
	}
	input["states"] = states
	input["initial_state_ordinals"] = []int{0}
	counts := object(input["declared_counts"])
	counts["states"], counts["evaluation_points"], counts["runs"], counts["initial_states"] = len(states), len(states), 1, 1
	result, err := Analyze(Request{Kind: "participant-opacity-model-check", Input: &JSONInput{Data: testJSON(t, input), Profile: profile}})
	if err != nil {
		t.Fatal(err)
	}
	if result.Document["outcome"] != "unsupported" || len(result.Diagnostics) != 1 || result.Diagnostics[0].Code != "participant-opacity-model-check.bound-exceeded" {
		t.Fatalf("wrong resource result: %v", result.Document)
	}
}

func TestReferenceReleaseMetadataRemainsDigestBound(t *testing.T) {
	raw := readTestFile(t, "../../../../contracts/fixtures/formal-analysis/participant-opacity-model-check-evidence-v1/valid/opaque-transition-model.json")
	expected := testObject(t, raw)
	config := object(expected["checker_configuration"])
	config["package_version"] = "1.2.3"
	identity, err := hash(config)
	if err != nil {
		t.Fatal(err)
	}
	expected["checker_configuration_digest"] = identity
	if err = referenceReleaseMetadata(expected); err != nil {
		t.Fatal(err)
	}
	if config["package_version"] != analysisPackageVersion {
		t.Fatal("stale release metadata retained")
	}
	identity, err = hash(config)
	if err != nil || expected["checker_configuration_digest"] != identity {
		t.Fatal("current release digest is not bound")
	}
	expected["checker_configuration_digest"] = "sha256:" + strings.Repeat("a", 64)
	if err = referenceReleaseMetadata(expected); err == nil {
		t.Fatal("forged reference digest admitted")
	}
}

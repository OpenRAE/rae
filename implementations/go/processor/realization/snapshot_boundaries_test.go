package realization

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestPreparedArtifactKeepsThePublishedSourceContract(t *testing.T) {
	original, manifest, availability, _ := artifactTestFixture(t)
	var document map[string]any
	if err := json.Unmarshal(requireJSON(t, original.ArtifactRequirement), &document); err != nil {
		t.Fatal(err)
	}
	node := map[string]any{"source": document["source"]}
	requirement, err := preparedArtifactRequirement(node, "server", "provision.node.server")
	if err != nil || requirement == nil || requirement.ArtifactRequirement == nil || requirement.Provenance != "backend-realized" {
		t.Fatalf("prepared artifact lost its native contract: %+v %v", requirement, err)
	}
	findings, err := ArtifactSupport([]Requirement{*requirement}, manifest, availability)
	if err != nil || len(findings) != 0 {
		t.Fatalf("prepared artifact no longer joins existing support facts: %+v %v", findings, err)
	}
	for _, source := range []any{map[string]any{"artifact_requirement": func() {}}, map[string]any{"artifact_requirement": 7}, map[string]any{"artifact_requirement": map[string]any{}}} {
		if _, err := preparedArtifactRequirement(map[string]any{"source": source}, "server", "provision.node.server"); err == nil {
			t.Fatal("invalid prepared artifact contract accepted")
		}
	}
}

func TestSnapshotSanitizationRefusesUnownedAddressesAndInvalidTransport(t *testing.T) {
	for _, addresses := range [][]string{{"evaluation.test"}, {"provision.node.host", "provision.node.host"}, {strings.Repeat("x", 4097)}, make([]string, 16385)} {
		if preparedSanitizationAddresses(addresses) == nil {
			t.Fatal("invalid prepared snapshot address set accepted")
		}
	}
	valid := evaluationTestSnapshot(t, map[string]any{})
	if _, err := SanitizeSnapshot(make([]Requirement, sdl.DefaultLimits().MaxComposedNodes+1), valid); err == nil {
		t.Fatal("unbounded snapshot requirements accepted")
	}
	var malformed binding.RuntimeSnapshotV1
	if err := malformed.Entries.UnmarshalJSON([]byte(`{"provision.node.host":7}`)); err != nil {
		t.Fatal(err)
	}
	entries, _ := malformed.Entries.Value()
	entries["provision.node.host"] = json.RawMessage(`{`)
	if _, err := SanitizeSnapshot(nil, malformed); err == nil {
		t.Fatal("invalid snapshot transport accepted")
	}
	if _, err := SanitizePreparedNodeSnapshot([]string{"provision.node.host"}, malformed); err == nil {
		t.Fatal("invalid prepared snapshot transport accepted")
	}
}

func TestSoftwareReferenceValidationChecksOnlyTypedRuntimeReferences(t *testing.T) {
	for _, payload := range []map[string]any{nil, {"spec": map[string]any{"node": map[string]any{"runtime": "not-a-runtime"}}}, {"spec": map[string]any{"node": map[string]any{"runtime": map[string]any{"software_components": []any{}}}}}} {
		if err := validateSoftwareReferences(payload); err != nil {
			t.Fatal(err)
		}
	}
	runtime := map[string]any{"software_components": []any{map[string]any{}}, "packages": func() {}}
	payload := map[string]any{"spec": map[string]any{"node": map[string]any{"runtime": runtime}}}
	if validateSoftwareReferences(payload) == nil {
		t.Fatal("non-JSON software references accepted")
	}
	runtime["packages"] = []any{}
	if validateSoftwareReferences(payload) == nil {
		t.Fatal("incomplete typed software component accepted")
	}
}

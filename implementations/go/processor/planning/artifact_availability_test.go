package planning_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

func TestPlannerThreadsAddressScopedArtifactAvailability(t *testing.T) {
	raw, err := os.ReadFile("../realization/testdata/artifact-contract.json")
	requireNoError(t, err)
	var contract struct {
		Source map[string]any `json:"source"`
	}
	requireNoError(t, json.Unmarshal(raw, &contract))
	scenario := map[string]any{"name": "portable-artifact-plan", "nodes": map[string]any{"web": map[string]any{"type": "compute", "os": "linux", "source": contract.Source}}}
	compiled := compile(t, string(requireJSON(t, scenario)))
	raw, err = os.ReadFile("../realization/testdata/artifact-manifest.json")
	requireNoError(t, err)
	var backend binding.BackendManifestV2
	requireNoError(t, json.Unmarshal(raw, &backend))
	for _, test := range []struct {
		name, address string
		digests       []string
		missing       bool
	}{
		{"unavailable", "provision.node.web", nil, true},
		{"available", "provision.node.web", []string{"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}, false},
		{"foreign-address", "provision.node.other", []string{"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			options := planning.Options{ArtifactAvailability: []planning.ArtifactAvailability{{Address: test.address, AvailableArtifactDigests: test.digests}}}
			result, planErr := planning.PlanWithManifest(compiled, backend, options)
			requireNoError(t, planErr)
			missing := false
			for _, finding := range result.Diagnostics {
				if finding.Code == "artifact.unavailable-exact-artifact" {
					missing = true
				}
			}
			if missing != test.missing {
				t.Fatalf("artifact unavailable=%v,expected=%v", missing, test.missing)
			}
		})
	}
}

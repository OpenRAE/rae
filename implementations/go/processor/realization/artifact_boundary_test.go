package realization

import (
	"encoding/json"
	"io/fs"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestArtifactPublishedFixturesUseTheExistingClosedContract(t *testing.T) {
	owner, err := realizationOwner()
	requireNoError(t, err)
	files := os.DirFS("../../../../contracts/fixtures/artifact-requirements/artifact-requirement-v1")
	for _, directory := range []string{"valid", "invalid"} {
		paths, err := fs.Glob(files, directory+"/*.json")
		requireNoError(t, err)
		if len(paths) == 0 {
			t.Fatal("published artifact fixtures missing")
		}
		for _, path := range paths {
			t.Run(path, func(t *testing.T) {
				raw, err := fs.ReadFile(files, path)
				requireNoError(t, err)
				err = owner.CheckPortable("artifact-requirement-v1", raw, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
				if (err == nil) != (directory == "valid") {
					t.Fatalf("published fixture admission: %v", err)
				}
			})
		}
	}
}

func TestArtifactSatisfactionRoundTripsThroughExistingSnapshotProvenance(t *testing.T) {
	raw, err := os.ReadFile("testdata/artifact-satisfaction.json")
	requireNoError(t, err)
	var satisfaction map[string]any
	requireNoError(t, json.Unmarshal(raw, &satisfaction))
	entry := map[string]any{"address": "provision.node.server", "field_path": "nodes.server.source.artifact_requirement", "domain": "runtime-realization", "requirement_kind": "source-artifact", "explicitness": "exact", "provenance": "author-declared", "governing_scope": "#/nodes/server/source/artifact_requirement", "artifact_satisfaction": satisfaction}
	document := map[string]any{"schema_version": "runtime-snapshot/v1", "entries": map[string]any{}, "realization_provenance": []any{entry}}
	var snapshot binding.RuntimeSnapshotV1
	requireNoError(t, json.Unmarshal(requireJSON(t, document), &snapshot))
	owner, err := realizationOwner()
	requireNoError(t, err)
	requireNoError(t, owner.CheckPortable("runtime-snapshot-v1", requireJSON(t, snapshot), ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}))
	var restored map[string]any
	requireNoError(t, json.Unmarshal(requireJSON(t, snapshot), &restored))
	provenance := requireType[[]any](t, restored["realization_provenance"])
	if !payloadEqual(requireType[map[string]any](t, provenance[0])["artifact_satisfaction"], satisfaction) {
		t.Fatal("existing provenance carrier changed artifact satisfaction")
	}
}

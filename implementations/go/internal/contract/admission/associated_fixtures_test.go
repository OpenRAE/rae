package admission

import (
	"encoding/json"
	"io"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

type associatedFixtureContext struct {
	parent         validation.Value
	payloads       map[string]io.Reader
	snapshotDigest string
}

func (c associatedFixtureContext) AssociatedParent() validation.Value       { return c.parent }
func (c associatedFixtureContext) AssociatedPayloads() map[string]io.Reader { return c.payloads }
func (c associatedFixtureContext) AssociatedParentDigest() string           { return c.snapshotDigest }

// These verdicts come from the full Python byte/parent validator. Structural
// CLI positives alone cannot vouch for a different independently supplied parent.
func TestPublishedAssociatedFixturesAgainstReferenceOwners(t *testing.T) {
	raw, err := os.ReadFile("testdata/associated-fixture-verdicts.json")
	if err != nil {
		t.Fatal(err)
	}
	var recording struct {
		SnapshotDigest string                     `json:"scenario_snapshot_digest"`
		Cases          []associatedFixtureVerdict `json:"cases"`
	}
	if err := json.Unmarshal(raw, &recording); err != nil {
		t.Fatal(err)
	}
	if len(recording.Cases) != 7 {
		t.Fatal("associated reference inventory changed")
	}
	e := boundTestOwner(t)
	for _, c := range recording.Cases {
		t.Run(c.Name, func(t *testing.T) { checkAssociatedFixture(t, e, c, recording.SnapshotDigest) })
	}
}

type associatedFixtureVerdict struct {
	Name   string   `json:"name"`
	Path   string   `json:"path"`
	Parent string   `json:"parent_contract"`
	Valid  bool     `json:"valid"`
	Codes  []string `json:"codes"`
}

func checkAssociatedFixture(t *testing.T, e *Validator, c associatedFixtureVerdict, snapshotDigest string) {
	t.Helper()
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	parentRaw := []byte(`{"name":"training-range","version":"1.0.0"}`)
	if c.Parent != "sdl-authoring-input-v1" {
		parentRaw = controlJSON(t, fixtureObject(t, "fixtures/experiment-core/"+c.Parent+"/valid/reference.json"))
	}
	parent, err := e.Validate(c.Parent, parentRaw, limits, referenceAttachmentParentContext(t))
	if err != nil {
		t.Fatalf("independent parent: %v", err)
	}
	context := associatedFixtureContext{parent: parent, payloads: map[string]io.Reader{"operator-guide": strings.NewReader("operator guide\n")}, snapshotDigest: snapshotDigest}
	input := controlJSON(t, fixtureObject(t, c.Path))
	admitted, err := e.Validate("associated-artifact-manifest-v1", input, limits, context)
	if (err == nil) != c.Valid {
		t.Fatalf("full admission=%v; full reference=%v (%v); %v", err == nil, c.Valid, c.Codes, err)
	}
	if err != nil && (admitted.ContractID() != "" || len(admitted.JSON()) != 0) {
		t.Fatal("refusal returned admitted data")
	}
}

func referenceAttachmentParentContext(t *testing.T) testExperimentContext {
	t.Helper()
	task := controlJSON(t, fixtureObject(t, "fixtures/experiment-core/experiment-task-v1/valid/reference.json"))
	run := controlJSON(t, fixtureObject(t, "fixtures/experiment-core/experiment-run-v1/valid/reference.json"))
	return testExperimentContext{testManifestContext: historicalManifestContext(t), task: task, tasks: [][]byte{task}, runs: [][]byte{run}}
}

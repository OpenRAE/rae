package admission

import (
	"bytes"
	"encoding/json"
	"io"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

type controlAssetReferenceCase struct {
	Name            string          `json:"name"`
	Asset           json.RawMessage `json:"asset"`
	RegisteredAsset json.RawMessage `json:"registered_asset"`
	Manifest        json.RawMessage `json:"manifest"`
	Parent          json.RawMessage `json:"parent"`
	Content         []byte          `json:"content"`
	ReaderAvailable bool            `json:"reader_available"`
	Admitted        bool            `json:"admitted"`
}

type controlAssetContentTestContext struct {
	*controlAgreementTestContext
	associatedFixtureContext

	manifest []byte
}

func (c controlAssetContentTestContext) ControlContentManifest() []byte { return c.manifest }

func TestControlAssetContentBindingsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Snapshot json.RawMessage             `json:"snapshot"`
		Cases    []controlAssetReferenceCase `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/control-asset-verdicts.json", &reference)
	if len(reference.Cases) != 9 {
		t.Fatal("independent control asset inventory changed")
	}
	e := boundTestOwner(t)
	for _, c := range reference.Cases {
		t.Run(c.Name, func(t *testing.T) { checkControlAssetReference(t, e, reference.Snapshot, c) })
	}
}

func checkControlAssetReference(t *testing.T, e *Validator, rawSnapshot []byte, c controlAssetReferenceCase) {
	t.Helper()
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	parent, err := e.Validate("experiment-task-v1", c.Parent, limits, nil)
	if err != nil {
		t.Fatal("independent task parent:", err)
	}
	snapshot := decodeRuleObject(t, string(rawSnapshot))
	generation, ok := at(snapshot, "episode_generation").(json.Number)
	if !ok {
		t.Fatal("reference snapshot generation is not numeric")
	}
	state := ControlSnapshot{ScopeRef: stringAt(snapshot, "scope_ref"), RunID: stringAt(snapshot, "run_id"), ParticipantAddress: stringAt(snapshot, "participant_address"), EpisodeID: stringAt(snapshot, "episode_id"), AudienceScopeRef: stringAt(snapshot, "audience_scope_ref"), EpisodeGeneration: generation, RecordCut: controlJSON(t, at(snapshot, "record_cut"))}
	attachment := associatedFixtureContext{parent: parent, payloads: map[string]io.Reader{}}
	context := controlAssetContentTestContext{controlAgreementTestContext: &controlAgreementTestContext{snapshot: state, allow: true}, associatedFixtureContext: attachment, manifest: c.Manifest}
	if object(decodeRuleObject(t, string(c.RegisteredAsset))) != nil {
		context.assets = [][]byte{c.RegisteredAsset}
	}
	if c.ReaderAvailable {
		asset := decodeRuleObject(t, string(c.Asset))
		context.payloads[stringAt(asset, "content", "artifact_id")] = bytes.NewReader(c.Content)
	}
	admitted, err := e.Validate(termParticipantControlContextAssetV1, c.Asset, limits, context)
	if (err == nil) != c.Admitted {
		t.Fatalf("control asset content differs from Python (admitted=%v): %v", c.Admitted, err)
	}
	if err != nil && (admitted.ContractID() != "" || len(admitted.JSON()) != 0) {
		t.Fatal("refused content returned admitted data")
	}
}

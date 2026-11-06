package consumer

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// phase is a recorded compiler result. The fixture keeps the JSON members of
// admission.MaterializationCompilation as JSON.
type phase struct {
	SourceSHA256             string                         `json:"SourceSHA256"`
	Document                 json.RawMessage                `json:"Document"`
	FullDocument             json.RawMessage                `json:"FullDocument"`
	Resources                []json.RawMessage              `json:"Resources"`
	RealizationRequirements  []json.RawMessage              `json:"RealizationRequirements"`
	CollectionIdentities     map[string][]string            `json:"CollectionIdentities"`
	NodeCollection           json.RawMessage                `json:"NodeCollection"`
	NodeConcerns             map[string][]json.RawMessage   `json:"NodeConcerns"`
	PreparedNodeRequirements map[string][]json.RawMessage   `json:"PreparedNodeRequirements"`
	OrdinarySelections       map[string]string              `json:"OrdinarySelections"`
	NodePresence             map[string]map[string][]string `json:"NodePresence"`
}

func rows(items []json.RawMessage) [][]byte {
	result := make([][]byte, 0, len(items))
	for _, item := range items {
		result = append(result, item)
	}
	return result
}

func (p phase) compilation() admission.MaterializationCompilation {
	concerns, prepared := map[string][][]byte{}, map[string][][]byte{}
	for key, items := range p.NodeConcerns {
		concerns[key] = rows(items)
	}
	for key, items := range p.PreparedNodeRequirements {
		prepared[key] = rows(items)
	}
	var collection []byte
	if string(p.NodeCollection) != "null" {
		collection = p.NodeCollection
	}
	return admission.MaterializationCompilation{SourceSHA256: p.SourceSHA256, Document: p.Document, FullDocument: p.FullDocument, Resources: rows(p.Resources), RealizationRequirements: rows(p.RealizationRequirements), CollectionIdentities: p.CollectionIdentities, NodeCollection: collection, NodeConcerns: concerns, PreparedNodeRequirements: prepared, OrdinarySelections: p.OrdinarySelections, NodePresence: p.NodePresence}
}

type fixture struct {
	Execution struct {
		Submission  string          `json:"Submission"`
		Plan        json.RawMessage `json:"Plan"`
		Manifest    json.RawMessage `json:"Manifest"`
		Predecessor json.RawMessage `json:"Predecessor"`
		Actual      json.RawMessage `json:"Actual"`
		Envelope    json.RawMessage `json:"Envelope"`
		Original    phase           `json:"Original"`
		Current     phase           `json:"Current"`
	} `json:"Execution"`
	Retained struct {
		SDL    string          `json:"SDL"`
		Phase  phase           `json:"Phase"`
		Record json.RawMessage `json:"Record"`
	} `json:"Retained"`
}

// owner is the consumer's trusted materialization owner. It returns recorded
// compiler results and authenticates the protected SDL of each attestation.
type owner struct {
	snapshot                    admission.MaterializationExecutionSnapshot
	envelope                    validation.Value
	original, current, retained admission.MaterializationCompilation
	sources                     map[string][]byte
}

func (o *owner) MaterializationExecutionSnapshot() admission.MaterializationExecutionSnapshot {
	return o.snapshot
}
func (o *owner) MaterializationEnvelope() validation.Value { return o.envelope }

func (o *owner) CompileMaterialization(request admission.MaterializationCompileRequest) (admission.MaterializationCompilation, error) {
	source := digest.SHA256(request.Source)
	if source == o.retained.SourceSHA256 {
		return o.retained, nil
	}
	compiled := o.current
	if request.ContractID == "instantiated-scenario-v1" {
		compiled = o.original
	}
	if request.Plan.ContractID() != "provisioning-plan-v1" || source != compiled.SourceSHA256 {
		return admission.MaterializationCompilation{}, errors.New("unknown compiler request")
	}
	return compiled, nil
}

// NormalizeMaterializationNode returns the recorded node of a compiled resource.
// It never derives trusted data from the candidate.
func (o *owner) NormalizeMaterializationNode(request admission.MaterializationNodeProjection) (json.RawMessage, error) {
	var operand any
	if err := json.Unmarshal(request.Node, &operand); err != nil {
		return nil, err
	}
	want, err := json.Marshal(operand)
	if err != nil {
		return nil, err
	}
	for _, compiled := range []admission.MaterializationCompilation{o.original, o.current} {
		node, err := recordedNode(compiled, request.Name, want)
		if err != nil || node != nil {
			return node, err
		}
	}
	return nil, errors.New("unknown normalized node")
}

// recordedNode returns the compiled node named name whose resource specifies
// the node want, or nil.
func recordedNode(compiled admission.MaterializationCompilation, name string, want []byte) (json.RawMessage, error) {
	var full struct {
		Nodes map[string]json.RawMessage `json:"nodes"`
	}
	if err := json.Unmarshal(compiled.FullDocument, &full); err != nil {
		return nil, err
	}
	for _, resource := range compiled.Resources {
		var row struct {
			Payload struct {
				Name string `json:"name"`
				Spec struct {
					Node any `json:"node"`
				} `json:"spec"`
			} `json:"payload"`
		}
		if err := json.Unmarshal(resource, &row); err != nil {
			return nil, err
		}
		node, err := json.Marshal(row.Payload.Spec.Node)
		if err != nil {
			return nil, err
		}
		if row.Payload.Name == name && bytes.Equal(node, want) {
			return full.Nodes[name], nil
		}
	}
	return nil, nil
}

func (o *owner) RetainedMaterializationSDL(record json.RawMessage) ([]byte, error) {
	var archive struct {
		Reference struct {
			RefID string `json:"ref_id"`
		} `json:"reference"`
	}
	if err := json.Unmarshal(record, &archive); err != nil {
		return nil, err
	}
	source, ok := o.sources[archive.Reference.RefID]
	if !ok {
		return nil, errors.New("unknown protected archive")
	}
	return source, nil
}

func archiveLimits() ingress.Limits { return ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64} }

func load(t *testing.T, v *admission.Validator) (*owner, fixture) {
	t.Helper()
	raw, err := os.ReadFile("testdata/materialization-archive.json")
	if err != nil {
		t.Fatal(err)
	}
	var f fixture
	if err = json.Unmarshal(raw, &f); err != nil {
		t.Fatal(err)
	}
	values := map[string]validation.Value{}
	for id, data := range map[string][]byte{"provisioning-plan-v1": f.Execution.Plan, "backend-manifest-v2": f.Execution.Manifest, "runtime-snapshot-v1": f.Execution.Actual, "realization-envelope-v1": f.Execution.Envelope} {
		if values[id], err = v.Validate(id, data, archiveLimits(), nil); err != nil {
			t.Fatalf("admit %s: %v", id, err)
		}
	}
	return &owner{
		snapshot: admission.MaterializationExecutionSnapshot{Plan: values["provisioning-plan-v1"], Manifest: values["backend-manifest-v2"], Actual: values["runtime-snapshot-v1"], Predecessor: f.Execution.Predecessor, Submission: []byte(f.Execution.Submission)},
		envelope: values["realization-envelope-v1"],
		original: f.Execution.Original.compilation(), current: f.Execution.Current.compilation(), retained: f.Retained.Phase.compilation(),
		sources: map[string][]byte{"inventory-1": []byte(f.Retained.SDL)},
	}, f
}

// archiveParts returns the reference record without its inventory, and that inventory.
func archiveParts(t *testing.T, record json.RawMessage) (map[string]any, json.RawMessage) {
	t.Helper()
	var parts map[string]json.RawMessage
	if err := json.Unmarshal(record, &parts); err != nil {
		t.Fatal(err)
	}
	inventory := parts["inventory"]
	var document map[string]any
	if err := json.Unmarshal(record, &document); err != nil {
		t.Fatal(err)
	}
	delete(document, "inventory")
	return document, inventory
}

// decode converts a JSON value into a generated transport type.
func decode(t *testing.T, v, target any) {
	t.Helper()
	data, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(data, target); err != nil {
		t.Fatal(err)
	}
}

func archiveRecord(t *testing.T, v any) binding.MaterializationArchiveRecordV1 {
	t.Helper()
	var record binding.MaterializationArchiveRecordV1
	decode(t, v, &record)
	return record
}

func archiveInventory(t *testing.T, v any) binding.BackendRuntimeDescendantsV1 {
	t.Helper()
	var inventory binding.BackendRuntimeDescendantsV1
	decode(t, v, &inventory)
	return inventory
}

func canonical(t *testing.T, data []byte) string {
	t.Helper()
	var v any
	if err := json.Unmarshal(data, &v); err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return string(encoded)
}

func TestMaterializationArchiveRoundTrip(t *testing.T) {
	v, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	o, f := load(t, v)
	document, report := archiveParts(t, f.Retained.Record)
	inventory := archiveInventory(t, report)
	admitted, err := admission.MaterializationArchive(v, archiveRecord(t, document), &inventory, archiveLimits(), o)
	if err != nil {
		t.Fatal(err)
	}
	if canonical(t, admitted.JSON()) != canonical(t, f.Retained.Record) {
		t.Error("the archive does not serialize the reference record")
	}
	artifact, ok := document["artifact"].(map[string]any)
	if !ok {
		t.Fatal("record artifact is not an object")
	}
	delete(artifact, "description")
	omitted, err := admission.MaterializationArchive(v, archiveRecord(t, document), &inventory, archiveLimits(), o)
	if err != nil || !bytes.Equal(omitted.JSON(), admitted.JSON()) {
		t.Errorf("an omitted default changed the archive: %v", err)
	}
	record, restored, value, err := admission.RestoreMaterializationArchive(v, admitted.JSON(), archiveLimits(), o)
	if err != nil {
		t.Fatal(err)
	}
	restoredRecord, err := json.Marshal(record)
	if err != nil {
		t.Fatal(err)
	}
	restoredInventory, err := json.Marshal(restored)
	if err != nil {
		t.Fatal(err)
	}
	if restored == nil || canonical(t, restoredInventory) != canonical(t, report) || canonical(t, restoredRecord) != canonical(t, f.Retained.Record) || !bytes.Equal(value.JSON(), admitted.JSON()) {
		t.Error("the restored archive differs from the admitted archive")
	}
}

func TestMaterializationArchiveRefusals(t *testing.T) {
	v, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	o, f := load(t, v)
	document, report := archiveParts(t, f.Retained.Record)
	record := archiveRecord(t, document)
	inventory := archiveInventory(t, report)
	stale := *o
	stale.sources = map[string][]byte{}
	var wrong map[string]any
	if err = json.Unmarshal(report, &wrong); err != nil {
		t.Fatal(err)
	}
	descendants, ok := wrong["descendants"].([]any)
	if !ok || len(descendants) == 0 {
		t.Fatal("the fixture inventory has no descendants")
	}
	first, ok := descendants[0].(map[string]any)
	if !ok {
		t.Fatal("descendant is not an object")
	}
	first["parent_address"] = "provision.node.other"
	wrongParent := archiveInventory(t, wrong)
	withInventory := archiveRecord(t, f.Retained.Record)
	for name, err := range map[string]error{
		"caller-supplied inventory": second(admission.MaterializationArchive(v, withInventory, &inventory, archiveLimits(), o)),
		"stale context":             second(admission.MaterializationArchive(v, record, &inventory, archiveLimits(), &stale)),
		"wrong parent binding":      second(admission.MaterializationArchive(v, record, &wrongParent, archiveLimits(), o)),
		"missing context":           second(admission.MaterializationArchive(v, record, &inventory, archiveLimits(), nil)),
	} {
		if err == nil {
			t.Errorf("%s was admitted", name)
		}
	}
	admitted, err := admission.MaterializationArchive(v, record, &inventory, archiveLimits(), o)
	if err != nil {
		t.Fatal(err)
	}
	corrupted := bytes.Replace(admitted.JSON(), []byte(`"provision.node.worker"`), []byte(`"provision.node.other"`), 1)
	if bytes.Equal(corrupted, admitted.JSON()) {
		t.Fatal("the fixture inventory changed")
	}
	for name, data := range map[string][]byte{"corrupted inventory": corrupted, "invalid input": admitted.JSON()[:16]} {
		if _, restored, value, err := admission.RestoreMaterializationArchive(v, data, archiveLimits(), o); err == nil || restored != nil || value.ContractID() != "" {
			t.Errorf("%s was restored", name)
		}
	}
	if _, _, _, err := admission.RestoreMaterializationArchive(v, admitted.JSON(), archiveLimits(), &stale); err == nil {
		t.Error("a stale context restored the archive")
	}
}

// The protected archive stays valid; only the execution authority is missing.
func TestMaterializationArchiveNeedsTheExecution(t *testing.T) {
	v, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	o, f := load(t, v)
	document, report := archiveParts(t, f.Retained.Record)
	record := archiveRecord(t, document)
	inventory := archiveInventory(t, report)
	admitted, err := admission.MaterializationArchive(v, record, &inventory, archiveLimits(), o)
	if err != nil {
		t.Fatal(err)
	}
	unexecuted := *o
	unexecuted.snapshot = admission.MaterializationExecutionSnapshot{}
	if _, err := admission.MaterializationArchive(v, record, &inventory, archiveLimits(), &unexecuted); err == nil {
		t.Error("the inventory was archived without its execution authority")
	}
	if _, _, _, err := admission.RestoreMaterializationArchive(v, admitted.JSON(), archiveLimits(), &unexecuted); err != nil {
		t.Errorf("the archive binding needed the execution authority: %v", err)
	}
}

func second[T any](_ T, err error) error { return err }

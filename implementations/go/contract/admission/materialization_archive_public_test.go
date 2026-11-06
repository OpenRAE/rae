package admission

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

// archivePublicContext authenticates the protected SDL bytes of each
// attestation for the trusted owner stand-in.
type archivePublicContext struct {
	*materializationInventoryTestContext

	sources map[string][]byte
}

func (c archivePublicContext) RetainedMaterializationSDL(record json.RawMessage) ([]byte, error) {
	v, err := materializationJSON(record)
	if err != nil {
		return nil, err
	}
	source, ok := c.sources[stringAt(v, "reference", "ref_id")]
	if !ok {
		return nil, errors.New("private-protected-archive-refusal")
	}
	return source, nil
}

// archivePublicFixture returns the first materialization's execution context,
// its inventory report and the reference archive record that retained them.
func archivePublicFixture(t *testing.T, e *Validator) (archivePublicContext, any, any) {
	t.Helper()
	raw, err := os.ReadFile("testdata/materialization-inventory.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []materializationInventoryFixture
	if err = json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	initial, retained := cases[0], cases[1].Retained[0]
	c := materializationInventoryTestFixture(t, e, initial)
	c.retained = cases[1].Retained
	full, err := materializationJSON(initial.Current.FullDocument)
	if err != nil {
		t.Fatal(err)
	}
	record, err := materializationJSON(retained.Record)
	if err != nil {
		t.Fatal(err)
	}
	return archivePublicContext{c, map[string][]byte{"inventory-1": []byte(retained.SDL)}}, at(full, "materialization_provenance", "inventory"), record
}

func archiveRecord(t *testing.T, v any) binding.MaterializationArchiveRecordV1 {
	t.Helper()
	var record binding.MaterializationArchiveRecordV1
	if err := json.Unmarshal(controlJSON(t, v), &record); err != nil {
		t.Fatal(err)
	}
	return record
}

func archiveInventory(t *testing.T, v any) binding.BackendRuntimeDescendantsV1 {
	t.Helper()
	var inventory binding.BackendRuntimeDescendantsV1
	if err := json.Unmarshal(controlJSON(t, v), &inventory); err != nil {
		t.Fatal(err)
	}
	return inventory
}

func withoutMember(t *testing.T, v any, path ...string) any {
	t.Helper()
	clone, err := materializationJSON(controlJSON(t, v))
	if err != nil {
		t.Fatal(err)
	}
	parent := clone
	for _, name := range path[:len(path)-1] {
		parent = at(parent, name)
	}
	delete(object(parent), path[len(path)-1])
	return clone
}

func TestMaterializationArchiveRoundTripsTheTypedInventory(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	c, report, reference := archivePublicFixture(t, e)
	inventory := archiveInventory(t, report)
	record := archiveRecord(t, withoutMember(t, reference, "inventory"))
	admitted, err := MaterializationArchive(e, record, &inventory, limits, c)
	if err != nil {
		t.Fatal(err)
	}
	if !equal(mustJSON(t, admitted.JSON()), reference) {
		t.Error("MaterializationArchive did not serialize the reference archive record")
	}
	omitted := archiveRecord(t, withoutMember(t, withoutMember(t, reference, "inventory"), "artifact", "description"))
	defaulted, err := MaterializationArchive(e, omitted, &inventory, limits, c)
	if err != nil || !bytes.Equal(defaulted.JSON(), admitted.JSON()) {
		t.Errorf("MaterializationArchive(omitted default) = %v, want the same serialized record", err)
	}
	restored, restoredInventory, value, err := RestoreMaterializationArchive(e, admitted.JSON(), limits, c)
	if err != nil {
		t.Fatal(err)
	}
	if restoredInventory == nil || !equal(mustJSON(t, controlJSON(t, restoredInventory)), report) || !equal(mustJSON(t, controlJSON(t, restored)), reference) || !bytes.Equal(value.JSON(), admitted.JSON()) {
		t.Error("RestoreMaterializationArchive changed the archived record or inventory")
	}
}

func TestMaterializationArchiveOmitsAnAbsentInventory(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	raw, archive := materializationArchiveTestFixture(t)
	reference, err := materializationJSON(raw)
	if err != nil {
		t.Fatal(err)
	}
	c := archivePublicContext{&materializationInventoryTestContext{materializationExecutionTestContext: &materializationExecutionTestContext{}}, map[string][]byte{"materialization-1": archive.source}}
	c.retained = []materializationRetainedFixture{{SDL: string(archive.source), Phase: materializationPhaseFixture{SourceSHA256: archive.compilation.SourceSHA256, Document: archive.compilation.Document, FullDocument: archive.compilation.FullDocument}}}
	admitted, err := MaterializationArchive(e, archiveRecord(t, reference), nil, limits, c)
	if err != nil {
		t.Fatal(err)
	}
	if inventory, present := object(mustJSON(t, admitted.JSON()))["inventory"]; !present || inventory != nil {
		t.Errorf("serialized inventory = %v, %t, want the published null default", inventory, present)
	}
	_, inventory, _, err := RestoreMaterializationArchive(e, admitted.JSON(), limits, c)
	if err != nil || inventory != nil {
		t.Errorf("RestoreMaterializationArchive() inventory = %v, %v, want none", inventory, err)
	}
}

func TestMaterializationArchiveRefusesUnboundInput(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	c, report, reference := archivePublicFixture(t, e)
	inventory := archiveInventory(t, report)
	record := archiveRecord(t, withoutMember(t, reference, "inventory"))
	stale := archivePublicContext{c.materializationInventoryTestContext, map[string][]byte{}}
	wrongParent := withoutMember(t, report, "unavailable_evidence")
	object(array(at(wrongParent, "descendants"))[0])["parent_address"] = "provision.node.other"
	object(wrongParent)["unavailable_evidence"] = []any{}
	foreign := archiveInventory(t, wrongParent)
	for name, archive := range map[string]func() error{
		"caller inventory": func() error {
			_, err := MaterializationArchive(e, archiveRecord(t, reference), &inventory, limits, c)
			return err
		},
		"missing context": func() error { _, err := MaterializationArchive(e, record, &inventory, limits, nil); return err },
		"stale context":   func() error { _, err := MaterializationArchive(e, record, &inventory, limits, stale); return err },
		"wrong parent":    func() error { _, err := MaterializationArchive(e, record, &foreign, limits, c); return err },
		"missing record": func() error {
			_, err := MaterializationArchive(e, archiveRecord(t, withoutMember(t, withoutMember(t, reference, "inventory"), "run_id")), &inventory, limits, c)
			return err
		},
	} {
		if err := archive(); err == nil {
			t.Errorf("MaterializationArchive(%s) = nil, want refusal", name)
		}
	}
	admitted, err := MaterializationArchive(e, record, &inventory, limits, c)
	if err != nil {
		t.Fatal(err)
	}
	corrupted := mustJSON(t, admitted.JSON())
	object(at(corrupted, "inventory"))["attempt_id"] = "attempt:corrupted"
	for name, data := range map[string][]byte{"corrupted inventory": controlJSON(t, corrupted), "truncated": admitted.JSON()[:32]} {
		if _, inventory, value, err := RestoreMaterializationArchive(e, data, limits, c); err == nil || inventory != nil || value.ContractID() != "" {
			t.Errorf("RestoreMaterializationArchive(%s) = %v, want refusal without data", name, err)
		}
	}
	if _, _, _, err := RestoreMaterializationArchive(e, admitted.JSON(), limits, stale); err == nil {
		t.Error("RestoreMaterializationArchive accepted a stale context")
	}
}

func mustJSON(t *testing.T, data []byte) any {
	t.Helper()
	v, err := materializationJSON(data)
	if err != nil {
		t.Fatal(err)
	}
	return v
}

// countingArchiveContext counts the trusted owner's reads of record bytes.
type countingArchiveContext struct {
	archivePublicContext

	reads *int
}

func (c countingArchiveContext) RetainedMaterializationSDL(record json.RawMessage) ([]byte, error) {
	*c.reads++
	return c.archivePublicContext.RetainedMaterializationSDL(record)
}

func TestMaterializationArchiveBoundsRecordsBeforeTheOwner(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	c, report, reference := archivePublicFixture(t, e)
	inventory := archiveInventory(t, report)
	admitted, err := MaterializationArchive(e, archiveRecord(t, withoutMember(t, reference, "inventory")), &inventory, limits, c)
	if err != nil {
		t.Fatal(err)
	}
	valid := admitted.JSON()
	for name, tc := range map[string]struct {
		data   []byte
		limits ingress.Limits
	}{
		"oversized":   {valid, ingress.Limits{MaxBytes: len(valid) - 1, MaxDepth: 64}},
		"too deep":    {valid, ingress.Limits{MaxBytes: len(valid), MaxDepth: 2}},
		"duplicate":   {append([]byte(`{"run_id":"run-1",`), valid[1:]...), limits},
		"malformed":   {valid[:len(valid)-1], limits},
		"wrong shape": {[]byte(`{"run_id":"run-1"}`), limits},
	} {
		reads := 0
		if _, _, _, err := RestoreMaterializationArchive(e, tc.data, tc.limits, countingArchiveContext{c, &reads}); err == nil || reads != 0 {
			t.Errorf("RestoreMaterializationArchive(%s) = %v after %d owner reads, want refusal before the owner", name, err, reads)
		}
	}
	reads := 0
	if _, _, _, err := RestoreMaterializationArchive(e, valid, limits, countingArchiveContext{c, &reads}); err != nil || reads != 1 {
		t.Errorf("RestoreMaterializationArchive(valid) = %v after %d owner reads, want one read", err, reads)
	}
}

// The protected archive and the inventory stay valid; only the execution
// authority belongs to another materialization. The archive alone still admits.
func TestMaterializationArchiveAdmitsTheInventoryUnderItsExecution(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	c, report, reference := archivePublicFixture(t, e)
	inventory := archiveInventory(t, report)
	record := archiveRecord(t, withoutMember(t, reference, "inventory"))
	admitted, err := MaterializationArchive(e, record, &inventory, limits, c)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile("testdata/materialization-inventory.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []materializationInventoryFixture
	if err = json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	foreign := materializationInventoryTestFixture(t, e, cases[1])
	foreign.retained = c.retained
	other := archivePublicContext{foreign, c.sources}
	if _, err := MaterializationArchive(e, record, &inventory, limits, other); err == nil {
		t.Error("MaterializationArchive admitted an inventory under another execution")
	}
	if _, _, _, err := RestoreMaterializationArchive(e, admitted.JSON(), limits, other); err != nil {
		t.Errorf("RestoreMaterializationArchive() = %v; the archive binding does not need the execution", err)
	}
}

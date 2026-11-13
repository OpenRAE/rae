package planning

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestPreparedNodeCompletionRequiresValidNativeFactsAndIndependentEnvelope(t *testing.T) {
	raw, err := os.ReadFile("../../../../contracts/fixtures/backend-manifest/backend-manifest-v2/valid/stub.json")
	if err != nil {
		t.Fatal(err)
	}
	var manifest binding.BackendManifestV2
	if err := json.Unmarshal(raw, &manifest); err != nil {
		t.Fatal(err)
	}
	for _, operations := range [][]planOperation{
		nil,
		{{Address: "provision.node.host", Action: "create", Kind: "node", Payload: json.RawMessage(`{"os_family":"unknown"}`)}},
		{{Address: "provision.node.host", Action: "create", Kind: "node", Payload: json.RawMessage(`{}`)}},
	} {
		selection := preparedSelection{original: &executionPlan{manifest: manifest}, operations: operations}
		violation, err := selection.portableNodeViolation()
		if err != nil || violation != termBackendPreparationSelectedAnInadmissiblePortableNodeCompletion {
			t.Fatalf("unbound prepared node completion: %q %v", violation, err)
		}
	}
}

func TestPreparedInventoryRefusesCorruptPredecessorsAndPayloads(t *testing.T) {
	selection := preparedSelection{original: &executionPlan{}}
	if err := selection.original.context.Snapshot.Entries.UnmarshalJSON([]byte(`{"provision.node.host":true}`)); err != nil {
		t.Fatal(err)
	}
	if _, _, err := selection.selectedInventory(); err == nil {
		t.Fatal("corrupt predecessor became a selected native inventory")
	}
	selection.original.context.Snapshot = binding.RuntimeSnapshotV1{}
	selection.operations = []planOperation{{Address: "provision.node.host", Payload: json.RawMessage(`{`)}}
	if _, _, err := selection.selectedInventory(); err == nil {
		t.Fatal("non-JSON prepared payload became a native inventory")
	}
	if _, err := selection.portableNodeViolation(); err == nil {
		t.Fatal("invalid selected inventory reached node completion")
	}
}

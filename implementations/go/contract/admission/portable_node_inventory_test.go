package admission

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func portableInventoryFixture(t *testing.T) (binding.RuntimeSnapshotV1, binding.BackendManifestV2, binding.RealizationEnvelopeV1, MaterializationCompilation) {
	t.Helper()
	raw, err := os.ReadFile("testdata/materialization-inventory.json")
	requireNoError(t, err)
	var cases []materializationInventoryFixture
	if json.Unmarshal(raw, &cases) != nil || len(cases) == 0 {
		t.Fatal("inventory fixture")
	}
	var inventory binding.RuntimeSnapshotV1
	var manifest binding.BackendManifestV2
	var envelope binding.RealizationEnvelopeV1
	if json.Unmarshal(cases[0].Actual, &inventory) != nil || json.Unmarshal(cases[0].Manifest, &manifest) != nil || json.Unmarshal(cases[0].Envelope, &envelope) != nil {
		t.Fatal("portable fixture")
	}
	entries := map[string]json.RawMessage{}
	compilation := cases[0].Current.compilation()
	var supplied map[string]any
	if json.Unmarshal(compilation.Document, &supplied) != nil {
		t.Fatal("native source fixture")
	}
	for _, raw := range cases[0].Current.Resources {
		var identity struct {
			Address string `json:"address"`
		}
		if json.Unmarshal(raw, &identity) != nil {
			t.Fatal("resource identity")
		}
		entries[identity.Address] = raw
		var entry map[string]any
		if json.Unmarshal(raw, &entry) != nil {
			t.Fatal("native entry fixture")
		}
		if stringAt(entry, "resource_type") == "node" || stringAt(entry, "resource_type") == "network" {
			object(supplied["nodes"])[stringAt(entry, "payload", "name")] = at(entry, "payload", "spec", "node")
		}
	}
	if inventory.Entries.UnmarshalJSON(projectionTestJSON(t, entries)) != nil {
		t.Fatal("inventory entries")
	}
	compilation.Document = projectionTestJSON(t, supplied)
	return inventory, manifest, envelope, compilation
}

func TestPortableNodeOfferUsesSuppliedValuesWithoutConstructorSubstitution(t *testing.T) {
	owner, err := New()
	requireNoError(t, err)
	inventory, manifest, _, compilation := portableInventoryFixture(t)
	envelope := preparedEnvelopeFixture(t, "exact")
	var offer map[string]any
	if json.Unmarshal(projectionTestJSON(t, envelope), &offer) != nil {
		t.Fatal("offer fixture")
	}
	bindings := array(at(offer, "expression", "bindings"))
	object(bindings[0])["path"] = "nodes.worker.description"
	object(at(offer, "expression", "domains", "engine"))["value"] = ""
	delete(offer, "digest")
	canonical, err := sortedJSON(offer)
	requireNoError(t, err)
	offer["digest"] = digest.SHA256([]byte(canonical))
	if json.Unmarshal(projectionTestJSON(t, offer), &envelope) != nil {
		t.Fatal("offer projection")
	}
	var target map[string]any
	if json.Unmarshal(projectionTestJSON(t, manifest), &target) != nil {
		t.Fatal("target fixture")
	}
	target["realization_envelope"] = map[string]any{"envelope_id": offer["id"], "digest": offer["digest"], "configuration_digest": at(offer, "configuration", "configuration_digest")}
	if json.Unmarshal(projectionTestJSON(t, target), &manifest) != nil {
		t.Fatal("target projection")
	}
	entries, _ := inventory.Entries.Value()
	var worker, document map[string]any
	if json.Unmarshal(entries["provision.node.worker"], &worker) != nil || json.Unmarshal(compilation.Document, &document) != nil {
		t.Fatal("candidate fixture")
	}
	delete(object(at(worker, "payload", "spec", "node")), "description")
	delete(object(at(document, "nodes", "worker")), "description")
	entries["provision.node.worker"] = projectionTestJSON(t, worker)
	compilation.Document = projectionTestJSON(t, document)
	admitted, err := CheckPortableNodeInventory(owner, inventory, manifest, envelope, []string{"provision.node.host"}, compilation)
	if err != nil || admitted {
		t.Fatalf("missing supplied description replaced by constructor default: admitted=%v err=%v", admitted, err)
	}
}
func TestPortableNodeInventoryReusesCanonicalIdentityAndReferences(t *testing.T) {
	owner, err := New()
	requireNoError(t, err)
	inventory, manifest, envelope, compilation := portableInventoryFixture(t)
	admitted, err := CheckPortableNodeInventory(owner, inventory, manifest, envelope, []string{"provision.node.host"}, compilation)
	if err != nil || !admitted {
		t.Fatalf("native inventory refused: %v", err)
	}
	entries, _ := inventory.Entries.Value()
	var worker map[string]any
	if json.Unmarshal(entries["provision.node.worker"], &worker) != nil {
		t.Fatal("worker fixture")
	}
	object(worker["payload"])["node_name"] = "other"
	entries["provision.node.worker"] = projectionTestJSON(t, worker)
	admitted, err = CheckPortableNodeInventory(owner, inventory, manifest, envelope, []string{"provision.node.host"}, compilation)
	if err != nil || admitted {
		t.Fatalf("changed canonical identity admitted=%v err=%v", admitted, err)
	}
}
func TestPortableNodeInventoryRequiresTheBoundRawCandidate(t *testing.T) {
	owner, err := New()
	requireNoError(t, err)
	inventory, manifest, envelope, compilation := portableInventoryFixture(t)
	var context map[string]any
	if json.Unmarshal(compilation.Document, &context) != nil {
		t.Fatal("node context")
	}
	object(object(context["nodes"])["worker"])["description"] = "changed"
	compilation.Document = projectionTestJSON(t, context)
	admitted, err := CheckPortableNodeInventory(owner, inventory, manifest, envelope, []string{"provision.node.host"}, compilation)
	if err == nil && admitted {
		t.Fatal("candidate differs from the bytes independently given to the native owner")
	}
}

func TestPortableNodeInventoryBindsTheConfiguredEnvelope(t *testing.T) {
	owner, err := New()
	requireNoError(t, err)
	inventory, manifest, envelope, compilation := portableInventoryFixture(t)
	var target map[string]any
	if json.Unmarshal(projectionTestJSON(t, manifest), &target) != nil {
		t.Fatal("target fixture")
	}
	object(target["realization_envelope"])["digest"] = "sha256:" + strings.Repeat("f", 64)
	if json.Unmarshal(projectionTestJSON(t, target), &manifest) != nil {
		t.Fatal("target identity")
	}
	admitted, err := CheckPortableNodeInventory(owner, inventory, manifest, envelope, []string{"provision.node.host"}, compilation)
	if err == nil && admitted {
		t.Fatal("foreign configured envelope established portable support")
	}
}

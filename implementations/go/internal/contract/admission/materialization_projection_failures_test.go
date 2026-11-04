package admission

import (
	"encoding/json"
	"testing"
)

func TestMaterializationCapabilitiesRefuseBrokenOwnerProjections(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	fixture := materializationInventoryCases(t)[1]
	baseline := materializationInventoryState(t, e, fixture)
	if err := baseline.capabilities(); err != nil {
		t.Fatal("independent capability baseline:", err)
	}
	for name, mutate := range map[string]func(*materializationInventory){
		"missing-provisioner": func(r *materializationInventory) {
			delete(object(at(r.execution.manifest, "capabilities")), "provisioner")
		},
		"total-capacity": func(r *materializationInventory) {
			object(at(r.execution.manifest, "capabilities", "provisioner"))["max_total_nodes"] = jsonOne
		},
		"cyclic-dependency": func(r *materializationInventory) {
			object(r.entries["provision.node.worker"])["ordering_dependencies"] = []any{"provision.node.leaf"}
			object(r.entries["provision.node.leaf"])["ordering_dependencies"] = []any{"provision.node.worker"}
		},
		"duplicate-name": func(r *materializationInventory) {
			object(at(r.entries["provision.node.worker"], "payload"))["name"] = at(r.entries["provision.node.host"], "payload", "name")
		},
		"acl-capability": func(r *materializationInventory) {
			object(at(r.execution.manifest, "capabilities", "provisioner"))["supports_acls"] = false
			object(at(r.entries["provision.node.worker"], "payload", "spec", "infrastructure"))["acls"] = []any{map[string]any{"name": "guard"}}
		},
		"operating-system": func(r *materializationInventory) {
			object(at(r.entries["provision.node.worker"], "payload"))["os_family"] = "foreign"
		},
		"architecture": func(r *materializationInventory) {
			object(at(r.entries["provision.node.worker"], "payload"))["architecture"] = "foreign"
		},
		"missing-dependency": func(r *materializationInventory) {
			object(r.entries["provision.node.worker"])["ordering_dependencies"] = []any{"provision.node.absent"}
		},
		"prepared-requirement": func(r *materializationInventory) {
			r.execution.current.prepared["provision.node.worker"] = []json.RawMessage{json.RawMessage(`[]`)}
		},
		"requirement-address": func(r *materializationInventory) {
			r.execution.current.prepared["provision.node.worker"] = []json.RawMessage{json.RawMessage(`{"address":"foreign"}`)}
		},
	} {
		t.Run(name, func(t *testing.T) {
			r := materializationInventoryState(t, e, fixture)
			mutate(r)
			if err := r.capabilities(); err == nil {
				t.Fatal("broken capability owner projection admitted")
			}
		})
	}
}

func TestMaterializationNodeIdentityRejectsSubstitutedCompiledMetadata(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	fixture := materializationInventoryCases(t)[1]
	for name, mutate := range map[string]func(any, any){
		"extra-spec":     func(entry, _ any) { object(at(entry, "payload", "spec"))["hidden"] = true },
		"node-name":      func(entry, _ any) { object(at(entry, "payload"))["node_name"] = "foreign" },
		"address":        func(entry, _ any) { object(entry)["address"] = "provision.node.foreign" },
		"protected-role": func(_, node any) { object(node)["roles"] = map[string]any{"operator": "foreign"} },
		"topology":       func(entry, _ any) { object(at(entry, "payload"))["domain_topology"] = map[string]any{} },
		"count-binding":  func(entry, _ any) { object(at(entry, "payload"))["count"] = json.Number("2") },
		"negative-count": func(entry, _ any) {
			object(at(entry, "payload"))["count"] = json.Number("-1")
			object(at(entry, "payload", "spec", "infrastructure"))["count"] = json.Number("-1")
		},
		"fractional-count": func(entry, _ any) {
			object(at(entry, "payload"))["count"] = json.Number("1.5")
			object(at(entry, "payload", "spec", "infrastructure"))["count"] = json.Number("1.5")
		},
		"os-identity":    func(entry, _ any) { object(at(entry, "payload"))["os_version"] = "foreign" },
		"hidden-payload": func(entry, _ any) { object(at(entry, "payload"))["hidden"] = true },
	} {
		t.Run(name, func(t *testing.T) {
			r := materializationInventoryState(t, e, fixture)
			entry := r.entries["provision.node.worker"]
			node, err := r.execution.normalizedNode(stringAt(entry, "payload", "name"), at(entry, "payload", "spec", "node"), nil)
			if err != nil {
				t.Fatal(err)
			}
			if err = materializationNodeIdentity(entry, node); err != nil {
				t.Fatal("independent node identity:", err)
			}
			mutate(entry, node)
			if err = materializationNodeIdentity(entry, node); err == nil {
				t.Fatal("substituted compiler node metadata admitted")
			}
		})
	}
}

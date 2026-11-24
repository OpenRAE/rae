package admission

import (
	"encoding/json"
	"os"
	"testing"
)

func materializationInventoryCases(t *testing.T) []materializationInventoryFixture {
	t.Helper()
	raw, err := os.ReadFile("testdata/materialization-inventory.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []materializationInventoryFixture
	if err = json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	return cases
}
func materializationInventoryState(t *testing.T, e *Validator, g materializationInventoryFixture) *materializationInventory {
	t.Helper()
	c := materializationInventoryTestFixture(t, e, g)
	r := &materializationInventory{context: c, execution: materializationExecution{owner: e, context: c, snapshot: c.snapshot}}
	if err := r.execution.load(); err != nil {
		t.Fatal(err)
	}
	if err := r.execution.compile(c.snapshot.Submission); err != nil {
		t.Fatal(err)
	}
	r.report = at(r.execution.current.full, "materialization_provenance", "inventory")
	r.originals = materializationScope(r.execution.original.resources, "provisioning")
	if err := r.predecessor(); err != nil {
		t.Fatal(err)
	}
	if err := r.project(); err != nil {
		t.Fatal(err)
	}
	return r
}
func TestMaterializationInventoryRefusesIndependentAuthorityAndLineageDefects(t *testing.T) {
	e := boundTestOwner(t)
	cases := materializationInventoryCases(t)
	for _, test := range []struct {
		name  string
		apply func(*materializationInventory) error
	}{
		{"attempt", func(r *materializationInventory) error {
			object(r.report)["attempt_id"] = "foreign"
			return r.boundReport()
		}},
		{"target", func(r *materializationInventory) error {
			object(r.report)["target_scope"] = "target:foreign"
			return r.boundReport()
		}},
		{"run", func(r *materializationInventory) error {
			object(r.report)["run_id"] = "foreign"
			return r.boundReport()
		}},
		{"replay", func(r *materializationInventory) error {
			object(r.report)["sequence"] = at(r.preceding, "sequence")
			return r.lineage()
		}},
		{"incomplete", func(r *materializationInventory) error { object(r.report)["complete"] = false; return r.lineage() }},
		{"unavailable", func(r *materializationInventory) error {
			object(r.report)["unavailable_evidence"] = []any{"sha256:missing"}
			return r.lineage()
		}},
		{"omission", func(r *materializationInventory) error { object(r.report)["descendants"] = []any{}; return r.lineage() }},
		{"replacement", func(r *materializationInventory) error {
			object(array(at(r.report, "descendants"))[0])["native_identity_digest"] = "sha256:replacement"
			return r.lineage()
		}},
		{"creation", func(r *materializationInventory) error {
			object(at(array(at(r.report, "descendants"))[0], "creation"))["operation_id"] = "foreign"
			return r.lineage()
		}},
		{"source", func(r *materializationInventory) error {
			object(array(at(r.report, "descendants"))[0])["source_address"] = "provision.node.missing"
			return r.lineage()
		}},
		{"cycle", func(r *materializationInventory) error {
			row := array(at(r.report, "descendants"))[0]
			object(row)["parent_address"] = at(row, "address")
			return r.ancestry(row, controlRows(at(r.report, "descendants"), "address"))
		}},
		{"parent-instance", func(r *materializationInventory) error {
			rows := controlRows(at(r.report, "descendants"), "address")
			object(rows["provision.node.leaf"])["parent_instance_index"] = jsonOne
			return r.ancestry(rows["provision.node.leaf"], rows)
		}},
		{"root-instance", func(r *materializationInventory) error {
			rows := controlRows(at(r.report, "descendants"), "address")
			object(rows["provision.node.worker"])["parent_instance_index"] = jsonOne
			return r.ancestry(rows["provision.node.worker"], rows)
		}},
		{"description-coverage", func(r *materializationInventory) error {
			delete(r.execution.current.resources, "provision.node.worker")
			return r.project()
		}},
		{"closed-membership", func(r *materializationInventory) error {
			object(at(r.execution.original.collection, "constraint_document", "root", "fields", "", "closure"))["posture"] = "closed"
			return r.membership()
		}},
		{"unsupported-type", func(r *materializationInventory) error {
			object(at(r.execution.manifest, "capabilities", "provisioner"))["supported_node_types"] = []any{}
			return r.capabilities()
		}},
		{"closed-augmentation", func(r *materializationInventory) error {
			policy := map[string]any{"default": "closed", "scopes": []any{}}
			object(r.execution.original.full)["augmentation_scope"] = policy
			object(r.execution.current.full)["augmentation_scope"] = policy
			return r.augmentation()
		}},
		{"policy-substitution", func(r *materializationInventory) error {
			object(r.execution.current.full)["augmentation_scope"] = map[string]any{"default": "open"}
			return r.augmentation()
		}},
		{"unknown-backend-choice", func(r *materializationInventory) error {
			object(r.report)["backend_selections"] = []any{map[string]any{"address": "provision.node.leaf", "field_path": "nodes.leaf.missing", "requirement_kind": "missing"}}
			return r.selections()
		}},
		{"unreadable-predecessor", func(r *materializationInventory) error {
			c, ok := r.context.(*materializationInventoryTestContext)
			if !ok {
				panic("unexpected test context")
			}
			c.retained = nil
			return r.predecessor()
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			r := materializationInventoryState(t, e, cases[1])
			if err := test.apply(r); err == nil {
				t.Fatal("accepted independent inventory defect")
			}
		})
	}
}
func TestMaterializationLifecycleCannotResurrectOrRewriteReceipt(t *testing.T) {
	e := boundTestOwner(t)
	cases := materializationInventoryCases(t)
	r := materializationInventoryState(t, e, cases[3])
	rows := controlRows(at(r.report, "descendants"), "address")
	old := controlRows(at(r.preceding, "descendants"), "address")
	leaf := rows["provision.node.leaf"]
	if err := materializationRetainedIdentity(old["provision.node.leaf"], leaf); err != nil {
		t.Fatal(err)
	}
	object(leaf)["state"] = "active"
	if err := materializationRetainedIdentity(old["provision.node.leaf"], leaf); err == nil {
		t.Fatal("resurrected terminated descendant")
	}
	r = materializationInventoryState(t, e, cases[2])
	leaf = controlRows(at(r.report, "descendants"), "address")["provision.node.leaf"]
	object(at(leaf, "lifecycle"))["attempt_id"] = "foreign-attempt"
	if err := r.lineage(); err == nil {
		t.Fatal("accepted foreign lifecycle receipt")
	}
}
func TestMaterializationExecutionRefusesChangedScopeOriginsAndReplicaGaps(t *testing.T) {
	e := boundTestOwner(t)
	g := materializationInventoryCases(t)[0]
	for _, name := range []string{"plan", "predecessor", "producer", "missing-origin", "invented-origin", "omitted-resource", "extra-resource", "replica-count", "binding-source"} {
		t.Run(name, func(t *testing.T) {
			r := materializationInventoryState(t, e, g)
			p := object(at(r.execution.current.full, "materialization_provenance"))
			switch name {
			case "plan":
				p["plan_digest"] = "sha256:foreign"
			case "predecessor":
				p["predecessor_digest"] = "sha256:foreign"
			case "producer":
				object(p["producer"])["name"] = "foreign"
			case "missing-origin":
				p["origins"] = []any{}
			case "invented-origin":
				p["origins"] = append(array(p["origins"]), map[string]any{"change": "selected", "field_pointer": "/name", "source_pointer": "/name", "origin": "backend-realized"})
			case "omitted-resource":
				delete(r.execution.current.resources, "provision.node.host")
			case "extra-resource":
				r.execution.current.resources["provision.node.extra"] = r.execution.current.resources["provision.node.host"]
			case "replica-count":
				object(at(r.execution.current.resources["provision.node.host"], "payload"))["count"] = json.Number("1000000")
			case "binding-source":
				object(array(p["resource_bindings"])[0])["source_node"] = "foreign"
			}
			projected := object(r.execution.actual)
			projected["entries"] = r.entries
			if err := r.execution.check(); err == nil {
				t.Fatal("accepted changed materialization execution")
			}
		})
	}
}

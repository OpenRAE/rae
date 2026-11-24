package admission

import "testing"

func TestMaterializationAugmentationKeepsClosedDescendantScopes(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	fixture := materializationInventoryCases(t)[1]
	for _, name := range []string{"open", "closed-descendant", "removed-subtree", "invalid-difference", "invalid-rule", "subtree-budget", "address-budget", "matching-policy", "changed-policy"} {
		t.Run(name, func(t *testing.T) {
			r := materializationInventoryState(t, e, fixture)
			policy := map[string]any{"default": "open", "scopes": []any{map[string]any{"scope": "/nodes/host", "permission": "open"}}}
			object(r.execution.original.full)["augmentation_scope"] = policy
			object(r.execution.current.full)["augmentation_scope"] = policy
			difference := map[string]any{"change": "added", "field_pointer": "/nodes"}
			rules := []materializationScopeRule{{path: "/nodes/host", permission: "open"}}
			remaining := 100000
			valid := name == "open" || name == "removed-subtree" || name == "matching-policy"
			switch name {
			case "closed-descendant":
				rules[0].permission = "closed"
			case "removed-subtree":
				difference["change"] = "removed"
			case "invalid-difference":
				difference["field_pointer"] = "/absent"
			case "invalid-rule":
				rules[0].path = "/nodes/absent"
			case "subtree-budget":
				remaining = 2
			case "address-budget":
				remaining = 0
			case "matching-policy":
				assertAugmentationResult(t, r, true)
				return
			case "changed-policy":
				object(r.execution.current.full)["augmentation_scope"] = map[string]any{"default": "closed"}
				assertAugmentationResult(t, r, false)
				return
			}
			err := r.augmentationDifference(difference, policy, rules, &remaining)
			if (err == nil) != valid {
				t.Fatalf("augmentation boundary valid=%v: %v", valid, err)
			}
		})
	}
}

func TestOrdinaryMaterializationSelectionsRequireTheirDeclaredAuthority(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	fixture := materializationInventoryCases(t)[1]
	for _, mode := range []string{"open", "constrained", "exact", "foreign"} {
		t.Run(mode, func(t *testing.T) {
			r := materializationInventoryState(t, e, fixture)
			r.execution.original.ordinary = map[string]string{"/nodes/host/count": "nodes.host.count"}
			object(r.execution.plan)["realization_authority"] = []any{map[string]any{"field_path": "nodes.host.count", "mode": mode}}
			difference := map[string]any{"change": "selected", "field_pointer": "/nodes/host/count"}
			expected := mode == "open" || mode == "constrained"
			if r.ordinarySelection(difference) != expected {
				t.Fatal("ordinary selection lost its declared authority")
			}
			if expected {
				remaining := 0
				if err := r.augmentationDifference(difference, map[string]any{"default": "closed"}, nil, &remaining); err != nil {
					t.Fatal("ordinary admitted selection was treated as augmentation", err)
				}
			}
			difference["field_pointer"] = "/nodes/host/unknown"
			if r.ordinarySelection(difference) {
				t.Fatal("undeclared ordinary field was admitted")
			}
		})
	}
}

func assertAugmentationResult(t *testing.T, r *materializationInventory, valid bool) {
	t.Helper()
	err := r.augmentation()
	if (err == nil) != valid {
		t.Fatalf("augmentation admission=%v: %v", valid, err)
	}
}

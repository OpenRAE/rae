package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestRequiredSemanticRulesRefuseMissingOwners(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	checked := map[string]bool{}
	for _, key := range e.low.Keys() {
		rule, known := e.checker(key.InvariantID)
		if !known {
			t.Fatal("missing published rule:", key)
		}
		if !rule.requiresContext || checked[key.InvariantID] {
			continue
		}
		checked[key.InvariantID] = true
		t.Run(key.InvariantID, func(t *testing.T) {
			root := map[string]any{}
			err := rule.check(validation.Invocation{Key: key, Instance: root, Root: root})
			if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
				t.Fatalf("required owner absence did not refuse: %v", err)
			}
		})
	}
	if len(checked) < 20 {
		t.Fatal("required owner coverage inventory shrank")
	}
}

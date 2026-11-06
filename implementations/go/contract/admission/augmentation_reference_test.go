package admission

import (
	"encoding/json"
	"fmt"
	"testing"
)

func TestAugmentationNamespacePermissionsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Policy    json.RawMessage `json:"policy"`
			Scope     string          `json:"scope"`
			Namespace []string        `json:"namespace"`
			Admitted  bool            `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/augmentation-verdicts.json", &reference)
	if len(reference.Cases) != 924 {
		t.Fatal("independent augmentation policy inventory changed")
	}
	for index, c := range reference.Cases {
		t.Run(fmt.Sprintf("%03d", index), func(t *testing.T) {
			policy := decodeRuleObject(t, string(c.Policy))
			rules := []materializationScopeRule{}
			for _, rule := range array(at(policy, "scopes")) {
				rules = append(rules, materializationScopeRule{path: stringAt(rule, "scope"), permission: stringAt(rule, "permission"), namespace: stringsOf(at(rule, "namespace"))})
			}
			if admitted := materializationScopeOpen(policy, rules, c.Scope, c.Namespace); admitted != c.Admitted {
				t.Fatalf("augmentation permission=%v, Python=%v", admitted, c.Admitted)
			}
		})
	}
}

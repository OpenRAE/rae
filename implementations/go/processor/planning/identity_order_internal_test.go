package planning

import (
	"encoding/json"
	"errors"
	"math"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// The document, value and expected order come from the reference
// realization_preparation._identity_order over the same admitted document.
const (
	identityOrderDocument = `{"semantic_profile": "raes/test-identity-order/v1", "root": {"kind": "definition-reference", "target": "net"}, "definitions": {"net": {"kind": "all-of", "constraints": [{"kind": "recursive-record", "fields": {"routes": {"kind": "keyed-collection", "collection_kind": "routes", "identity_fields": ["address"], "members": [{"identity": ["b"], "constraint": {"kind": "recursive-record", "fields": {"hops": {"kind": "sequence", "items": [{"kind": "keyed-collection", "collection_kind": "hops", "identity_fields": ["id"], "members": []}]}}}}]}, "mixed": {"kind": "keyed-collection", "collection_kind": "mixed", "identity_fields": ["id"], "members": []}, "missing": {"kind": "definition-reference", "target": "absent"}, "loop": {"kind": "definition-reference", "target": "loop"}}}, {"kind": "recursive-record", "fields": {"tags": {"kind": "keyed-collection", "collection_kind": "tags", "identity_fields": ["name", "scope"], "members": []}}}]}, "loop": {"kind": "definition-reference", "target": "loop"}}}`
	identityOrderValue    = `{"routes": [{"address": "c"}, {"address": "a"}, {"address": "b", "hops": [[{"id": 2}, {"id": 1}], [{"id": 9}, {"id": 3}]]}], "mixed": [{"id": 2}, "scalar", {"id": 1}], "missing": [3, 1], "other": [{"id": 2}, {"id": 1}], "tags": [{"name": "z", "scope": 1}, {"name": "a"}, {"name": "a", "scope": null}], "loop": [{"id": 2}, {"id": 1}]}`
	identityOrderExpected = `{"loop": [{"id": 2}, {"id": 1}], "missing": [3, 1], "mixed": [{"id": 2}, "scalar", {"id": 1}], "other": [{"id": 2}, {"id": 1}], "routes": [{"address": "a"}, {"address": "b", "hops": [[{"id": 2}, {"id": 1}], [{"id": 9}, {"id": 3}]]}, {"address": "c"}], "tags": [{"name": "z", "scope": 1}, {"name": "a"}, {"name": "a", "scope": null}]}`
)

func TestIdentityOrderMatchesReferenceStructures(t *testing.T) {
	var document map[string]any
	var value, want any
	for raw, target := range map[string]any{identityOrderDocument: &document, identityOrderValue: &value, identityOrderExpected: &want} {
		if err := json.Unmarshal([]byte(raw), target); err != nil {
			t.Fatal(err)
		}
	}
	definitions, _ := document["definitions"].(map[string]any)
	root, _ := document["root"].(map[string]any)
	got, err := identityOrdering{definitions: definitions}.order(value, root, 0)
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Fatalf("identity order (-reference +got):\n%s", diff)
	}
}

func TestIdentityOrderRefusesValuesWithoutCanonicalJSON(t *testing.T) {
	keyed := map[string]any{"kind": "keyed-collection", "identity_fields": []any{"id"}}
	for name, test := range map[string]struct {
		value     any
		structure map[string]any
	}{
		"member identity": {[]any{}, map[string]any{"kind": "keyed-collection", "members": []any{map[string]any{"identity": []any{math.NaN()}}}}},
		"item identity":   {[]any{map[string]any{"id": math.Inf(1)}}, keyed},
		"record field":    {map[string]any{"routes": []any{map[string]any{"id": math.NaN()}}}, map[string]any{"kind": "recursive-record", "fields": map[string]any{"routes": keyed}}},
		"sequence item":   {[]any{[]any{map[string]any{"id": math.NaN()}}}, map[string]any{"kind": "sequence", "items": []any{keyed}}},
		"all-of member":   {[]any{map[string]any{"id": math.NaN()}}, map[string]any{"kind": "all-of", "constraints": []any{keyed}}},
		"member constraint": {
			[]any{map[string]any{"id": "a", "routes": []any{map[string]any{"id": math.NaN()}}}},
			map[string]any{"kind": "keyed-collection", "identity_fields": []any{"id"}, "members": []any{map[string]any{"identity": []any{"a"}, "constraint": map[string]any{"kind": "recursive-record", "fields": map[string]any{"routes": keyed}}}}},
		},
	} {
		_, err := identityOrdering{}.order(test.value, test.structure, 0)
		if _, ok := errors.AsType[*fault.Error](err); !ok {
			t.Errorf("%s: order error = %v; want a plan refusal", name, err)
		}
	}
}

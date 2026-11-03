package admission

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestAdmissionExactNumberBoundary(t *testing.T) {
	left := decodeRuleObject(t, `{"nested":[32.0,{"value":0.0}]}`)
	right := decodeRuleObject(t, `{"nested":[32,{"value":0}]}`)
	if !equal(left, right) {
		t.Error("integral number spellings differ")
	}
	if !equal([]any{"a"}, []string{"a"}) || !equal([]string{"a"}, []any{"a"}) {
		t.Error("JSON array representation changed equality")
	}
	if equal(json.Number("1"), true) || equal(true, json.Number("1")) {
		t.Error("boolean acquired integer semantics")
	}
	for _, literal := range []string{"1e999999999", "1e-999999999", "1/2", "NaN", strings.Repeat("9", 4301)} {
		if _, ok := number(json.Number(literal)); ok {
			t.Errorf("accepted malformed or unbounded number %q", literal[:min(len(literal), 20)])
		}
	}
}

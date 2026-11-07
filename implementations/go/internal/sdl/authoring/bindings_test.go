package authoring

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestBindingScalarSpellings(t *testing.T) {
	cases := []struct {
		value any
		want  string
	}{
		{json.Number("1.2"), "1.2"}, {float64(2), "2.0"},
		{1e20, "1e+20"}, {1e-5, "1e-05"}, {1e-4, "0.0001"},
		{json.Number("999999999999999999999999999999"), "999999999999999999999999999999"},
		{true, "True"}, {false, "False"}, {nil, "None"},
	}
	for _, c := range cases {
		if got := pythonScalar(c.value); got != c.want {
			t.Errorf("%v: %q, want %q", c.value, got, c.want)
		}
	}
	if !scalarEqual(json.Number("2"), float64(2)) || scalarEqual(json.Number("9007199254740993"), float64(9007199254740992)) || !scalarEqual(json.Number("0.1"), float64(0.1)) || scalarEqual(json.Number("9007199254740993"), json.Number("9007199254740993.0")) {
		t.Fatal("numeric equality narrowed an integer or lost a float match")
	}
}
func TestBindingPrivateReferenceGuard(t *testing.T) {
	baseline := map[string]any{"agents": map[string]any{"a": map[string]any{"affiliations": []any{"m.__private.team"}}}}
	if err := authoredReferences(baseline, baseline); err != nil {
		t.Fatal(err)
	}
	altered := map[string]any{"agents": map[string]any{"a": map[string]any{"affiliations": []any{"m.__private.other"}}}}
	if authoredReferences(altered, baseline) == nil {
		t.Fatal("binding introduced a private reference")
	}
}
func TestModelJSONPreservesHTMLBytes(t *testing.T) {
	value := strings.Repeat("<&>", 1000)
	raw, err := encode(ordered{{name: "description", value: value}}, int64(len(value)+18), false)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(raw), `\u003`) || !strings.Contains(string(raw), value) {
		t.Fatal("HTML presentation changed model bytes")
	}
}

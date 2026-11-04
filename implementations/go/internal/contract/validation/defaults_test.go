package validation

import (
	"encoding/json"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func TestDefaultsPreserveSchemaAcceptanceAndOwnership(t *testing.T) {
	source := sourceFixture()
	source["schemas/example.json"] = &fstest.MapFile{Data: []byte(`{"type":"object","$defs":{"settings":{"type":"object","properties":{"enabled":{"type":"boolean","default":false},"count":{"type":"integer","default":0},"nullable":{"type":["string","null"],"default":null}}}},"properties":{"settings":{"$ref":"#/$defs/settings","default":{}},"rows":{"type":"array","items":{"$ref":"#/$defs/settings"}}}}`)}
	v, err := load(source, nil)
	if err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: 4096, MaxDepth: 16}
	first, err := v.Defaulted("example", []byte(`{"rows":[{}]}`), limits)
	if err != nil {
		t.Fatal(err)
	}
	want := `{"rows":[{"count":0,"enabled":false,"nullable":null}],"settings":{"count":0,"enabled":false,"nullable":null}}`
	encoded, err := json.Marshal(first)
	if err != nil {
		t.Fatal(err)
	}
	if string(encoded) != want {
		t.Errorf("Defaulted() = %s, want %s", encoded, want)
	}
	defaultObject(t, defaultObject(t, first)["settings"])["count"] = json.Number("99")
	second, err := v.Defaulted("example", []byte(`{}`), limits)
	if err != nil {
		t.Fatal(err)
	}
	if defaultObject(t, defaultObject(t, second)["settings"])["count"] != json.Number("0") {
		t.Error("default catalog was mutated")
	}
	if _, err := v.Defaulted("example", []byte(`{"settings":{"count":"0"}}`), limits); err == nil {
		t.Error("defaults made a wrong input type valid")
	}
}

func defaultObject(t *testing.T, value any) map[string]any {
	t.Helper()
	object, ok := value.(map[string]any)
	if !ok {
		t.Fatalf("Defaulted() returned %T, want object", value)
	}
	return object
}

func TestDefaultsSelectOriginalBranchesAndRejectAmbiguity(t *testing.T) {
	for _, test := range []struct {
		schema, raw, want string
		valid             bool
	}{
		{`{"type":"object","oneOf":[{"properties":{"kind":{"const":"a"},"value":{"default":false}},"required":["kind"]},{"properties":{"kind":{"const":"b"},"value":{"default":true}},"required":["kind"]}]}`, `{"kind":"a"}`, `{"kind":"a","value":false}`, true},
		{`{"type":"object","anyOf":[{"properties":{"value":{"default":false}}},{"properties":{"value":{"default":true}}}]}`, `{}`, ``, false},
		{`{"type":"object","$defs":{"recursive":{"type":"object","properties":{"next":{"$ref":"#/$defs/recursive","default":{}}}}},"$ref":"#/$defs/recursive"}`, `{}`, ``, false},
	} {
		source := sourceFixture()
		source["schemas/example.json"] = &fstest.MapFile{Data: []byte(test.schema)}
		v, err := load(source, nil)
		if err != nil {
			t.Fatal(err)
		}
		got, err := v.Defaulted("example", []byte(test.raw), ingress.Limits{MaxBytes: 4096, MaxDepth: 64})
		if (err == nil) != test.valid {
			t.Errorf("Defaulted(%s) = %v, want valid=%v", test.raw, err, test.valid)
		}
		if test.valid {
			encoded, marshalErr := json.Marshal(got)
			if marshalErr != nil {
				t.Fatal(marshalErr)
			}
			if string(encoded) != test.want {
				t.Errorf("Defaulted() = %s, want %s", encoded, test.want)
			}
		}
	}
}

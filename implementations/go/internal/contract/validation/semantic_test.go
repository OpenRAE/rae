package validation

import (
	"bytes"
	"encoding/json"
	"errors"
	"slices"
	"testing"
	"testing/fstest"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func TestApplicableRules(t *testing.T) {
	raw := `{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","properties":{"choice":{"anyOf":[{"type":"string","x-raes-invariants":[{"id":"text","inputs":[{"contract_id":"test","instance_path":"#/choice"}]}]},{"type":"number","x-raes-invariants":[{"id":"number","inputs":[{"contract_id":"test","instance_path":"#/choice"}]}]}]}},"required":["choice"]}`
	doc, err := jsonschema.UnmarshalJSON(bytes.NewBufferString(raw))
	if err != nil {
		t.Fatal(err)
	}
	compiler := jsonschema.NewCompiler()
	compiler.UseLoader(offline{})
	if err = compiler.AddResource("urn:test", doc); err != nil {
		t.Fatal(err)
	}
	schema, err := compiler.Compile("urn:test")
	if err != nil {
		t.Fatal(err)
	}
	annotations := map[string][]annotation{}
	root, ok := doc.(map[string]any)
	if !ok {
		t.Fatal("test schema is not object")
	}
	if err := collect(root, "#", annotations); err != nil {
		t.Fatal(err)
	}
	calls := 0
	key := Key{"test", "text"}
	v := &Validator{contracts: map[string]contract{"test": {schema: schema, annotations: annotations, raw: root}}, rules: map[Key]Rule{key: {Key: key, RequiresContext: true, Check: func(i Invocation) error {
		calls++
		if i.Path != "/choice" || i.Instance != "safe" {
			return errors.New("wrong instance")
		}
		return nil
	}}}}
	payload := map[string]any{"choice": "safe"}
	if err := v.semantic("test", payload, nil); err == nil {
		t.Error("semantic(nil context) = nil, want refusal")
	}
	if err := v.semantic("test", payload, "trusted"); err != nil {
		t.Fatal(err)
	}
	if calls != 1 {
		t.Errorf("calls = %d, want 1", calls)
	}
	if err := v.semantic("test", map[string]any{"choice": json.Number("1")}, "trusted"); err == nil {
		t.Error("semantic(unregistered number) = nil, want refusal")
	}
}

func TestImmutableAdmission(t *testing.T) {
	v, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	data := []byte(`{"profile_id":"raes-semantic-invariants-v1","schema_version":"raes-semantic-invariants/v1","invariant_entry_schema":"#/$defs/RaesSemanticInvariantEntryModel","profile_reference_schema":"#/$defs/RaesSemanticInvariantProfileReferenceModel","keyword":"x-raes-invariants","uri":"https://openrae.github.io/rae/schemas/semantic-invariants/v1","invariants":[]}`)
	// The profile itself has no semantic annotations.
	value, err := v.Validate("raes-semantic-invariants-v1", data, ingress.Limits{MaxBytes: 4096, MaxDepth: 32}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if value.ContractID() != "raes-semantic-invariants-v1" {
		t.Fatal("admitted identity changed")
	}
	original := string(data)
	data[0] = '['
	cloned := value.JSON()
	cloned[0] = '['
	if got := string(value.JSON()); got != original {
		t.Errorf("JSON() = %s, want original bytes", got)
	}
	if _, err := value.Transport(); err != nil {
		t.Fatal(err)
	}
	if _, err := (Value{}).Transport(); err == nil {
		t.Error("zero.Transport() = nil, want refusal")
	}
}

func TestDispatchAcrossApplicators(t *testing.T) {
	annotationText := func(id string) string {
		return `"x-raes-invariants":[{"id":"` + id + `","inputs":[{"contract_id":"example","instance_path":"#"}]}]`
	}
	for _, test := range []struct {
		name, schema, payload string
		want                  []string
	}{
		{"conditional", `{"type":"object","if":{"required":["flag"],"properties":{"flag":{"const":true}}},"then":{` + annotationText("then") + `},"else":{` + annotationText("else") + `}}`, `{"flag":true}`, []string{"then@"}},
		{"else", `{"type":"object","if":{"required":["flag"]},"then":{` + annotationText("then") + `},"else":{` + annotationText("else") + `}}`, `{}`, []string{"else@"}},
		{"array", `{"type":"array","prefixItems":[{"type":"string",` + annotationText("first") + `}],"items":{"type":"number",` + annotationText("rest") + `},"contains":{"type":"integer",` + annotationText("integral") + `}}`, `["x",1,2.5]`, []string{"first@/0", "integral@/1", "rest@/1", "rest@/2"}},
		{"object", `{"type":"object","properties":{"fixed":{"type":"string",` + annotationText("fixed") + `}},"patternProperties":{"^dyn_":{"type":"number",` + annotationText("dynamic") + `}},"additionalProperties":{"type":"boolean",` + annotationText("extra") + `},"propertyNames":{"type":"string",` + annotationText("name") + `}}`, `{"fixed":"a","dyn_x":1,"other":true}`, []string{"dynamic@/dyn_x", "extra@/other", "fixed@/fixed", "name@/dyn_x", "name@/fixed", "name@/other"}},
		{"reused reference", `{"type":"object","allOf":[{"$ref":"#/$defs/Rule"},{"$ref":"#/$defs/Rule"}],"$defs":{"Rule":{` + annotationText("shared") + `}}}`, `{}`, []string{"shared@"}},
	} {
		t.Run(test.name, func(t *testing.T) { checkDispatch(t, test.schema, test.payload, test.want) })
	}
}

func checkDispatch(t *testing.T, schemaText, payloadText string, want []string) {
	t.Helper()

	source := sourceFixture()
	source["schemas/example.json"] = &fstest.MapFile{Data: []byte(schemaText)}
	var root any
	if err := json.Unmarshal([]byte(payloadText), &root); err != nil {
		t.Fatal(err)
	}
	var schema map[string]any
	if err := json.Unmarshal([]byte(schemaText), &schema); err != nil {
		t.Fatal(err)
	}
	annotations := map[string][]annotation{}
	if err := collect(schema, "#", annotations); err != nil {
		t.Fatal(err)
	}
	var got []string
	rules := recordingRules(annotations, &got)
	v, err := load(source, rules)
	if err != nil {
		t.Fatal(err)
	}
	if err := v.semantic("example", root, nil); err != nil {
		t.Fatal(err)
	}
	slices.Sort(got)
	if !slices.Equal(got, want) {
		t.Errorf("invocations = %v, want %v", got, want)
	}
}

func recordingRules(annotations map[string][]annotation, got *[]string) []Rule {
	rules := []Rule{}
	keys := map[string]bool{}
	for _, rows := range annotations {
		for _, row := range rows {
			if keys[row.ID] {
				continue
			}
			keys[row.ID] = true
			rules = append(rules, Rule{Key: Key{"example", row.ID}, Check: func(i Invocation) error { *got = append(*got, i.Key.InvariantID+"@"+i.Path); return nil }})
		}
	}
	return rules
}

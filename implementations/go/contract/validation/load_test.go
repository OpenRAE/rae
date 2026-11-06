package validation

import (
	"errors"
	"io/fs"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func sourceFixture() fstest.MapFS {
	return fstest.MapFS{
		"schema-publication-manifest.json":        {Data: []byte(`{"entries_directory":"contracts/schema-publication/entries"}`)},
		"schema-publication/entries/example.json": {Data: []byte(`{"contract_id":"example","schema_path":"contracts/schemas/example.json"}`)},
		"schemas/example.json":                    {Data: []byte(`{"type":"object","x-raes-invariants":[{"id":"agreement","inputs":[{"contract_id":"example","instance_path":"#"}]}]}`)},
	}
}

func TestLoadRejectsBrokenResources(t *testing.T) {
	for _, test := range []struct{ name, path, text string }{
		{"missing manifest", "schema-publication-manifest.json", ""},
		{"malformed manifest", "schema-publication-manifest.json", "{"},
		{"outside directory", "schema-publication-manifest.json", `{"entries_directory":"other/entries"}`},
		{"traversal directory", "schema-publication-manifest.json", `{"entries_directory":"contracts/../entries"}`},
		{"missing directory", "schema-publication-manifest.json", `{"entries_directory":"contracts/missing"}`},
		{"malformed entry", "schema-publication/entries/example.json", "{"},
		{"empty identity", "schema-publication/entries/example.json", `{"schema_path":"contracts/schemas/example.json"}`},
		{"outside schema", "schema-publication/entries/example.json", `{"contract_id":"example","schema_path":"outside/schema.json"}`},
		{"missing schema", "schemas/example.json", ""},
		{"malformed schema", "schemas/example.json", "{"},
		{"invalid keyword", "schemas/example.json", `{"type":"imaginary"}`},
		{"nonobject schema", "schemas/example.json", `true`},
		{"external file", "schemas/example.json", `{"$ref":"file:///sensitive"}`},
		{"external HTTP", "schemas/example.json", `{"$ref":"https://example.invalid/private"}`},
		{"invalid invariant", "schemas/example.json", `{"type":"object","x-raes-invariants":{}}`},
		{"unnamed invariant", "schemas/example.json", `{"type":"object","x-raes-invariants":[{"inputs":[{"contract_id":"example","instance_path":"#"}]}]}`},
		{"invalid input", "schemas/example.json", `{"type":"object","x-raes-invariants":[{"id":"rule","inputs":[{"contract_id":"example","instance_path":"invalid"}]}]}`},
	} {
		t.Run(test.name, func(t *testing.T) {
			source := sourceFixture()
			if test.text == "" {
				delete(source, test.path)
			} else {
				source[test.path] = &fstest.MapFile{Data: []byte(test.text)}
			}
			_, err := load(source, nil)
			if category, ok := fault.CategoryOf(err); !ok || category != fault.Operational {
				t.Errorf("load() = %v, want operational failure", err)
			}
			if err != nil && strings.Contains(err.Error(), "sensitive") {
				t.Error("load() disclosed a source value")
			}
		})
	}
	empty := fstest.MapFS{"schema-publication-manifest.json": sourceFixture()["schema-publication-manifest.json"], "schema-publication/entries": {Mode: fs.ModeDir}}
	if _, err := load(empty, nil); err == nil {
		t.Error("load(empty) = nil, want refusal")
	}
	duplicated := sourceFixture()
	duplicated["schema-publication/entries/duplicate.json"] = duplicated["schema-publication/entries/example.json"]
	if _, err := load(duplicated, nil); err == nil {
		t.Error("load(duplicate contract) = nil, want refusal")
	}
}

func TestRuleRegistrationAndPrivacy(t *testing.T) {
	key := Key{"example", "agreement"}
	good := Rule{Key: key, Check: func(Invocation) error { return nil }}
	for _, rules := range [][]Rule{{{Key: Key{"example", "unknown"}, Check: good.Check}}, {{Key: key}}, {good, good}} {
		if _, err := load(sourceFixture(), rules); err == nil {
			t.Error("load(invalid registration) = nil, want refusal")
		}
	}
	sensitive := errors.New("private payload value")
	v, err := load(sourceFixture(), []Rule{{Key: key, Check: func(Invocation) error { return sensitive }}})
	if err != nil {
		t.Fatal(err)
	}
	err = v.semantic("example", map[string]any{}, nil)
	if err == nil || strings.Contains(err.Error(), "private") {
		t.Errorf("semantic() = %v, want safe failure", err)
	}
	if errors.Is(err, sensitive) {
		t.Error("semantic() retained the sensitive third-party cause")
	}
	rules := []Rule{good}
	v, err = load(sourceFixture(), rules)
	if err != nil {
		t.Fatal(err)
	}
	rules[0].Check = nil
	if err = v.semantic("example", map[string]any{}, nil); err != nil {
		t.Fatal(err)
	}
	if len(v.rules) != 1 {
		t.Errorf("rules = %d, want 1", len(v.rules))
	}
}

func TestInputLimitsAndExactNumbers(t *testing.T) {
	source := sourceFixture()
	source["schemas/example.json"] = &fstest.MapFile{Data: []byte(`{"type":"object","properties":{"count":{"type":"integer","minimum":9007199254740993,"maximum":9007199254740993},"flag":{"type":"boolean"}}}`)}
	v, err := load(source, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		text   string
		limits ingress.Limits
		valid  bool
	}{
		{`{"count":9007199254740993,"flag":false}`, ingress.Limits{MaxBytes: 100, MaxDepth: 8}, true},
		{`{"count":9007199254740992}`, ingress.Limits{MaxBytes: 100, MaxDepth: 8}, false},
		{`{"count":true}`, ingress.Limits{MaxBytes: 100, MaxDepth: 8}, false},
		{`{"flag":"false"}`, ingress.Limits{MaxBytes: 100, MaxDepth: 8}, false},
		{`{"flag":false}`, ingress.Limits{MaxBytes: 3, MaxDepth: 8}, false},
		{`{"nested":{"again":{}}}`, ingress.Limits{MaxBytes: 100, MaxDepth: 2}, false},
		{`{"count":NaN}`, ingress.Limits{MaxBytes: 100, MaxDepth: 8}, false},
		{`{"extra":[1e-4301]}`, ingress.Limits{MaxBytes: 100, MaxDepth: 8}, false},
		{`{"extra":[1e-999999999]}`, ingress.Limits{MaxBytes: 100, MaxDepth: 8}, false},
		{`{"extra":[1e-4300]}`, ingress.Limits{MaxBytes: 100, MaxDepth: 8}, true},
	} {
		checkErr := v.CheckSchema("example", []byte(test.text), test.limits)
		if (checkErr == nil) != test.valid {
			t.Errorf("CheckSchema(%s) = %v, want valid=%v", test.text, checkErr, test.valid)
		}
	}
	var zero *Validator
	if err := zero.CheckSchema("example", []byte(`{}`), ingress.Limits{MaxBytes: 100}); err == nil {
		t.Error("nil.CheckSchema() = nil, want refusal")
	}
}

func TestRejectsUnknownInvariantReferences(t *testing.T) {
	for _, schema := range []string{
		`{"type":"object","x-raes-invariants":[{"id":"agreement","inputs":[{"contract_id":"unknown","instance_path":"#"}]}]}`,
		`{"type":"object","x-raes-semantic-profile":{"contract_id":"other","keyword":"x-raes-invariants","required":true}}`,
	} {
		source := sourceFixture()
		source["schemas/example.json"] = &fstest.MapFile{Data: []byte(schema)}
		if _, err := load(source, nil); err == nil {
			t.Error("load(invalid reference) = nil, want refusal")
		}
	}
}

func TestArrayRootAndBindingErrors(t *testing.T) {
	source := sourceFixture()
	source["schemas/example.json"] = &fstest.MapFile{Data: []byte(`{"type":"array","items":{"type":"integer"}}`)}
	v, err := load(source, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		raw   string
		valid bool
	}{{`[]`, true}, {`[1.0]`, true}, {`[true]`, false}, {`{}`, false}} {
		checkErr := v.CheckSchema("example", []byte(test.raw), ingress.Limits{MaxBytes: 100, MaxDepth: 8})
		if (checkErr == nil) != test.valid {
			t.Errorf("CheckSchema(%s) = %v, want valid=%v", test.raw, checkErr, test.valid)
		}
	}
	if _, err = v.DecodeSchema("unknown", []byte(`[]`), ingress.Limits{MaxBytes: 100}); err == nil {
		t.Error("DecodeSchema(unknown) = nil, want refusal")
	}
	if _, err = decodeTransport("unknown", []byte(`{}`)); err == nil {
		t.Error("decodeTransport(unknown) = nil, want refusal")
	}
}

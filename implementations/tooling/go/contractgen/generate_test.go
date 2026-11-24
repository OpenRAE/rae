package contractgen

import (
	"bytes"
	"encoding/json"
	"io/fs"
	"strings"
	"testing"
	"testing/fstest"
)

func TestGenerateAndDrift(t *testing.T) {
	source := fstest.MapFS{
		"specs/conformance/contract-invariant-rules.json":      {Data: []byte(`{"specification":"raes-contract-invariant-rules/v1","rules":[]}`)},
		"THIRD_PARTY_NOTICES.md":                               {Data: []byte("required notice")},
		"contracts/schema-publication-manifest.json":           {Data: []byte(`{"entries_directory":"contracts/schema-publication/entries"}`)},
		"contracts/schema-publication/entries/example-v1.json": {Data: []byte(`{"contract_id":"example-v1","schema_path":"contracts/schemas/example-v1.json"}`)},
		"contracts/schemas/example-v1.json":                    {Data: []byte(`{"type":"object","additionalProperties":false,"properties":{"count":{"type":"integer"},"values":{"type":"array","items":{"type":"string"}}}}`)},
		"contracts/fixtures/example-v1/valid/example.json":     {Data: []byte(`{"count":0}`)},
	}
	got, err := Generate(source)
	if err != nil {
		t.Fatal(err)
	}
	again, err := Generate(source)
	if err != nil {
		t.Fatal(err)
	}
	for name, content := range got {
		if !bytes.Equal(content, again[name]) {
			t.Errorf("Generate() differs for %s", name)
		}
	}
	output := fstest.MapFS{}
	for name, content := range got {
		output[name] = &fstest.MapFile{Data: content}
	}
	if err := Check(output, got); err != nil {
		t.Fatal(err)
	}
	for name := range output {
		output[name].Data = []byte("stale")
		break
	}
	if err := Check(output, got); err == nil {
		t.Error("Check(stale) = nil, want drift")
	}
}

func TestMissingRuleSpecification(t *testing.T) {
	source := fstest.MapFS{
		"THIRD_PARTY_NOTICES.md":                               {Data: []byte("notice")},
		"contracts/schema-publication-manifest.json":           {Data: []byte(`{"entries_directory":"contracts/schema-publication/entries"}`)},
		"contracts/schema-publication/entries/example-v1.json": {Data: []byte(`{"contract_id":"example-v1","schema_path":"contracts/schemas/example-v1.json"}`)},
		"contracts/schemas/example-v1.json":                    {Data: []byte(`{"type":"object","x-raes-invariants":[{"id":"required-rule","description":"Required rule.","level":"error","inputs":[{"contract_id":"example-v1","instance_path":"#"}]}]}`)},
		"specs/conformance/contract-invariant-rules.json":      {Data: []byte(`{"specification":"raes-contract-invariant-rules/v1","rules":[]}`)},
	}
	if _, err := Generate(source); err == nil {
		t.Error("Generate(unwritten rule) = nil, want missing specification")
	}
}

func generatorSource() fstest.MapFS {
	return fstest.MapFS{
		"THIRD_PARTY_NOTICES.md":                               {Data: []byte("required notice")},
		"contracts/schema-publication-manifest.json":           {Data: []byte(`{"entries_directory":"contracts/schema-publication/entries"}`)},
		"contracts/schema-publication/entries/example-v1.json": {Data: []byte(`{"contract_id":"example-v1","schema_path":"contracts/schemas/example-v1.json"}`)},
		"contracts/schemas/example-v1.json":                    {Data: []byte(`{"type":"object","additionalProperties":false,"properties":{"value":{"$ref":"#/$defs/Value"},"map":{"type":"object","additionalProperties":{"type":"number"}},"choice":{"anyOf":[{"type":"string"},{"type":"number"}]}},"$defs":{"Value":{"type":"object","additionalProperties":false,"properties":{"x-y":{"type":"boolean"},"x_y":{"type":"integer"},"self":{"$ref":"#/$defs/Value"},"raw":{"$ref":"#/$defs/Raw"}},"required":["x-y"]},"Raw":{}}}`)},
		"specs/conformance/contract-invariant-rules.json":      {Data: []byte(`{"specification":"raes-contract-invariant-rules/v1","rules":[]}`)},
	}
}

func TestGeneratorRejectsAuthorityAndPathErrors(t *testing.T) {
	for _, test := range []struct{ name, path, value string }{
		{"manifest JSON", "contracts/schema-publication-manifest.json", "{"},
		{"manifest path", "contracts/schema-publication-manifest.json", `{"entries_directory":"../entries"}`},
		{"missing entries", "contracts/schema-publication-manifest.json", `{"entries_directory":"contracts/missing"}`},
		{"entry JSON", "contracts/schema-publication/entries/example-v1.json", "{"},
		{"entry identity", "contracts/schema-publication/entries/example-v1.json", `{"contract_id":"../../escape","schema_path":"contracts/schemas/example-v1.json"}`},
		{"entry schema path", "contracts/schema-publication/entries/example-v1.json", `{"contract_id":"example-v1","schema_path":"contracts/schemas/../outside.json"}`},
		{"missing schema", "contracts/schema-publication/entries/example-v1.json", `{"contract_id":"example-v1","schema_path":"contracts/schemas/missing.json"}`},
		{"schema JSON", "contracts/schemas/example-v1.json", "{"},
		{"remote reference", "contracts/schemas/example-v1.json", `{"$ref":"https://example.invalid/schema"}`},
		{"missing definition", "contracts/schemas/example-v1.json", `{"$ref":"#/$defs/Missing"}`},
		{"missing notice", "THIRD_PARTY_NOTICES.md", ""},
		{"missing specification", "specs/conformance/contract-invariant-rules.json", ""},
		{"specification JSON", "specs/conformance/contract-invariant-rules.json", "{"},
		{"specification version", "specs/conformance/contract-invariant-rules.json", `{"specification":"unknown","rules":[]}`},
	} {
		t.Run(test.name, func(t *testing.T) {
			source := generatorSource()
			if test.value == "" {
				delete(source, test.path)
			} else {
				source[test.path] = &fstest.MapFile{Data: []byte(test.value)}
			}
			if _, err := Generate(source); err == nil {
				t.Error("Generate(invalid source) = nil, want refusal")
			}
		})
	}
	source := generatorSource()
	source["contracts/schemas/extra.json"] = &fstest.MapFile{Data: []byte(`{}`)}
	if _, err := Generate(source); err == nil {
		t.Error("Generate(unpublished schema) = nil, want refusal")
	}
	source = generatorSource()
	source["contracts/linked"] = &fstest.MapFile{Mode: fs.ModeSymlink, Data: []byte("outside")}
	if _, err := Generate(source); err == nil {
		t.Error("Generate(symlink) = nil, want refusal")
	}
}

func TestGeneratedNestedTypesAndCompleteOutput(t *testing.T) {
	source := generatorSource()
	got, err := Generate(source)
	if err != nil {
		t.Fatal(err)
	}
	output := fstest.MapFS{}
	for name, data := range got {
		output[name] = &fstest.MapFile{Data: data}
	}
	const extra = "implementations/go/contract/binding/stale_generated.go"
	output[extra] = &fstest.MapFile{Data: []byte("stale")}
	if err := Check(output, got); err == nil {
		t.Error("Check(extra) = nil, want refusal")
	}
	delete(output, extra)
	for name := range got {
		delete(output, name)
		break
	}
	if err := Check(output, got); err == nil {
		t.Error("Check(missing) = nil, want refusal")
	}
	schema := []byte(`{"type":"array","items":{"type":"object","additionalProperties":{"type":"string"}}}`)
	source["contracts/schemas/example-v1.json"] = &fstest.MapFile{Data: schema}
	if _, err := Generate(source); err != nil {
		t.Fatal(err)
	}
}

func TestRuleSpecificationsKeepLocations(t *testing.T) {
	source := generatorSource()
	row := map[string]any{"id": "example-rule", "description": "The required values agree.", "level": "error", "inputs": []any{map[string]any{"contract_id": "example-v1", "instance_path": "#/value"}}}
	schema := map[string]any{"type": "object", "properties": map[string]any{"a/b~c": map[string]any{"type": "string", "x-raes-invariants": []any{row}}}}
	data, err := json.Marshal(schema)
	if err != nil {
		t.Fatal(err)
	}
	source["contracts/schemas/example-v1.json"] = &fstest.MapFile{Data: data}
	rules := ruleSpecifications(schema, "example-v1", "#")
	if got := rules[0]["schema_pointer"]; got != "#/properties/a~1b~0c" {
		t.Errorf("schema_pointer = %v, want escaped location", got)
	}
	data, err = json.Marshal(map[string]any{"specification": "raes-contract-invariant-rules/v1", "rules": rules})
	if err != nil {
		t.Fatal(err)
	}
	source["specs/conformance/contract-invariant-rules.json"] = &fstest.MapFile{Data: data}
	if _, err := Generate(source); err != nil {
		t.Fatal(err)
	}
}

// The public binding package and the internal corpus are the only destinations.
func TestGeneratedDestinationsKeepTheCorpusInternal(t *testing.T) {
	got, err := Generate(generatorSource())
	if err != nil {
		t.Fatal(err)
	}
	output := fstest.MapFS{}
	for name, data := range got {
		if !strings.HasPrefix(name, "implementations/go/contract/binding/") && !strings.HasPrefix(name, "implementations/go/internal/contract/corpus/data/") {
			t.Errorf("Generate wrote %s outside the binding and corpus destinations", name)
		}
		output[name] = &fstest.MapFile{Data: data}
	}
	const extra = "implementations/go/internal/contract/corpus/data/9999"
	output[extra] = &fstest.MapFile{Data: []byte("stale")}
	if err := Check(output, got); err == nil {
		t.Error("Check(extra corpus piece) = nil, want refusal")
	}
}

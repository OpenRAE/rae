package contractgen

import (
	"archive/zip"
	"bytes"
	"encoding/hex"
	"go/token"
	"io"
	"slices"
	"strings"
	"testing"
	"testing/fstest"
)

func TestGeneratorTransportTypeIdentity(t *testing.T) {
	for _, c := range []struct{ name, schema, want string }{
		{"raw", `{}`, "type ExampleV1 = json.RawMessage"},
		{"integer", `{"type":"integer"}`, "type ExampleV1 = json.Number"},
		{"number", `{"type":"number"}`, "type ExampleV1 = json.Number"},
		{"raw reference", `{"$ref":"#/$defs/R","$defs":{"R":{}}}`, "type ExampleV1 = json.RawMessage"},
		{"number reference", `{"$ref":"#/$defs/R","$defs":{"R":{"type":"number"}}}`, "type ExampleV1 = json.Number"},
		{"raw field reference", `{"$ref":"#/$defs/R"}`, "Field[json.RawMessage]"},
		{"number field reference", `{"$ref":"#/$defs/N"}`, "Field[json.Number]"},
		{"anyOf field", `{"anyOf":[{"type":"string"},{"type":"integer"}]}`, "Field[json.RawMessage]"},
		{"oneOf field", `{"oneOf":[{"type":"string"},{"type":"integer"}]}`, "Field[json.RawMessage]"},
		{"empty closed object field", `{"type":"object","properties":{},"additionalProperties":false}`, "Field[map[string]json.RawMessage]"},
		{"open object field", `{"type":"object","properties":{"x":{"type":"string"}},"additionalProperties":true}`, "type ExampleV1 map[string]json.RawMessage"},
		{"implicit open object field", `{"type":"object","properties":{"x":{"type":"string"}}}`, "type ExampleV1 map[string]json.RawMessage"},
		{"typed map field", `{"type":"object","additionalProperties":{"type":"string"}}`, "Field[map[string]string]"},
		{"annotations on a string field", `{"type":"string","properties":{"x":{"type":"string"}}}`, "Field[string]"},
	} {
		t.Run(c.name, func(t *testing.T) {
			schema := c.schema
			if strings.Contains(c.want, "Field[") {
				schema = `{"type":"object","additionalProperties":false,"properties":{"value":` + schema + `},"$defs":{"R":{},"N":{"type":"number"}}}`
			}
			source := generatorSource()
			source["contracts/schemas/example-v1.json"] = &fstest.MapFile{Data: []byte(schema)}
			generated, _, err := generateBinding(source, publication{ID: "example-v1", SchemaPath: "contracts/schemas/example-v1.json"})
			if err != nil {
				t.Fatal(err)
			}
			if !strings.Contains(string(generated), c.want) {
				t.Fatalf("generated transport lost type identity %q:\n%s", c.want, generated)
			}
		})
	}
}

func TestGeneratorExportedIdentifiers(t *testing.T) {
	for input, want := range map[string]string{"": "Value", "***": "Value", "0": "N0", "9": "N9", "alpha-beta": "AlphaBeta", "Á-value": "ÁValue", "٣-value": "N٣Value", "\u4e2d\u6587": "N\u4e2d\u6587", "ß-value": "NßValue"} {
		got := identifier(input)
		if got != want || !token.IsIdentifier(got) || !token.IsExported(got) {
			t.Errorf("identifier(%q)=%q, want exported %q", input, got, want)
		}
	}
}

func TestGeneratorPackagesEveryResource(t *testing.T) {
	source := generatorSource()
	got, err := Generate(source)
	if err != nil {
		t.Fatal(err)
	}
	reader := generatedArchive(t, got)
	expected := map[string][]byte{"provenance/THIRD_PARTY_NOTICES.md": source["THIRD_PARTY_NOTICES.md"].Data}
	for name, file := range source {
		if relative, ok := strings.CutPrefix(name, "contracts/"); ok {
			expected[relative] = file.Data
		}
	}
	if len(reader.File) != len(expected) {
		t.Fatal("packaged resource inventory changed")
	}
	for name, want := range expected {
		file, err := reader.Open(name)
		if err != nil {
			t.Fatal(err)
		}
		got, err := io.ReadAll(file)
		closeErr := file.Close()
		if err != nil || closeErr != nil || !bytes.Equal(got, want) {
			t.Fatalf("packaged bytes changed for %s", name)
		}
	}
}

func generatedArchive(t *testing.T, output map[string][]byte) *zip.Reader {
	t.Helper()
	names := []string{}
	for name := range output {
		if strings.Contains(name, "/corpus/data/") {
			names = append(names, name)
		}
	}
	slices.Sort(names)
	if len(names) == 0 {
		t.Fatal("generator omitted packaged resources")
	}
	var archive bytes.Buffer
	for _, name := range names {
		decoded, err := hex.DecodeString(strings.TrimSuffix(string(output[name]), "\n"))
		if err != nil || len(decoded) == 0 {
			t.Fatalf("invalid archive piece %s: %v", name, err)
		}
		archive.Write(decoded)
	}
	reader, err := zip.NewReader(bytes.NewReader(archive.Bytes()), int64(archive.Len()))
	if err != nil {
		t.Fatal(err)
	}
	return reader
}

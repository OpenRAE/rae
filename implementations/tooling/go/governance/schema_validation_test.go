package governance

import (
	"encoding/json"
	"testing"
)

func TestCandidateSchemaRepository(t *testing.T) {
	r, err := openRepository("../../../..")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	for _, name := range discoverJSON(r, schemasPrefix, true) {
		t.Run(name, func(t *testing.T) {
			data, err := r.read(name)
			if err != nil {
				t.Fatal(err)
			}
			if _, err := candidateSchema(data); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestJSONArtifactCandidate(t *testing.T) {
	root := t.TempDir()
	schema := "contracts/schemas/profiles/example-v1.json"
	fixture := "contracts/fixtures/profiles/example-v1/valid/example.json"
	testWrite(t, root, schema, []byte(`{"type":"object","properties":{"value":{"type":"string"}},"required":["value"]}`))
	testWrite(t, root, fixture, []byte(`{"value":"accepted"}`))
	request := Request{Tool: jsonArtifactCheck, Root: root, Paths: []string{fixture}}
	report, err := Check(t.Context(), request)
	if err != nil || report.ExitCode != 0 {
		t.Fatalf("positive artifact: %+v %v", report, err)
	}
	// Changing supplied schema bytes must affect evaluation even if the bundle's
	// published schema would accept the fixture.
	testWrite(t, root, schema, []byte(`{"type":"object","properties":{"value":{"type":"integer"}},"required":["value"]}`))
	report, err = Check(t.Context(), request)
	if err != nil || report.ExitCode != 1 {
		t.Fatalf("changed candidate: %+v %v", report, err)
	}
}

func TestJSONArtifactRepository(t *testing.T) {
	report, err := Check(t.Context(), Request{Tool: jsonArtifactCheck, Root: "../../../..", Paths: []string{schemasPrefix}})
	if err != nil || report.ExitCode != 0 {
		t.Fatalf("JSON artifact repository: %+v %v", report, err)
	}
}

func TestCandidateMetaDoesNotResolve(t *testing.T) {
	value, err := decodeJSON([]byte(`{"$ref":"https://unavailable.invalid/schema"}`), 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if err := checkCandidateMeta(value, false); err != nil {
		t.Fatalf("syntax checker resolved ref: %v", err)
	}
	if _, err := compileCandidate(value, false, true); err == nil {
		t.Fatal("compiler accepted unavailable reference")
	}
}

func TestCandidateSchemaReference(t *testing.T) {
	for _, tc := range readReference[[]struct {
		Name, Profile string
		Schema, Value json.RawMessage
		Valid         bool
	}](t, "candidate-schema-reference") {
		t.Run(tc.Name+"/"+tc.Profile, func(t *testing.T) {
			schema, err := decodeJSON(tc.Schema, 0, false)
			if err != nil {
				t.Fatal(err)
			}
			value, err := decodeJSON(tc.Value, 0, false)
			if err != nil {
				t.Fatal(err)
			}
			compiled, err := compileCandidate(schema, tc.Profile == "python", tc.Profile != "python")
			if err == nil {
				err = compiled.Validate(schemaTransport(value))
			}
			if (err == nil) != tc.Valid {
				t.Fatalf("valid=%t want=%t: %v", err == nil, tc.Valid, err)
			}
		})
	}
}

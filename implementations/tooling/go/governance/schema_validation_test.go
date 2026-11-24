package governance

import (
	"encoding/json"
	"errors"
	"slices"
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
			_, err = candidateSchema(data)
			if slices.Contains(unsupportedRepositorySchemas(), name) {
				if !errors.Is(err, errSchemaPattern) {
					t.Fatalf("expected unsupported syntax: %v", err)
				}
			} else if err != nil {
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
	if !errors.Is(err, errSchemaPattern) {
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
			want := nativeCandidateVerdict(tc.Name, tc.Profile, schema, value, tc.Valid)
			if (err == nil) != want {
				t.Fatalf("valid=%t want=%t: %v", err == nil, want, err)
			}
		})
	}
}

// These exact unchanged published schemas contain syntax Go cannot compile.
func unsupportedRepositorySchemas() []string {
	return []string{
		"contracts/schemas/artifact-requirements/artifact-requirement-v1.json",
		"contracts/schemas/plans/backend-realization-preparation-v1.json",
		"contracts/schemas/plans/evaluation-plan-v1.json",
		"contracts/schemas/plans/orchestration-plan-v1.json",
		"contracts/schemas/plans/provisioning-plan-v1.json",
		"contracts/schemas/satisfiability/scenario-satisfiability-evidence-v1.json",
		"contracts/schemas/sdl/instantiated-scenario-snapshot-v1.json",
		"contracts/schemas/sdl/instantiated-scenario-v1.json",
		"contracts/schemas/sdl/materialized-scenario-v1.json",
		"contracts/schemas/sdl/sdl-authoring-input-v1.json",
		"contracts/schemas/sdl/sdl-semantic-migration-context-v1.json",
	}
}

func nativeCandidateVerdict(name, profile string, schema, value any, reference bool) bool {
	want := reference
	// Exact reference cases affected by Go character classes and anchors.
	switch name {
	case "schema-15-value-23", "schema-16-value-24", "schema-16-value-25", "schema-17-value-27", "schema-18-value-26":
		want = false
	}
	pattern, _ := object(schema).get("pattern").(string)
	if _, text := value.(string); !text && profile == "ecmascript" && slices.Contains([]string{"]", "{", "}", `\a`, `\123`, `\!`}, pattern) {
		// Go accepts these spellings. Patterns do not constrain non-string payloads.
		want = true
	}
	return want
}

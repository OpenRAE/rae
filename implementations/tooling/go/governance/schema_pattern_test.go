package governance

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func TestSchemaPatternGoSyntax(t *testing.T) {
	for _, tc := range []struct {
		pattern, value string
		matches        bool
	}{
		{`^\d$`, "2", true}, {`^\d$`, "٢", false},
		{`^\w$`, "é", false}, {`^\p{L}+$`, "é", true},
		{`(?s)^.$`, "\n", true}, {`^.$`, "\n", false},
		{`^a$`, "a\n", false}, {`^a\z`, "a", true},
		{`\Qa.b\E`, "a.b", true}, {`b`, "abc", true},
	} {
		re, err := compileSchemaPattern(tc.pattern)
		if err != nil {
			t.Errorf("%q: %v", tc.pattern, err)
			continue
		}
		if got := re.MatchString(tc.value); got != tc.matches {
			t.Errorf("%q on %q=%t want %t", tc.pattern, tc.value, got, tc.matches)
		}
	}
}

func TestSchemaPatternUnsupported(t *testing.T) {
	for _, source := range []string{`(`, `(?=a)`, `(a)\1`, `a\Z`, `\N{LATIN CAPITAL LETTER A}`} {
		if _, err := compileSchemaPattern(source); !errors.Is(err, errSchemaPattern) {
			t.Errorf("%q: %v", source, err)
		}
	}
}

func TestSchemaPatternConfigurationBoundary(t *testing.T) {
	for _, pattern := range []string{`(`, `(?=a)`, `a\Z`} {
		t.Run(pattern, func(t *testing.T) {
			root := t.TempDir()
			schema := "contracts/schemas/profiles/example-v1.json"
			fixture := "contracts/fixtures/profiles/example-v1/valid/example.json"
			data, err := json.Marshal(map[string]any{"type": "string", "pattern": pattern})
			if err != nil {
				t.Fatal(err)
			}
			testWrite(t, root, schema, data)
			testWrite(t, root, fixture, []byte(`"accepted"`))
			_, err = Check(t.Context(), Request{Tool: jsonArtifactCheck, Root: root, Paths: []string{fixture}})
			if !errors.Is(err, errSchemaPattern) {
				t.Fatalf("configuration became a verdict: %v", err)
			}
			if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
				t.Fatalf("category=%v known=%t", category, ok)
			}
		})
	}
}

func TestToolingPatternConfiguration(t *testing.T) {
	for _, pattern := range []string{`(`, `(?=a)`, `a\Z`} {
		root := t.TempDir()
		data, err := json.Marshal(map[string]any{"type": "object", "patternProperties": map[string]any{pattern: map[string]any{"type": "string"}}})
		if err != nil {
			t.Fatal(err)
		}
		testWrite(t, root, "implementations/tooling/schemas/artifact-lock.schema.json", data)
		r, err := openRepository(root)
		if err != nil {
			t.Fatal(err)
		}
		err = toolingRecord(r, newMapping(), artifactLockPath, "")
		_ = r.root.Close()
		if !errors.Is(err, errSchemaPattern) {
			t.Fatalf("tooling pattern %q lost configuration error: %v", pattern, err)
		}
	}
}

func TestSchemaNestedPatternConfiguration(t *testing.T) {
	for _, data := range []string{
		`{"properties":{"nested":{"pattern":"(?=a)"}}}`,
		`{"patternProperties":{"(?=a)":{}}}`,
		`{"$defs":{"unused":{"pattern":"(?=a)"}}}`,
	} {
		schema, err := decodeJSON([]byte(data), 0, false)
		if err != nil {
			t.Fatal(err)
		}
		for _, coverage := range []bool{false, true} {
			_, err = compileCandidate(schema, coverage, false)
			if !errors.Is(err, errSchemaPattern) {
				t.Fatalf("nested pattern lost refusal: %v", err)
			}
			if err = checkCandidateMeta(schema, coverage); !errors.Is(err, errSchemaPattern) {
				t.Fatalf("meta pattern lost refusal: %v", err)
			}
		}
	}
}

func TestSchemaRegexPayloadBoundary(t *testing.T) {
	root := t.TempDir()
	schema := "contracts/schemas/profiles/example-v1.json"
	fixture := "contracts/fixtures/profiles/example-v1/valid/example.json"
	testWrite(t, root, schema, []byte(`{"type":"string","format":"regex"}`))
	testWrite(t, root, fixture, []byte(`"(?=a)"`))
	report, err := Check(t.Context(), Request{Tool: jsonArtifactCheck, Root: root, Paths: []string{fixture}})
	if err != nil || report.ExitCode != 1 || len(report.Findings) != 1 || report.Findings[0].RuleID != jsonValidationRule {
		t.Fatalf("regex payload became a configuration error: %+v %v", report, err)
	}
}

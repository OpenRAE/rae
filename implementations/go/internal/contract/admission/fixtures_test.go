package admission

import (
	"bytes"
	"encoding/json"
	"io/fs"
	"sync"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

// Immutable archive and bytes are shared; each call still decodes a fresh tree.
var sharedFixtureCorpus = sync.OnceValues(corpus.Open) //nolint:gochecknoglobals // Read-only test archive, independent of the corruption tests.
var sharedFixtureBytes sync.Map                        //nolint:gochecknoglobals // Immutable source bytes; decoded mutable values are never cached.

func fixtureObject(t *testing.T, path string) map[string]any {
	t.Helper()
	source, err := sharedFixtureCorpus()
	if err != nil {
		t.Fatal(err)
	}
	read := sync.OnceValues(func() ([]byte, error) { return fs.ReadFile(source, path) })
	cached, _ := sharedFixtureBytes.LoadOrStore(path, read)
	load, ok := cached.(func() ([]byte, error))
	if !ok {
		t.Fatal("invalid shared fixture reader")
	}
	raw, err := load()
	if err != nil {
		t.Fatal(err)
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var value map[string]any
	if err := decoder.Decode(&value); err != nil {
		t.Fatal(err)
	}
	return value
}

// Compile the immutable production registry once per test process. Requests and
// contexts remain independent. Tests that corrupt catalogs must construct New.
var sharedTestOwner = sync.OnceValues(New) //nolint:gochecknoglobals // Immutable test fixture; once-only construction is safe across independent requests.

// Family tests use the production constructor and complete published registry.
func boundTestOwner(t *testing.T) *Validator {
	t.Helper()
	e, err := sharedTestOwner()
	if err != nil {
		t.Fatal(err)
	}
	return e
}

// validateTestDocument exercises public dispatch, schemas, rules and model checks.
func validateTestDocument(t *testing.T, e *Validator, id string, value, context any) error {
	t.Helper()
	_, err := e.Validate(id, controlJSON(t, value), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, context)
	return err
}
func assertObjectRule(t *testing.T, id string, v any, valid bool) {
	t.Helper()
	raw, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	assertRule(t, id, string(raw), valid)
}

func TestPublishedLocalFixtures(t *testing.T) {
	for _, test := range []struct{ id, path string }{
		{"participant-configuration-digest-valid", "fixtures/participant-implementation-configuration/participant-configuration-result-v1/valid/reference.json"},
		{"authoring-vector-bound-inputs", "fixtures/authoring-adapters/authoring-adapter-vector-v1/valid/reference.json"},
		{"authoring-comparison-evidence-shape", "fixtures/authoring-adapters/authoring-adapter-comparison-v1/valid/reference.json"},
		{"artifact-transformation-deterministic-order", "fixtures/artifact-transformations/artifact-transformation-report-v1/valid/canonical-identity.json"},
		{"exact-source-artifact-id-match", "fixtures/artifact-requirements/artifact-requirement-v1/valid/exact-artifact.json"},
		{"validation-profile-catalog-reference-integrity", "profiles/validation/validation-profile-catalog-v1.json"},
	} {
		t.Run(test.id, func(t *testing.T) { assertObjectRule(t, test.id, fixtureObject(t, test.path), true) })
	}
	root := fixtureObject(t, "fixtures/experiment-core/experiment-apparatus-context-v1/valid/reference.json")
	assertObjectRule(t, "manifest-reference-digest-scope-valid", at(root, "components", "processor", "manifest_ref"), true)
	manifest := object(at(root, "components", "processor", "manifest_ref"))
	manifest["ref_digest"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
	assertObjectRule(t, "manifest-reference-digest-scope-valid", manifest, true)
	manifest["ref_version"] = "2.0.0"
	assertObjectRule(t, "manifest-reference-digest-scope-valid", manifest, false)
}

func TestFixtureObjectsRemainIndependent(t *testing.T) {
	const path = "fixtures/participant-runtime/participant-control-evaluation-v1/valid/teaching-inject.json"
	first := fixtureObject(t, path)
	second := fixtureObject(t, path)
	object(at(first, "request"))["request_id"] = "substituted"
	if equal(first, second) || stringAt(fixtureObject(t, path), "request", "request_id") == "substituted" {
		t.Fatal("mutable fixture data was shared")
	}
}

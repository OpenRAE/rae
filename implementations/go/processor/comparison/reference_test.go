package comparison_test

import (
	"bytes"
	"encoding/json"
	"os"
	"slices"
	"sync"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/profile"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/processor/comparison"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type artifactVector struct {
	Owner   string            `json:"owner"`
	Input   json.RawMessage   `json:"input"`
	Root    string            `json:"root"`
	Sources map[string]string `json:"sources"`
}
type profileVector struct {
	ID         string            `json:"profile_id"`
	Analyzer   string            `json:"analyzer_profile"`
	Projection string            `json:"projection_profile"`
	Closure    string            `json:"impact_closure_policy"`
	Identity   string            `json:"identity_axis"`
	Textual    string            `json:"textual_axis"`
	Structural string            `json:"structural_axis"`
	Semantic   string            `json:"semantic_axis"`
	Rules      map[string]string `json:"dependency_rule_versions"`
	Owners     map[string]string `json:"owner_projection_versions"`
	Limits     struct {
		Subjects    int `json:"max_subjects"`
		Edges       int `json:"max_dependency_edges"`
		Depth       int `json:"max_path_depth"`
		Paths       int `json:"max_paths"`
		Diagnostics int `json:"max_diagnostics"`
	} `json:"limits"`
}

func (v profileVector) native() profile.ComparisonProfile {
	return profile.ComparisonProfile{ProfileID: v.ID, AnalyzerProfile: v.Analyzer, ProjectionProfile: v.Projection, ImpactClosurePolicy: v.Closure, IdentityAxis: v.Identity, TextualAxis: v.Textual, StructuralAxis: v.Structural, SemanticAxis: v.Semantic, DependencyRuleVersions: v.Rules, OwnerProjectionVersions: v.Owners, Limits: profile.ComparisonLimits{MaxSubjects: v.Limits.Subjects, MaxDependencyEdges: v.Limits.Edges, MaxPathDepth: v.Limits.Depth, MaxPaths: v.Limits.Paths, MaxDiagnostics: v.Limits.Diagnostics}}
}

type analysisVector struct {
	Name        string          `json:"name"`
	Profile     profileVector   `json:"profile"`
	Request     json.RawMessage `json:"request"`
	Before      int             `json:"before"`
	After       int             `json:"after"`
	BeforeScope []int           `json:"before_scope"`
	AfterScope  []int           `json:"after_scope"`
	Report      json.RawMessage `json:"transformation_report"`
	Evidence    []string        `json:"evidence_digests"`
	Expected    json.RawMessage `json:"expected"`
	Valid       bool            `json:"valid"`
}
type referenceVectors struct {
	Artifacts   []artifactVector `json:"artifacts"`
	Coordinates []struct {
		Name     string          `json:"name"`
		Artifact int             `json:"artifact"`
		Revision string          `json:"revision"`
		Expected json.RawMessage `json:"expected"`
	} `json:"coordinates"`
	Cases []analysisVector `json:"cases"`
}

var nativeOwners = sync.OnceValues(func() (*validation.Validator, error) { //nolint:gochecknoglobals // Immutable schemas are shared by these bounded tests.
	base, err := validation.New(nil)
	if err != nil {
		return nil, err
	}
	rules := make([]validation.Rule, 0, len(base.Keys()))
	for _, key := range base.Keys() {
		rules = append(rules, validation.Rule{Key: key, Check: func(validation.Invocation) error { return nil }})
	}
	return base.WithRules(rules)
})

func testLimits() ingress.Limits { return ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64} }
func testOwner(t *testing.T) *validation.Validator {
	t.Helper()
	owner, err := nativeOwners()
	if err != nil {
		t.Fatal(err)
	}
	return owner
}
func valueFrom(t *testing.T, id string, raw []byte) validation.Value {
	t.Helper()
	owner := testOwner(t)
	result, err := owner.Validate(id, raw, testLimits(), nil)
	if err != nil {
		t.Fatal(id, err)
	}
	return result
}
func document(t *testing.T, raw []byte) any {
	t.Helper()
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var result any
	if err := decoder.Decode(&result); err != nil {
		t.Fatal(err)
	}
	return result
}
func assertJSON(t *testing.T, actual, expected []byte) {
	t.Helper()
	if difference := cmp.Diff(document(t, expected), document(t, actual)); difference != "" {
		t.Fatalf("JSON differs (-expected +actual):\n%s", difference)
	}
}
func marshal(t *testing.T, input any) []byte {
	t.Helper()
	raw, err := json.Marshal(input)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}
func references(t *testing.T) referenceVectors {
	t.Helper()
	var result referenceVectors
	for _, path := range []string{"testdata/reference.json", "testdata/reference-2.json"} {
		raw, err := os.ReadFile(path) //nolint:gosec // The fixture paths are a fixed literal list.
		if err != nil {
			t.Fatal(err)
		}
		var part referenceVectors
		if err := json.Unmarshal(raw, &part); err != nil {
			t.Fatal(err)
		}
		result.Artifacts = append(result.Artifacts, part.Artifacts...)
		result.Coordinates = append(result.Coordinates, part.Coordinates...)
		result.Cases = append(result.Cases, part.Cases...)
	}
	if len(result.Artifacts) != 48 || len(result.Coordinates) != 8 || len(result.Cases) != 77 {
		t.Fatal("comparison reference inventory changed")
	}
	return result
}

//nolint:ireturn // Fixtures use only exact native sealed constructors.
func referenceArtifact(t *testing.T, input artifactVector) comparison.Artifact {
	t.Helper()
	var result comparison.Artifact
	var err error
	switch input.Owner {
	case "scenario":
		source, sourceErr := referenceScenario(input)
		if sourceErr != nil {
			t.Fatal(sourceErr)
		}
		result, err = comparison.FromScenario(source)
	case "resolved-import-provenance":
		owner, ownerErr := admission.New()
		if ownerErr != nil {
			t.Fatal(ownerErr)
		}
		source, sourceErr := admission.AdmitFragment(owner, admission.ResolvedImportProvenance, document(t, input.Input), testLimits())
		if sourceErr != nil {
			t.Fatal(sourceErr)
		}
		result, err = comparison.FromModule(source)
	default:
		result, err = comparison.FromDocument(valueFrom(t, input.Owner, input.Input))
	}
	if err != nil {
		t.Fatal(input.Owner, err)
	}
	return result
}

//nolint:ireturn // Source maps are admitted by the native offline owner.
func referenceScenario(input artifactVector) (sdl.Scenario, error) {
	if len(input.Sources) == 0 {
		return sdl.AuthoredScenario(input.Input, sdl.DefaultParseOptions())
	}
	sources := make(map[string][]byte, len(input.Sources))
	for name, source := range input.Sources {
		sources[name] = []byte(source)
	}
	return sdl.ParseSources(sources, input.Root, sdl.DefaultParseOptions())
}
func TestComparisonCoordinatesMatchIndependentPython(t *testing.T) {
	vectors := references(t)
	for _, test := range vectors.Coordinates {
		t.Run(test.Name, func(t *testing.T) {
			source := referenceArtifact(t, vectors.Artifacts[test.Artifact])
			actual, err := comparison.Coordinate(source, test.Revision, nil)
			if err != nil {
				t.Fatal(err)
			}
			assertJSON(t, marshal(t, actual.Document()), test.Expected)
		})
	}
}
func scopeArtifacts(t *testing.T, indices []int, vectors referenceVectors, cache map[int]comparison.Artifact) []comparison.Artifact {
	t.Helper()
	result := make([]comparison.Artifact, 0, len(indices))
	for _, index := range indices {
		if cache[index] == nil {
			cache[index] = referenceArtifact(t, vectors.Artifacts[index])
		}
		result = append(result, cache[index])
	}
	return result
}
func TestComparisonAnalyzerMatchesIndependentPython(t *testing.T) {
	vectors := references(t)
	cache := map[int]comparison.Artifact{}
	for _, test := range vectors.Cases {
		t.Run(test.Name, func(t *testing.T) {
			pair := scopeArtifacts(t, []int{test.Before, test.After}, vectors, cache)
			options := comparison.Options{BeforeScope: scopeArtifacts(t, test.BeforeScope, vectors, cache), AfterScope: scopeArtifacts(t, test.AfterScope, vectors, cache), EvidenceDigests: test.Evidence}
			if test.Report != nil {
				options.TransformationReport = valueFrom(t, "artifact-transformation-report-v1", test.Report)
			}
			request := valueFrom(t, "semantic-comparison-request-v1", test.Request)
			actual, err := comparison.Analyze(test.Profile.native(), request, pair[0], pair[1], options)
			if (err == nil) != test.Valid {
				t.Fatalf("valid=%v err=%v", test.Valid, err)
			}
			if err == nil {
				assertJSON(t, actual.JSON(), test.Expected)
			}
		})
	}
}

func TestComparisonImpactScopesMatchIndependentPython(t *testing.T) {
	vectors := references(t)
	cache := map[int]comparison.Artifact{}
	for _, test := range vectors.Cases {
		if !test.Valid {
			continue
		}
		t.Run(test.Name, func(t *testing.T) {
			checkImpactScopeReference(t, test, vectors, cache)
		})
	}
}

func checkImpactScopeReference(t *testing.T, test analysisVector, vectors referenceVectors, cache map[int]comparison.Artifact) {
	t.Helper()
	var request struct {
		Scope struct {
			ID     string   `json:"scope_id"`
			Status string   `json:"closure_status"`
			Roots  []string `json:"traversal_roots"`
		} `json:"impact_scope"`
	}
	if err := json.Unmarshal(test.Request, &request); err != nil {
		t.Fatal(err)
	}
	var raw struct {
		Scope json.RawMessage `json:"impact_scope"`
	}
	if err := json.Unmarshal(test.Request, &raw); err != nil {
		t.Fatal(err)
	}
	beforeIDs, afterIDs := test.BeforeScope, test.AfterScope
	if len(beforeIDs) == 0 {
		beforeIDs = []int{test.Before}
	}
	if len(afterIDs) == 0 {
		afterIDs = []int{test.After}
	}
	before, after := scopeArtifacts(t, beforeIDs, vectors, cache), scopeArtifacts(t, afterIDs, vectors, cache)
	slices.Reverse(before)
	slices.Reverse(after)
	roots := append([]string{}, request.Scope.Roots...)
	roots = append(roots, roots[0])
	slices.Reverse(roots)
	actual, err := comparison.BuildImpactScope(before, after, roots, request.Scope.Status, request.Scope.ID, test.Profile.Owners["scenario"])
	if err != nil {
		t.Fatal(err)
	}
	assertJSON(t, marshal(t, actual.Document()), raw.Scope)
}

package comparison_test

import (
	"encoding/json"
	"errors"
	"maps"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/processor/comparison"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type foreignArtifact struct{ comparison.Artifact }
type foreignScenario struct{ sdl.Scenario }

func (foreignScenario) Document() map[string]any    { panic("foreign source method called") }
func (foreignScenario) SemanticallyValidated() bool { panic("foreign source method called") }

type foreignFragment struct{ admission.Fragment }

func (foreignFragment) Document() any                      { panic("foreign fragment method called") }
func (foreignFragment) Profile() admission.FragmentProfile { panic("foreign fragment method called") }
func requireInputError(t *testing.T, err error) {
	t.Helper()
	category, ok := fault.CategoryOf(err)
	if err == nil || !ok || category != fault.InvalidInput {
		t.Fatalf("expected input fault, got %v", err)
	}
	if strings.Contains(err.Error(), "private-secret") {
		t.Fatal("rejected input echoed")
	}
}
func TestComparisonRejectsForeignOwnershipBeforeMethods(t *testing.T) {
	source, err := sdl.AuthoredScenario([]byte(`{"name":"arena","version":"1"}`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	artifact, err := comparison.FromScenario(source)
	if err != nil {
		t.Fatal(err)
	}
	for _, source := range []sdl.Scenario{nil, foreignScenario{}, foreignScenario{source}} {
		_, sourceErr := comparison.FromScenario(source)
		requireInputError(t, sourceErr)
	}
	instance, err := sdl.Instantiate(source, nil)
	if err != nil {
		t.Fatal(err)
	}
	_, err = comparison.FromScenario(instance)
	requireInputError(t, err)
	for _, input := range []comparison.Artifact{nil, foreignArtifact{}, foreignArtifact{artifact}} {
		_, err = comparison.Coordinate(input, "2", nil)
		requireInputError(t, err)
		_, err = comparison.BuildImpactScope([]comparison.Artifact{input}, []comparison.Artifact{artifact}, []string{"scenario:arena"}, "complete", "scope", "2")
		requireInputError(t, err)
	}
	for _, input := range []admission.Fragment{foreignFragment{}, foreignFragment{}} {
		_, err = comparison.FromModule(input)
		requireInputError(t, err)
		_, err = comparison.Coordinate(artifact, "2", input)
		requireInputError(t, err)
	}
	_, err = comparison.FromDocument(validation.Value{})
	requireInputError(t, err)
}
func TestComparisonScopeAndOptionsRejectMalformedInputWithoutEcho(t *testing.T) {
	vectors := references(t)
	test := vectors.Cases[0]
	before, after := referenceArtifact(t, vectors.Artifacts[test.Before]), referenceArtifact(t, vectors.Artifacts[test.After])
	request := valueFrom(t, "semantic-comparison-request-v1", test.Request)
	roots := []string{"private-secret\xff", strings.Repeat("x", (1<<20)+1)}
	for _, root := range roots {
		_, err := comparison.BuildImpactScope([]comparison.Artifact{before}, []comparison.Artifact{after}, []string{root}, "complete", "scope", "2")
		requireInputError(t, err)
	}
	for _, options := range []comparison.Options{{EvidenceDigests: []string{"private-secret"}}, {EvidenceDigests: []string{"sha256:" + strings.Repeat("b", 64), "sha256:" + strings.Repeat("a", 64)}}, {EvidenceDigests: []string{"sha256:" + strings.Repeat("a", 64), "sha256:" + strings.Repeat("a", 64)}}, {BeforeScope: []comparison.Artifact{foreignArtifact{before}}}, {TransformationReport: request}} {
		_, err := comparison.Analyze(test.Profile.native(), request, before, after, options)
		requireInputError(t, err)
	}
	_, err := comparison.BuildImpactScope(make([]comparison.Artifact, 4097), []comparison.Artifact{after}, []string{"scenario:arena"}, "complete", "scope", "2")
	requireInputError(t, err)
	_, err = comparison.BuildImpactScope([]comparison.Artifact{before, before}, []comparison.Artifact{after}, []string{"scenario:arena"}, "complete", "scope", "2")
	requireInputError(t, err)
}
func TestComparisonArtifactsRetainIndependentOwnerMeaning(t *testing.T) {
	vectors := references(t)
	test := vectors.Cases[0]
	input := vectors.Artifacts[test.Before]
	source, err := referenceScenario(input)
	if err != nil {
		t.Fatal(err)
	}
	artifact, err := comparison.FromScenario(source)
	if err != nil {
		t.Fatal(err)
	}
	first, err := comparison.Coordinate(artifact, "2", nil)
	if err != nil {
		t.Fatal(err)
	}
	expected := marshal(t, first.Document())
	projection := source.Document()
	projection["name"] = "changed"
	coordinate := fragmentObject(t, first)
	coordinate["canonical_digest"] = "private-secret"
	again, err := comparison.Coordinate(artifact, "2", nil)
	if err != nil {
		t.Fatal(err)
	}
	assertJSON(t, marshal(t, again.Document()), expected)
	exactOwner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	exact, err := admission.AdmitFragment(exactOwner, admission.ExactRepresentation, map[string]any{"profile": "utf8-json/v1", "media_type": "application/json", "byte_digest": "sha256:" + strings.Repeat("a", 64)}, testLimits())
	if err != nil {
		t.Fatal(err)
	}
	fragmentObject(t, exact)["byte_digest"] = "private-secret"
	withExact, err := comparison.Coordinate(artifact, "2", exact)
	if err != nil {
		t.Fatal(err)
	}
	var data struct {
		Exact struct {
			Digest string `json:"byte_digest"`
		} `json:"exact_representation"`
	}
	if json.Unmarshal(marshal(t, withExact.Document()), &data) != nil || data.Exact.Digest != "sha256:"+strings.Repeat("a", 64) {
		t.Fatal("exact evidence mutated")
	}
}
func fragmentObject(t *testing.T, input admission.Fragment) map[string]any {
	t.Helper()
	result, ok := input.Document().(map[string]any)
	if !ok {
		t.Fatal("expected object fragment")
	}
	return result
}

func TestComparisonRechecksRequestPinsAndProfileBeforeAnalysis(t *testing.T) {
	vectors := references(t)
	test := vectors.Cases[0]
	before, after := referenceArtifact(t, vectors.Artifacts[test.Before]), referenceArtifact(t, vectors.Artifacts[test.After])
	request := valueFrom(t, "semantic-comparison-request-v1", test.Request)
	for _, field := range []string{"comparison_profile_digest", "scope_digest", "canonical_identity"} {
		t.Run(field, func(t *testing.T) {
			supplied := changedComparisonRequest(t, test.Request, field)
			_, err := comparison.Analyze(test.Profile.native(), supplied, before, after, comparison.Options{})
			requireInputError(t, err)
		})
	}
	governed := test.Profile.native()
	governed.OwnerProjectionVersions = maps.Clone(governed.OwnerProjectionVersions)
	governed.OwnerProjectionVersions["module"] = "2"
	_, err := comparison.Analyze(governed, request, before, after, comparison.Options{})
	requireInputError(t, err)
	// A caller-supplied cached profile digest never overrides its governed meaning.
	governed = test.Profile.native()
	governed.Digest = "private-secret"
	actual, err := comparison.Analyze(governed, request, before, after, comparison.Options{})
	if err != nil {
		t.Fatal(err)
	}
	assertJSON(t, actual.JSON(), test.Expected)
	for _, input := range []validation.Value{{}} {
		_, err := comparison.Analyze(test.Profile.native(), input, before, after, comparison.Options{})
		requireInputError(t, err)
	}
}

func TestComparisonRequestIngressLimitsAndRecovery(t *testing.T) {
	test := references(t).Cases[0]
	duplicate := append(append([]byte{}, test.Request[:len(test.Request)-1]...), []byte(`,"schema_version":"semantic-comparison-request/v1"}`)...)
	oversized := append(append([]byte{}, test.Request...), []byte(strings.Repeat(" ", 1<<20))...)
	for _, input := range []struct {
		name string
		raw  []byte
		code string
	}{{"duplicate", duplicate, ingress.DuplicateMember}, {"byte-bound", oversized, ingress.TooLarge}} {
		t.Run(input.name, func(t *testing.T) {
			_, err := testOwner(t).Validate("semantic-comparison-request-v1", input.raw, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}, nil)
			requireInputError(t, err)
			detail, ok := errors.AsType[*ingress.Error](err)
			if !ok || detail.Code != input.code {
				t.Fatalf("expected ingress %s got %v", input.code, err)
			}
		})
	}
	if _, err := testOwner(t).Validate("semantic-comparison-request-v1", test.Request, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}, nil); err != nil {
		t.Fatal("valid request after refusal", err)
	}
}

func TestComparisonResultsRetainScopePinsOnReadmission(t *testing.T) {
	vectors := references(t)
	test := vectors.Cases[0]
	before, after := referenceArtifact(t, vectors.Artifacts[test.Before]), referenceArtifact(t, vectors.Artifacts[test.After])
	request := valueFrom(t, "semantic-comparison-request-v1", test.Request)
	actual, err := comparison.Analyze(test.Profile.native(), request, before, after, comparison.Options{})
	if err != nil {
		t.Fatal(err)
	}
	output, ok := document(t, actual.JSON()).(map[string]any)
	if !ok {
		t.Fatal("result is not an object")
	}
	output["impact_scope_digest"] = "sha256:" + strings.Repeat("f", 64)
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	_, err = owner.Validate("semantic-comparison-result-v1", marshal(t, output), testLimits(), nil)
	requireInputError(t, err)
	assertJSON(t, actual.JSON(), test.Expected)
}

func changedComparisonRequest(t *testing.T, input []byte, field string) validation.Value {
	t.Helper()
	raw := document(t, input)
	object, ok := raw.(map[string]any)
	if !ok {
		t.Fatal("request is not an object")
	}
	switch field {
	case "comparison_profile_digest":
		object[field] = "sha256:" + strings.Repeat("f", 64)
	case "scope_digest":
		scope, ok := object["impact_scope"].(map[string]any)
		if !ok {
			t.Fatal("scope is not an object")
		}
		scope[field] = "sha256:" + strings.Repeat("f", 64)
	case "canonical_identity":
		coordinate, ok := object["before"].(map[string]any)
		if !ok {
			t.Fatal("coordinate is not an object")
		}
		coordinate[field] = "scenario:private-secret"
	}
	return valueFrom(t, "semantic-comparison-request-v1", marshal(t, object))
}

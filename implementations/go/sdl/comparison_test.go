package sdl_test

import (
	"encoding/json"
	"os"
	"strconv"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type comparisonReference struct {
	Case            string                       `json:"name"`
	Source          string                       `json:"source"`
	Root            string                       `json:"root,omitempty"`
	Sources         map[string]string            `json:"sources,omitempty"`
	Revision        string                       `json:"revision"`
	Name            string                       `json:"Name"`
	Version         string                       `json:"Version"`
	CanonicalDigest string                       `json:"CanonicalDigest"`
	Structural      json.RawMessage              `json:"Structural"`
	Semantic        json.RawMessage              `json:"Semantic"`
	Subjects        []comparisonSubjectReference `json:"Subjects"`
	Imports         []json.RawMessage            `json:"Imports"`
}
type comparisonSubjectReference struct {
	Family        string          `json:"Family"`
	Name          string          `json:"Name"`
	ModelType     string          `json:"ModelType"`
	PresentFields []string        `json:"PresentFields"`
	Semantic      json.RawMessage `json:"Semantic"`
}

func TestComparisonProjectionMatchesIndependentNativeModelReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/comparison-projections.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []comparisonReference
	if err = json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		t.Run(test.Case+"/"+test.Revision, func(t *testing.T) { checkComparisonReference(t, test) })
	}
}
func checkComparisonReference(t *testing.T, test comparisonReference) {
	t.Helper()
	source := comparisonReferenceSource(t, test)
	actual, err := sdl.ProjectComparison(source, test.Revision)
	if err != nil {
		t.Fatal(err)
	}
	if actual.Name != test.Name || actual.Version != test.Version || actual.CanonicalDigest != test.CanonicalDigest {
		t.Fatalf("coordinate=%s %s %s want=%s %s %s", actual.Name, actual.Version, actual.CanonicalDigest, test.Name, test.Version, test.CanonicalDigest)
	}
	if !equalDescriptorJSON(t, descriptorJSON(t, actual.Structural.Document()), test.Structural) || !equalDescriptorJSON(t, descriptorJSON(t, actual.Semantic.Document()), test.Semantic) {
		t.Fatal("root owner projections differ")
	}
	if len(actual.Subjects) != len(test.Subjects) || len(actual.Imports) != len(test.Imports) {
		t.Fatalf("child/import counts=%d/%d want=%d/%d", len(actual.Subjects), len(actual.Imports), len(test.Subjects), len(test.Imports))
	}
	for i, subject := range actual.Subjects {
		checkComparisonSubject(t, i, subject, test.Subjects[i])
	}
	for i, record := range actual.Imports {
		if !equalDescriptorJSON(t, descriptorJSON(t, record.Document()), test.Imports[i]) {
			t.Fatalf("import %d defaults differ", i)
		}
	}
}

//nolint:ireturn // Independent fixtures enter only through the native sealed source owner.
func comparisonReferenceSource(t *testing.T, test comparisonReference) sdl.Scenario {
	t.Helper()
	var source sdl.Scenario
	var err error
	if len(test.Sources) > 0 {
		sources := make(map[string][]byte, len(test.Sources))
		for name, text := range test.Sources {
			sources[name] = []byte(text)
		}
		source, err = sdl.ParseSources(sources, test.Root, sdl.DefaultParseOptions())
	} else {
		source, err = sdl.AuthoredScenario([]byte(test.Source), sdl.DefaultParseOptions())
	}
	if err != nil {
		t.Fatal(err)
	}
	return source
}
func checkComparisonSubject(t *testing.T, index int, actual sdl.ComparisonSubject, expected comparisonSubjectReference) {
	t.Helper()
	if actual.Family != expected.Family || actual.Name != expected.Name || actual.ModelType != expected.ModelType {
		t.Fatalf("subject %d identity/type differ", index)
	}
	if !equalDescriptorJSON(t, descriptorJSON(t, actual.PresentFields), descriptorJSON(t, expected.PresentFields)) || !equalDescriptorJSON(t, descriptorJSON(t, actual.Semantic.Document()), expected.Semantic) {
		t.Fatalf("subject %d fields/semantics differ", index)
	}
}
func TestComparisonProjectionRejectsForeignPhasesAndRevisions(t *testing.T) {
	source, err := sdl.Parse([]byte("name: sample\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(source, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, input := range []sdl.Scenario{nil, instance, replacedDescriptorScenario{source}} {
		if _, err := sdl.ProjectComparison(input, "2"); err == nil {
			t.Fatal("foreign or concrete phase accepted")
		}
	}
	if _, err := sdl.ProjectComparison(source, "3"); err == nil {
		t.Fatal("unsupported projection accepted")
	}
}

func TestComparisonProjectionBoundsAggregateBeforePublication(t *testing.T) {
	raw, err := os.ReadFile("testdata/comparison-projections.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []comparisonReference
	if err = json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	var sourceText string
	for _, test := range cases {
		if test.Case == "private-first" {
			sourceText = test.Source
			break
		}
	}
	var input map[string]any
	if err = json.Unmarshal([]byte(sourceText), &input); err != nil {
		t.Fatal(err)
	}
	content := requireType[map[string]any](t, input["content"])
	seed := requireType[map[string]any](t, content["seed"])
	profile := requireType[map[string]any](t, seed["service_materialization"])
	payload := map[string]any{}
	for i := range 8 {
		payload[strconv.Itoa(i)] = strings.Repeat("x", 600000)
	}
	profile["value"] = payload
	encoded, err := json.Marshal(input)
	if err != nil {
		t.Fatal(err)
	}
	source, err := sdl.AuthoredScenario(encoded, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := sdl.ProjectComparison(source, "2"); err == nil {
		t.Fatal("aggregate owner projection exceeded the shared publication budget")
	}
}

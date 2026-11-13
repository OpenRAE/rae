package processor_test

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type referenceResource struct {
	Payload  json.RawMessage `json:"payload"`
	Ordering []string        `json:"ordering_dependencies"`
	Refresh  []string        `json:"refresh_dependencies"`
}
type referenceCompilationCase struct {
	Name        string                       `json:"name"`
	Source      json.RawMessage              `json:"source"`
	Resources   map[string]referenceResource `json:"resources"`
	Diagnostics json.RawMessage              `json:"diagnostics"`
}

func TestCompiledResourcesKeepReferenceRuntimeCases(t *testing.T) {
	assertReferenceCompilationFiles(t, []string{"testdata/compiled-runtime-reference.json"}, 13)
}
func TestCompiledResourcesKeepReferenceParticipantCases(t *testing.T) {
	assertReferenceCompilationFiles(t, []string{
		"testdata/compiled-participant-reference.json", "testdata/compiled-participant-reference-2.json",
		"testdata/compiled-participant-reference-3.json", "testdata/compiled-participant-reference-4.json",
		"testdata/compiled-participant-reference-5.json", "testdata/compiled-participant-reference-6.json",
		"testdata/compiled-participant-reference-7.json",
	}, 39)
}
func referenceParts(t *testing.T, paths []string) [][]byte {
	t.Helper()
	result := make([][]byte, 0, len(paths))
	for _, path := range paths {
		raw, err := os.ReadFile(path) //nolint:gosec // Callers supply fixed repository fixture paths.
		if err != nil {
			t.Fatal(err)
		}
		result = append(result, raw)
	}
	return result
}
func assertReferenceCompilationFiles(t *testing.T, paths []string, want int) {
	t.Helper()
	var cases []referenceCompilationCase
	for _, raw := range referenceParts(t, paths) {
		var part []referenceCompilationCase
		if err := json.Unmarshal(raw, &part); err != nil {
			t.Fatal(err)
		}
		cases = append(cases, part...)
	}
	if len(cases) != want {
		t.Fatalf("compiled reference inventory=%d, want=%d", len(cases), want)
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			scenario, err := sdl.Parse(test.Source, sdl.DefaultParseOptions())
			if err != nil {
				t.Fatal(err)
			}
			compiled, err := processor.Compile(scenario, nil)
			if err != nil {
				t.Fatal(err)
			}
			assertReferenceResources(t, compiled.Model().View(), test.Resources)
			assertReferenceDiagnostics(t, compiled.Diagnostics(), test.Diagnostics)
		})
	}
}
func assertReferenceResources(t *testing.T, view processor.CompiledScenario, want map[string]referenceResource) {
	t.Helper()
	got := map[string]referenceResource{}
	for _, resources := range [][]processor.Resource{view.Resources, view.ParticipantResources} {
		for _, resource := range resources {
			got[resource.Address] = referenceResource{resource.Payload.JSON(), append([]string{}, resource.OrderingDependencies...), append([]string{}, resource.RefreshDependencies...)}
		}
	}
	if len(got) != len(want) {
		t.Fatalf("resource count=%d want=%d", len(got), len(want))
	}
	for address, expected := range want {
		actual, found := got[address]
		if !found {
			t.Error("missing resource", address)
			continue
		}
		assertReferenceJSON(t, address, requireJSON(t, actual), requireJSON(t, expected))
	}
}
func assertReferenceDiagnostics(t *testing.T, got []diagnostic.Diagnostic, want json.RawMessage) {
	t.Helper()
	records := []map[string]any{}
	for _, finding := range got {
		records = append(records, map[string]any{"code": finding.Code, "domain": finding.Domain, "address": finding.Address, "message": finding.Message, "severity": finding.Severity})
	}
	assertReferenceJSON(t, "diagnostics", requireJSON(t, records), want)
}
func assertReferenceJSON(t *testing.T, label string, got, want []byte) {
	t.Helper()
	actual, err := canonjson.JCS(got)
	if err != nil {
		t.Fatal(err)
	}
	expected, err := canonjson.JCS(want)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(actual, expected) {
		t.Errorf("%s mismatch\ngot=%s\nwant=%s", label, actual, expected)
	}
}

func TestCompilerSourceAdmissionRefusesUnboundGraph(t *testing.T) {
	raw, err := os.ReadFile("testdata/compiler-invalid-graph.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name   string `json:"name"`
		Source string `json:"source"`
	}
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			_, err := sdl.Parse([]byte(test.Source), sdl.DefaultParseOptions())
			if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
				t.Fatalf("invalid compiler graph error=%v", err)
			}
		})
	}
}

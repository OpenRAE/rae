package analysis

import (
	"context"
	"encoding/json"
	"io/fs"
	"math"
	"slices"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func requireCategory(t *testing.T, err error, expected fault.Category) {
	t.Helper()
	if category, ok := fault.CategoryOf(err); !ok || category != expected {
		t.Fatalf("got %v, want category %v", err, expected)
	}
}

// satisfiabilityEvidenceValue admits the published v2 evidence fixture.
func satisfiabilityEvidenceValue(t *testing.T) validation.Value {
	t.Helper()
	packaged, err := corpus.Open()
	if err != nil {
		t.Fatal(err)
	}
	raw, err := fs.ReadFile(packaged, "fixtures/satisfiability/scenario-satisfiability-evidence-v2/valid/reconciliation-workflow.json")
	if err != nil {
		t.Fatal(err)
	}
	owner, err := analysisOwner()
	if err != nil {
		t.Fatal(err)
	}
	value, err := owner.Validate("scenario-satisfiability-evidence-v2", raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}, witnessPhaseOwner{ctx: t.Context()})
	if err != nil {
		t.Fatal(err)
	}
	return value
}

func TestAnalyzeRefusesMissingContextUnknownKindsAndCancellation(t *testing.T) {
	var missing context.Context
	_, err := AnalyzeContext(missing, Request{Kind: satisfiabilityKind})
	requireCategory(t, err, fault.InvalidInput)
	cancelled, cancel := context.WithCancel(t.Context())
	cancel()
	_, err = AnalyzeContext(cancelled, Request{Kind: satisfiabilityKind})
	requireCategory(t, err, fault.Operational)
	for _, request := range []Request{{Kind: "unknown"}, {Kind: "semantic-comparison"}} {
		_, err = Analyze(request)
		requireCategory(t, err, fault.InvalidInput)
	}
}

func TestReplayRefusesMissingContextForeignEvidenceAndCancellation(t *testing.T) {
	var missing context.Context
	if _, err := ReplayContext(missing, Request{Kind: satisfiabilityKind}, satisfiabilityEvidenceValue(t)); err == nil {
		t.Fatal("got nil error, want a missing-context refusal")
	}
	if _, err := ReplayContext(t.Context(), Request{Kind: "unknown"}, satisfiabilityEvidenceValue(t)); err == nil {
		t.Fatal("got nil error, want an unknown-kind refusal")
	}
	if _, err := ReplayContext(t.Context(), Request{Kind: exploitKind}, satisfiabilityEvidenceValue(t)); err == nil {
		t.Fatal("got nil error, want a foreign-contract refusal")
	}
	cancelled, cancel := context.WithCancel(t.Context())
	cancel()
	_, err := ReplayContext(cancelled, Request{Kind: satisfiabilityKind}, satisfiabilityEvidenceValue(t))
	requireCategory(t, err, fault.Operational)
}

func TestReplaySourceBindingRequiresTheEvidenceSourceBytes(t *testing.T) {
	if _, err := bindReplaySource(Request{Kind: exploitKind}, nil); err == nil {
		t.Fatal("got nil error, want a missing-input refusal")
	}
	evidence := []byte(`{"source":{"byte_digest":"sha256:0000000000000000000000000000000000000000000000000000000000000000"}}`)
	_, err := bindReplaySource(Request{Kind: exploitKind, Input: &JSONInput{Data: []byte(`{}`)}}, evidence)
	requireCategory(t, err, fault.EvidenceIntegrity)
	if _, err = bindReplaySource(Request{Kind: exploitKind, Input: &JSONInput{Data: []byte(`{}`)}}, []byte(`[`)); err == nil {
		t.Fatal("got nil error, want malformed evidence refused")
	}
	request := Request{Kind: "candidate-synthesis"}
	if got, err := bindReplaySource(request, nil); err != nil || got.Kind != request.Kind {
		t.Fatalf("got %v, %v, want the unchanged request", got, err)
	}
}

func TestCanonicalEncodingRefusesUnrepresentableValues(t *testing.T) {
	if _, err := hash(math.NaN()); err == nil {
		t.Fatal("got nil error, want NaN refused")
	}
	if _, err := decodeShape[map[string]any](math.Inf(1)); err == nil {
		t.Fatal("got nil error, want infinity refused")
	}
	if _, err := admitOutput("scenario-satisfiability-evidence-v2", math.NaN(), nil); err == nil {
		t.Fatal("got nil error, want an unencodable document refused")
	}
	if _, err := admitOutput("scenario-satisfiability-evidence-v2", map[string]any{}, nil); err == nil {
		t.Fatal("got nil error, want an inadmissible document refused")
	}
}

func TestSatisfiabilityRefusesForeignProfilesBeforeReadingSource(t *testing.T) {
	_, err := Analyze(Request{Kind: satisfiabilityKind, Options: map[string]any{"profile": "other"}})
	requireCategory(t, err, fault.Operational)
	_, err = Analyze(Request{Kind: satisfiabilityKind, Options: map[string]any{"profile": satisfiabilityProfile, "extra": true}})
	requireCategory(t, err, fault.Operational)
}

func TestSatisfiabilitySourceReadingStaysBounded(t *testing.T) {
	options := sdl.DefaultParseOptions()
	small := sdl.DefaultParseOptions()
	small.Limits.MaxInputBytes = 4
	files := fstest.MapFS{
		"scenario.yaml": &fstest.MapFile{Data: []byte("name: x\n")},
		"folder/a.yaml": &fstest.MapFile{Data: []byte("name: x\n")},
	}
	for name, input := range map[string]*SourceInput{
		"missing input":       nil,
		"invalid options":     {Options: sdl.ParseOptions{}},
		"root dot":            {Source: sdl.SourceContext{Root: ".", RootBytes: []byte("name: x\n")}, Options: options},
		"two authorities":     {Source: sdl.SourceContext{Root: "a.yaml", FS: files, Sources: map[string][]byte{}}, Options: options},
		"missing source":      {Source: sdl.SourceContext{Root: "a.yaml", Sources: map[string][]byte{}}, Options: options},
		"oversized bytes":     {Source: sdl.SourceContext{Root: "a.yaml", RootBytes: []byte("name: x\n")}, Options: small},
		"missing file":        {Source: sdl.SourceContext{Root: "absent.yaml", FS: files}, Options: options},
		"directory":           {Source: sdl.SourceContext{Root: "folder", FS: files}, Options: options},
		"file over the limit": {Source: sdl.SourceContext{Root: "scenario.yaml", FS: files}, Options: small},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := readAnalysisSource(input); err == nil {
				t.Fatal("got nil error, want the source refused")
			}
		})
	}
	source, err := readAnalysisSource(&SourceInput{Source: sdl.SourceContext{Root: "a.yaml", Sources: map[string][]byte{"a.yaml": []byte("name: x\n")}}, Options: options})
	if err != nil || string(source.RootBytes) != "name: x\n" {
		t.Fatalf("got %q, %v, want the supplied root source", source.RootBytes, err)
	}
	source, err = readAnalysisSource(&SourceInput{Source: sdl.SourceContext{Root: "scenario.yaml", FS: files}, Options: options})
	if err != nil || string(source.RootBytes) != "name: x\n" {
		t.Fatalf("got %q, %v, want the file source", source.RootBytes, err)
	}
	_, err = Analyze(Request{Kind: satisfiabilityKind, Source: &SourceInput{Source: sdl.SourceContext{Root: "bad.yaml", RootBytes: []byte("name: [\n")}, Options: options}})
	if err == nil {
		t.Fatal("got nil error, want malformed SDL refused")
	}
}

func TestAttackPointersFollowPythonIndexing(t *testing.T) {
	document := map[string]any{"items": []any{map[string]any{"name": "first"}, "second"}}
	for _, tc := range []struct {
		pointer  string
		expected bool
	}{
		{"/items/0/name", true},
		{"/items/-1", true},
		// Python int() strips surrounding whitespace from an index token.
		{"/items/ 1 ", true},
		{"/items/-3", false},
		{"/items/2", false},
		{"/items/x", false},
		{"/items/1/name", false},
		{"/missing", false},
	} {
		if got := attackPointerResolves(document, tc.pointer); got != tc.expected {
			t.Fatalf("pointer %q: got %v, want %v", tc.pointer, got, tc.expected)
		}
	}
}

func TestAttackPreflightReportsEveryUnsupportedGraphFeature(t *testing.T) {
	var graph attackGraph
	raw := []byte(`{
		"state_facts": [{"fact_id": "start"}, {"fact_id": "goal"}],
		"transitions": [{"transition_id": "move", "semantics": "other/v1", "prerequisites": [], "effects": [], "observations": []}],
		"bindings": [
			{"binding_id": "a", "target_kind": "state-fact", "target_id": "start", "raes_address": "/nodes/host"},
			{"binding_id": "b", "target_kind": "state-fact", "target_id": "start", "raes_address": "/nodes/host"},
			{"binding_id": "c", "target_kind": "state-fact", "target_id": "absent", "raes_address": "/nodes/missing"}
		]
	}`)
	if err := json.Unmarshal(raw, &graph); err != nil {
		t.Fatal(err)
	}
	input := attackInput{
		graph:    graph,
		query:    attackQuery{Start: []string{"start"}, Goal: []string{"elsewhere"}, Semantics: []string{"other/v1"}},
		snapshot: map[string]any{"nodes": map[string]any{"host": map[string]any{}}},
	}
	codes := []string{}
	for _, finding := range attackPreflight(input) {
		codes = append(codes, finding.code)
	}
	for _, expected := range []string{"binding-target-dangling", "binding-missing", "binding-ambiguous", "unsupported-semantics", "query-dangling-fact"} {
		if !slices.Contains(codes, expected) {
			t.Fatalf("got %v, want %s reported", codes, expected)
		}
	}
}

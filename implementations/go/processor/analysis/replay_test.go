package analysis

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestReplayRecomputesOpacityAndSynthesis(t *testing.T) {
	for _, tc := range []struct{ kind, contract, path string }{
		{"participant-opacity", "participant-opacity-analysis-evidence-v1", "formal-analysis/participant-opacity-analysis-input-v1/valid/opaque-pair.json"},
		{"candidate-synthesis", "sdl-candidate-synthesis-record-v1", "candidate-synthesis/sdl-candidate-synthesis-input-v1/valid/nist-csf.json"},
	} {
		t.Run(tc.kind, func(t *testing.T) {
			checkReplayInput(t, tc.kind, tc.contract, tc.path)
		})
	}
}

func checkReplayInput(t *testing.T, kind, contract, path string) {
	t.Helper()
	raw := readTestFile(t, "../../../../contracts/fixtures/"+path)
	request := Request{Kind: kind, Input: &JSONInput{Data: raw}}
	result, err := Analyze(request)
	if err != nil {
		t.Fatal(err)
	}
	encoded := testJSON(t, result.Document)
	evidence := testAdmission(t, contract, encoded, nil)
	if _, err = ReplayContext(t.Context(), request, evidence); err != nil {
		t.Fatal(err)
	}
	cancelled, cancel := context.WithCancel(t.Context())
	cancel()
	if _, err = ReplayContext(cancelled, request, evidence); err == nil {
		t.Fatal("cancelled replay succeeded")
	}
	input := testObject(t, raw)
	if kind == "participant-opacity" {
		input["complete_enumeration"] = false
	} else {
		input["decisions"] = []any{}
	}
	request.Input.Data = testJSON(t, input)
	if _, err = ReplayContext(t.Context(), request, evidence); err == nil {
		t.Fatal("changed input replay succeeded")
	}
}

func TestReplayChecksOriginalSourceBeforeAnalysis(t *testing.T) {
	path := "../../../../contracts/fixtures/exploit-path-analysis/exploit-path-analysis-evidence-v1/valid/valid-path.json"
	evidence := testAdmission(t, "exploit-path-analysis-evidence-v1", readTestFile(t, path), nil)
	_, err := ReplayContext(t.Context(), Request{Kind: "exploit-path", Input: &JSONInput{SourceID: "changed.json", Data: []byte("not JSON")}}, evidence)
	if category, ok := fault.CategoryOf(err); !ok || category != fault.EvidenceIntegrity {
		t.Fatalf("changed source reached analysis: %v", err)
	}
}

func TestReplayEverySolverAndExploitOutcomeRejectsTampering(t *testing.T) {
	for _, kind := range []string{"satisfiability", "exploit-path"} {
		t.Run(kind, func(t *testing.T) {
			if kind == "satisfiability" && os.Getenv("RAES_TEST_Z3") == "" {
				t.Skip("explicit admitted executable required")
			}
			checkReplayOutcomeReferences(t, kind)
		})
	}
}

func checkReplayTampering(t *testing.T, row analysisReference) {
	t.Helper()
	request, err := row.request()
	if err != nil {
		t.Fatal(err)
	}
	result, err := AnalyzeContext(t.Context(), request)
	if err != nil {
		t.Fatal(err)
	}
	contract := "exploit-path-analysis-evidence-v1"
	var authority any
	if row.Kind == "satisfiability" {
		contract = "scenario-satisfiability-evidence-v2"
		authority = witnessPhaseOwner{ctx: t.Context()}
	}
	encoded := testJSON(t, result.Document)
	valid := testAdmission(t, contract, encoded, authority)
	if _, err = ReplayContext(t.Context(), request, valid); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(map[string]any){
		"unknown field":   func(value map[string]any) { value["unpublished"] = true },
		"source identity": func(value map[string]any) { object(value["source"])["source_id"] = "other.json" },
		"model digest": func(value map[string]any) {
			field := "normalized_model_digest"
			if row.Kind == "exploit-path" {
				field = "normalized_graph_digest"
			}
			value[field] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
		},
		"query or solver": func(value map[string]any) {
			field := "solver_configuration_digest"
			if row.Kind == "exploit-path" {
				field = "query_digest"
			}
			value[field] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
		},
		"cross outcome": func(value map[string]any) { value["outcome"] = "unsupported"; value["unsupported"] = nil },
	} {
		t.Run(name, func(t *testing.T) {
			value := testObject(t, encoded)
			mutate(value)
			checkTamperedReplay(t, request, contract, testJSON(t, value), authority)
		})
	}
}

func checkReplayOutcomeReferences(t *testing.T, kind string) {
	t.Helper()
	var fixture struct {
		Cases []analysisReference `json:"cases"`
	}
	decoder := json.NewDecoder(bytes.NewReader(testGzip(t, readTestFile(t, "testdata/"+kind+".json.gz"))))
	decoder.UseNumber()
	if err := decoder.Decode(&fixture); err != nil {
		t.Fatal(err)
	}
	seen := map[string]bool{}
	for _, row := range fixture.Cases {
		outcome := text(row.Expected["outcome"])
		if row.ErrorType != "" || outcome == "" || seen[outcome] {
			continue
		}
		seen[outcome] = true
		t.Run(outcome, func(t *testing.T) { checkReplayTampering(t, row) })
	}
	if len(seen) < 3 {
		t.Fatalf("missing outcome coverage: %v", seen)
	}
}

func checkTamperedReplay(t *testing.T, request Request, contract string, raw []byte, authority any) {
	t.Helper()
	owner, ownerErr := analysisOwner()
	if ownerErr != nil {
		t.Fatal(ownerErr)
	}
	changed, refusal := owner.Validate(contract, raw, ingress.Limits{MaxBytes: 16 << 20, MaxDepth: 128}, authority)
	if refusal != nil {
		return
	}
	_, refusal = ReplayContext(t.Context(), request, changed)
	if category, ok := fault.CategoryOf(refusal); !ok || category != fault.EvidenceIntegrity {
		t.Fatalf("tampered evidence escaped: %v", refusal)
	}
}

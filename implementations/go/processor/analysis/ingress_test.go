package analysis

import (
	"bytes"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func TestAnalysisJSONIngressBoundsPrivacyAndRecovery(t *testing.T) {
	for _, kind := range []string{"participant-opacity", "participant-opacity-model-check", "candidate-synthesis", "exploit-path"} {
		t.Run(kind, func(t *testing.T) {
			for name, raw := range map[string][]byte{
				"duplicate": []byte(`{"private-sentinel":1,"private-sentinel":2}`),
				"unknown":   []byte(`{"private-sentinel":true}`),
				"depth":     []byte(`{"private-sentinel":` + strings.Repeat("[", 129) + "0" + strings.Repeat("]", 129) + "}"),
				"bytes":     bytes.Repeat([]byte(" "), (16<<20)+1),
			} {
				t.Run(name, func(t *testing.T) {
					checkMalformedAnalysisInput(t, kind, raw)
				})
			}
		})
	}
	// A refused request cannot poison the immutable shared admission owner.
	raw := readTestFile(t, "../../../../contracts/fixtures/formal-analysis/participant-opacity-analysis-input-v1/valid/opaque-pair.json")
	if _, err := Analyze(Request{Kind: "participant-opacity", Input: &JSONInput{Data: raw}}); err != nil {
		t.Fatal(err)
	}
}

func checkMalformedAnalysisInput(t *testing.T, kind string, raw []byte) {
	t.Helper()
	result, err := Analyze(Request{Kind: kind, Input: &JSONInput{Data: raw}})
	expected := fault.InvalidInput
	if kind == "exploit-path" {
		expected = fault.Operational
	}
	if category, ok := fault.CategoryOf(err); !ok || category != expected {
		t.Fatalf("malformed input did not fail at ingress: %v", err)
	}
	if strings.Contains(err.Error(), "private-sentinel") || result.Document != nil || result.Candidate != nil {
		t.Fatal("refusal exposed untrusted content or partial evidence")
	}
}

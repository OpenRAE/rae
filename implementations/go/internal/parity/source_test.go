package parity

import (
	"encoding/json"
	"os"
	"slices"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// TestSourceCorpusBoundary checks only source-owned behavior in the unchanged
// command goldens. Model admission and command envelopes retain their port owners.
// The source package's reference vectors also check exact values and ranges.
func TestSourceCorpusBoundary(t *testing.T) {
	cases, err := Load(os.DirFS("testdata"))
	if err != nil {
		t.Fatal(err)
	}
	for _, c := range cases {
		if c.Key() != "cli semantic parse" {
			continue
		}
		t.Run(c.Name, func(t *testing.T) { checkSourceBoundary(t, c) })
	}
}
func checkSourceBoundary(t *testing.T, c Case) {
	t.Helper()
	var expected struct {
		Exit   int `json:"exit_code"`
		Output *struct {
			Contract    string `json:"contract_id"`
			Migration   string `json:"migration_policy"`
			Diagnostics []struct {
				Code     string `json:"code"`
				Severity string `json:"severity"`
			} `json:"diagnostics"`
		} `json:"stdout"`
	}
	if err := json.Unmarshal(c.Result, &expected); err != nil {
		t.Fatal(err)
	}
	if expected.Output == nil || expected.Output.Contract != "sdl-yaml/v1" {
		t.Skip("the recorded case does not expose an SDL source result")
	}
	var want []string
	for _, d := range expected.Output.Diagnostics {
		if strings.HasPrefix(d.Code, "sdl.") && d.Code != "sdl.model.invalid" {
			want = append(want, d.Code+":"+d.Severity)
		}
	}
	if expected.Exit != 0 && len(want) == 0 {
		t.Skip("the refusal belongs to model admission or a later operation")
	}
	options := source.DefaultOptions()
	options.RequireMapping = true
	if expected.Output.Migration != "" {
		options.MigrationPolicy = expected.Output.Migration
	}
	data, ok := c.Files["input.yaml"]
	if !ok {
		t.Fatal("source case has no input.yaml")
	}
	document, err := source.Decode(data, options)
	diagnostics := source.Diagnostics(err)
	if err == nil {
		diagnostics = document.Diagnostics()
	}
	if len(want) == 0 && err != nil {
		t.Fatalf("Decode() refused a recorded positive source: %v, diagnostics %+v", err, diagnostics)
	}
	checkSourceDiagnostics(t, want, diagnostics)
}
func checkSourceDiagnostics(t *testing.T, want []string, diagnostics []source.Diagnostic) {
	t.Helper()
	var got []string
	for _, d := range diagnostics {
		got = append(got, d.Code+":"+d.Severity)
	}
	slices.Sort(want)
	slices.Sort(got)
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("source diagnostics mismatch (-want +got):\n%s", diff)
	}
}

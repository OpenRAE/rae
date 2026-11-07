package parity

import (
	"encoding/json"
	"errors"
	"slices"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/authoring"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// TestSourceCorpusBoundary checks only source-owned behavior in the unchanged
// command goldens. Model admission and command envelopes retain their port owners.
// The source package's reference vectors also check exact values and ranges.
func TestSourceCorpusBoundary(t *testing.T) {
	cases, err := loadTestCases()
	if err != nil {
		t.Fatal(err)
	}
	parser, err := authoring.New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, c := range cases {
		if c.Key() != "cli semantic parse" {
			continue
		}
		t.Run(c.Name, func(t *testing.T) { checkSourceBoundary(t, parser, c) })
	}
}
func checkSourceBoundary(t *testing.T, parser *authoring.Parser, c Case) {
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
	name, data := sourceBoundaryInput(t, c)
	document, err := source.Decode(data, options)
	diagnostics := source.Diagnostics(err)
	if err == nil {
		diagnostics = document.Diagnostics()
	}
	if len(want) == 0 && err != nil {
		t.Fatalf("Decode() refused a recorded positive source: %v, diagnostics %+v", err, diagnostics)
	}
	if err == nil && slices.Equal(want, []string{"sdl.parse:error"}) && missingSourceImport(parser, c, name) {
		return
	}
	checkSourceDiagnostics(t, want, diagnostics)
}

func sourceBoundaryInput(t *testing.T, c Case) (string, []byte) {
	t.Helper()
	var name string
	for _, arg := range c.Args {
		if _, present := c.Files[arg]; present {
			if name != "" {
				t.Fatal("source case has ambiguous input arguments")
			}
			name = arg
		}
	}
	if name == "" {
		t.Fatal("source case has no input file argument")
	}
	return name, c.Files[name]
}

func missingSourceImport(parser *authoring.Parser, c Case, name string) bool {
	files := fstest.MapFS{}
	for path, content := range c.Files {
		files[path] = &fstest.MapFile{Data: content}
	}
	_, err := parser.Decode(authoring.Request{Source: c.Files[name], Name: name, FS: files})
	classified, ok := errors.AsType[interface {
		error
		Code() string
	}](err)
	return ok && classified.Code() == "sdl.import.source-missing"
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

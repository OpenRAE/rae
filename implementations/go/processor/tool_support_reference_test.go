package processor_test

import (
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type toolSupportDiagnostic struct {
	Code     string `json:"code"`
	Domain   string `json:"domain"`
	Address  string `json:"address"`
	Message  string `json:"message"`
	Severity string `json:"severity"`
}
type toolSupportReference struct {
	Sources    map[string]toolSupportSource           `json:"sources"`
	Backends   map[string]binding.BackendManifestV2   `json:"backends"`
	Processors map[string]binding.ProcessorManifestV2 `json:"processors"`
	Cases      []struct {
		Name        string                  `json:"name"`
		Source      string                  `json:"source"`
		Backend     string                  `json:"backend"`
		Processor   string                  `json:"processor"`
		Diagnostics []toolSupportDiagnostic `json:"diagnostics"`
	} `json:"cases"`
	InvalidInputs []struct {
		Name     string                    `json:"name"`
		Manifest binding.BackendManifestV2 `json:"manifest"`
	} `json:"invalid_inputs"`
}
type toolSupportSource struct {
	Path string `json:"path"`
	Text string `json:"text"`
}

func toolSupportVectors(t *testing.T) toolSupportReference {
	t.Helper()
	raw, err := os.ReadFile("testdata/tool-support-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var result toolSupportReference
	if err := json.Unmarshal(raw, &result); err != nil {
		t.Fatal(err)
	}
	return result
}

//nolint:ireturn // The public compiler supplies the exact native model under test.
func toolSupportModel(t *testing.T, input toolSupportSource) processor.RuntimeModel {
	t.Helper()
	var scenario sdl.Scenario
	var err error
	if input.Path != "" {
		scenario, err = sdl.ParseFile(os.DirFS("../../.."), input.Path, sdl.DefaultParseOptions())
	} else {
		scenario, err = sdl.Parse([]byte(input.Text), sdl.DefaultParseOptions())
	}
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	return compiled.Model()
}
func toolSupportDiagnostics(input []diagnostic.Diagnostic) []toolSupportDiagnostic {
	result := make([]toolSupportDiagnostic, len(input))
	for index, entry := range input {
		result[index] = toolSupportDiagnostic{Code: entry.Code, Domain: entry.Domain, Address: entry.Address, Message: entry.Message, Severity: entry.Severity}
	}
	return result
}

func TestParticipantToolSupportMatchesPureReference(t *testing.T) {
	vectors := toolSupportVectors(t)
	models := map[string]processor.RuntimeModel{}
	for name, raw := range vectors.Sources {
		t.Run("source-"+name, func(t *testing.T) { models[name] = toolSupportModel(t, raw) })
	}
	for _, test := range vectors.Cases {
		t.Run(test.Name, func(t *testing.T) {
			var selected *binding.ProcessorManifestV2
			if test.Processor != "" {
				entry := vectors.Processors[test.Processor]
				selected = &entry
			}
			result, err := processor.ParticipantSupport(models[test.Source], vectors.Backends[test.Backend], selected)
			if err != nil {
				t.Fatal(err)
			}
			if diff := cmp.Diff(test.Diagnostics, toolSupportDiagnostics(result.Tools)); diff != "" {
				t.Fatalf("tool diagnostics differ (-reference +native):\n%s", diff)
			}
		})
	}
}

func TestParticipantToolSupportRefusesCorruptedClaimsWithoutEcho(t *testing.T) {
	vectors := toolSupportVectors(t)
	model := toolSupportModel(t, vectors.Sources["toolkit"])
	for _, test := range vectors.InvalidInputs {
		t.Run(test.Name, func(t *testing.T) {
			result, err := processor.ParticipantSupport(model, test.Manifest, nil)
			if err == nil {
				t.Fatal("corrupted nested capability accepted")
			}
			if len(result.Tools)+len(result.Execution)+len(result.MixedControl) != 0 {
				t.Fatal("refused input returned a partial support result")
			}
			toolSupportErrorIsValueFree(t, err)
		})
	}
}

func toolSupportErrorIsValueFree(t *testing.T, err error) {
	t.Helper()
	for current := err; current != nil; current = errors.Unwrap(current) {
		if strings.Contains(current.Error(), "private.token.canary") {
			t.Fatal("private nested capability appeared in the error")
		}
	}
	if detailed, ok := errors.AsType[diagnostic.Error](err); ok {
		if strings.Contains(string(requireJSON(t, toolSupportDiagnostics(detailed.Diagnostics()))), "private.token.canary") {
			t.Fatal("private nested capability appeared in a diagnostic")
		}
	}
}

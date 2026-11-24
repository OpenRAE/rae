package admission

import (
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func TestExperimentYAMLMatchesExamplesAndReferenceRefusals(t *testing.T) {
	t.Parallel()
	raw, err := os.ReadFile("testdata/experiment-yaml-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var recording struct {
		Cases []experimentYAMLReferenceCase `json:"cases"`
	}
	if json.Unmarshal(raw, &recording) != nil {
		t.Fatal("invalid reference fixture")
	}
	if len(recording.Cases) != 25 {
		t.Fatal("case count =", len(recording.Cases), "want 25")
	}
	for _, c := range recording.Cases {
		t.Run(c.Name, func(t *testing.T) { checkExperimentYAMLReference(t, c) })
	}
}

func TestExperimentLoadingContainsFilesAndSortsDiscovery(t *testing.T) {
	t.Parallel()
	raw, err := os.ReadFile("../../../../examples/experiments/techvault-smoke-run.exp.yaml")
	if err != nil {
		t.Fatal(err)
	}
	source := fstest.MapFS{"examples/z.exp.yaml": {Data: raw}, "examples/a.exp.yaml": {Data: raw}, "examples/nested/b.exp.yaml": {Data: raw}, "examples/other.yaml": {Data: raw}}
	paths, err := DiscoverExperiments(source, "examples")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Join(paths, ",") != "examples/a.exp.yaml,examples/z.exp.yaml" {
		t.Fatal("discovery =", paths)
	}
	if _, err := LoadExperiment(source, "examples/a.exp.yaml", nil); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadExperiment(source, "../private.exp.yaml", nil); err == nil {
		t.Fatal("uncontained path admitted")
	}
	if _, err := LoadExperiment(source, "missing.exp.yaml", nil); err == nil {
		t.Fatal("missing file admitted")
	}
	if paths, err := DiscoverExperiments(source, "missing"); err != nil || len(paths) != 0 {
		t.Fatal("missing directory =", paths, err)
	}
}

func TestExperimentYAMLBinaryUsesNativeTextCoercion(t *testing.T) {
	var reference struct {
		Cases []struct {
			Name   string          `json:"name"`
			Text   string          `json:"text"`
			Result json.RawMessage `json:"result"`
			Code   *string         `json:"code"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/experiment-yaml-binary-reference.json", &reference)
	for _, item := range reference.Cases {
		t.Run(item.Name, func(t *testing.T) {
			got, err := ParseExperiment([]byte(item.Text), nil)
			if item.Code != nil {
				classified, ok := errors.AsType[*fault.Error](err)
				if !ok || classified.Code() != *item.Code {
					t.Fatal(err, item.Code)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			want, _ := canonjson.JCS(item.Result)
			actual, _ := canonjson.JCS(got.JSON())
			if string(want) != string(actual) {
				t.Fatal("coerced document differs")
			}
		})
	}
}

type experimentYAMLReferenceCase struct {
	Name   string          `json:"name"`
	Text   string          `json:"text"`
	Result json.RawMessage `json:"result"`
	Code   *string         `json:"code"`
}

func checkExperimentYAMLReference(t *testing.T, c experimentYAMLReferenceCase) {
	t.Helper()

	got, err := ParseExperiment([]byte(c.Text), nil)
	if c.Code != nil {
		f, ok := errors.AsType[*fault.Error](err)
		if !ok || f.Code() != *c.Code {
			t.Fatalf("refusal = %v, want %s", err, *c.Code)
		}
		if strings.Contains(err.Error(), "2026-02-30") {
			t.Fatal("parser source leaked")
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	actual, err := canonjson.JCS(got.JSON())
	if err != nil {
		t.Fatal(err)
	}
	expected, err := canonjson.JCS(c.Result)
	if err != nil {
		t.Fatal(err)
	}
	if string(actual) != string(expected) {
		t.Fatalf("experiment = %s, want %s", actual, expected)
	}
}

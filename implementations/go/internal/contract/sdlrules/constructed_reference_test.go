package sdlrules_test

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"io"
	"os"
	"slices"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/sdlrules"
)

type sharedReferenceVector struct {
	Name     string          `json:"name"`
	Data     json.RawMessage `json:"data"`
	Findings []struct {
		Message string   `json:"message"`
		Owner   []string `json:"owner"`
	} `json:"findings"`
}

func TestSharedReferenceRulesOnConstructedDocuments(t *testing.T) {
	for _, row := range sharedReferenceVectors(t) {
		t.Run(row.Name, func(t *testing.T) { checkConstructedSharedRules(t, row) })
	}
}

func sharedReferenceVectors(t *testing.T) []sharedReferenceVector {
	t.Helper()
	raw, err := os.ReadFile("testdata/constructed-reference.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	reader, err := gzip.NewReader(bytes.NewReader(raw))
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = reader.Close() }()
	raw, err = io.ReadAll(reader)
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []sharedReferenceVector `json:"cases"`
	}
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	if len(fixture.Cases) == 0 {
		t.Fatal("missing independent constructed reference cases")
	}
	return fixture.Cases
}

func checkConstructedSharedRules(t *testing.T, row sharedReferenceVector) {
	t.Helper()
	for _, check := range []func([]byte, map[string][]string) ([]sdlrules.Finding, error){sdlrules.TemporalBindings, sdlrules.StatefulReferences, sdlrules.ServiceMaterialization} {
		findings, err := check(row.Data, nil)
		if err != nil {
			t.Fatal(err)
		}
		for _, finding := range findings {
			checkSharedReferenceFinding(t, finding, row)
		}
	}
}

func checkSharedReferenceFinding(t *testing.T, finding sdlrules.Finding, row sharedReferenceVector) {
	t.Helper()
	for _, expected := range row.Findings {
		if expected.Message == finding.Message && slices.Equal(expected.Owner, []string{finding.Owner.Section, finding.Owner.Name}) {
			return
		}
	}
	t.Fatalf("shared predicate differs from the Python reference: %+v", finding)
}

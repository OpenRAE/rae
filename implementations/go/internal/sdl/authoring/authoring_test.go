package authoring

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type formatterVector struct {
	Limits      json.RawMessage `json:"limits"`
	Name        string          `json:"name"`
	Source      string          `json:"source"`
	Content     string          `json:"content"`
	Accepted    bool            `json:"accepted"`
	Diagnostics []string        `json:"diagnostics"`
}

func TestFormatterReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var vectors struct {
		Cases []formatterVector `json:"cases"`
	}
	if err = json.Unmarshal(raw, &vectors); err != nil {
		t.Fatal(err)
	}
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, v := range vectors.Cases {
		t.Run(v.Name, func(t *testing.T) { checkFormatterVector(t, parser, v) })
	}
}
func checkFormatterVector(t *testing.T, parser *Parser, v formatterVector) {
	t.Helper()
	if len(v.Limits) > 0 {
		limits := source.DefaultLimits()
		if err := json.Unmarshal(v.Limits, &limits); err != nil {
			t.Fatal(err)
		}
		configured, err := New(limits)
		if err != nil {
			t.Fatal(err)
		}
		parser = configured
	}
	result, err := parser.Format(Request{Source: []byte(v.Source)})
	if (err == nil) != v.Accepted {
		t.Fatalf("accepted=%v, want %v: %v", err == nil, v.Accepted, err)
	}
	if err != nil {
		return
	}
	if diff := cmp.Diff(v.Content, string(result.Content)); diff != "" {
		t.Errorf("content (-want +got):\n%s", diff)
	}
	codes := make([]string, 0, len(result.Diagnostics))
	for _, d := range result.Diagnostics {
		codes = append(codes, d.Code)
	}
	if diff := cmp.Diff(v.Diagnostics, codes); diff != "" {
		t.Errorf("diagnostics (-want +got):\n%s", diff)
	}
}

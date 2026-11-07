package authoring

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestFormatterReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var vectors struct {
		Cases []struct {
			Name, Source, Content string
			Accepted              bool
			Diagnostics           []string
		}
	}
	if err = json.Unmarshal(raw, &vectors); err != nil {
		t.Fatal(err)
	}
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, v := range vectors.Cases {
		t.Run(v.Name, func(t *testing.T) {
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
		})
	}
}

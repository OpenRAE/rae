package authoring

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestMaterializedFormatterKeepsSourceWorkCeiling(t *testing.T) {
	// Independently recorded from the unchanged Python formatter at the pinned
	// reference revision: 20,000 minimal nodes remain inside source limits.
	raw, err := os.ReadFile("testdata/imports.json")
	if err != nil {
		t.Fatal(err)
	}
	var rows []importVector
	if err = json.Unmarshal(raw, &rows); err != nil {
		t.Fatal(err)
	}
	var value map[string]any
	for _, row := range rows {
		if row.Name == "supplied-materialized-root" {
			if err = json.Unmarshal([]byte(row.Files["main.yaml"]), &value); err != nil {
				t.Fatal(err)
			}
		}
	}
	if value == nil {
		t.Fatal("materialized fixture missing")
	}
	nodes := map[string]any{}
	for i := range 20000 {
		nodes[fmt.Sprintf("n%05d", i)] = map[string]any{"type": "compute"}
	}
	value["nodes"] = nodes
	raw, err = json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	result, err := parser.Format(Request{Source: raw})
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Content) != 561109 || fmt.Sprintf("%x", sha256.Sum256(result.Content)) != "df048def02b446530e9202ede0004f4a58d03bdac6ed2603ae092b487cf29301" {
		t.Fatal("large materialized output differs from reference bytes")
	}
}

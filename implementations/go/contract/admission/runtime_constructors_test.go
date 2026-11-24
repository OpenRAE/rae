package admission

import (
	"encoding/json"
	"fmt"
	"testing"
)

func TestRuntimeConstructorReference(t *testing.T) {
	var manifest struct {
		CaseCount int                        `json:"case_count"`
		Models    map[string]string          `json:"models"`
		Baselines map[string]json.RawMessage `json:"baselines"`
		CaseFiles []string                   `json:"case_files"`
	}
	readFullReferenceJSON(t, "testdata/runtime-constructors.json", &manifest)
	if len(manifest.Models) != 180 || len(manifest.CaseFiles) == 0 {
		t.Fatal("incomplete runtime constructor inventory")
	}
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	count := 0
	covered := map[string]bool{}
	for i, file := range manifest.CaseFiles {
		if file != fmt.Sprintf("runtime-constructors-%03d.json", i) {
			t.Fatal("unsafe constructor shard path")
		}
		var shard struct {
			Cases []sdlConstructorVector `json:"cases"`
		}
		readFullReferenceJSON(t, "testdata/"+file, &shard)
		for _, c := range shard.Cases {
			c = runtimeConstructorInput(c, manifest.Baselines)
			count++
			if c.Accepted {
				covered[c.Pointer] = true
			}
			t.Run(c.Name, func(t *testing.T) { checkSDLConstructorVector(t, owner, c) })
		}
	}
	if count != manifest.CaseCount || len(covered) != len(manifest.Models) {
		t.Fatal("incomplete runtime constructor cases")
	}
}

func runtimeConstructorInput(c sdlConstructorVector, baselines map[string]json.RawMessage) sdlConstructorVector {
	if len(c.Data) == 0 {
		c.Data = baselines[c.Pointer]
	}
	return c
}

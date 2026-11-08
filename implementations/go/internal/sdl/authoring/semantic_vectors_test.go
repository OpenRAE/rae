package authoring

import (
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func readSemanticVectors(t *testing.T) []semanticVector {
	t.Helper()
	raw, err := os.ReadFile("testdata/semantics.json")
	if err != nil {
		t.Fatal(err)
	}
	var manifest struct {
		Schema string `json:"schema"`
		Count  int    `json:"case_count"`
		Shards []struct {
			Name   string `json:"name"`
			Count  int    `json:"case_count"`
			SHA256 string `json:"sha256"`
		} `json:"shards"`
	}
	if json.Unmarshal(raw, &manifest) != nil || manifest.Schema != "raes-sdl-semantic-vectors/v1" || manifest.Count == 0 || len(manifest.Shards) == 0 {
		t.Fatal("invalid semantic vector manifest")
	}
	var result []semanticVector
	seen := map[string]bool{}
	for index, shard := range manifest.Shards {
		if shard.Name != fmt.Sprintf("semantics-%03d.json", index) {
			t.Fatal("unexpected semantic shard name")
		}
		rows := readSemanticShard(t, shard.Name, shard.SHA256, shard.Count)
		for _, row := range rows {
			if row.Name == "" || seen[row.Name] {
				t.Fatal("missing or duplicate semantic case name")
			}
			seen[row.Name] = true
		}
		result = append(result, rows...)
	}
	if len(result) != manifest.Count {
		t.Fatal("incomplete semantic vector inventory")
	}
	return result
}

func readSemanticShard(t *testing.T, name, sha256 string, count int) []semanticVector {
	t.Helper()
	data, err := fs.ReadFile(os.DirFS("testdata"), name)
	if err != nil || len(data) > 450*1024 || digest.SHA256(data) != "sha256:"+sha256 {
		t.Fatal("semantic shard changed or exceeds its ceiling", name, err)
	}
	var rows []semanticVector
	if json.Unmarshal(data, &rows) != nil || len(rows) != count {
		t.Fatal("invalid semantic shard count", name)
	}
	return rows
}

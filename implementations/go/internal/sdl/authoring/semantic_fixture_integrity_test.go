package authoring

import (
	"bytes"
	"encoding/json"
	"io/fs"
	"os"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

const fixtureRow = `{"name":"example","source":"name: example\n","accepted":true,"findings":[],"locations":[],"advisories":[],"canonical":"{}","digest":"sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"}`

func semanticFixtureFS(t *testing.T, shard string) fstest.MapFS {
	t.Helper()
	count := 1
	var rows []json.RawMessage
	if json.Unmarshal([]byte(shard), &rows) == nil {
		count = len(rows)
	}
	manifest := semanticManifest{Schema: "raes-sdl-semantic-vectors/v1", Count: count,
		Shards: []semanticShard{{Name: "semantics-000.json", Count: count, SHA256: strings.TrimPrefix(digest.SHA256([]byte(shard)), "sha256:")}}}
	raw, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	return fstest.MapFS{"semantics.json": {Data: raw}, "semantics-000.json": {Data: []byte(shard)}}
}

func TestSemanticFixtureInventoryCanGrow(t *testing.T) {
	data := "[" + fixtureRow + "," + strings.Replace(fixtureRow, `"name":"example"`, `"name":"second"`, 1) + "]"
	if rows, err := loadSemanticVectors(semanticFixtureFS(t, data)); err != nil || len(rows) != 2 {
		t.Fatalf("loadSemanticVectors(added case) = %v, %v", rows, err)
	}
}

func TestSemanticFixtureIntegrity(t *testing.T) {
	valid := "[" + fixtureRow + "]"
	if rows, err := loadSemanticVectors(semanticFixtureFS(t, valid)); err != nil || len(rows) != 1 || rows[0].Name != "example" {
		t.Fatalf("loadSemanticVectors(valid) = %v, %v", rows, err)
	}
	for _, test := range []struct {
		name string
		edit func(fstest.MapFS)
	}{
		{"missing-manifest", func(source fstest.MapFS) { delete(source, "semantics.json") }},
		{"missing-shard", func(source fstest.MapFS) { delete(source, "semantics-000.json") }},
		{"changed-bytes", func(source fstest.MapFS) {
			source["semantics-000.json"].Data = append(source["semantics-000.json"].Data, ' ')
		}},
		{"extra-shard", func(source fstest.MapFS) { source["semantics-001.json"] = &fstest.MapFile{Data: []byte(valid)} }},
		{"symlink", func(source fstest.MapFS) { source["semantics-000.json"].Mode = fs.ModeSymlink }},
		{"wrong-count", func(source fstest.MapFS) {
			source["semantics.json"].Data = bytes.ReplaceAll(source["semantics.json"].Data, []byte(`"case_count":1`), []byte(`"case_count":2`))
		}},
		{"unsafe-name", func(source fstest.MapFS) {
			source["semantics.json"].Data = bytes.ReplaceAll(source["semantics.json"].Data, []byte("semantics-000.json"), []byte("../semantics-000.json"))
		}},
		{"wrong-version", func(source fstest.MapFS) {
			source["semantics.json"].Data = bytes.ReplaceAll(source["semantics.json"].Data, []byte("vectors/v1"), []byte("vectors/v2"))
		}},
		{"unknown-manifest-field", func(source fstest.MapFS) {
			source["semantics.json"].Data = append([]byte(`{"ignored":true,`), source["semantics.json"].Data[1:]...)
		}},
		{"duplicate-manifest-field", func(source fstest.MapFS) {
			source["semantics.json"].Data = append([]byte(`{"case_count":1,`), source["semantics.json"].Data[1:]...)
		}},
		{"oversized-manifest", func(source fstest.MapFS) { source["semantics.json"].Data = bytes.Repeat([]byte(" "), 450*1024+1) }},
	} {
		t.Run(test.name, func(t *testing.T) {
			source := semanticFixtureFS(t, valid)
			test.edit(source)
			if _, err := loadSemanticVectors(source); err == nil {
				t.Fatal("corrupt semantic fixture accepted")
			}
		})
	}
}

func TestSemanticFixtureRecordShapes(t *testing.T) {
	for name, row := range map[string]string{
		"empty-inventory":         "",
		"duplicate-cases":         fixtureRow + "," + fixtureRow,
		"missing-source":          strings.ReplaceAll(fixtureRow, `"source":"name: example\n",`, ""),
		"missing-acceptance":      strings.ReplaceAll(fixtureRow, `"accepted":true,`, ""),
		"null-acceptance":         strings.ReplaceAll(fixtureRow, `"accepted":true`, `"accepted":null`),
		"missing-findings":        strings.ReplaceAll(fixtureRow, `"findings":[],`, ""),
		"unknown-field":           strings.ReplaceAll(fixtureRow, `"accepted":true`, `"accepted":true,"ignored":true`),
		"ignored-limits":          strings.ReplaceAll(fixtureRow, `"accepted":true`, `"accepted":true,"limits":{}`),
		"duplicate-member":        strings.ReplaceAll(fixtureRow, `"accepted":true`, `"accepted":true,"accepted":false`),
		"unaligned-locations":     strings.ReplaceAll(fixtureRow, `"locations":[]`, `"locations":[null]`),
		"refused-with-identity":   strings.ReplaceAll(fixtureRow, `"accepted":true`, `"accepted":false`),
		"unknown-admission-error": strings.ReplaceAll(fixtureRow, `"accepted":true`, `"accepted":false,"admission_error":"other"`),
		"null-advisory":           strings.ReplaceAll(fixtureRow, `"advisories":[]`, `"advisories":[null]`),
		"malformed-json":          `{`,
		"null-row":                `null`,
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := loadSemanticVectors(semanticFixtureFS(t, "["+row+"]")); err == nil {
				t.Fatal("malformed semantic record accepted")
			}
		})
	}
}

func TestSemanticFixturePackaging(t *testing.T) {
	packaged, err := corpus.Open()
	if err != nil {
		t.Fatal(err)
	}
	packaged, err = fs.Sub(packaged, semanticFixtureFamily)
	if err != nil {
		t.Fatal(err)
	}
	local := os.DirFS("../../../../../contracts/" + semanticFixtureFamily)
	entries, err := fs.ReadDir(local, ".")
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range entries {
		want, localErr := fs.ReadFile(local, entry.Name())
		got, packageErr := fs.ReadFile(packaged, entry.Name())
		if localErr != nil || packageErr != nil || !bytes.Equal(got, want) {
			t.Fatalf("packaged fixture %s differs: local %v, packaged %v", entry.Name(), localErr, packageErr)
		}
	}
	t.Chdir(t.TempDir())
	if rows, err := loadSemanticVectors(packaged); err != nil || len(rows) == 0 {
		t.Fatalf("packaged semantic fixtures without checkout: %v", err)
	}
}

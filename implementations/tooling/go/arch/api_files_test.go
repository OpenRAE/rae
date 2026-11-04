package arch

import (
	"encoding/json"
	"strings"
	"testing"
	"testing/fstest"
)

const apiFixturePath = "implementations/architecture-api/example-01.json"

func TestAPIFileSnapshotsRetainExactComparison(t *testing.T) {
	m := &Model{Packages: []Package{{Dir: "example", APIFiles: map[string][]string{"linux": {apiFixturePath}}}}}
	repo := fstest.MapFS{apiFixturePath: {Data: []byte(`["package example","type example.Value constraints[] string"]`)}}
	if err := m.loadAPIFiles(repo); err != nil {
		t.Fatal(err)
	}
	actual := API{"example": {"linux": {"package example", "type example.Value constraints[] string"}}}
	if findings := m.CheckAPI(actual); len(findings) != 0 {
		t.Fatal(findings)
	}
	actual["example"]["linux"][1] = "type example.Value constraints[] int"
	if len(m.CheckAPI(actual)) != 1 {
		t.Fatal("changed declarations escaped comparison")
	}
	// The same data is accepted through the strict model loader.
	model := validModel()
	model.Packages[0].API = nil
	model.Packages[0].APIFiles = map[string][]string{"linux": {apiFixturePath}}
	raw, err := json.Marshal(model)
	if err != nil {
		t.Fatal(err)
	}
	repo["model.json"] = &fstest.MapFile{Data: raw}
	loaded, err := Load(repo, "model.json")
	if err != nil {
		t.Fatal(err)
	}
	if len(loaded.Packages[0].API["linux"]) != 2 {
		t.Fatal("snapshot was not expanded")
	}
}

func TestAPIFileSnapshotsRefuseUnsafeAndUnboundedInput(t *testing.T) {
	for _, test := range []struct{ name, path, content string }{
		{"traversal", "implementations/architecture-api/../private.json", `["package x"]`},
		{"absolute", "/implementations/architecture-api/x.json", `["package x"]`},
		{"outside", "docs/x.json", `["package x"]`},
		{"wrong extension", "implementations/architecture-api/x.txt", `["package x"]`},
		{"missing", apiFixturePath, ""},
		{"malformed", apiFixturePath, "["},
		{"wrong root", apiFixturePath, `{}`},
		{"null", apiFixturePath, `null`},
		{"empty", apiFixturePath, `[]`},
		{"wrong member", apiFixturePath, `[12]`},
		{"trailing", apiFixturePath, `["package x"] []`},
		{"oversize", apiFixturePath, strings.Repeat(" ", apiFileLimit+1)},
	} {
		t.Run(test.name, func(t *testing.T) {
			repo := fstest.MapFS{}
			if test.content != "" {
				repo[test.path] = &fstest.MapFile{Data: []byte(test.content)}
			}
			budget := apiTotalLimit
			if _, err := readAPIFile(repo, test.path, &budget); err == nil {
				t.Fatal("accepted invalid snapshot")
			}
		})
	}
	budget := 1
	if _, err := readAPIFile(fstest.MapFS{apiFixturePath: {Data: []byte(`["package x"]`)}}, apiFixturePath, &budget); err == nil {
		t.Fatal("ignored shared read budget")
	}
}

func TestAPIFileSnapshotsRefuseAmbiguousDeclarations(t *testing.T) {
	for _, pkg := range []Package{
		{API: map[string][]string{}, APIFiles: map[string][]string{"linux": {apiFixturePath}}},
		{APIFiles: map[string][]string{"linux": {}}},
		{APIFiles: map[string][]string{"linux": make([]string, apiFileCountLimit+1)}},
	} {
		m := &Model{Packages: []Package{pkg}}
		if err := m.loadAPIFiles(fstest.MapFS{}); err == nil {
			t.Fatal("accepted ambiguous or unbounded snapshot declaration")
		}
	}
}

func TestAPIFileSnapshotInclusiveBounds(t *testing.T) {
	value := `["package example"]`
	padded := value + strings.Repeat(" ", apiFileLimit-len(value))
	repo := fstest.MapFS{apiFixturePath: {Data: []byte(padded)}}
	budget := apiFileLimit
	if _, err := readAPIFile(repo, apiFixturePath, &budget); err != nil || budget != 0 {
		t.Fatalf("inclusive limit rejected: budget=%d err=%v", budget, err)
	}
	if _, err := readAPIFile(repo, apiFixturePath, &budget); err == nil {
		t.Fatal("a second file escaped the shared budget")
	}
}

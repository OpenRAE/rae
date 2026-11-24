package governance

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestJSONRoutingHistoricalDepth(t *testing.T) {
	root := t.TempDir()
	testWrite(t, root, identityManifest, jsonDepthSource("array", governanceJSONDepth+1))
	r, err := openRepository(root)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	if targets, err := collectJSONTargets(r, nil); err == nil {
		t.Fatalf("historical decoder depth became successful routing: %v", targets)
	}
}

func TestJSONRoutingOutsidePath(t *testing.T) {
	r, err := openRepository(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	outside := filepath.Join(t.TempDir(), "never-read.txt")
	if targets, err := collectJSONTargets(r, []string{outside}); err == nil {
		t.Fatalf("outside absolute path became successful routing: %v", targets)
	}
}

type jsonRouteReference struct {
	Base  map[string]string
	Cases []jsonRouteCase
}

type jsonRouteCase struct {
	Name    string
	Changes map[string]*string
	Paths   []string
	Error   string
	Targets []struct {
		Path       string  `json:"path"`
		SchemaPath *string `json:"schema_path"`
		Mode       string  `json:"mode"`
	}
}

func TestJSONRoutingReference(t *testing.T) {
	fixture := readReference[jsonRouteReference](t, "json-routes-reference")
	for _, tc := range fixture.Cases {
		t.Run(tc.Name, func(t *testing.T) { checkJSONRouteReference(t, fixture.Base, tc) })
	}
}

func checkJSONRouteReference(t *testing.T, base map[string]string, tc jsonRouteCase) {
	t.Helper()
	root := seedRepositoryReference(t, repositoryReference{Files: deltaFiles(base, tc.Changes)})
	r, err := openRepository(root)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	targets, err := collectJSONTargets(r, tc.Paths)
	if tc.Error != "" {
		if err == nil || err.Error() != tc.Error {
			t.Fatalf("routing error=%v want=%q", err, tc.Error)
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	want := make([]jsonTarget, len(tc.Targets))
	for i, row := range tc.Targets {
		want[i] = jsonTarget{path: row.Path, mode: row.Mode}
		if row.SchemaPath != nil {
			want[i].schema = *row.SchemaPath
		}
	}
	if diff := cmp.Diff(want, targets, cmp.AllowUnexported(jsonTarget{})); diff != "" {
		t.Errorf("routing (-want +got):\n%s", diff)
	}
}

func TestJSONRoutingSymlinks(t *testing.T) {
	for _, outside := range []bool{false, true} {
		for _, parent := range []bool{false, true} {
			t.Run(map[bool]string{true: "outside", false: "inside"}[outside]+"/"+map[bool]string{true: "parent", false: "leaf"}[parent], func(t *testing.T) {
				checkJSONRouteLink(t, outside, parent)
			})
		}
	}
}

func checkJSONRouteLink(t *testing.T, outside, parent bool) {
	t.Helper()
	root := t.TempDir()
	targetRoot := root
	if outside {
		targetRoot = t.TempDir()
	}
	testWrite(t, targetRoot, "source/data.json", []byte(`{"schema_version":"example/v1"}`))
	const prefix = "contracts/profiles/semantic/"
	if err := os.MkdirAll(filepath.Join(root, prefix), 0o700); err != nil {
		t.Fatal(err)
	}
	name := prefix + "data.json"
	target := filepath.Join(targetRoot, "source/data.json")
	if parent {
		name = prefix + "linked/data.json"
		target = filepath.Join(targetRoot, "source")
		if err := os.Symlink(target, filepath.Join(root, prefix, "linked")); err != nil {
			t.Fatal(err)
		}
	} else if err := os.Symlink(target, filepath.Join(root, name)); err != nil {
		t.Fatal(err)
	}
	r, err := openRepository(root)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	for _, paths := range [][]string{nil, {name}} {
		targets, err := collectJSONTargets(r, paths)
		if err != nil || len(targets) != 0 {
			t.Fatalf("routed a symlink: %v, %v", targets, err)
		}
	}
}

func TestJSONRoutingInvalidText(t *testing.T) {
	root := t.TempDir()
	const name = "contracts/profiles/semantic/bad.json"
	testWrite(t, root, name, []byte{0xff})
	r, err := openRepository(root)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	_, err = collectJSONTargets(r, []string{name})
	if err == nil || err.Error() != name+" is not UTF-8 JSON within the decoder limits" {
		t.Fatalf("invalid source text error=%v", err)
	}
}

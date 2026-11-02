package parity

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io/fs"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"
)

const (
	manifest = `{"schema": "raes-parity-corpus/v1", "provenance": {"python_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "python_tree": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "recorder_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", "lock_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd", "python_version": "3.14.7"}}`
	input    = "name: a\n"
	caseName = "cases/cli/semantic-validate/examples/a.json"
)

// corpus returns a corpus with one case that reads input as input.yaml. The
// input store holds stored under the digest of input.
func corpus(stored []byte) fstest.MapFS {
	sum := sha256.Sum256([]byte(input))
	digest := hex.EncodeToString(sum[:])
	fsys := fstest.MapFS{
		"manifest.json": {Data: []byte(manifest)},
		caseName: {Data: []byte(`{"name": "examples/a", "surface": "cli", "command": "semantic validate", "args": ["semantic", "validate", "input.yaml"],` +
			` "files": {"input.yaml": "` + digest + `"}, "result": {"exit_code": 0}}`)},
	}
	if stored != nil {
		fsys["inputs/"+digest] = &fstest.MapFile{Data: stored}
	}
	return fsys
}

func TestLoadReadsEachCaseWithItsInputs(t *testing.T) {
	got, err := Load(corpus([]byte(input)))
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	want := []Case{{
		Name:    "examples/a",
		Surface: "cli",
		Command: "semantic validate",
		Args:    []string{"semantic", "validate", "input.yaml"},
		Files:   map[string][]byte{"input.yaml": []byte("name: a\n")},
		Result:  json.RawMessage(`{"exit_code": 0}`),
	}}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("Load() mismatch (-want +got):\n%s", diff)
	}
	if key := got[0].Key(); key != "cli semantic validate" {
		t.Errorf("Key() = %q, want %q", key, "cli semantic validate")
	}
}

func TestLoadRejectsAnInvalidCorpus(t *testing.T) {
	tests := map[string]fstest.MapFS{
		"missing input":                        corpus(nil),
		"input that does not match its digest": corpus([]byte("changed")),
	}
	for name, content := range map[string]string{
		"unknown schema":       strings.Replace(manifest, Schema, "other/v1", 1),
		"unknown field":        strings.TrimSuffix(manifest, "}") + `, "x": 1}`,
		"data after the value": manifest + " {}",
	} {
		fsys := corpus([]byte(input))
		fsys["manifest.json"] = &fstest.MapFile{Data: []byte(content)}
		tests[name] = fsys
	}
	tests["missing manifest"] = corpus([]byte(input))
	delete(tests["missing manifest"], "manifest.json")
	tests["case that is not JSON"] = corpus([]byte(input))
	tests["case that is not JSON"][caseName] = &fstest.MapFile{Data: []byte("{")}
	tests["missing cases directory"] = corpus([]byte(input))
	delete(tests["missing cases directory"], caseName)
	for name, fsys := range tests {
		t.Run(name, func(t *testing.T) {
			if _, err := Load(fsys); err == nil {
				t.Error("Load() error = nil, want an error")
			}
		})
	}
}

func TestLoadRejectsMissingProvenanceAndUnsafeCases(t *testing.T) {
	for _, test := range []struct{ name, old, replacement string }{
		{"missing commit", strings.Repeat("a", 40), ""},
		{"invalid tree", strings.Repeat("b", 40), strings.Repeat("z", 40)},
		{"missing recorder", strings.Repeat("c", 64), ""},
		{"missing lock", strings.Repeat("d", 64), ""},
		{"missing version", "3.14.7", ""},
	} {
		t.Run(test.name, func(t *testing.T) {
			fsys := corpus([]byte(input))
			fsys["manifest.json"].Data = []byte(strings.Replace(manifest, test.old, test.replacement, 1))
			if _, err := Load(fsys); err == nil {
				t.Error("Load() error = nil, want error")
			}
		})
	}
	for _, test := range []struct{ name, old, replacement string }{
		{"empty identity", `"examples/a"`, `""`},
		{"empty surface", `"cli"`, `""`},
		{"empty command", `"semantic validate"`, `" "`},
		{"absent result", `, "result": {"exit_code": 0}`, ``},
		{"missing result", `{"exit_code": 0}`, `null`},
		{"parent traversal", `"input.yaml"`, `"../escape"`},
		{"absolute file", `"input.yaml"`, `"/escape"`},
		{"windows traversal", `"input.yaml"`, `"C:\\escape"`},
		{"backslash traversal", `"input.yaml"`, `"a\\escape"`},
		{"drive file", `"input.yaml"`, `"C:escape"`},
	} {
		t.Run(test.name, func(t *testing.T) {
			fsys := corpus([]byte(input))
			fsys[caseName].Data = []byte(strings.ReplaceAll(string(fsys[caseName].Data), test.old, test.replacement))
			if _, err := Load(fsys); err == nil {
				t.Error("Load() error = nil, want error")
			}
		})
	}
	fsys := corpus([]byte(input))
	sum := sha256.Sum256([]byte(input))
	fsys[caseName].Data = []byte(strings.ReplaceAll(string(fsys[caseName].Data), hex.EncodeToString(sum[:]), "../escape"))
	if _, err := Load(fsys); err == nil {
		t.Error("Load(bad digest) error = nil, want error")
	}
	fsys = corpus([]byte(input))
	fsys["cases/duplicate.json"] = fsys[caseName]
	if _, err := Load(fsys); err == nil {
		t.Error("Load(duplicate) error = nil, want error")
	}
	fsys = corpus([]byte(input))
	delete(fsys, caseName)
	fsys["cases"] = &fstest.MapFile{Mode: 0o755 | fs.ModeDir}
	if _, err := Load(fsys); err == nil {
		t.Error("Load(empty) error = nil, want error")
	}
}

func TestHexDigestRequiresLowercaseHexOfTheExactLength(t *testing.T) {
	for _, test := range []struct {
		value  string
		length int
		valid  bool
	}{
		{"09af", 4, true}, {"09AF", 4, false}, {"09az", 4, false}, {"09a", 4, false}, {"09af0", 4, false},
	} {
		if got := hexDigest(test.value, test.length); got != test.valid {
			t.Errorf("hexDigest(%q, %d) = %t, want %t", test.value, test.length, got, test.valid)
		}
	}
}

// observedFS records file reads so the security test can distinguish rejecting
// a path before lookup from detecting bad content after an unsafe lookup.
type observedFS struct {
	fs.FS

	opened []string
}

func (f *observedFS) Open(name string) (fs.File, error) {
	f.opened = append(f.opened, name)
	return f.FS.Open(name)
}

func TestLoadRejectsAnInvalidDigestBeforeOpeningItsPath(t *testing.T) {
	fsys := corpus([]byte(input))
	sum := sha256.Sum256([]byte(input))
	fsys[caseName].Data = []byte(strings.ReplaceAll(string(fsys[caseName].Data), hex.EncodeToString(sum[:]), "../escape"))
	observed := &observedFS{FS: fsys}
	if _, err := Load(observed); err == nil {
		t.Error("Load() error = nil, want error")
	}
	for _, name := range observed.opened {
		if name == "escape" {
			t.Error("Load() opened an input path outside inputs/, want rejection before lookup")
		}
	}
}

package parity

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"testing"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"
)

const (
	manifest = `{"schema": "raes-parity-corpus/v1", "python_commit": "abc123"}`
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
		caseName: {Data: []byte(`{"surface": "cli", "command": "semantic validate", "args": ["semantic", "validate", "input.yaml"],` +
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
	want := Corpus{
		PythonCommit: "abc123",
		Cases: []Case{{
			Name:    "cli/semantic-validate/examples/a",
			Surface: "cli",
			Command: "semantic validate",
			Args:    []string{"semantic", "validate", "input.yaml"},
			Files:   map[string][]byte{"input.yaml": []byte("name: a\n")},
			Result:  json.RawMessage(`{"exit_code": 0}`),
		}},
	}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("Load() mismatch (-want +got):\n%s", diff)
	}
	if key := got.Cases[0].Key(); key != "cli semantic validate" {
		t.Errorf("Key() = %q, want %q", key, "cli semantic validate")
	}
}

func TestLoadRejectsAnInvalidCorpus(t *testing.T) {
	tests := map[string]fstest.MapFS{
		"missing input":                        corpus(nil),
		"input that does not match its digest": corpus([]byte("changed")),
	}
	for name, content := range map[string]string{
		"unknown schema":       `{"schema": "other/v1"}`,
		"unknown field":        `{"schema": "raes-parity-corpus/v1", "x": 1}`,
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

package parity

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"
)

const (
	manifest = `{"schema":"raes-parity-corpus/v1","reference":{"python_version":"3.14.7",
        "source_sha256":"0000000000000000000000000000000000000000000000000000000000000000",
        "recorder_sha256":"1111111111111111111111111111111111111111111111111111111111111111",
        "environment_sha256":"2222222222222222222222222222222222222222222222222222222222222222"}}`
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

func TestResultComparisonKeepsExactNumbers(t *testing.T) {
	for _, pair := range [][2]string{
		{`{"n":9007199254740992}`, `{"n":9007199254740993}`},
		{`[-9007199254740992]`, `[-9007199254740993]`},
		{`1.00000000000000000001`, `1`},
		{`1e100000000000000000000`, `1e100000000000000000001`},
	} {
		if cmp.Equal(decode(t, json.RawMessage(pair[0])), decode(t, json.RawMessage(pair[1]))) {
			t.Errorf("compare(%s, %s) = equal, want different", pair[0], pair[1])
		}
	}
	for _, pair := range [][2]string{
		{`1`, `1.00e0`}, {`-0.0`, `0`}, {`12.30e-1`, `1.23`},
		{`-12300e-2`, `-123`}, {`1E+1000000`, `10e999999`},
	} {
		if !cmp.Equal(decode(t, json.RawMessage(pair[0])), decode(t, json.RawMessage(pair[1]))) {
			t.Errorf("compare(%s, %s) = different, want equal", pair[0], pair[1])
		}
	}
	if cmp.Equal(decode(t, json.RawMessage(`"1"`)), decode(t, json.RawMessage(`1`))) {
		t.Error("compare(string, number) = equal, want different")
	}
}

func TestImplementedCommandsCannotBecomeSkipped(t *testing.T) {
	cases := map[string][]Case{"canonical encode": {{Name: "edge"}}}
	if err := checkRunners(cases, runners(), false); err != nil {
		t.Fatalf("checkRunners() error = %v, want nil", err)
	}
	if err := checkRunners(cases, map[string]Runner{}, false); err == nil {
		t.Error("checkRunners(no runner) error = nil, want an error")
	}
	if err := checkRunners(map[string][]Case{}, runners(), false); err == nil {
		t.Error("checkRunners(no cases) error = nil, want an error")
	}
	cases["unported command"] = []Case{{Name: "pending"}}
	if err := checkRunners(cases, runners(), false); err != nil {
		t.Errorf("checkRunners(partial) error = %v, want nil", err)
	}
	if err := checkRunners(cases, runners(), true); err == nil {
		t.Error("checkRunners(complete) error = nil, want an error")
	}
	delete(cases, "unported command")
	if err := checkRunners(cases, runners(), true); err != nil {
		t.Errorf("checkRunners(complete) error = %v, want nil", err)
	}
}

func TestLoadRequiresReferenceIdentityAndSafeInputNames(t *testing.T) {
	for _, content := range []string{
		`{"schema":"raes-parity-corpus/v1"}`,
		strings.Replace(manifest, strings.Repeat("0", 64), "short", 1),
		strings.Replace(manifest, strings.Repeat("1", 64), strings.Repeat("A", 64), 1),
		strings.Replace(manifest, strings.Repeat("2", 64), strings.Repeat("z", 64), 1),
	} {
		fsys := corpus([]byte(input))
		fsys["manifest.json"] = &fstest.MapFile{Data: []byte(content)}
		if _, err := Load(fsys); err == nil {
			t.Error("Load(invalid reference) error = nil, want an error")
		}
	}
	for _, digest := range []string{"../manifest.json", strings.Repeat("G", 64), strings.Repeat("a", 63)} {
		fsys := corpus([]byte(input))
		sum := sha256.Sum256([]byte(input))
		fsys[caseName].Data = []byte(strings.Replace(string(fsys[caseName].Data), hex.EncodeToString(sum[:]), digest, 1))
		if _, err := Load(fsys); err == nil {
			t.Errorf("Load(input %q) error = nil, want an error", digest)
		}
	}
}

func TestCanonicalRunnerRequiresItsInput(t *testing.T) {
	if _, err := canonicalEncode(t.Context(), Case{}); err == nil {
		t.Error("canonicalEncode(no input) error = nil, want an error")
	}
}

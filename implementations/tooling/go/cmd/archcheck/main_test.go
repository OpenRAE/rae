package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/tooling/go/arch"
)

// rulesADR is an ADR whose rule table maps each rule to its check.
const rulesADR = `# ADR-122

| Rule | Statement | Check |
| --- | --- | --- |
| ARCH-001 | Modules. | ` + "`archcheck`" + ` |
| ARCH-002 | Layers. | ` + "`archcheck`" + ` |
| ARCH-003 | Packages. | ` + "`archcheck`" + ` |
| ARCH-004 | Declared imports. | ` + "`archcheck`" + ` |
| ARCH-005 | Classification. | ` + "`archcheck`" + ` |
| ARCH-006 | Code imports. | ` + "`archcheck`" + ` |
| ARCH-007 | Test imports. | ` + "`archcheck`" + ` |
| ARCH-008 | External imports. | ` + "`archcheck`" + ` |
| ARCH-009 | Rule table. | ` + "`archcheck`" + ` |
| ARCH-010 | Import cycles. | ` + "`archcheck`" + ` |
| ARCH-011 | Internal packages. | ` + "`go build`" + ` |
| ARCH-012 | Exported identifiers. | ` + "`go build`" + ` |
| ARCH-013 | API contract. | ` + "`archcheck`" + ` |
| ARCH-014 | Current view. | ` + "`archcheck`" + ` |
| ARCH-015 | Consumer API. | ` + "`archcheck`" + ` |
`

// model returns a model of one module with the package p in the layer l.
func model(uses string) string {
	return `{
  "schema": "raes-go-architecture/v2",
 "configurations": [{"id":"linux","goos":"linux","goarch":"amd64","tags":[]}],
 "overview":"docs/overview.md", "sources":{"docs/evidence.md":"ee8250fb76e094b34b471f13a73dbbe51d1ae142e9df59d7c0d31ec20f0a0a8e"},
  "modules": [{"dir": "m", "path": "example.com/m"}],
  "layers": [{"name": "l", "dir": "m", "doc": "The layer.", "uses": [` + uses + `], "external": []}],
  "packages": [{"design":"docs/design.md","api":{"linux":["package p"]},"dir": "m/p", "layer": "l", "public": false, "doc": "The package.", "imports": []}]
}
`
}

func TestRunRejectsBadUsage(t *testing.T) {
	for _, args := range [][]string{{"-unknown"}, {"extra"}} {
		var stdout, stderr bytes.Buffer
		if status := run(t.Context(), args, &stdout, &stderr); status != 2 {
			t.Errorf("run(%q) = %d, want 2", args, status)
		}
		if stderr.Len() == 0 {
			t.Errorf("run(%q) wrote no usage message", args)
		}
	}
}

func TestRunReportsNoFindingsWhenTheModelAndTheCodeAgree(t *testing.T) {
	repository(t, map[string]string{
		"implementations/architecture.json":                    model(""),
		"docs/decisions/adrs/adr-122-go-architecture-model.md": rulesADR,
		"m/go.mod": "module example.com/m\n\ngo 1.27\n",
		"m/p/p.go": "package p\n",
	})
	for _, args := range [][]string{nil, {"-design"}} {
		stdout, stderr, status := runCommand(t, args...)
		if status != 0 || stdout != "archcheck: no findings\n" || stderr != "" {
			t.Errorf("run(%q) = %d, stdout %q, stderr %q, want 0 and no findings", args, status, stdout, stderr)
		}
	}
}

func TestRunReportsEachFinding(t *testing.T) {
	tests := map[string]struct {
		files map[string]string
		args  []string
		want  string
	}{
		"design": {
			files: map[string]string{"implementations/architecture.json": model(`"l"`)},
			args:  []string{"-design"},
			want:  "archcheck: ARCH-002 m:",
		},
		"design before code": {
			files: map[string]string{"implementations/architecture.json": model(`"l"`)},
			want:  "archcheck: ARCH-002 m:",
		},
		"rule table": {
			files: map[string]string{
				"implementations/architecture.json":                    model(""),
				"docs/decisions/adrs/adr-122-go-architecture-model.md": strings.ReplaceAll(rulesADR, "| ARCH-012", "| ARCH-099"),
				"m/go.mod": "module example.com/m\n\ngo 1.27\n",
				"m/p/p.go": "package p\n",
			},
			want: "archcheck: ARCH-009 docs/decisions/adrs/adr-122-go-architecture-model.md:",
		},
		"code": {
			files: map[string]string{
				"implementations/architecture.json":                    model(""),
				"docs/decisions/adrs/adr-122-go-architecture-model.md": rulesADR,
				"m/go.mod":  "module example.com/m\n\ngo 1.27\n",
				"m/p/p.go":  "package p\n",
				"m/q/q.go":  "package q\n",
				"n/go.mod":  "module example.com/n\n\ngo 1.27\n",
				"_x/go.mod": "module example.com/x\n\ngo 1.27\n",
			},
			want: "archcheck: ARCH-001 n/go.mod:",
		},
	}
	for name, test := range tests {
		t.Run(name, func(t *testing.T) {
			repository(t, test.files)
			_, stderr, status := runCommand(t, test.args...)
			if status != 1 || !strings.Contains(stderr, test.want) || !strings.Contains(stderr, " Fix: ") {
				t.Errorf("run(%q) = %d, stderr %q, want 1 and a finding with %q and a fix", test.args, status, stderr, test.want)
			}
		})
	}
}

func TestRunReportsAnError(t *testing.T) {
	tests := map[string]map[string]string{
		"missing model": {},
		"missing ADR":   {"implementations/architecture.json": model("")},
		"package error": {
			"implementations/architecture.json":                    model(""),
			"docs/decisions/adrs/adr-122-go-architecture-model.md": rulesADR,
			"m/go.mod": "module example.com/m\n\ngo 1.27\n",
			"m/p/p.go": "package p\n\nimport (\n",
		},
	}
	for name, files := range tests {
		t.Run(name, func(t *testing.T) {
			repository(t, files)
			_, stderr, status := runCommand(t)
			if status != 1 || !strings.HasPrefix(stderr, "archcheck: ") {
				t.Errorf("run() = %d, stderr %q, want 1 and an error", status, stderr)
			}
		})
	}
}

// repository writes files, keyed by slash-separated path, under a new
// temporary directory and makes it the working directory of the test.
func repository(t *testing.T, files map[string]string) {
	t.Helper()
	root := t.TempDir()
	if raw, ok := files["implementations/architecture.json"]; ok {
		var m arch.Model
		if err := json.Unmarshal([]byte(raw), &m); err != nil {
			t.Fatal(err)
		}
		files["docs/overview.md"] = m.View()
		files["docs/evidence.md"] = "evidence"
		files["docs/design.md"] = "<!-- go-api m/p 12b3503fdcf049c8163b6ea46b2432a4bdd8f2820060e946683420ef0fb06c29 -->"
	}
	for name, content := range files {
		file := filepath.Join(root, filepath.FromSlash(name))
		if err := os.MkdirAll(filepath.Dir(file), 0o750); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(file, []byte(content), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	t.Chdir(root)
}

func runCommand(t *testing.T, args ...string) (stdout, stderr string, status int) {
	t.Helper()
	var out, errOut bytes.Buffer
	status = run(t.Context(), args, &out, &errOut)
	return out.String(), errOut.String(), status
}

func TestRunRejectsExportWithoutDesignUpdate(t *testing.T) {
	repository(t, map[string]string{"implementations/architecture.json": model(""), rulesPath: rulesADR, "m/go.mod": "module example.com/m\n\ngo 1.27\n", "m/p/p.go": "package p\nfunc Unexpected() {}\n"})
	_, stderr, status := runCommand(t)
	if status != 1 || !strings.Contains(stderr, "ARCH-013 m/p:") || !strings.Contains(stderr, "Fix:") {
		t.Errorf("run() = %d, %s, want API finding", status, stderr)
	}
}

func TestDesignRejectsEscapingSymlink(t *testing.T) {
	repository(t, map[string]string{"implementations/architecture.json": model("")})
	if err := os.Remove("docs/design.md"); err != nil {
		t.Fatal(err)
	}
	outside := filepath.Join(t.TempDir(), "outside.md")
	if err := os.WriteFile(outside, []byte("private"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, "docs/design.md"); err != nil {
		t.Fatal(err)
	}
	_, stderr, status := runCommand(t, "-design")
	if status != 1 || strings.Contains(stderr, "private") {
		t.Errorf("run(-design) = %d, %s, want contained failure", status, stderr)
	}
}

func TestDesignWorksBeforeProductCodeExists(t *testing.T) {
	repository(t, map[string]string{"implementations/architecture.json": model("")})
	_, stderr, status := runCommand(t, "-design")
	if status != 0 {
		t.Errorf("run(-design) = %d, %s, want pre-code success", status, stderr)
	}
}

func TestRenderPrintsCandidatesWithoutChangingIntent(t *testing.T) {
	repository(t, map[string]string{"implementations/architecture.json": model(""), "m/go.mod": "module example.com/m\n\ngo 1.27\n", "m/p/p.go": "package p\nconst NewAPI=3\n"})
	before, err := os.ReadFile(modelPath)
	if err != nil {
		t.Fatal(err)
	}
	for _, flag := range []string{"-api", "-view"} {
		stdout, stderr, status := runCommand(t, flag)
		if status != 0 || stdout == "" || stderr != "" {
			t.Errorf("run(%s) = %d, %q, %q", flag, status, stdout, stderr)
		}
	}
	after, err := os.ReadFile(modelPath)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(before, after) {
		t.Error("rendering changed the intended API")
	}
	for _, flags := range [][]string{{"-api", "-view"}, {"-design", "-api"}, {"-design", "-view"}} {
		_, _, status := runCommand(t, flags...)
		if status != 2 {
			t.Errorf("run(%v) = %d, want usage error", flags, status)
		}
	}
	if err := os.Remove(modelPath); err != nil {
		t.Fatal(err)
	}
	_, stderr, status := runCommand(t, "-view")
	if status != 1 || stderr == "" {
		t.Errorf("run(-view) without model = %d, %q", status, stderr)
	}
}

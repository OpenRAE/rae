package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
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
| ARCH-010 | Import cycles. | ` + "`go build`" + ` |
| ARCH-011 | Internal packages. | ` + "`go build`" + ` |
| ARCH-012 | Exported identifiers. | ` + "`go build`" + ` |
`

// model returns a model of one module with the package p in the layer l.
func model(uses string) string {
	return `{
  "schema": "raes-go-architecture/v1",
  "modules": [{"dir": "m", "path": "example.com/m"}],
  "layers": [{"name": "l", "dir": "m", "doc": "The layer.", "uses": [` + uses + `], "external": []}],
  "packages": [{"dir": "m/p", "layer": "l", "public": false, "doc": "The package.", "imports": []}]
}
`
}

func TestRunRejectsBadUsage(t *testing.T) {
	for _, args := range [][]string{{"-unknown"}, {"extra"}} {
		var stdout, stderr bytes.Buffer
		if status := run(t.Context(), args, &stdout, &stderr); status != 2 {
			t.Errorf("run(%q) = %d, want 2", args, status)
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

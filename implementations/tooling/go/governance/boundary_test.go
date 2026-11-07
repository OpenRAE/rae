package governance

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestReaderProfiles(t *testing.T) {
	data := []byte(`{"value":1,"value":1}`)
	value, err := decodeJSON(data, 0, false)
	if err != nil {
		t.Fatalf("ordinary JSON error = %v, want the reference's last-member behavior", err)
	}
	object, ok := value.(*mapping)
	if !ok || object.get("value") != json.Number("1") {
		t.Fatalf("ordinary JSON value = %v, want value=1", value)
	}
	if _, err := decodeJSON(data, 0, true); err == nil {
		t.Fatal("bounded strict JSON accepts duplicate members")
	}
	if _, err := decodeJSON([]byte(`{"value":1}`), 1, false); err == nil {
		t.Fatal("bounded JSON accepts more than its byte limit")
	}
}

func TestInertPythonSyntax(t *testing.T) {
	for _, tc := range []struct {
		name, source string
		valid        bool
	}{
		{"imports-and-annotations", "from raes import parser as p\nclass C:\n    def f(self, x: int) -> str:\n        return 'import private_module'\n", true},
		{"malformed", "def broken(:\n", false},
		{"never-executed", "raise RuntimeError('must not execute')\n", true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			tree, err := pythonSyntax(context.Background(), []byte(tc.source))
			if tree != nil {
				tree.Release()
			}
			if (err == nil) != tc.valid {
				t.Fatalf("pythonSyntax error = %v, want valid=%t", err, tc.valid)
			}
		})
	}
}

func TestDocumentationReadBoundary(t *testing.T) {
	root := t.TempDir()
	public := filepath.Join(root, "docs", "public")
	if err := os.MkdirAll(public, 0750); err != nil {
		t.Fatal(err)
	}
	request := Request{Tool: "public-docs-reads", Root: root, Documentation: &Documentation{
		SourceRoot: public,
		Reads:      []DocumentRead{{Page: "index", File: "../development/record.md"}},
	}}
	report, err := Check(context.Background(), request)
	if err != nil {
		t.Fatalf("recorded-read check error = %v, want an evaluated containment finding", err)
	}
	if len(report.Findings) != 1 {
		t.Fatalf("recorded-read findings = %v, want the outside-source read to be refused", report.Findings)
	}
}

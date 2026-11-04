package main

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"
)

func TestCommandUsage(t *testing.T) {
	for _, args := range [][]string{{"-unknown"}, {"unexpected"}} {
		var stderr bytes.Buffer
		if got := run(args, &stderr); got != 2 {
			t.Errorf("run(%v) = %d, want 2", args, got)
		}
	}
}

func TestCommandGeneratesAndChecks(t *testing.T) {
	t.Chdir(t.TempDir())
	files := map[string]string{
		"THIRD_PARTY_NOTICES.md":                               "notice",
		"contracts/schema-publication-manifest.json":           `{"entries_directory":"contracts/schema-publication/entries"}`,
		"contracts/schema-publication/entries/example-v1.json": `{"contract_id":"example-v1","schema_path":"contracts/schemas/example-v1.json"}`,
		"contracts/schemas/example-v1.json":                    `{"type":"object"}`,
		"specs/conformance/contract-invariant-rules.json":      `{"specification":"raes-contract-invariant-rules/v1","rules":[]}`,
	}
	for name, data := range files {
		if err := os.MkdirAll(filepath.Dir(name), 0750); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(name, []byte(data), 0600); err != nil {
			t.Fatal(err)
		}
	}
	for _, args := range [][]string{nil, {"-check"}} {
		var stderr bytes.Buffer
		if got := run(args, &stderr); got != 0 {
			t.Errorf("run(%v) = %d, stderr=%s, want 0", args, got, &stderr)
		}
	}
	if err := os.WriteFile("implementations/go/internal/contract/binding/example-v1_generated.go", []byte("stale"), 0600); err != nil {
		t.Fatal(err)
	}
	var stderr bytes.Buffer
	if got := run([]string{"-check"}, &stderr); got != 1 {
		t.Errorf("run(stale check) = %d, want 1", got)
	}
}

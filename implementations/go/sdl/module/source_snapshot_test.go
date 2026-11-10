package module

import (
	"bytes"
	"fmt"
	"strings"
	"testing"
)

func TestVerifiedSourceSnapshotIsConfinedAndOwned(t *testing.T) {
	files := map[string][]byte{
		"nested/module:root.yaml": []byte("name: root\nimports: [{path: '../common.yaml', namespace: c}]\n"),
		"common.yaml":             []byte("name: common\nimports: [{path: 'nested/module:root.yaml', namespace: cycle}, {source: 'oci:registry.example/remote', namespace: remote}]\n"),
	}
	captured, err := captureSources(files, "nested/module:root.yaml")
	if err != nil {
		t.Fatal(err)
	}
	expected := bytes.Clone(files["common.yaml"])
	clear(files["common.yaml"])
	delete(files, "nested/module:root.yaml")
	if len(captured) != 2 || !bytes.Equal(captured["common.yaml"], expected) {
		t.Fatal("source snapshot retained mutable caller storage or followed remote authority")
	}
	for _, source := range []string{
		"name: a\nimports: wrong\n", "name: a\nimports: [wrong]\n",
		"name: a\nimports: [{path: '../escape.yaml'}]\n",
		"name: a\nimports: [{path: 'missing.yaml'}]\n",
		"name: a\nimports: [{path: '/absolute.yaml'}]\n",
		"name: a\nimports: [{path: 'C:/escape.yaml'}]\n",
		"name: a\nimports: [{path: ''}]\n",
	} {
		if snapshot, err := captureSources(map[string][]byte{"root.yaml": []byte(source)}, "root.yaml"); err == nil || snapshot != nil {
			t.Fatal("invalid verified source graph was captured")
		}
	}
}
func TestVerifiedSourceSnapshotKeepsImportBudget(t *testing.T) {
	var rows strings.Builder
	rows.WriteString("name: root\nimports:\n")
	for i := range 256 {
		_, _ = fmt.Fprintf(&rows, "  - {path: child.yaml, namespace: n%d}\n", i)
	}
	files := map[string][]byte{"root.yaml": []byte(rows.String()), "child.yaml": []byte("name: child\n")}
	if _, err := captureSources(files, "root.yaml"); err != nil {
		t.Fatalf("exact import boundary rejected: %v", err)
	}
	rows.WriteString("  - {path: child.yaml, namespace: extra}\n")
	files["root.yaml"] = []byte(rows.String())
	if snapshot, err := captureSources(files, "root.yaml"); err == nil || snapshot != nil {
		t.Fatal("source capture bypassed the aggregate import budget")
	}
}

package governance

import (
	"slices"
	"strings"
	"testing"
)

type documentReadReference struct {
	Name                                         string
	Files, ModuleRoots, ImportedModules, Outside []string
}

func TestDocumentationReadReference(t *testing.T) {
	for _, tc := range readReference[[]documentReadReference](t, "docs-reads-reference") {
		t.Run(tc.Name, func(t *testing.T) { checkDocumentReadReference(t, tc) })
	}
}

func checkDocumentReadReference(t *testing.T, tc documentReadReference) {
	t.Helper()
	root := t.TempDir()
	docs := &Documentation{SourceRoot: "docs/public", ModuleRoots: tc.ModuleRoots, ImportedModules: tc.ImportedModules}
	for _, file := range tc.Files {
		docs.Reads = append(docs.Reads, DocumentRead{Page: "index", File: strings.ReplaceAll(file, "%ROOT%", root)})
	}
	request := Request{Tool: "public-docs-reads", Root: root, Documentation: docs}
	for range 2 {
		checkDocumentReadResult(t, root, tc.Outside, request)
	}
}

func checkDocumentReadResult(t *testing.T, root string, expected []string, request Request) {
	t.Helper()
	report, err := Check(t.Context(), request)
	if err != nil {
		t.Fatal(err)
	}
	outside := []string{}
	for _, f := range report.Findings {
		if f.RuleID != "public-docs-read-escape" || f.Path == nil || *f.Path != "index" {
			t.Fatalf("read finding: %+v", f)
		}
		path := strings.TrimSuffix(strings.TrimPrefix(f.Message, "page reads "), ", which is outside the documentation source directory")
		outside = append(outside, strings.ReplaceAll(path, root, "%ROOT%"))
	}
	if !slices.Equal(outside, expected) {
		t.Fatalf("outside=%q want=%q", outside, expected)
	}
}

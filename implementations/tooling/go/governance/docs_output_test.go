package governance

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestPublicDocumentationOutputReference(t *testing.T) {
	fixture := readReference[struct {
		Base  map[string]string
		Cases []documentationOutputReference
	}](t, "docs-output-reference")
	for _, tc := range fixture.Cases {
		t.Run(tc.Name, func(t *testing.T) { checkDocumentationOutputReference(t, fixture.Base, tc) })
	}
}

type documentationOutputReference struct {
	Name           string
	AbsoluteOutput bool
	Changes        map[string]*string
	Links          map[string]string
	Findings       []Finding
}

func checkDocumentationOutputReference(t *testing.T, base map[string]string, tc documentationOutputReference) {
	t.Helper()

	root := seedRepositoryReference(t, repositoryReference{Files: deltaFiles(base, tc.Changes)})
	for name, target := range tc.Links {
		if !repositoryPath(name) {
			t.Fatal("invalid fixture link")
		}
		destination := filepath.Join(root, name)
		if err := os.MkdirAll(filepath.Dir(destination), 0o700); err != nil {
			t.Fatal(err)
		}
		if err := os.Symlink(strings.ReplaceAll(target, "<ROOT>", root), destination); err != nil {
			t.Fatal(err)
		}
	}
	output := "site"
	if tc.AbsoluteOutput {
		output = filepath.Join(root, output)
	}
	for i, f := range tc.Findings {
		if f.Path != nil {
			name := strings.ReplaceAll(*f.Path, "<ROOT>", root)
			tc.Findings[i].Path = &name
		}
	}
	report, err := Check(t.Context(), Request{Tool: "public-docs", Root: root, OutputRoot: output})
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(tc.Findings, report.Findings); diff != "" {
		t.Errorf("output (-reference +Go):\n%s", diff)
	}
}

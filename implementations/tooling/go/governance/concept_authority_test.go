package governance

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestConceptAuthorityReference(t *testing.T) {
	fixture := readReference[deltaRepositoryReference](t, "concept-reference")
	c := new(checker)
	for _, tc := range fixture.Cases {
		t.Run(tc.Name, func(t *testing.T) {
			root := seedRepositoryReference(t, repositoryReference{Files: deltaFiles(fixture.Base, tc.Changes)})
			report, err := c.evaluate(t.Context(), Request{Tool: "concept-authority-governance", Root: root})
			if err != nil {
				t.Fatal(err)
			}
			want := finish(tc.Findings)
			// Model/decoder prose can differ; rule, path, order and verdict cannot.
			conceptDiagnosticProse(report.Findings)
			conceptDiagnosticProse(want.Findings)
			if diff := cmp.Diff(want, report); diff != "" {
				t.Errorf("concept authority (-want +got):\n%s", diff)
			}
		})
	}
}

func conceptDiagnosticProse(findings []Finding) {
	for i := range findings {
		if strings.HasSuffix(findings[i].RuleID, "-catalog-invalid") {
			findings[i].Message = "invalid catalog"
		}
	}
}

func TestConceptAuthorityRepository(t *testing.T) {
	report, err := Check(t.Context(), Request{Tool: "concept-authority-governance", Root: "../../../.."})
	if err != nil || report.ExitCode != 0 {
		t.Fatalf("repository concept authority=%+v, %v", report, err)
	}
}

func TestConceptAuthorityFileBoundaries(t *testing.T) {
	for _, kind := range []string{"inside-catalog-link", "outside-catalog-link", "inside-adr-link", "outside-adr-link", "invalid-adr-text", "invalid-catalog-text"} {
		t.Run(kind, func(t *testing.T) { checkConceptBoundary(t, kind) })
	}
}

func checkConceptBoundary(t *testing.T, kind string) {
	t.Helper()
	root := deltaFixture(t, "concept-reference", "valid")
	want := 1
	switch kind {
	case "inside-catalog-link", "outside-catalog-link":
		target := filepath.Join(root, "families.json")
		if kind == "outside-catalog-link" {
			target = filepath.Join(t.TempDir(), "families.json")
		} else {
			want = 0
		}
		moveConceptLink(t, filepath.Join(root, conceptFamiliesPath), target)
	case "inside-adr-link", "outside-adr-link":
		target := filepath.Join(root, "reviewed.md")
		if kind == "outside-adr-link" {
			target = filepath.Join(t.TempDir(), "reviewed.md")
		} else {
			want = 0
		}
		moveConceptLink(t, filepath.Join(root, adrDirectory, "adr-001-concept-families.md"), target)
	case "invalid-adr-text":
		testWrite(t, root, adrDirectory+"/adr-001-concept-families.md", []byte{0xff})
	case "invalid-catalog-text":
		testWrite(t, root, conceptFamiliesPath, []byte{0xff})
	}
	report, err := Check(t.Context(), Request{Tool: "concept-authority-governance", Root: root})
	if err != nil || report.ExitCode != want {
		t.Fatalf("boundary report=%+v error=%v want exit=%d", report, err, want)
	}
}

func moveConceptLink(t *testing.T, name, target string) {
	t.Helper()
	if err := os.Rename(name, target); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(target, name); err != nil {
		t.Fatal(err)
	}
}

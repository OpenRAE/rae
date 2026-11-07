package governance

import (
	"maps"
	"os"
	"path/filepath"
	"testing"

	"github.com/google/go-cmp/cmp"
)

type editedPolicyReference struct {
	Name        string
	Error       string
	Changes     map[string]*string
	JSONEdits   map[string][]referenceJSONEdit
	Directories []string
	Findings    []Finding
	VerdictOnly bool
}

func TestAuthorityBoundaryReference(t *testing.T) {
	fixture := readReference[struct {
		Base  map[string]string
		Cases []editedPolicyReference
	}](t, "authority-reference")
	for _, tc := range fixture.Cases {
		t.Run(tc.Name, func(t *testing.T) { checkEditedPolicyReference(t, "authority-boundary", fixture.Base, tc) })
	}
}
func checkEditedPolicyReference(t *testing.T, tool string, base map[string]string, tc editedPolicyReference) {
	t.Helper()
	changes := referenceJSONEdits(t, base, tc.JSONEdits)
	maps.Copy(changes, tc.Changes)
	root := seedRepositoryReference(t, repositoryReference{Files: deltaFiles(base, changes)})
	for _, name := range tc.Directories {
		if !repositoryPath(name) {
			t.Fatal("unsafe fixture directory")
		}
		if err := os.MkdirAll(filepath.Join(root, name), 0o700); err != nil {
			t.Fatal(err)
		}
	}
	report, err := Check(t.Context(), Request{Tool: tool, Root: root})
	if tc.Error != "" {
		if err == nil {
			t.Fatal("reference error became a policy verdict")
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	if tc.VerdictOnly {
		if (len(report.Findings) == 0) != (len(tc.Findings) == 0) {
			t.Fatalf("verdict changed: %+v want %+v", report, tc.Findings)
		}
		return
	}
	if diff := cmp.Diff(tc.Findings, report.Findings); diff != "" {
		t.Fatalf("findings (-reference +Go):\n%s", diff)
	}
}

func TestAuthorityBoundaryRepository(t *testing.T) {
	report, err := Check(t.Context(), Request{Tool: "authority-boundary", Root: "../../../.."})
	if err != nil || len(report.Findings) > 0 {
		t.Fatalf("repository authority=%+v, %v", report, err)
	}
}

func TestAuthorityBoundaryReadErrors(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root bypasses file read permissions")
	}
	fixture := readReference[struct{ Base map[string]string }](t, "authority-reference")
	for _, name := range []string{boundaryPolicy, "contracts/schemas"} {
		t.Run(name, func(t *testing.T) {
			root := seedRepositoryReference(t, repositoryReference{Files: fixture.Base})
			selected := filepath.Join(root, name)
			before, err := os.Stat(selected)
			if err != nil {
				t.Fatal(err)
			}
			if chmodErr := os.Chmod(selected, 0); chmodErr != nil {
				t.Fatal(chmodErr)
			}
			t.Cleanup(func() {
				if err := os.Chmod(selected, before.Mode().Perm()); err != nil {
					t.Error(err)
				}
			})
			if report, err := Check(t.Context(), Request{Tool: "authority-boundary", Root: root}); err == nil {
				t.Fatalf("operational read error became a suppressible report: %+v", report)
			}
		})
	}
}

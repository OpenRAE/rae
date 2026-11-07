package governance

import (
	"errors"
	"io/fs"
	"path/filepath"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func TestRepositoryPolicyErrorCategories(t *testing.T) {
	_, err := Check(t.Context(), Request{Tool: "project-positioning", Root: filepath.Join(t.TempDir(), "missing")})
	if category, known := fault.CategoryOf(err); !known || category != fault.Operational || !errors.Is(err, fs.ErrNotExist) {
		t.Fatalf("missing repository category=%v known=%t error=%v", category, known, err)
	}
	input := classifyPolicyError(errNotUTF8)
	if category, known := fault.CategoryOf(input); !known || category != fault.InvalidInput || !errors.Is(input, errNotUTF8) {
		t.Fatalf("invalid source category=%v known=%t error=%v", category, known, input)
	}
	defect := errors.New("unexpected internal defect")
	classified := classifyPolicyError(defect)
	if _, known := fault.CategoryOf(classified); known || !errors.Is(classified, defect) {
		t.Fatal("unexpected defect was reclassified as an operational input failure")
	}
}

func TestReferenceInputErrorCategories(t *testing.T) {
	for _, err := range []error{policyInputError("invalid policy"), requirementError("Invalid requirement."), scopeError(scopeReadFailure)} {
		if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
			t.Errorf("category=%v known=%t, want the canonical invalid-input category", category, ok)
		}
	}
}

func TestExplicitEmptyRequirementBranch(t *testing.T) {
	t.Setenv("RAES_REQUIREMENT_BRANCH", "feature-GOV-001")
	t.Setenv("RAES_REQUIREMENT_UID", "")
	empty := ""
	report, err := Check(t.Context(), Request{Tool: "requirement-context", Root: t.TempDir(), Branch: &empty})
	if err != nil {
		t.Fatal(err)
	}
	if report.Text != "\n" {
		t.Errorf("explicit empty branch result=%q, want an empty context", report.Text)
	}
}

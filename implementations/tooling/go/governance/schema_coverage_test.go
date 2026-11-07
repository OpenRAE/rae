package governance

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"slices"
	"testing"

	"github.com/google/go-cmp/cmp"
)

type coverageReference struct {
	repositoryReference

	ErrorType     string
	NativeRefusal string
	Padding       map[string]int
}

func TestSchemaCoverageReference(t *testing.T) {
	for _, tc := range readReference[[]coverageReference](t, "coverage-reference") {
		t.Run(tc.Name, func(t *testing.T) { checkCoverageReference(t, tc) })
	}
}

func checkCoverageReference(t *testing.T, tc coverageReference) {
	t.Helper()
	root := seedRepositoryReference(t, tc.repositoryReference)
	for name, size := range tc.Padding {
		data, err := os.ReadFile(filepath.Join(root, name)) // #nosec G304 -- Recorded input recipe under a private fixture root.
		if err != nil {
			t.Fatal(err)
		}
		testWrite(t, root, name, append(data, bytes.Repeat([]byte{' '}, size-len(data))...))
	}
	request := Request{Tool: schemaCoverageCheck, Root: root}
	report, err := Check(t.Context(), request)
	if tc.NativeRefusal != "" {
		checkApprovedCoverageRefusal(t, tc.NativeRefusal, report, err)
		return
	}
	if tc.ErrorType != "" {
		if err == nil {
			t.Fatalf("reference %s became verdict %+v", tc.ErrorType, report)
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(tc.Findings, report.Findings); diff != "" {
		t.Errorf("findings (-want +got):\n%s", diff)
	}
	want := 0
	if len(tc.Findings) > 0 {
		want = 1
	}
	if report.ExitCode != want {
		t.Errorf("exit=%d want=%d", report.ExitCode, want)
	}
	request.Mode = Inventory
	report, err = Check(t.Context(), request)
	if err != nil || report.ExitCode != 0 || report.Text != tc.Text {
		t.Errorf("inventory text=%q want=%q error=%v", report.Text, tc.Text, err)
	}
}

func TestSchemaCoverageRepository(t *testing.T) {
	report, err := Check(t.Context(), Request{Tool: schemaCoverageCheck, Root: "../../../.."})
	if err != nil || report.ExitCode != 0 {
		t.Fatalf("coverage repository: %+v %v", report, err)
	}
}

func TestSchemaCoverageChangedSchema(t *testing.T) {
	rows := readReference[[]repositoryReference](t, "coverage-reference")
	root := seedRepositoryReference(t, rows[0])
	report, err := Check(t.Context(), Request{Tool: schemaCoverageCheck, Root: root})
	if err != nil || report.ExitCode != 0 {
		t.Fatalf("positive declaration: %+v %v", report, err)
	}
	testWrite(t, root, "contracts/schemas/example/example-v1.json", []byte(`{"type":"integer"}`))
	report, err = Check(t.Context(), Request{Tool: schemaCoverageCheck, Root: root})
	if err != nil || report.ExitCode != 1 || !slices.ContainsFunc(report.Findings, func(f Finding) bool { return f.RuleID == coverageDeclarationRule }) {
		t.Fatalf("changed schema did not invalidate evidence: %+v %v", report, err)
	}
}

func checkApprovedCoverageRefusal(t *testing.T, reason string, report Report, err error) {
	t.Helper()
	if reason == "standard-regexp" {
		if !errors.Is(err, errSchemaPattern) {
			t.Fatalf("unsupported pattern became ordinary verdict: %+v %v", report, err)
		}
		return
	}
	// These two stricter profiles were explicitly approved on2026-11-07. The
	// fixture retains Python's original successful verdict for review.
	if err != nil || report.ExitCode != 1 || !slices.ContainsFunc(report.Findings, func(f Finding) bool { return f.RuleID == coverageDeclarationRule }) {
		t.Fatalf("approved %s refusal missing: %+v %v", reason, report, err)
	}
}

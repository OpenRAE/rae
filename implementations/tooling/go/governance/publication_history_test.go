package governance

import (
	"os"
	"path/filepath"
	"slices"
	"testing"
)

type publicationHistoryReference struct {
	Name, Revision, ErrorType string
	Base                      map[string]string
	Changes                   map[string]*string
	Messages                  []string
}

func TestPublicationHistoryReference(t *testing.T) {
	for _, tc := range readReference[[]publicationHistoryReference](t, "publication-history-reference") {
		t.Run(tc.Name, func(t *testing.T) { checkPublicationHistoryReference(t, tc) })
	}
}

func checkPublicationHistoryReference(t *testing.T, tc publicationHistoryReference) {
	t.Helper()
	root := testGitRepository(t)
	for name, text := range tc.Base {
		testWrite(t, root, name, []byte(text))
	}
	testGit(t, root, "add", ".")
	testGit(t, root, "commit", "-qm", "base")
	for name, text := range tc.Changes {
		if text == nil {
			if err := os.Remove(filepath.Join(root, name)); err != nil {
				t.Fatal(err)
			}
		} else {
			testWrite(t, root, name, []byte(*text))
		}
	}
	report, err := Check(t.Context(), Request{Tool: schemaPublicationCheck, Root: root, BaseRevision: tc.Revision})
	if tc.ErrorType != "" {
		checkPublicationReferenceError(t, err, tc.ErrorType)
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	messages := make([]string, len(report.Findings))
	for i, finding := range report.Findings {
		messages[i] = finding.Message
	}
	if !slices.Equal(messages, tc.Messages) {
		t.Errorf("history findings=%q want=%q", messages, tc.Messages)
	}
	want := 0
	if len(tc.Messages) > 0 {
		want = 1
	}
	if report.ExitCode != want {
		t.Fatalf("history exit=%d want=%d", report.ExitCode, want)
	}
}

package governance

import (
	"slices"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

type publicationReference struct {
	Name, ErrorType string
	Changes         map[string]*string
	Messages        []string
	ProseFree       bool
}

func TestSchemaPublicationReference(t *testing.T) {
	fixture := readReference[struct {
		Base  map[string]string
		Cases []publicationReference
	}](t, "publication-reference")
	for _, tc := range fixture.Cases {
		t.Run(tc.Name, func(t *testing.T) { checkPublicationReference(t, fixture.Base, tc) })
	}
}

func checkPublicationReference(t *testing.T, base map[string]string, tc publicationReference) {
	t.Helper()
	root := seedRepositoryReference(t, repositoryReference{Files: deltaFiles(base, tc.Changes)})
	report, err := Check(t.Context(), Request{Tool: schemaPublicationCheck, Root: root})
	if tc.ErrorType != "" {
		checkPublicationReferenceError(t, err, tc.ErrorType)
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	messages := make([]string, len(report.Findings))
	for i, f := range report.Findings {
		if f.RuleID != schemaPublicationCheck || f.Path != nil || f.Status != "" {
			t.Fatalf("publication finding has a different code/path/status: %+v", f)
		}
		messages[i] = f.Message
	}
	if tc.ProseFree {
		if len(messages) != len(tc.Messages) {
			t.Errorf("publication finding count=%d want=%d: %q", len(messages), len(tc.Messages), messages)
		}
	} else if !slices.Equal(messages, tc.Messages) {
		t.Errorf("publication findings=%q want=%q", messages, tc.Messages)
	}
	want := 0
	if len(tc.Messages) > 0 {
		want = 1
	}
	if report.ExitCode != want {
		t.Fatalf("publication exit=%d want=%d", report.ExitCode, want)
	}
}

func checkPublicationReferenceError(t *testing.T, err error, referenceType string) {
	t.Helper()
	if err == nil {
		t.Fatalf("reference %s became a policy verdict", referenceType)
	}
	// The reference's unhashable metadata TypeError is malformed candidate
	// input, classified through the canonical Go input-error owner.
	expected := referenceType == "InvalidInputError" || referenceType == "UnicodeDecodeError" || referenceType == "OSError" || referenceType == "IsADirectoryError" || referenceType == "TypeError"
	if _, known := fault.CategoryOf(err); known != expected {
		t.Fatalf("reference %s native error=%v known=%t want known=%t", referenceType, err, known, expected)
	}
}

func TestSchemaPublicationRepository(t *testing.T) {
	report, err := Check(t.Context(), Request{Tool: schemaPublicationCheck, Root: "../../../.."})
	if err != nil || report.ExitCode != 0 {
		t.Fatalf("repository schema publication=%+v error=%v", report, err)
	}
}

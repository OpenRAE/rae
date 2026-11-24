package governance

import (
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestDocumentationMarkupReference(t *testing.T) {
	for _, tc := range readReference[[]struct {
		Name, Text        string
		Links, Directives []string
	}](t, "docs-markup-reference") {
		t.Run(tc.Name, func(t *testing.T) {
			if diff := cmp.Diff(tc.Links, markdownLinkTargets(tc.Text)); diff != "" {
				t.Errorf("links (-reference +Go):\n%s", diff)
			}
			if diff := cmp.Diff(tc.Directives, directiveTargets(tc.Text)); diff != "" {
				t.Errorf("directives (-reference +Go):\n%s", diff)
			}
		})
	}
}

func TestPublicDocumentationReference(t *testing.T) {
	runDeltaReference(t, "public-docs", "public-docs-reference")
}

func TestPublicDocumentationRepository(t *testing.T) {
	report, err := Check(t.Context(), Request{Tool: "public-docs", Root: "../../../.."})
	if err != nil || len(report.Findings) != 0 {
		t.Fatalf("repository documentation=%+v, %v", report, err)
	}
}

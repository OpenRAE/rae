package governance

import (
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestRepoPolicyReference(t *testing.T) {
	fixture := readReference[struct {
		Base  map[string]string
		Cases []struct {
			Name, CheckSet, Error string
			Changes               map[string]*string
			Changed               []string
			Findings              []Finding
		}
	}](t, "repo-reference")
	for _, tc := range fixture.Cases {
		t.Run(tc.Name, func(t *testing.T) {
			root := seedRepositoryReference(t, repositoryReference{Files: deltaFiles(fixture.Base, tc.Changes)})
			report, err := Check(t.Context(), Request{Tool: "repo-policy", Root: root, Paths: tc.Changed, CheckSet: tc.CheckSet})
			if tc.Error != "" {
				if err == nil {
					t.Fatalf("source error became a policy verdict: %+v", report)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if diff := cmp.Diff(tc.Findings, report.Findings); diff != "" {
				t.Fatalf("findings (-source +native):\n%s", diff)
			}
		})
	}
}

func TestRepoPolicyRepository(t *testing.T) {
	report, err := Check(t.Context(), Request{Tool: "repo-policy", Root: "../../../..", Paths: []string{}, CheckSet: "full"})
	if err != nil || len(report.Findings) > 0 {
		t.Fatalf("repository policy=%+v, %v", report, err)
	}
}

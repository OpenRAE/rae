package governance

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestPRBodyIssueHTTP(t *testing.T) {
	for _, tc := range []struct {
		name, body           string
		status               int
		exists, open, failed bool
		uid                  string
	}{
		{"open", `{"body":"","state":"open"}`, 200, true, true, false, ""},
		{"closed", `{"body":null,"state":"closed"}`, 200, true, false, false, ""},
		{"requirements", `{"body":"## Requirements\n- SEM-218\n","state":"open"}`, 200, true, true, false, "SEM-218"},
		{"pull-request", `{"body":null,"state":"open","pull_request":{}}`, 200, false, false, false, ""},
		{"missing", `{}`, 404, false, false, false, ""},
		{"server", `{}`, 503, false, false, true, ""},
		{"multiple-choices", `{"body":"","state":"open"}`, 300, false, false, true, ""},
		{"no-location", `{"body":"","state":"open"}`, 302, false, false, true, ""},
		{"not-modified", ``, 304, false, false, true, ""},
		{"not-object", `[]`, 200, false, false, true, ""},
		{"missing-body", `{"state":"open"}`, 200, false, false, true, ""},
		{"wrong-body", `{"body":42,"state":"open"}`, 200, false, false, true, ""},
		{"invalid-json", `[`, 200, false, false, true, ""},
	} {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				checkIssueRequest(t, r)
				w.WriteHeader(tc.status)
				_, _ = w.Write([]byte(tc.body))
			}))
			defer server.Close()
			facts, err := prReadGitHubIssue(t.Context(), server.Client(), server.URL, "OpenRAE/rae", "test-only-token", "123")
			if tc.failed {
				if _, expected := errors.AsType[prLookupError](err); !expected {
					t.Fatalf("invalid issue response accepted: %+v, %v", facts, err)
				}
				return
			}
			if err != nil || facts.exists != tc.exists || facts.open != tc.open || strings.Join(facts.uids, ",") != tc.uid {
				t.Fatalf("issue facts=%+v error=%v", facts, err)
			}
		})
	}
}

func checkIssueRequest(t *testing.T, r *http.Request) {
	t.Helper()
	if r.Method != http.MethodGet || r.URL.Path != "/repos/OpenRAE/rae/issues/123" || r.Header.Get("Authorization") != "Bearer test-only-token" || r.Header.Get("X-Github-Api-Version") != "2022-11-28" {
		t.Error("unexpected issue request")
	}
}

func TestPRBodyLookupDefectsPropagate(t *testing.T) {
	defect := errors.New("unexpected lookup defect")
	lookup := func(context.Context, string) (prIssueFacts, error) { return prIssueFacts{}, defect }
	_, err := prInspectIssue(t.Context(), prIssueReference{"Closes", "123"}, lookup)
	if !errors.Is(err, defect) {
		t.Fatalf("lookup defect became a finding: %v", err)
	}
	_, err = prOpenIssueReport(t.Context(), "Closes #123", lookup, "7")
	if !errors.Is(err, defect) {
		t.Fatalf("audit defect became an inspection error: %v", err)
	}
}

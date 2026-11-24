package governance

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestRequirementHTTPBodyCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	headers := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		if err := http.NewResponseController(w).Flush(); err != nil {
			return
		}
		close(headers)
		<-r.Context().Done()
	}))
	defer server.Close()
	client := server.Client()
	client.Timeout = time.Second
	authority := httpAuthority{base: server.URL, client: client}
	done := make(chan error, 1)
	go func() {
		_, err := authority.request(ctx, "/")
		done <- err
	}()
	select {
	case <-headers:
	case err := <-done:
		t.Fatalf("request completed before body cancellation: %v", err)
	}
	cancel()
	if err := <-done; !errors.Is(err, context.Canceled) {
		t.Fatalf("body cancellation lost its cause: %v", err)
	}
}

type httpReference struct {
	Name   string `json:"Name"`
	Status int    `json:"Status"`
	Body   string `json:"Body"`
	Links  string `json:"Links"`
	Error  string `json:"Error"`
	Auth   bool   `json:"Auth"`
}

func TestRequirementHTTPReference(t *testing.T) {
	for _, tc := range readReference[[]httpReference](t, "http-reference") {
		t.Run(tc.Name, func(t *testing.T) { checkHTTPReference(t, tc) })
	}
}

func TestRequirementHTTPRedirectWithoutLocation(t *testing.T) {
	checkHTTPReference(t, httpReference{Status: http.StatusFound, Body: `{"id":"r1","uid":"GOV-001","status":"ACTIVE"}`, Links: "[]", Error: "HTTP 302"})
}

func TestRequirementHTTPTimeoutSelection(t *testing.T) {
	for _, tc := range []struct {
		value string
		want  time.Duration
	}{{"", 5 * time.Second}, {"12.5", 12500 * time.Millisecond}, {"not-a-number", 5 * time.Second}, {"0", 5 * time.Second}, {"-1", 5 * time.Second}} {
		t.Run(tc.value, func(t *testing.T) {
			t.Setenv("GC_HTTP_TIMEOUT_SECONDS", tc.value)
			if got := requirementHTTPTimeout(); got != tc.want {
				t.Fatalf("timeout=%v want %v", got, tc.want)
			}
		})
	}
}

func TestRequirementHTTPLinkSpelling(t *testing.T) {
	for _, source := range []string{`{"linkType":"IMPLEMENTS","artifactType":"SPEC","artifactIdentifier":"contract"}`, `{"link_type":null,"linkType":"IMPLEMENTS","artifact_type":null,"artifactType":"SPEC","artifact_identifier":null,"artifactIdentifier":"contract"}`, `{"link_type":"IMPLEMENTS","linkType":"OTHER","artifact_type":"SPEC","artifactType":"OTHER","artifact_identifier":"contract","artifactIdentifier":"other"}`} {
		value, err := decodeJSON([]byte(source), 0, false)
		if err != nil {
			t.Fatal(err)
		}
		link, err := httpRequirementLink(value)
		if err != nil || link.kind != "IMPLEMENTS" || link.artifact != "SPEC" || link.identifier != "contract" {
			t.Fatalf("traceability=%+v, %v", link, err)
		}
	}
}

func checkHTTPReference(t *testing.T, tc httpReference) {
	t.Helper()
	server := httptest.NewServer(referenceHTTPHandler(t, tc))
	t.Cleanup(server.Close)
	t.Setenv("GC_BASE_URL", server.URL+"/")
	t.Setenv("GROUND_CONTROL_API_TOKEN", "fixture")
	dir := t.TempDir()
	testWrite(t, dir, exceptionPath, []byte("exceptions: []\n"))
	r, err := openRepository(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = r.root.Close() })
	policy := &requirementPolicy{project: "project with space", phases: []requirementPhase{{id: "one", uids: []string{"GOV-001"}}}}
	c := &checker{request: Request{}}
	for _, required := range []bool{false, true} {
		report, err := c.httpRequirements(t.Context(), r, policy, nil, "GOV-001", nil, required)
		if err != nil {
			t.Fatal(err)
		}
		checkHTTPReport(t, tc, report, required)
	}
}

func checkHTTPReport(t *testing.T, tc httpReference, report Report, required bool) {
	t.Helper()
	if tc.Error == "" {
		if len(report.Findings) != 0 || report.ExitCode != 0 {
			t.Fatalf("successful authority response=%+v", report)
		}
		return
	}
	want := unevaluatedGovernance("ground-control-unavailable", tc.Error, required)
	if tc.Auth {
		want = unevaluatedGovernance("ground-control-auth-required", "Ground Control requires authentication ("+tc.Error+")", required)
	}
	if len(report.Findings) != 1 || report.Findings[0].RuleID != want.Findings[0].RuleID || report.Findings[0].Message != want.Findings[0].Message || report.Status != want.Status || report.ExitCode != want.ExitCode {
		t.Fatalf("authority failure=%+v, want %+v", report, want)
	}
}

func referenceHTTPHandler(t *testing.T, tc httpReference) http.HandlerFunc {
	t.Helper()
	return func(w http.ResponseWriter, req *http.Request) {
		if req.Header.Get("X-Actor") != "repo-policy" || req.Header.Get("Authorization") != "Bearer fixture" {
			t.Error("authority request headers differ")
		}
		if strings.HasSuffix(req.URL.Path, "/traceability") {
			_, _ = io.WriteString(w, tc.Links)
			return
		}
		if req.URL.Query().Get("project") != "project with space" {
			t.Error("authority request lost project parameter")
		}
		w.WriteHeader(tc.Status)
		_, _ = io.WriteString(w, tc.Body)
	}
}

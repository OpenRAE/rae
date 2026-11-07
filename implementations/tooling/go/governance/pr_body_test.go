package governance

import (
	"encoding/json"
	"path/filepath"
	"testing"

	"github.com/google/go-cmp/cmp"
)

type prBodyReference struct {
	Name, Body, RawBody, Issues, Text string
	Findings                          []Finding
	Audit                             bool
}

func TestPRBodyReference(t *testing.T) {
	for _, tc := range readReference[[]prBodyReference](t, "pr-body-reference") {
		t.Run(tc.Name, func(t *testing.T) { checkPRBodyReference(t, tc) })
	}
}

func checkPRBodyReference(t *testing.T, tc prBodyReference) {
	t.Helper()
	var body any = tc.Body
	if tc.RawBody != "" {
		body = json.RawMessage(tc.RawBody)
	}
	request := prBodyFixture(t, prBodyEvent(body), tc.Issues)
	if tc.Audit {
		request.Mode = ClosingAudit
	}
	report, err := Check(t.Context(), request)
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(tc.Findings, report.Findings); diff != "" {
		t.Errorf("body findings (-want +got):\n%s", diff)
	}
	wantExit := 0
	if len(tc.Findings) > 0 {
		wantExit = 1
	}
	if report.ExitCode != wantExit || report.Text != tc.Text {
		t.Errorf("exit=%d want=%d, text=%q want=%q", report.ExitCode, wantExit, report.Text, tc.Text)
	}
}

func prBodyEvent(body any) map[string]any {
	return map[string]any{"repository": map[string]string{"full_name": "OpenRAE/rae"}, "pull_request": map[string]any{"number": 7, "body": body, "user": map[string]string{"login": "contributor"}, "head": map[string]string{"ref": "1799-go-policy-checks"}}}
}

func prBodyFixture(t *testing.T, event map[string]any, issues string) Request {
	t.Helper()
	dir := t.TempDir()
	data, err := json.Marshal(event)
	if err != nil {
		t.Fatal(err)
	}
	testWrite(t, dir, "event.json", data)
	testWrite(t, dir, "issues.json", []byte(issues))
	return Request{Tool: "pr-body", Root: dir, EventPath: filepath.Join(dir, "event.json"), IssuesFile: filepath.Join(dir, "issues.json")}
}

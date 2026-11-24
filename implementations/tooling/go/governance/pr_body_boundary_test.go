package governance

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func prBodyExample(t *testing.T) string {
	t.Helper()
	return readReference[[]prBodyReference](t, "pr-body-reference")[0].Body
}

func checkPRBodyExit(t *testing.T, request Request, wanted int) Report {
	t.Helper()
	report, err := Check(t.Context(), request)
	if err != nil {
		t.Fatal(err)
	}
	if report.ExitCode != wanted {
		t.Fatalf("exit=%d want=%d findings=%v", report.ExitCode, wanted, report.Findings)
	}
	if wanted != 0 && len(report.Findings) == 0 {
		t.Fatal("failed body evaluation has no diagnostic")
	}
	return report
}

func TestPRBodyExternalInputs(t *testing.T) {
	request := prBodyFixture(t, prBodyEvent(prBodyExample(t)), `{"123":"open"}`)
	request.Root = t.TempDir()
	checkPRBodyExit(t, request, 0)
}

func TestPRBodyFileBoundaries(t *testing.T) {
	for _, kind := range []string{"event-link", "issues-link", "parent-link", "event-array", "event-utf8", "event-directory", "missing-event", "missing-issues", "duplicate-members", "secret-path"} {
		t.Run(kind, func(t *testing.T) { checkPRBodyFileBoundary(t, kind) })
	}
}

func checkPRBodyFileBoundary(t *testing.T, kind string) {
	t.Helper()
	request := prBodyFixture(t, prBodyEvent(prBodyExample(t)), `{"123":"open"}`)
	wanted := 2
	switch kind {
	case "event-link", "issues-link":
		link := filepath.Join(request.Root, "input-link.json")
		target := request.EventPath
		if kind == "issues-link" {
			target = request.IssuesFile
		}
		if err := os.Symlink(target, link); err != nil {
			t.Fatal(err)
		}
		if kind == "event-link" {
			request.EventPath = link
		} else {
			request.IssuesFile = link
		}
	case "parent-link":
		parent := t.TempDir()
		if err := os.Symlink(request.Root, filepath.Join(parent, "inputs")); err != nil {
			t.Fatal(err)
		}
		request.EventPath = filepath.Join(parent, "inputs", "event.json")
		request.IssuesFile = filepath.Join(parent, "inputs", "issues.json")
		wanted = 0
	case "event-array":
		testWrite(t, request.Root, "event.json", []byte(`[]`))
	case "event-utf8":
		testWrite(t, request.Root, "event.json", []byte{0xff})
	case "event-directory":
		request.EventPath = request.Root
	case "missing-event":
		request.EventPath = filepath.Join(request.Root, "missing.json")
	case "missing-issues":
		request.IssuesFile = filepath.Join(request.Root, "missing.json")
	case "duplicate-members":
		testWrite(t, request.Root, "issues.json", []byte(`{"123":"closed","123":"open"}`))
		wanted = 0
	case "secret-path":
		request.EventPath = filepath.Join(request.Root, ".secrets", "event.json")
	}
	checkPRBodyExit(t, request, wanted)
}

func TestPRBodyEventCannotSelectFixture(t *testing.T) {
	t.Setenv("GH_TOKEN", "")
	event := prBodyEvent(prBodyExample(t))
	event["issues_file"] = "issues.json"
	event["issue_facts"] = map[string]string{"123": "open"}
	request := prBodyFixture(t, event, `{"123":"open"}`)
	request.IssuesFile = ""
	report := checkPRBodyExit(t, request, 2)
	if report.Findings[0].Message != "GH_TOKEN is required to verify closing issues" {
		t.Fatalf("event affected fixture authority: %v", report.Findings)
	}
}

func TestPRBodyAutomation(t *testing.T) {
	t.Setenv("GH_TOKEN", "")
	t.Setenv("GITHUB_REPOSITORY", "")
	for _, tc := range []struct {
		author, sender, head string
		exempt               bool
	}{
		{"dependabot[bot]", "human", "updates", true},
		{"release-please[bot]", "human", "release", true},
		{"github-actions[bot]", "human", "release-please--branches--main", true},
		{"github-actions[bot]", "human", "ordinary", false},
		{"human", "dependabot[bot]", "updates", false},
	} {
		t.Run(tc.author+"/"+tc.head, func(t *testing.T) {
			event := prBodyEvent("")
			event["repository"] = map[string]string{}
			event["sender"] = map[string]string{"login": tc.sender}
			event["pull_request"] = map[string]any{"body": "", "user": map[string]string{"login": tc.author}, "head": map[string]string{"ref": tc.head}}
			request := prBodyFixture(t, event, `{}`)
			request.IssuesFile = ""
			wanted := 2
			if tc.exempt {
				wanted = 0
			}
			checkPRBodyExit(t, request, wanted)
		})
	}
}

func TestPRBodyRejectsMalformedAutomationBody(t *testing.T) {
	event := prBodyEvent(nil)
	event["pull_request"] = map[string]any{"body": nil, "user": map[string]string{"login": "dependabot[bot]"}}
	request := prBodyFixture(t, event, `{}`)
	checkPRBodyExit(t, request, 2)
}

func TestPRBodyOrdinaryEventJSON(t *testing.T) {
	request := prBodyFixture(t, prBodyEvent(prBodyExample(t)), `{"123":"open"}`)
	body, err := json.Marshal(prBodyExample(t))
	if err != nil {
		t.Fatal(err)
	}
	data := `{"ignored":NaN,"repository":{"full_name":"OpenRAE/rae"},"pull_request":{"body":null,"body":` + string(body) + `}}`
	testWrite(t, request.Root, "event.json", []byte(data))
	checkPRBodyExit(t, request, 0)
}

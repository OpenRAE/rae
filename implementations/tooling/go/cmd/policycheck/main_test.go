package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func commandFile(t *testing.T, name string, data []byte) string {
	t.Helper()
	name = filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(name, data, 0o600); err != nil {
		t.Fatal(err)
	}
	return name
}

func invoke(t *testing.T, want int, args ...string) (string, string) {
	t.Helper()
	var stdout, stderr bytes.Buffer
	if status := run(args, &stdout, &stderr); status != want {
		t.Fatalf("exit=%d want=%d stdout=%q stderr=%q", status, want, stdout.String(), stderr.String())
	}
	return stdout.String(), stderr.String()
}

func TestChangeSelectionFlags(t *testing.T) {
	request, _, err := parseRequest([]string{"--tool", "requirement-governance", "--base-rev=", "--branch="}, io.Discard)
	if err != nil {
		t.Fatal(err)
	}
	if request.Paths != nil || !request.BaseRevisionSet || request.Branch == nil || *request.Branch != "" {
		t.Fatalf("lost implicit paths or explicit empty selections: %+v", request)
	}
	request, _, err = parseRequest([]string{"--tool", "requirement-governance", "--staged", "requirements/GOV-918.md"}, io.Discard)
	if err != nil || len(request.Paths) != 1 || !request.Staged || request.BaseRevisionSet || request.Branch != nil {
		t.Fatalf("lost explicit paths or implicit selections: %+v, %v", request, err)
	}
}

func TestRepoPolicySelection(t *testing.T) {
	for _, args := range [][]string{{"--check-set=invalid"}, {"--base-rev="}, {"--staged", "--base-rev=-option"}} {
		if _, _, err := parseRequest(append([]string{"--tool=repo-policy"}, args...), io.Discard); err == nil {
			t.Fatalf("invalid selection accepted: %q", args)
		}
	}
	request, _, err := parseRequest([]string{"--tool=repo-policy", "--check-set=file-local", "./pkg//file.py", "pkg/../outside.py", "//absolute//file.py"}, io.Discard)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Join(request.Paths, "|") != "pkg/file.py|pkg/../outside.py|//absolute/file.py" {
		t.Fatalf("changed paths=%q", request.Paths)
	}
	root := t.TempDir()
	commandFile(t, "unused", nil)
	config := filepath.Join(root, "tools/policy")
	if err := os.MkdirAll(config, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(config, "adr_policy.yaml"), []byte("{}"), 0o600); err != nil {
		t.Fatal(err)
	}
	output, _ := invoke(t, 1, "--tool=repo-policy", "--repo-root", root, "--check-set=file-local", "--json", "../outside.py")
	var findings []struct {
		Rule string `json:"rule_id"`
	}
	if err := json.Unmarshal([]byte(output), &findings); err != nil {
		t.Fatal(err)
	}
	if len(findings) < 1 || findings[0].Rule != "policy-path-unsafe" {
		t.Fatalf("CLI refusal=%s", output)
	}
}

func TestExplicitEmptyVocabularyInputs(t *testing.T) {
	for _, flag := range []string{"local-input", "activitystreams-local-input", "fipa-local-input"} {
		request, _, err := parseRequest([]string{"--tool", "autonomous-behavior-vocabularies", "--verify-remote", "--" + flag + "="}, io.Discard)
		if err != nil {
			t.Fatal(err)
		}
		value := map[string]string{"local-input": request.LocalInput, "activitystreams-local-input": request.ActivityStreamsLocalInput, "fipa-local-input": request.FIPALocalInput}[flag]
		if value != "." {
			t.Fatalf("explicit --%s= became omitted input: %q", flag, value)
		}
	}
}

func TestTitleInputs(t *testing.T) {
	t.Setenv("GITHUB_EVENT_PATH", "")
	t.Setenv("PR_TITLE", "feat: environment title")
	t.Setenv("PR_BODY", "environment body")
	valid := commandFile(t, "event.json", []byte(`{"pull_request":{"title":"fix: event title","body":null},"unrelated":NaN}`))
	invalid := commandFile(t, "bad.json", []byte(`[`))
	for _, tc := range []struct {
		name string
		args []string
		want int
	}{
		{"environment", nil, 0},
		{"explicit-empty", []string{"--title="}, 1},
		{"explicit-valid", []string{"--title", "feat: explicit title", "--event-path", invalid}, 0},
		{"event", []string{"--event-path", valid}, 0},
		{"invalid-event", []string{"--event-path", invalid}, 2},
		{"missing-event", []string{"--event-path", invalid + ".missing"}, 2},
	} {
		t.Run(tc.name, func(t *testing.T) {
			invoke(t, tc.want, append([]string{"--tool", "pr-title"}, tc.args...)...)
		})
	}
}

func TestTitleEventTypes(t *testing.T) {
	for _, tc := range []struct {
		value string
		want  int
	}{
		{`null`, 2}, {`42`, 1}, {`false`, 1}, {`[]`, 1}, {`{}`, 1}, {`""`, 1}, {`"docs: explain policy"`, 0},
	} {
		t.Run(tc.value, func(t *testing.T) {
			event := commandFile(t, "event.json", []byte(`{"pull_request":{"title":`+tc.value+`}}`))
			invoke(t, tc.want, "--tool", "pr-title", "--event-path", event)
		})
	}
}

func TestTitleCommitMessages(t *testing.T) {
	for _, tc := range []struct {
		name, text string
		want       int
	}{
		{"ordinary", "fix: preserve names", 0},
		{"breaking", "fix: preserve names\r\n\r\nBREAKING CHANGE: retire " + "A" + "CES", 1},
		{"invalid-text", "\xff", 2},
	} {
		t.Run(tc.name, func(t *testing.T) {
			file := commandFile(t, "commits.txt", []byte(tc.text))
			invoke(t, tc.want, "--tool", "pr-title", "--title", "feat: preserve names", "--commit-messages-file", file)
		})
	}
	invoke(t, 2, "--tool", "pr-title", "--title", "feat: preserve names", "--commit-messages-file", filepath.Join(t.TempDir(), "missing"))
}

func TestTitleInputSymlinks(t *testing.T) {
	event := commandFile(t, "event.json", []byte(`{"pull_request":{"title":"feat: follow explicit input"}}`))
	commits := commandFile(t, "commits.txt", []byte("fix: retain explicit file reads"))
	for _, name := range []string{event, commits} {
		if err := os.Symlink(name, name+".link"); err != nil {
			t.Fatal(err)
		}
	}
	invoke(t, 0, "--tool", "pr-title", "--event-path", event+".link", "--commit-messages-file", commits+".link")
}

func bodyArguments(t *testing.T, body string) []string {
	t.Helper()
	event, err := json.Marshal(map[string]any{"repository": map[string]string{"full_name": "OpenRAE/rae"}, "pull_request": map[string]any{"number": 7, "body": body}})
	if err != nil {
		t.Fatal(err)
	}
	return []string{"--tool", "pr-body", "--event-path", commandFile(t, "event.json", event), "--issues-file", commandFile(t, "issues.json", []byte(`{"123":"open"}`))}
}

func validBody() string {
	return "## Summary\nPreserve reviewed policy checks.\n## Requirement UIDs\nGOV-918\n## Related Issues\nCloses #123\n## ADR Impact\nNo design changes.\n## Changes\nPort policy checks.\n## Test Plan\ngo test passed.\n## Ground Control Checks\nReviewed manually.\n## Traceability\nGOV-918\n## Checklist\nReviewed.\n"
}

func TestPRBodyOutput(t *testing.T) {
	stdout, stderr := invoke(t, 0, bodyArguments(t, validBody())...)
	if stdout != "pr-body-guard: OK\n" || stderr != "" {
		t.Fatalf("success output=%q, %q", stdout, stderr)
	}
	stdout, stderr = invoke(t, 1, bodyArguments(t, "")...)
	if stdout != "" || !strings.HasPrefix(stderr, "pr-body-guard: rejected pull request body\n- [required-section]") {
		t.Fatalf("rejection output=%q, %q", stdout, stderr)
	}
	args := bodyArguments(t, validBody())
	args[3] += ".missing"
	stdout, stderr = invoke(t, 2, args...)
	if stdout != "" || !strings.HasPrefix(stderr, "pr-body-guard: configuration error:") {
		t.Fatalf("configuration output=%q, %q", stdout, stderr)
	}
}

func TestPRBodyAuditDestinations(t *testing.T) {
	args := append(bodyArguments(t, validBody()), "--report-open-closing-issues")
	stdout, stderr := invoke(t, 0, args...)
	if !strings.Contains(stdout, "- `#123`") || stderr != "" {
		t.Fatalf("audit output=%q, %q", stdout, stderr)
	}
	name := filepath.Join(t.TempDir(), "summary.md")
	output, diagnostics := invoke(t, 0, append(args, "--summary-file", name)...)
	data, err := os.ReadFile(name) // #nosec G304 -- Read the audit destination in this test's temporary directory.
	if err != nil || string(data) != stdout || output != "" || diagnostics != "" {
		t.Fatalf("file audit=%q %v, stdout=%q stderr=%q", data, err, output, diagnostics)
	}
	invoke(t, 0, append(args, "--summary-file", name)...)
	hardLink := filepath.Join(t.TempDir(), "same-summary.md")
	if linkErr := os.Link(name, hardLink); linkErr != nil {
		t.Fatal(linkErr)
	}
	if writeErr := os.WriteFile(name, []byte("previous audit"), 0o600); writeErr != nil { // #nosec G304 -- Test-owned temporary audit destination.
		t.Fatal(writeErr)
	}
	invoke(t, 0, append(args, "--summary-file", name)...)
	linked, err := os.ReadFile(hardLink) // #nosec G304 -- Test-owned temporary hard link to the audit destination.
	if err != nil || string(linked) != stdout {
		t.Fatalf("hard-linked audit=%q %v", linked, err)
	}
	invoke(t, 2, append(args, "--summary-file", filepath.Join(name, "child"))...)
	link := filepath.Join(t.TempDir(), "summary-link.md")
	if err := os.Symlink(name, link); err != nil {
		t.Fatal(err)
	}
	invoke(t, 2, append(args, "--summary-file", link)...)
	invoke(t, 2, append(args, "--summary-file", filepath.Join(t.TempDir(), ".secrets", "summary.md"))...)
}

func TestPRBodyAuditPermissions(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root bypasses ordinary file write permission checks")
	}
	args := append(bodyArguments(t, validBody()), "--report-open-closing-issues")
	name := commandFile(t, "summary.md", []byte("original"))
	if err := os.Chmod(name, 0o400); err != nil {
		t.Fatal(err)
	}
	invoke(t, 2, append(args, "--summary-file", name)...)
	data, err := os.ReadFile(name) // #nosec G304 -- Test-owned temporary audit destination.
	if err != nil || string(data) != "original" {
		t.Fatalf("protected audit changed: %q %v", data, err)
	}
	if err := os.Chmod(name, 0o600); err != nil {
		t.Fatal(err)
	}
	parent := filepath.Dir(name)
	if err := os.Chmod(parent, 0o500); err != nil { // #nosec G302 -- Owner-only read/search tests an existing writable file in a non-writable parent.
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := os.Chmod(parent, 0o700); err != nil { // #nosec G302 -- Restore owner-only directory access for test cleanup.
			t.Error(err)
		}
	})
	invoke(t, 0, append(args, "--summary-file", name)...)
}

func commandLinkedParent(t *testing.T) (string, string, string) {
	t.Helper()
	wrong, selected := t.TempDir(), t.TempDir()
	if err := os.Mkdir(filepath.Join(selected, "deep"), 0o700); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(wrong, "link")
	if err := os.Symlink(filepath.Join(selected, "deep"), link); err != nil {
		t.Fatal(err)
	}
	return wrong, selected, link + string(filepath.Separator) + ".."
}

func TestPRInputLinkedParent(t *testing.T) {
	wrong, selected, parent := commandLinkedParent(t)
	if err := os.WriteFile(filepath.Join(wrong, "event.json"), []byte(`[]`), 0o600); err != nil {
		t.Fatal(err)
	}
	event := []byte(`{"pull_request":{"body":"","title":"feat: resolve selected input","user":{"login":"dependabot[bot]"}}}`)
	if err := os.WriteFile(filepath.Join(selected, "event.json"), event, 0o600); err != nil {
		t.Fatal(err)
	}
	for _, tool := range []string{"pr-title", prBodyTool} {
		invoke(t, 0, "--tool", tool, "--event-path", parent+string(filepath.Separator)+"event.json")
	}
	missingParent := selected + "/missing/../event.json"
	invoke(t, 2, "--tool", prBodyTool, "--event-path", missingParent)
}

func TestPRAuditLinkedParent(t *testing.T) {
	wrong, selected, parent := commandLinkedParent(t)
	protected := filepath.Join(wrong, "summary.md")
	if err := os.WriteFile(protected, []byte("keep original"), 0o600); err != nil {
		t.Fatal(err)
	}
	args := append(bodyArguments(t, validBody()), "--report-open-closing-issues", "--summary-file", parent+string(filepath.Separator)+"summary.md")
	invoke(t, 0, args...)
	text, err := os.ReadFile(protected) // #nosec G304 -- Private fixture whose contents must remain unchanged.
	if err != nil || string(text) != "keep original" {
		t.Fatalf("wrote the wrong summary destination: %q, %v", text, err)
	}
	report, err := os.ReadFile(filepath.Join(selected, "summary.md")) // #nosec G304 -- Explicit selected fixture destination.
	if err != nil || !strings.Contains(string(report), "- `#123`") {
		t.Fatalf("selected summary missing: %q, %v", report, err)
	}
}

type failedOutput struct{}

func (failedOutput) Write([]byte) (int, error) { return 0, errors.New("test output failure") }

func TestPRBodyOutputFailure(t *testing.T) {
	args := append(bodyArguments(t, validBody()), "--report-open-closing-issues")
	if status := run(args, failedOutput{}, io.Discard); status != 2 {
		t.Fatalf("audit write exit=%d want=2", status)
	}
}

func TestCommandConfiguration(t *testing.T) {
	t.Setenv("GITHUB_EVENT_PATH", "")
	invoke(t, 2)
	invoke(t, 2, "--unknown")
	invoke(t, 2, "--tool", "pr-body", "--body", validBody())
	invoke(t, 2, "--tool", "attack-tactic-vocabulary", "--local-input", "source.json")
	stdout, stderr := invoke(t, 1, "--tool", "pr-title", "--title=", "--json")
	if !strings.Contains(stdout, `"rule_id":"pr-title-empty"`) || stderr != "" {
		t.Fatalf("JSON output=%q, %q", stdout, stderr)
	}
}

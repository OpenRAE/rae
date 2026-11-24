package governance

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"go.yaml.in/yaml/v3"
)

type workflowFile struct {
	Jobs map[string]workflowJob `yaml:"jobs"`
}
type workflowJob struct {
	Env   map[string]string `yaml:"env"`
	Steps []workflowStep    `yaml:"steps"`
}
type workflowStep struct {
	ID   string            `yaml:"id"`
	Uses string            `yaml:"uses"`
	Run  string            `yaml:"run"`
	With map[string]any    `yaml:"with"`
	Env  map[string]string `yaml:"env"`
}

func workflow(t *testing.T, name string) workflowFile {
	t.Helper()
	data, err := os.ReadFile("../../../../.github/workflows/" + name) // #nosec G304 -- Callers select fixed repository workflow fixtures.
	if err != nil {
		t.Fatal(err)
	}
	var w workflowFile
	if err := yaml.Unmarshal(data, &w); err != nil {
		t.Fatal(err)
	}
	return w
}

func TestBaseRevisionGuard(t *testing.T) {
	w := workflow(t, "pr-body-policy.yml")
	job, ok := w.Jobs["go-body-guard"]
	if !ok {
		t.Fatal("PR body workflow has no Go base-revision guard job")
	}
	var run string
	checkouts := 0
	for _, step := range job.Steps {
		if strings.HasPrefix(step.Uses, "actions/checkout@") {
			checkouts++
			if step.With["ref"] != "${{ github.event.pull_request.base.sha }}" || step.With["persist-credentials"] != false {
				t.Fatal("Go body guard does not select the credential-free base checkout")
			}
		}
		if step.ID == "validate-go-body" {
			run = step.Run
		}
	}
	if checkouts != 1 || run == "" {
		t.Fatalf("Go guard checkouts = %d, command = %q, want one base checkout and its validation command", checkouts, run)
	}
	for _, tc := range []struct {
		name               string
		baseGuard, baseJob bool
		wantExit           int
	}{
		{"trusted-base", true, true, 0},
		{"introducing-PR", false, false, 0},
		{"broken-established-base", false, true, 1},
	} {
		t.Run(tc.name, func(t *testing.T) { exerciseBaseGuard(t, run, tc.baseGuard, tc.baseJob, tc.wantExit) })
	}
}

func exerciseBaseGuard(t *testing.T, script string, baseGuard, baseJob bool, wantExit int) {
	t.Helper()
	root := t.TempDir()
	runner := t.TempDir()
	marker := filepath.Join(runner, "head-executed")
	write := func(name, data string) { testWrite(t, root, name, []byte(data)) }
	git := func(args ...string) string { return strings.TrimSpace(string(testGit(t, root, args...))) }

	git("init", "-q")
	git("config", "user.name", "Test")
	git("config", "user.email", "test@example.invalid")
	git("config", "commit.gpgsign", "false")
	baseWorkflow := "jobs:\n  body-guard: {}\n"
	if baseJob {
		baseWorkflow += "  go-body-guard: {}\n"
	}
	write(".github/workflows/pr-body-policy.yml", baseWorkflow)
	const module = "implementations/tooling/go/"
	if baseGuard {
		write(module+"go.mod", "module guardfixture\n\ngo 1.27.3\n")
		write(module+"cmd/policycheck/main.go", "package main\nimport (\"flag\"; \"fmt\"; \"os\")\nfunc main(){tool:=flag.String(\"tool\",\"\",\"\"); event:=flag.String(\"event-path\",\"\",\"\");flag.Parse();if *tool!=\"pr-body\"||*event==\"\"||flag.NArg()!=0{os.Exit(2)};fmt.Println(\"trusted-base\")}\n")
	}
	git("add", ".")
	git("commit", "-qm", "base")
	base := git("rev-parse", "HEAD")
	write(module+"go.mod", "module guardfixture\n\ngo 1.27.3\n")
	write(module+"cmd/policycheck/main.go", "package main\nimport \"os\"\nfunc main(){_ = os.WriteFile(os.Getenv(\"HEAD_EXECUTION_MARKER\"),[]byte(\"executed\"),0600)}\n")
	git("add", ".")
	git("commit", "-qm", "candidate")
	// actions/checkout's admitted ref above determines which Git tree executes.
	// Run the exact production validation step against that selected tree.
	git("checkout", "-q", "--detach", base)
	event := filepath.Join(runner, "event.json")
	if err := os.WriteFile(event, []byte(`{"pull_request":{"number":1,"body":"untrusted event"}}`), 0600); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "bash", "-eu", "-o", "pipefail", "-c", script) // #nosec G204 -- Execute the inspected production workflow step against isolated base/head fixture repositories.
	cmd.Dir = root
	cache, err := os.UserCacheDir()
	if err != nil {
		t.Fatal(err)
	}
	cmd.Env = []string{"PATH=" + filepath.Join(testGoRoot(t), "bin") + string(os.PathListSeparator) + os.Getenv("PATH"), "GOCACHE=" + filepath.Join(cache, "go-build"), "GOTOOLCHAIN=local", "GOPROXY=off", "RUNNER_TEMP=" + runner, "GITHUB_EVENT_PATH=" + event, "GITHUB_REPOSITORY=OpenRAE/rae", "HEAD_EXECUTION_MARKER=" + marker}
	output, err := cmd.CombinedOutput()
	status := 0
	if err != nil {
		exited := &exec.ExitError{}
		if errors.As(err, &exited) {
			status = exited.ExitCode()
		} else {
			t.Fatal(err)
		}
	}
	if (status == 0) != (wantExit == 0) {
		t.Fatalf("base guard exit = %d (%s), want success=%t", status, output, wantExit == 0)
	}
	if _, err := os.Stat(marker); !os.IsNotExist(err) {
		t.Fatalf("candidate sentinel state = %v, want it never executed", err)
	}
	if baseGuard && !strings.Contains(string(output), "trusted-base") {
		t.Fatalf("guard output = %s, want the base executable's result", output)
	}
}

func TestHostedGates(t *testing.T) {
	w := workflow(t, "canonical-verification.yml")
	for _, name := range []string{"go", "go-architecture", "governance-parity"} {
		if _, ok := w.Jobs[name]; !ok {
			t.Errorf("canonical graph lacks job %q", name)
		}
	}
	job, ok := w.Jobs["governance-parity"]
	if !ok {
		return
	}
	found := false
	for _, step := range job.Steps {
		if step.ID == "compare-governance" {
			found = true
			if !strings.Contains(step.Run, "go -C implementations/tooling/go test ./governance") || !strings.Contains(step.Run, "TestReferenceParity") || !strings.Contains(step.Run, "TestLiveReferenceParity") || step.Env["GOVERNANCE_REFERENCE_PYTHON"] == "" || step.Env["GOVERNANCE_REFERENCE_TOOLING_PYTHON"] == "" {
				t.Errorf("parity invocation = %+v, want the reference comparison command and explicit interpreter", step)
			}
		}
	}
	if !found {
		t.Error("governance parity job lacks its comparison step")
	}
}

func testGoRoot(t *testing.T) string {
	t.Helper()
	data, err := exec.CommandContext(t.Context(), "go", "env", "GOROOT").Output()
	if err != nil {
		t.Fatal(err)
	}
	return strings.TrimSpace(string(data))
}

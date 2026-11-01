package main

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

func TestFindRegressionTestsListsTopLevelTests(t *testing.T) {
	source := []byte(`package p

import "testing"

func TestRegressionA(t *testing.T) {}
func TestOther(t *testing.T)       {}
func (s) TestRegressionMethod()    {}
func TestRegressionB(t *testing.T) {}

type s struct{}
`)
	got, err := findRegressionTests("p_test.go", source)
	if err != nil {
		t.Fatalf("findRegressionTests() error = %v", err)
	}
	if want := []string{"TestRegressionA", "TestRegressionB"}; !slices.Equal(got, want) {
		t.Errorf("findRegressionTests() = %v, want %v", got, want)
	}
}

func TestFindRegressionTestsRejectsInvalidSource(t *testing.T) {
	if _, err := findRegressionTests("p_test.go", []byte("package")); err == nil {
		t.Error("findRegressionTests() error = nil, want a parse error")
	}
}

func TestRunRejectsBadUsage(t *testing.T) {
	for _, args := range [][]string{nil, {"-base", "main", "extra"}, {"-unknown"}, {"-base", "--output=x"}} {
		var stdout, stderr bytes.Buffer
		if got := run(t.Context(), args, &stdout, &stderr); got != 2 {
			t.Errorf("run(%q) = %d, want 2", args, got)
		}
	}
}

const buggyAdd = "package m\n\nfunc Add(a, b int) int { return a - b }\n"

const fixedAdd = "package m\n\nfunc Add(a, b int) int { return a + b }\n"

const baseTest = "package m\n\nimport \"testing\"\n\nfunc TestAddZero(t *testing.T) {\n\tif Add(0, 0) != 0 {\n\t\tt.Fatal(\"Add(0, 0) != 0\")\n\t}\n}\n"

func TestRunAcceptsARegressionTestThatFailsOnTheBase(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"add.go":      fixedAdd,
		"add_test.go": baseTest + regressionTest("TestRegressionAdd", "Add(1, 2) != 3"),
	})

	stdout, stderr, status := runIn(t, repo)

	if status != 0 {
		t.Fatalf("run() = %d, want 0; stderr:\n%s", status, stderr)
	}
	if want := "1 new regression tests fail on the base revision"; !strings.Contains(stdout, want) {
		t.Errorf("run() stdout = %q, want it to contain %q", stdout, want)
	}
}

func TestRunRefusesARegressionTestThatPassesOnTheBase(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"add.go":      fixedAdd,
		"add_test.go": baseTest + regressionTest("TestRegressionZero", "Add(0, 0) != 0"),
	})

	_, stderr, status := runIn(t, repo)

	if status != 1 || !strings.Contains(stderr, "TestRegressionZero: passes on the base revision") {
		t.Errorf("run() = %d with stderr %q, want 1 and a pass on the base revision", status, stderr)
	}
}

func TestRunRefusesARegressionTestThatDoesNotBuildOnTheBase(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"add.go":      fixedAdd + "\nfunc Sub(a, b int) int { return a - b }\n",
		"add_test.go": baseTest + regressionTest("TestRegressionSub", "Sub(3, 1) != 2"),
	})

	_, stderr, status := runIn(t, repo)

	if status != 1 || !strings.Contains(stderr, "TestRegressionSub: does not build or run on the base revision") {
		t.Errorf("run() = %d with stderr %q, want 1 and a build failure on the base revision", status, stderr)
	}
}

func TestRunRefusesARegressionTestInANewPackage(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"sub/sub.go":      "package sub\n\nfunc One() int { return 1 }\n",
		"sub/sub_test.go": "package sub\n\nimport \"testing\"\n" + regressionTest("TestRegressionOne", "One() != 1"),
	})

	_, stderr, status := runIn(t, repo)

	if status != 1 || !strings.Contains(stderr, "TestRegressionOne: package sub does not exist on the base revision") {
		t.Errorf("run() = %d with stderr %q, want 1 and a missing base package", status, stderr)
	}
}

// A head fixture must reach the base run: a missing fixture would fail the
// test there and so give false evidence.
func TestRunReplaysTheTestdataOfTheHead(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"testdata/two.txt": "2\n",
		"fixture_test.go": "package m\n\nimport (\n\t\"os\"\n\t\"testing\"\n)\n\nfunc TestRegressionFixture(t *testing.T) {\n" +
			"\tif _, err := os.ReadFile(\"testdata/two.txt\"); err != nil {\n\t\tt.Fatal(err)\n\t}\n" +
			"\tif Add(0, 0) != 0 {\n\t\tt.Fatal(\"Add(0, 0) != 0\")\n\t}\n}\n",
	})

	_, stderr, status := runIn(t, repo)

	if status != 1 || !strings.Contains(stderr, "TestRegressionFixture: passes on the base revision") {
		t.Errorf("run() = %d with stderr %q, want 1 and a pass on the base revision", status, stderr)
	}
}

// Only the declarations that the new regression tests need reach the base run,
// so a new test of a new function does not break the base build.
func TestRunLeavesOutAnUnrelatedNewTest(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"add.go":             fixedAdd + "\nfunc Sub(a, b int) int { return a - b }\n",
		"sub_test.go":        "package m\n\nimport \"testing\"\n" + regressionTest("TestSub", "Sub(3, 1) != 2"),
		"regression_test.go": "package m\n\nimport \"testing\"\n" + regressionTest("TestRegressionAdd", "Add(1, 2) != 3"),
	})

	stdout, stderr, status := runIn(t, repo)

	if status != 0 || !strings.Contains(stdout, "1 new regression tests fail on the base revision") {
		t.Errorf("run() = %d with stdout %q and stderr %q, want 0 and one regression test", status, stdout, stderr)
	}
}

func TestRunFindsANewRegressionTestInARenamedFile(t *testing.T) {
	repo := fixtureRepo(t)
	gitIn(t, repo, "mv", "add_test.go", "sum_test.go")
	commit(t, repo, map[string]string{
		"add.go":      fixedAdd,
		"sum_test.go": baseTest + regressionTest("TestRegressionAdd", "Add(1, 2) != 3"),
	})

	stdout, stderr, status := runIn(t, repo)

	if status != 0 || !strings.Contains(stdout, "1 new regression tests fail on the base revision") {
		t.Errorf("run() = %d with stdout %q and stderr %q, want 0 and one regression test", status, stdout, stderr)
	}
}

// A regression test that the base already declares is not new when it moves
// to another file of its package.
func TestRunSkipsAnOldRegressionTestInAnotherFile(t *testing.T) {
	repo := fixtureRepo(t)
	gitIn(t, repo, "switch", "--quiet", "main")
	commit(t, repo, map[string]string{"old_test.go": "package m\n\nimport \"testing\"\n" + regressionTest("TestRegressionOld", "Add(0, 0) != 0")})
	gitIn(t, repo, "switch", "--quiet", "--force-create", "change")
	gitIn(t, repo, "mv", "old_test.go", "moved_test.go")
	commit(t, repo, map[string]string{"add.go": fixedAdd})

	stdout, stderr, status := runIn(t, repo)

	if status != 0 || !strings.Contains(stdout, "0 new regression tests") {
		t.Errorf("run() = %d with stdout %q and stderr %q, want 0 and no regression tests", status, stdout, stderr)
	}
}

// The base testdata must not decide the base run when the head deletes it.
func TestRunRemovesTheBaseTestdataThatTheHeadDeletes(t *testing.T) {
	repo := fixtureRepo(t)
	gitIn(t, repo, "switch", "--quiet", "main")
	commit(t, repo, map[string]string{"testdata/stale.txt": "stale\n"})
	gitIn(t, repo, "switch", "--quiet", "--force-create", "change")
	gitIn(t, repo, "rm", "-r", "--quiet", "testdata")
	commit(t, repo, map[string]string{
		"stale_test.go": "package m\n\nimport (\n\t\"os\"\n\t\"testing\"\n)\n\nfunc TestRegressionStale(t *testing.T) {\n" +
			"\tif _, err := os.Stat(\"testdata/stale.txt\"); err == nil {\n\t\tt.Fatal(\"a stale fixture exists\")\n\t}\n}\n",
	})

	_, stderr, status := runIn(t, repo)

	if status != 1 || !strings.Contains(stderr, "TestRegressionStale: passes on the base revision") {
		t.Errorf("run() = %d with stderr %q, want 1 and a pass on the base revision", status, stderr)
	}
}

// The replay keeps the head declarations that a regression test needs, from
// any test file of its package.
func TestRunKeepsTheHelpersThatARegressionTestNeeds(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"add.go":             fixedAdd,
		"helpers_test.go":    "package m\n\nfunc sum(a, b int) int { return Add(a, b) }\n",
		"regression_test.go": "package m\n\nimport \"testing\"\n" + regressionTest("TestRegressionSum", "sum(1, 2) != 3"),
	})

	stdout, stderr, status := runIn(t, repo)

	if status != 0 || !strings.Contains(stdout, "1 new regression tests fail on the base revision") {
		t.Errorf("run() = %d with stdout %q and stderr %q, want 0 and one regression test", status, stdout, stderr)
	}
}

// An external test package reaches the declarations of the internal test
// package through the package import.
func TestRunKeepsTheInternalHelpersOfAnExternalTest(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"add.go":         fixedAdd,
		"export_test.go": "package m\n\nvar AddForTest = Add\n",
		"external_test.go": "package m_test\n\nimport (\n\t\"testing\"\n\n\t\"example.com/m\"\n)\n" +
			regressionTest("TestRegressionExternal", "m.AddForTest(1, 2) != 3"),
	})

	stdout, stderr, status := runIn(t, repo)

	if status != 0 || !strings.Contains(stdout, "1 new regression tests fail on the base revision") {
		t.Errorf("run() = %d with stdout %q and stderr %q, want 0 and one regression test", status, stdout, stderr)
	}
}

func TestRunAcceptsAChangeWithoutRegressionTests(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{"add.go": fixedAdd})

	stdout, stderr, status := runIn(t, repo)

	if status != 0 || !strings.Contains(stdout, "0 new regression tests") {
		t.Errorf("run() = %d with stdout %q and stderr %q, want 0 and no regression tests", status, stdout, stderr)
	}
}

func TestRunReportsAnUnknownBaseRevision(t *testing.T) {
	repo := fixtureRepo(t)
	t.Chdir(repo)
	var stdout, stderr bytes.Buffer

	if got := run(t.Context(), []string{"-base", "missing"}, &stdout, &stderr); got != 1 || !strings.Contains(stderr.String(), "git merge-base") {
		t.Errorf("run() = %d with stderr %q, want 1 and a git merge-base error", got, stderr.String())
	}
}

// fixtureRepo creates a Git repository whose main branch has a buggy Add and a
// passing test, and checks out a new branch for the change under test.
func fixtureRepo(t *testing.T) string {
	t.Helper()
	repo := t.TempDir()
	gitIn(t, repo, "init", "--quiet", "--initial-branch=main")
	gitIn(t, repo, "config", "user.name", "regressiontest fixture")
	gitIn(t, repo, "config", "user.email", "fixture@example.invalid")
	gitIn(t, repo, "config", "commit.gpgsign", "false")
	commit(t, repo, map[string]string{"go.mod": "module example.com/m\n\ngo 1.27\n", "add.go": buggyAdd, "add_test.go": baseTest})
	gitIn(t, repo, "switch", "--quiet", "--create", "change")
	return repo
}

func regressionTest(name, condition string) string {
	return "\nfunc " + name + "(t *testing.T) {\n\tif " + condition + " {\n\t\tt.Fatal(\"" + condition + "\")\n\t}\n}\n"
}

func commit(t *testing.T, repo string, files map[string]string) {
	t.Helper()
	for name, content := range files {
		path := filepath.Join(repo, name)
		if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	gitIn(t, repo, "add", ".")
	gitIn(t, repo, "commit", "--quiet", "--message", "fixture")
}

func gitIn(t *testing.T, repo string, args ...string) {
	t.Helper()
	// Each call site passes fixed arguments for a temporary fixture repository.
	cmd := exec.CommandContext(t.Context(), "git", args...) //nolint:gosec // G204: see the comment above.
	cmd.Dir = repo
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, output)
	}
}

func runIn(t *testing.T, repo string) (stdout, stderr string, status int) {
	t.Helper()
	t.Chdir(repo)
	var out, errs bytes.Buffer
	status = run(t.Context(), []string{"-base", "main"}, &out, &errs)
	return out.String(), errs.String(), status
}

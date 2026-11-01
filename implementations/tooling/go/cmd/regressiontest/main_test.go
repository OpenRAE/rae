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

const testingHeader = "package m\n\nimport \"testing\"\n"

func TestRunAcceptsARegressionTestThatFailsOnTheBase(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"add.go":                 fixedAdd,
		"add_regression_test.go": testingHeader + regressionTest("TestRegressionAdd", "Add(1, 2) != 3"),
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
		"add.go":                  fixedAdd,
		"zero_regression_test.go": testingHeader + regressionTest("TestRegressionZero", "Add(0, 0) != 0"),
	})

	_, stderr, status := runIn(t, repo)

	if status != 1 || !strings.Contains(stderr, "TestRegressionZero: passes on the base revision") {
		t.Errorf("run() = %d with stderr %q, want 1 and a pass on the base revision", status, stderr)
	}
}

func TestRunRefusesARegressionTestThatDoesNotBuildOnTheBase(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"add.go":                 fixedAdd + "\nfunc Sub(a, b int) int { return a - b }\n",
		"sub_regression_test.go": testingHeader + regressionTest("TestRegressionSub", "Sub(3, 1) != 2"),
	})

	_, stderr, status := runIn(t, repo)

	if status != 1 || !strings.Contains(stderr, "TestRegressionSub: does not build or run on the base revision") {
		t.Errorf("run() = %d with stderr %q, want 1 and a build failure on the base revision", status, stderr)
	}
}

func TestRunRefusesARegressionTestInANewPackage(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"sub/sub.go":                 "package sub\n\nfunc One() int { return 1 }\n",
		"sub/sub_regression_test.go": "package sub\n\nimport \"testing\"\n" + regressionTest("TestRegressionOne", "One() != 1"),
	})

	_, stderr, status := runIn(t, repo)

	if status != 1 || !strings.Contains(stderr, "TestRegressionOne: package sub does not exist on the base revision") {
		t.Errorf("run() = %d with stderr %q, want 1 and a missing base package", status, stderr)
	}
}

func TestRunRefusesARegressionTestOutsideARegressionFile(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"add.go":      fixedAdd,
		"add_test.go": baseTest + regressionTest("TestRegressionAdd", "Add(1, 2) != 3"),
	})

	_, stderr, status := runIn(t, repo)

	if status != 1 || !strings.Contains(stderr, "TestRegressionAdd: add_test.go declares it; a regression test belongs in a file whose name ends with _regression_test.go") {
		t.Errorf("run() = %d with stderr %q, want 1 and a misplaced regression test", status, stderr)
	}
}

// A head fixture must reach the base run: a missing fixture would fail the
// test there and so give false evidence.
func TestRunReplaysTheTestdataOfTheHead(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"testdata/two.txt": "2\n",
		"fixture_regression_test.go": "package m\n\nimport (\n\t\"os\"\n\t\"testing\"\n)\n\nfunc TestRegressionFixture(t *testing.T) {\n" +
			"\tif _, err := os.ReadFile(\"testdata/two.txt\"); err != nil {\n\t\tt.Fatal(err)\n\t}\n" +
			"\tif Add(0, 0) != 0 {\n\t\tt.Fatal(\"Add(0, 0) != 0\")\n\t}\n}\n",
	})

	_, stderr, status := runIn(t, repo)

	if status != 1 || !strings.Contains(stderr, "TestRegressionFixture: passes on the base revision") {
		t.Errorf("run() = %d with stderr %q, want 1 and a pass on the base revision", status, stderr)
	}
}

// The other test files of the package stay out of the base run. Here they hold
// a new test and a helper, named like a testing method, that use an API that
// only the head has.
func TestRunIgnoresTheOtherTestFilesOfThePackage(t *testing.T) {
	repo := fixtureRepo(t)
	commit(t, repo, map[string]string{
		"add.go":                 fixedAdd + "\nfunc Mul(a, b int) int { return a * b }\n",
		"helpers_test.go":        "package m\n\nfunc TempDir() int { return Mul(2, 3) }\n",
		"mul_test.go":            testingHeader + regressionTest("TestMul", "Mul(2, 3) != 6"),
		"add_regression_test.go": testingHeader + regressionTest("TestRegressionAdd", "len(t.TempDir()) == 0 || Add(1, 2) != 3"),
	})

	stdout, stderr, status := runIn(t, repo)

	if status != 0 || !strings.Contains(stdout, "1 new regression tests fail on the base revision") {
		t.Errorf("run() = %d with stdout %q and stderr %q, want 0 and one regression test", status, stdout, stderr)
	}
}

func TestRunFindsANewRegressionTestInARenamedFile(t *testing.T) {
	repo := fixtureRepo(t)
	addToBase(t, repo, map[string]string{"old_regression_test.go": testingHeader + regressionTest("TestRegressionOld", "Add(0, 0) != 0")})
	gitIn(t, repo, "mv", "old_regression_test.go", "renamed_regression_test.go")
	commit(t, repo, map[string]string{
		"add.go": fixedAdd,
		"renamed_regression_test.go": testingHeader + regressionTest("TestRegressionOld", "Add(0, 0) != 0") +
			regressionTest("TestRegressionAdd", "Add(1, 2) != 3"),
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
	addToBase(t, repo, map[string]string{"old_regression_test.go": testingHeader + regressionTest("TestRegressionOld", "Add(0, 0) != 0")})
	gitIn(t, repo, "mv", "old_regression_test.go", "moved_regression_test.go")
	commit(t, repo, map[string]string{"add.go": fixedAdd})

	stdout, stderr, status := runIn(t, repo)

	if status != 0 || !strings.Contains(stdout, "0 new regression tests") {
		t.Errorf("run() = %d with stdout %q and stderr %q, want 0 and no regression tests", status, stdout, stderr)
	}
}

// The base testdata must not decide the base run when the head deletes it.
func TestRunRemovesTheBaseTestdataThatTheHeadDeletes(t *testing.T) {
	repo := fixtureRepo(t)
	addToBase(t, repo, map[string]string{"testdata/stale.txt": "stale\n"})
	gitIn(t, repo, "rm", "-r", "--quiet", "testdata")
	commit(t, repo, map[string]string{
		"stale_regression_test.go": "package m\n\nimport (\n\t\"os\"\n\t\"testing\"\n)\n\nfunc TestRegressionStale(t *testing.T) {\n" +
			"\tif _, err := os.Stat(\"testdata/stale.txt\"); err == nil {\n\t\tt.Fatal(\"a stale fixture exists\")\n\t}\n}\n",
	})

	_, stderr, status := runIn(t, repo)

	if status != 1 || !strings.Contains(stderr, "TestRegressionStale: passes on the base revision") {
		t.Errorf("run() = %d with stderr %q, want 1 and a pass on the base revision", status, stderr)
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

func TestRunReportsADirectoryOutsideGit(t *testing.T) {
	t.Chdir(t.TempDir())
	var stdout, stderr bytes.Buffer

	if got := run(t.Context(), []string{"-base", "main"}, &stdout, &stderr); got != 1 || !strings.Contains(stderr.String(), "git rev-parse") {
		t.Errorf("run() = %d with stderr %q, want 1 and a git rev-parse error", got, stderr.String())
	}
}

// TestRunReportsEachGitFailure puts a git wrapper first in PATH. The wrapper
// fails one subcommand, and the command must report the failure.
func TestRunReportsEachGitFailure(t *testing.T) {
	realGit, err := exec.LookPath("git")
	if err != nil {
		t.Fatal(err)
	}
	for _, subcommand := range []string{"merge-base", "diff", "ls-tree", "show", "rev-parse HEAD", "worktree add", "restore"} {
		t.Run(subcommand, func(t *testing.T) {
			repo := fixtureRepo(t)
			commit(t, repo, map[string]string{
				"add.go":                 fixedAdd,
				"add_regression_test.go": testingHeader + regressionTest("TestRegressionAdd", "Add(1, 2) != 3"),
			})
			bin := t.TempDir()
			wrapper := "#!/bin/sh\ncase \"$1 $2\" in \"" + subcommand + "\"*) exit 1 ;; esac\nexec \"" + realGit + "\" \"$@\"\n"
			if err := os.WriteFile(filepath.Join(bin, "git"), []byte(wrapper), 0o700); err != nil { //nolint:gosec // G306: the wrapper must be executable.
				t.Fatal(err)
			}
			t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))

			_, stderr, status := runIn(t, repo)

			if status != 1 || !strings.Contains(stderr, "regressiontest: git "+subcommand) {
				t.Errorf("run() = %d with stderr %q, want 1 and the failed git %s", status, stderr, subcommand)
			}
		})
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

// addToBase commits files on the main branch and starts the change branch
// again from it.
func addToBase(t *testing.T, repo string, files map[string]string) {
	t.Helper()
	gitIn(t, repo, "switch", "--quiet", "main")
	commit(t, repo, files)
	gitIn(t, repo, "switch", "--quiet", "--force-create", "change")
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

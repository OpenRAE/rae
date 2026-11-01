// Command regressiontest checks that each new regression test fails on the base
// revision.
//
// A regression test is a test function whose name starts with TestRegression,
// in a file whose name ends with _regression_test.go. That file holds the
// helpers that its tests need, and its fixtures are in testdata. For each
// regression test that the current commit adds to a package, the command runs
// the test against the package at the merge base with the base revision. The
// test must build there and fail. The ordinary test lane shows that it passes
// on the current commit.
//
// In the base run, the package keeps none of its base test files or testdata.
// It gets the regression test files and the testdata of the head commit. Thus
// base and head test code never mix, and another new test cannot change the
// outcome.
//
// Run the command from the root directory of a Go module:
//
//	regressiontest -base origin/dev
package main

import (
	"bytes"
	"context"
	"errors"
	"flag"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io"
	"maps"
	"os"
	"os/exec"
	"os/signal"
	"path"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
)

const (
	testPrefix = "TestRegression"
	fileSuffix = "_regression_test.go"
)

// replay holds the new regression tests of one package and the regression
// test files of the package at the head commit.
type replay struct {
	names []string
	files []string
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	status := run(ctx, os.Args[1:], os.Stdout, os.Stderr)
	stop()
	os.Exit(status)
}

// run executes the command and returns its exit status. A failed write to the
// output streams has no recovery path, so the exit status alone reports it.
func run(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("regressiontest", flag.ContinueOnError)
	flags.SetOutput(stderr)
	base := flags.String("base", "", "base revision, for example origin/dev")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if *base == "" || strings.HasPrefix(*base, "-") || flags.NArg() != 0 {
		_, _ = fmt.Fprintln(stderr, "usage: regressiontest -base <revision>")
		return 2
	}
	added, failures, err := check(ctx, *base)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "regressiontest: %v\n", err)
		return 1
	}
	for _, failure := range failures {
		_, _ = fmt.Fprintf(stderr, "regressiontest: %s\n", failure)
	}
	if len(failures) > 0 {
		return 1
	}
	_, _ = fmt.Fprintf(stdout, "regressiontest: %d new regression tests fail on the base revision\n", added)
	return 0
}

// check counts the new regression tests and returns one message for each that
// is misplaced or does not fail on the base revision.
func check(ctx context.Context, base string) (int, []string, error) {
	root, err := git(ctx, ".", "rev-parse", "--show-toplevel")
	if err != nil {
		return 0, nil, err
	}
	mergeBase, err := git(ctx, ".", "merge-base", "--end-of-options", base, "HEAD")
	if err != nil {
		return 0, nil, err
	}
	module, err := moduleDir(root)
	if err != nil {
		return 0, nil, err
	}
	added, misplaced, err := addedTests(ctx, root, mergeBase, module)
	if err != nil || len(added) == 0 {
		return 0, misplaced, err
	}
	head, err := git(ctx, root, "rev-parse", "HEAD")
	if err != nil {
		return 0, nil, err
	}
	count := 0
	for _, tests := range added {
		count += len(tests.names)
	}
	worktree, err := os.MkdirTemp("", "regressiontest-")
	if err != nil {
		return 0, nil, err
	}
	defer func() {
		// Cleanup of a temporary checkout: RemoveAll deletes the files even if git cannot unregister them.
		_, _ = git(context.WithoutCancel(ctx), root, "worktree", "remove", "--force", worktree)
		_ = os.RemoveAll(worktree)
	}()
	if _, err = git(ctx, root, "worktree", "add", "--detach", worktree, mergeBase); err != nil {
		return 0, nil, err
	}
	failures, err := runOnBase(ctx, worktree, head, added)
	return count, slices.Concat(misplaced, failures), err
}

// moduleDir returns the module directory, the working directory, relative to the repository root.
func moduleDir(root string) (string, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	resolved, err := filepath.EvalSymlinks(cwd)
	if err != nil {
		return "", err
	}
	return filepath.Rel(root, resolved)
}

// addedTests maps each package directory with a changed test file to the
// regression tests that the package declares at the head commit and not at
// the merge base. A test that moves between files of its package is thus not
// new, and a renamed file keeps its new tests. It also describes each head
// regression test outside a regression test file.
func addedTests(ctx context.Context, root, mergeBase, module string) (map[string]*replay, []string, error) {
	changed, err := git(ctx, root, "diff", "--name-only", "--no-renames", mergeBase, "HEAD", "--", module)
	if err != nil {
		return nil, nil, err
	}
	dirs := map[string]bool{}
	for file := range strings.SplitSeq(changed, "\n") {
		if strings.HasSuffix(file, "_test.go") {
			dirs[filepath.Dir(file)] = true
		}
	}
	added := map[string]*replay{}
	var misplaced []string
	for _, dir := range slices.Sorted(maps.Keys(dirs)) {
		tests, wrong, err := packageReplay(ctx, root, mergeBase, dir)
		if err != nil {
			return nil, nil, err
		}
		misplaced = append(misplaced, wrong...)
		if len(tests.names) > 0 {
			added[dir] = tests
		}
	}
	return added, misplaced, nil
}

// packageReplay returns the replay of the package in dir, and describes each
// head regression test outside a regression test file.
func packageReplay(ctx context.Context, root, mergeBase, dir string) (*replay, []string, error) {
	existing, _, err := regressionTests(ctx, root, mergeBase, dir)
	if err != nil {
		return nil, nil, err
	}
	current, files, err := regressionTests(ctx, root, "HEAD", dir)
	if err != nil {
		return nil, nil, err
	}
	tests := &replay{files: files}
	var misplaced []string
	for _, name := range slices.Sorted(maps.Keys(current)) {
		if !strings.HasSuffix(current[name], fileSuffix) {
			misplaced = append(misplaced, fmt.Sprintf("%s: %s declares it; a regression test belongs in a file whose name ends with %s", name, current[name], fileSuffix))
			continue
		}
		if _, old := existing[name]; !old {
			tests.names = append(tests.names, name)
		}
	}
	return tests, misplaced, nil
}

// regressionTests maps each regression test that the test files of the package
// in dir declare at rev to its file, and lists the regression test files. A
// file that does not parse declares no test: the build of its package fails
// anyway.
func regressionTests(ctx context.Context, root, rev, dir string) (map[string]string, []string, error) {
	listed, err := listTree(ctx, root, rev, filepath.ToSlash(dir)+"/")
	if err != nil {
		return nil, nil, err
	}
	tests := map[string]string{}
	var files []string
	for file := range strings.SplitSeq(listed, "\n") {
		if !strings.HasSuffix(file, "_test.go") {
			continue
		}
		if strings.HasSuffix(file, fileSuffix) {
			files = append(files, file)
		}
		source, err := git(ctx, root, "show", rev+":"+file)
		if err != nil {
			return nil, nil, err
		}
		names, _ := findRegressionTests(file, []byte(source))
		for _, name := range names {
			tests[name] = file
		}
	}
	return tests, files, nil
}

// findRegressionTests returns the names of the top-level regression test functions in a Go source file.
func findRegressionTests(path string, source []byte) ([]string, error) {
	file, err := parser.ParseFile(token.NewFileSet(), path, source, parser.SkipObjectResolution)
	if err != nil {
		return nil, err
	}
	var names []string
	for _, decl := range file.Decls {
		fn, ok := decl.(*ast.FuncDecl)
		if ok && fn.Recv == nil && strings.HasPrefix(fn.Name.Name, testPrefix) {
			names = append(names, fn.Name.Name)
		}
	}
	return names, nil
}

// runOnBase prepares the replay of the new regression tests of each package in
// the base checkout, and runs each test there.
func runOnBase(ctx context.Context, worktree, head string, added map[string]*replay) ([]string, error) {
	var failures []string
	for _, dir := range slices.Sorted(maps.Keys(added)) {
		target := filepath.Join(worktree, dir)
		if _, err := os.Stat(target); err != nil {
			for _, name := range added[dir].names {
				failures = append(failures, fmt.Sprintf("%s: package %s does not exist on the base revision", name, dir))
			}
			continue
		}
		if err := restoreReplay(ctx, worktree, head, dir, added[dir].files); err != nil {
			return nil, err
		}
		for _, name := range added[dir].names {
			if failure := baseOutcome(ctx, target, name); failure != "" {
				failures = append(failures, failure)
			}
		}
	}
	return failures, nil
}

// restoreReplay removes the test files and the testdata of the base package in
// dir. It then restores the regression test files and the testdata of the head
// commit.
func restoreReplay(ctx context.Context, worktree, head, dir string, files []string) error {
	target := filepath.Join(worktree, dir)
	baseFiles, err := filepath.Glob(filepath.Join(target, "*_test.go"))
	if err != nil {
		return err
	}
	for _, file := range append(baseFiles, filepath.Join(target, "testdata")) {
		if err = os.RemoveAll(file); err != nil {
			return err
		}
	}
	testdata := path.Join(filepath.ToSlash(dir), "testdata")
	listed, err := listTree(ctx, worktree, head, testdata)
	if err != nil {
		return err
	}
	paths := slices.Clone(files)
	if listed != "" {
		paths = append(paths, testdata)
	}
	_, err = git(ctx, worktree, append([]string{"restore", "--source=" + head, "--worktree", "--"}, paths...)...)
	return err
}

// baseOutcome runs one test in a base package directory and describes a wrong outcome.
func baseOutcome(ctx context.Context, dir, name string) string {
	// The command and its flags are constant, no shell runs, and the pattern quotes a Go identifier.
	cmd := exec.CommandContext(ctx, "go", "test", "-count=1", "-run", "^"+regexp.QuoteMeta(name)+"$", ".") //nolint:gosec // G204: see the comment above.
	cmd.Dir = dir
	output, err := cmd.CombinedOutput()
	if err == nil {
		return name + ": passes on the base revision; a regression test must fail there"
	}
	var exit *exec.ExitError
	if errors.As(err, &exit) && bytes.Contains(output, []byte("--- FAIL: "+name+" ")) {
		return ""
	}
	return name + ": does not build or run on the base revision; a regression test must fail there\n" + string(output)
}

// listTree returns the names of the entries of rev under name, one on each line.
func listTree(ctx context.Context, dir, rev, name string) (string, error) {
	return git(ctx, dir, "ls-tree", "--name-only", rev, "--", name)
}

// git runs a git command in dir and returns its trimmed standard output.
func git(ctx context.Context, dir string, args ...string) (string, error) {
	// No shell runs, and each revision that can come from the command line follows --end-of-options.
	cmd := exec.CommandContext(ctx, "git", args...) //nolint:gosec // G204: see the comment above.
	cmd.Dir = dir
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	output, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("git %s: %s: %w", strings.Join(args, " "), strings.TrimSpace(stderr.String()), err)
	}
	return strings.TrimSpace(string(output)), nil
}

// Command regressiontest checks that each new regression test fails on the base
// revision.
//
// A regression test is a test function whose name starts with TestRegression.
// For each such test that the current commit adds to a Go module, the command
// runs the test against the module at the merge base with the base revision.
// The test must build there and fail. The ordinary test lane shows that it
// passes on the current commit.
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
	"io/fs"
	"maps"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
)

const testPrefix = "TestRegression"

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

// check counts the new regression tests and returns one message for each that does not fail on the base revision.
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
	added, err := addedTests(ctx, root, mergeBase, module)
	if err != nil || len(added) == 0 {
		return 0, nil, err
	}
	count := 0
	for _, names := range added {
		count += len(names)
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
	failures, err := runOnBase(ctx, root, worktree, added)
	return count, failures, err
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

// addedTests maps each package directory to the regression tests that the current commit adds there.
func addedTests(ctx context.Context, root, mergeBase, module string) (map[string][]string, error) {
	changed, err := git(ctx, root, "diff", "--name-only", "--diff-filter=AM", mergeBase, "HEAD", "--", module)
	if err != nil {
		return nil, err
	}
	repo := os.DirFS(root)
	added := make(map[string][]string)
	for path := range strings.SplitSeq(changed, "\n") {
		if !strings.HasSuffix(path, "_test.go") {
			continue
		}
		head, err := fs.ReadFile(repo, path)
		if err != nil {
			return nil, err
		}
		// A file that the base revision lacks has no regression tests there.
		baseSource, _ := git(ctx, root, "show", mergeBase+":"+path)
		names, err := newRegressionTests(path, []byte(baseSource), head)
		if err != nil {
			return nil, err
		}
		if len(names) > 0 {
			dir := filepath.Dir(path)
			added[dir] = append(added[dir], names...)
		}
	}
	return added, nil
}

// newRegressionTests returns the regression tests in head that base does not declare.
// A base file that does not parse declares none.
func newRegressionTests(path string, base, head []byte) ([]string, error) {
	existing, _ := findRegressionTests(path, base)
	current, err := findRegressionTests(path, head)
	if err != nil {
		return nil, err
	}
	return slices.DeleteFunc(current, func(name string) bool { return slices.Contains(existing, name) }), nil
}

// findRegressionTests returns the names of the top-level regression test functions in a Go source file.
func findRegressionTests(path string, source []byte) ([]string, error) {
	if len(source) == 0 {
		return nil, nil
	}
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

// runOnBase copies the current test files into the base checkout and runs each new regression test there.
func runOnBase(ctx context.Context, root, worktree string, added map[string][]string) ([]string, error) {
	var failures []string
	for _, dir := range slices.Sorted(maps.Keys(added)) {
		target := filepath.Join(worktree, dir)
		if _, err := os.Stat(target); err != nil {
			for _, name := range added[dir] {
				failures = append(failures, fmt.Sprintf("%s: package %s does not exist on the base revision", name, dir))
			}
			continue
		}
		if err := copyTestFiles(filepath.Join(root, dir), target); err != nil {
			return nil, err
		}
		for _, name := range added[dir] {
			if failure := baseOutcome(ctx, target, name); failure != "" {
				failures = append(failures, failure)
			}
		}
	}
	return failures, nil
}

// copyTestFiles copies every test file of a package directory, without subdirectories.
func copyTestFiles(from, to string) (err error) {
	target, err := os.OpenRoot(to)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, target.Close()) }()
	source := os.DirFS(from)
	entries, err := fs.ReadDir(source, ".")
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), "_test.go") {
			continue
		}
		content, err := fs.ReadFile(source, entry.Name())
		if err != nil {
			return err
		}
		if err := target.WriteFile(entry.Name(), content, 0o600); err != nil {
			return err
		}
	}
	return nil
}

// baseOutcome runs one test in a base package directory and describes a wrong outcome.
func baseOutcome(ctx context.Context, dir, name string) string {
	// The command and its flags are constant, no shell runs, and the pattern quotes a Go identifier.
	cmd := exec.CommandContext(ctx, "go", "test", "-count=1", "-run", "^"+regexp.QuoteMeta(name)+"$", ".") //nolint:gosec // G204: see the comment above.
	cmd.Dir = dir
	output, err := cmd.CombinedOutput()
	var exit *exec.ExitError
	switch {
	case err == nil:
		return name + ": passes on the base revision; a regression test must fail there"
	case errors.As(err, &exit) && bytes.Contains(output, []byte("--- FAIL: "+name+" ")):
		return ""
	default:
		return name + ": does not build or run on the base revision; a regression test must fail there\n" + string(output)
	}
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

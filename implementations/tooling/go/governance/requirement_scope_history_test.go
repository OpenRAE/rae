package governance

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRequirementScopeHistory(t *testing.T) {
	for _, kind := range []string{"never", "untracked", "index", "deleted", "other-branch", "broken-git"} {
		t.Run(kind, func(t *testing.T) { checkRequirementScopeHistory(t, kind) })
	}
}

func checkRequirementScopeHistory(t *testing.T, kind string) {
	t.Helper()
	dir := scopeHistoryFixture(t, kind)
	r, err := openRepository(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = r.root.Close() })
	scope, err := loadRequirementScope(t.Context(), r, "9-feature")
	wantError := kind != "never" && kind != "untracked"
	if scope != nil || (err != nil) != wantError {
		t.Fatalf("history %s: scope=%v, error=%v", kind, scope, err)
	}
	if wantError && err.Error() != scopeReadFailure {
		t.Fatalf("history refusal=%v", err)
	}
}

func scopeHistoryFixture(t *testing.T, kind string) string {
	t.Helper()
	if kind == "broken-git" {
		dir := t.TempDir()
		if err := os.Mkdir(filepath.Join(dir, ".git"), 0o700); err != nil {
			t.Fatal(err)
		}
		return dir
	}
	dir := testGitRepository(t)
	testWrite(t, dir, "base.txt", []byte("base"))
	testCommit(t, dir)
	base := strings.TrimSpace(string(testGit(t, dir, "rev-parse", "HEAD")))
	if kind == "never" {
		return dir
	}
	const name = "docs/governance/requirement-scopes/9.json"
	testWrite(t, dir, name, []byte("{}\n"))
	if kind != "untracked" {
		testGit(t, dir, "add", "--", name)
	}
	if kind == "deleted" || kind == "other-branch" {
		testCommit(t, dir)
	}
	if kind == "other-branch" {
		testGit(t, dir, "checkout", "-q", "-b", "feature", base)
		return dir
	}
	if err := os.Remove(filepath.Join(dir, name)); err != nil {
		t.Fatal(err)
	}
	if kind == "deleted" {
		testCommit(t, dir)
	}
	return dir
}

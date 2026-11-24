package governance

import (
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

type mergeDiffReference struct {
	Name, Integration, Feature string
	Staged, Resolution         bool
	Paths                      []string
}

func TestRequirementMergeDiffReference(t *testing.T) {
	for _, tc := range readReference[[]mergeDiffReference](t, "merge-diff-reference") {
		t.Run(tc.Name, func(t *testing.T) { checkRequirementMergeDiff(t, tc) })
	}
}

func checkRequirementMergeDiff(t *testing.T, tc mergeDiffReference) {
	t.Helper()
	dir := testGitRepository(t)
	testGit(t, dir, "config", "core.quotepath", "false")
	testWrite(t, dir, "base.txt", []byte("base"))
	testWrite(t, dir, "resolution.txt", []byte("base resolution"))
	testCommit(t, dir)
	base := strings.TrimSpace(string(testGit(t, dir, "rev-parse", "HEAD")))
	testGit(t, dir, "checkout", "-q", "-b", "integration")
	testWrite(t, dir, "incoming.txt", []byte("first"))
	testCommit(t, dir)
	parent := strings.TrimSpace(string(testGit(t, dir, "rev-parse", "HEAD")))
	tip := parent
	switch tc.Integration {
	case "advanced":
		testWrite(t, dir, "incoming.txt", []byte("later"))
		testCommit(t, dir)
		tip = strings.TrimSpace(string(testGit(t, dir, "rev-parse", "HEAD")))
	case "unrelated":
		tip = base
	}
	if tc.Integration != "missing" {
		testGit(t, dir, "update-ref", "refs/remotes/origin/dev", tip)
	}
	testGit(t, dir, "checkout", "-q", "-b", "feature", base)
	testWrite(t, dir, tc.Feature, []byte("feature"))
	testCommit(t, dir)
	testGit(t, dir, "merge", "--no-commit", "--no-ff", parent)
	if tc.Resolution {
		testWrite(t, dir, "resolution.txt", []byte("worktree resolution"))
	}
	request := Request{Staged: tc.Staged}
	switch tc.Integration {
	case "empty":
		request.BaseRevisionSet = true
	case "explicit":
		request.BaseRevisionSet, request.BaseRevision = true, base
	}
	r, err := openRepository(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = r.root.Close() })
	c := checker{request: request}
	paths, err := c.requirementPaths(t.Context(), r)
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(tc.Paths, paths); diff != "" {
		t.Fatalf("merge paths (-want +got):\n%s", diff)
	}
}

package governance

import (
	"context"
	"errors"
	"os/exec"
	"strings"
	"unicode/utf8"
)

func (c *checker) requirementPaths(ctx context.Context, r *repository) ([]string, error) {
	if c.request.Paths != nil {
		return c.request.Paths, nil
	}
	ordinary, err := r.changed(ctx, c.request)
	if err != nil || c.request.BaseRevision != "" || c.request.BaseRevisionSet {
		return ordinary, err
	}
	merge, err := gitOptional(ctx, r, "", "rev-parse", "--verify", "MERGE_HEAD^{commit}")
	if err != nil || len(merge) == 0 {
		return ordinary, err
	}
	integration, err := gitOptional(ctx, r, "", "rev-parse", "--verify", "refs/remotes/origin/dev^{commit}")
	if err != nil || len(integration) == 0 {
		return ordinary, err
	}
	parent, tip := strings.TrimSpace(string(merge)), strings.TrimSpace(string(integration))
	if _, ancestorErr := r.git(ctx, "", "merge-base", "--is-ancestor", parent, tip); ancestorErr != nil {
		if _, exit := errors.AsType[*exec.ExitError](ancestorErr); exit {
			return ordinary, nil
		}
		return nil, ancestorErr
	}
	return mergeRequirementPaths(ctx, r, parent, c.request.Staged)
}

func mergeRequirementPaths(ctx context.Context, r *repository, parent string, staged bool) ([]string, error) {
	args := []string{"diff", "--name-only", "--diff-filter=d", "-z"}
	if staged {
		args = append(args, "--cached")
	}
	args = append(args, parent, "--")
	data, err := r.git(ctx, "", args...)
	if err != nil {
		return nil, err
	}
	if !utf8.Valid(data) {
		return nil, errNotUTF8
	}
	paths := []string{}
	text := strings.ReplaceAll(strings.ReplaceAll(string(data), "\r\n", "\n"), "\r", "\n")
	for name := range strings.SplitSeq(text, "\x00") {
		if name != "" {
			paths = append(paths, name)
		}
	}
	return paths, nil
}

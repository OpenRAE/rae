package governance

import (
	"context"
	"os"
	"regexp"
	"strings"
	"unicode"
	"unicode/utf8"
)

func currentRequirementBranch(ctx context.Context, r *repository) (string, error) {
	for _, name := range []string{"RAES_REQUIREMENT_BRANCH", "GITHUB_HEAD_REF"} {
		if branch := strings.TrimFunc(os.Getenv(name), pythonWhitespace); branch != "" {
			return branch, nil
		}
	}
	data, err := r.git(ctx, "", "branch", "--show-current")
	return strings.TrimFunc(string(data), pythonWhitespace), err
}

func requirementUIDFromContext(branch, explicit string) string {
	if explicit != "" {
		return explicit
	}
	if value := os.Getenv("RAES_REQUIREMENT_UID"); value != "" {
		return value
	}
	pattern := regexp.MustCompile(`[A-Za-zİıſK]{3}-\p{Nd}{3}`)
	for offset := 0; offset < len(branch); {
		match := pattern.FindStringIndex(branch[offset:])
		if match == nil {
			return ""
		}
		start, end := offset+match[0], offset+match[1]
		offset = start + 1
		if start > 0 {
			before, _ := utf8.DecodeLastRuneInString(branch[:start])
			if pythonWord(before) {
				continue
			}
		}
		if end < len(branch) {
			after, _ := utf8.DecodeRuneInString(branch[end:])
			if pythonWord(after) {
				continue
			}
		}
		return strings.ToUpper(branch[start:end])
	}
	return ""
}

func pythonWord(r rune) bool { return unicode.IsLetter(r) || unicode.IsNumber(r) || r == '_' }

func resolveRequirementContext(ctx context.Context, r *repository, branch, explicit string) (string, *requirementScope, error) {
	uid := requirementUIDFromContext(branch, explicit)
	scope, err := loadRequirementScope(ctx, r, branch)
	if err != nil {
		return "", nil, err
	}
	if scope != nil {
		if uid != "" && uid != scope.primary {
			return "", nil, scopeError("Selected requirement conflicts with the issue scope's primary requirement.")
		}
		uid = scope.primary
	}
	return uid, scope, nil
}

func (c *checker) requirementContext(ctx context.Context, r *repository) (Report, error) {
	branch, err := c.contextBranch(ctx, r)
	if err != nil {
		return Report{}, err
	}
	uid, _, err := resolveRequirementContext(ctx, r, branch, c.request.RequirementUID)
	if err != nil {
		return Report{}, err
	}
	return Report{Findings: []Finding{}, Text: uid + "\n"}, nil
}

func (c *checker) contextBranch(ctx context.Context, r *repository) (string, error) {
	if c.request.Branch != nil {
		return *c.request.Branch, nil
	}
	return currentRequirementBranch(ctx, r)
}

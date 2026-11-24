package governance

import (
	"context"
	"errors"
	"os"
	"slices"
	"strings"
)

func (c *checker) requirementGovernance(ctx context.Context, r *repository) (Report, error) {
	paths, err := c.requirementPaths(ctx, r)
	if err != nil {
		return Report{}, err
	}
	branch, err := c.contextBranch(ctx, r)
	if err != nil {
		return Report{}, err
	}
	uid, scope, err := resolveRequirementContext(ctx, r, branch, c.request.RequirementUID)
	if err != nil {
		if _, expected := errors.AsType[scopeError](err); expected {
			return finish([]Finding{finding("requirement-scope-invalid", err.Error(), "")}), nil
		}
		return Report{}, err
	}
	if scope != nil {
		return c.configuredRequirements(ctx, r, paths, uid, scope)
	}
	effective := governedRequirementPaths(paths)
	if !needsRequirement(effective) || os.Getenv("GITHUB_HEAD_REF") == "dev" && os.Getenv("GITHUB_BASE_REF") == "main" {
		return finish(nil), nil
	}
	if uid == "" {
		return finish([]Finding{finding("requirement-context-missing", "requirement UID is missing; set RAES_REQUIREMENT_UID or include a UID like GOV-918 in the branch name", "")}), nil
	}
	return c.configuredRequirements(ctx, r, effective, uid, nil)
}

func governedRequirementPaths(paths []string) []string {
	exempt := []string{
		".claude/agents/completion-verifier.md", ".claude/hooks/check_policy_after_edit.sh", ".claude/hooks/protect_files.sh", ".claude/hooks/verify-extra.sh", ".claude/settings.json", ".claude/skills/implement/SKILL.md",
		".github/PULL_REQUEST_TEMPLATE.md", ".github/workflows/ci.yml", ".pre-commit-config.yaml", ".codex", "AGENTS.md", "CHANGELOG.md",
		"implementations/python/tests/test_repo_policy_tools.py", "implementations/python/tests/test_requirement_governance.py", "implementations/python/tests/test_issue_1204_repository_governance.py", "implementations/python/tests/test_semantic_coverage.py",
	}
	filtered := []string{}
	for _, name := range paths {
		if !slices.Contains(exempt, name) && !strings.HasPrefix(name, "tools/") {
			filtered = append(filtered, name)
		}
	}
	return filtered
}

func needsRequirement(paths []string) bool {
	return slices.ContainsFunc(paths, governedPath)
}

func (c *checker) configuredRequirements(ctx context.Context, r *repository, paths []string, uid string, scope *requirementScope) (Report, error) {
	policy, err := loadRequirementPolicy(r)
	if err != nil {
		return Report{}, err
	}
	required := c.request.RequireGovernance || environmentFlag("GC_REQUIRE_GOVERNANCE") || scope != nil
	if policy.source == "ground-control-http" {
		return c.httpRequirements(ctx, r, policy, paths, uid, scope, required)
	}
	if policy.source != "repository" {
		return unevaluatedGovernance("requirement-source-invalid", "Unknown requirement authority source.", true), nil
	}
	authority := &repositoryAuthority{reader: requirementReader{repo: r}}
	findings, err := c.evaluateRequirements(ctx, r, policy, authority, paths, uid, scope)
	if _, invalid := errors.AsType[requirementError](err); invalid {
		return unevaluatedGovernance("repository-requirement-invalid", err.Error(), true), nil
	}
	return finish(findings), err
}

func (c *checker) evaluateRequirements(ctx context.Context, r *repository, policy *requirementPolicy, authority requirementAuthority, paths []string, uid string, scope *requirementScope) ([]Finding, error) {
	if scope != nil {
		return c.scopedRequirements(ctx, r, policy, authority, scope, paths)
	}
	findings, err := evaluateRequirement(ctx, policy, authority, uid, paths)
	if err != nil {
		return nil, err
	}
	entries, err := loadExceptions(r)
	if err != nil {
		return nil, err
	}
	return applyExceptions(findings, entries, uid, c.request.Today)
}

func (c *checker) scopedRequirements(ctx context.Context, r *repository, policy *requirementPolicy, authority requirementAuthority, scope *requirementScope, paths []string) ([]Finding, error) {
	changed := slices.Clone(paths)
	slices.Sort(changed)
	changed = slices.Compact(changed)
	findings := []Finding{}
	for _, name := range changed {
		if _, assigned := scope.bindings[name]; !assigned {
			findings = append(findings, finding("requirement-scope-unassigned", "Changed file has no explicit requirement assignment.", name))
		}
	}
	entries, err := loadExceptions(r)
	if err != nil {
		return nil, err
	}
	for _, uid := range scope.uids {
		owned := []string{}
		for _, name := range changed {
			if slices.Contains(scope.bindings[name], uid) {
				owned = append(owned, name)
			}
		}
		failures, err := evaluateRequirement(ctx, policy, authority, uid, owned)
		if err != nil {
			return nil, err
		}
		failures, err = applyExceptions(failures, entries, uid, c.request.Today)
		if err != nil {
			return nil, err
		}
		findings = append(findings, failures...)
	}
	return findings, nil
}

func unevaluatedGovernance(rule, message string, required bool) Report {
	status := "skipped-unavailable"
	exit := 0
	if required {
		status = "required-unevaluated"
		exit = 1
	}
	f := finding(rule, message, "")
	f.Status = status
	return Report{Findings: []Finding{f}, Status: status, ExitCode: exit}
}

func environmentFlag(name string) bool {
	value := strings.ToLower(strings.TrimFunc(os.Getenv(name), pythonWhitespace))
	return slices.Contains([]string{"1", trueLiteral, "yes", "on"}, value)
}

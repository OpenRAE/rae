package governance

import (
	"context"
	"slices"
	"strings"
)

func (c *checker) repoPolicy(ctx context.Context, r *repository) (Report, error) {
	if c.request.CheckSet == "" {
		c.request.CheckSet = repoFullCheck
	}
	if c.request.CheckSet != repoFullCheck && c.request.CheckSet != "file-local" {
		return Report{}, policyInputError("--check-set must be full or file-local")
	}
	if (c.request.BaseRevisionSet || c.request.BaseRevision != "") && !validRevision(c.request.BaseRevision) {
		return Report{}, policyInputError("invalid base revision")
	}
	policy, transport, findings := loadRepositoryPolicy(r)
	if len(findings) > 0 {
		return c.finish(r, findings)
	}
	changed, err := r.changed(ctx, c.request)
	if err != nil {
		return Report{}, err
	}
	safe, unsafe := repoSafeChanged(r, changed)
	findings = append(findings, unsafe...)
	if len(safe) > 0 {
		var problems []Finding
		problems, err = evaluateRepoRego(ctx, r, map[string]any{"changed": safe, "check_set": c.request.CheckSet, "policy": transport})
		if err != nil {
			return Report{}, err
		}
		findings = append(findings, problems...)
	}
	problems, err := c.repoFilePolicies(ctx, r, policy, safe)
	if err != nil {
		return Report{}, err
	}
	return c.finish(r, append(findings, problems...))
}

func repoSafeChanged(r *repository, changed []string) ([]string, []Finding) {
	safe, findings := []string{}, []Finding{}
	for _, name := range changed {
		if !r.safe(name) {
			findings = append(findings, finding("policy-path-unsafe", "changed path '"+name+"' resolves outside the repository root; refusing to inspect", name))
		} else {
			safe = append(safe, name)
		}
	}
	return safe, findings
}

func (c *checker) repoFilePolicies(ctx context.Context, r *repository, policy *mapping, safe []string) ([]Finding, error) {
	findings, err := repoLayerAndSize(ctx, r, policy, safe)
	if err != nil {
		return nil, err
	}
	problems, err := repoModules(ctx, r, policy, safe, c.request.CheckSet)
	if err != nil {
		return nil, err
	}
	findings = append(findings, problems...)
	if len(safe) > 0 && c.request.CheckSet == repoFullCheck {
		problems, err = repoADRChecks(r, policy, safe)
		if err != nil {
			return nil, err
		}
		findings = append(findings, problems...)
	}
	if slices.Contains(safe, "CHANGELOG.md") {
		problems, err = repoChangelog(r)
		if err != nil {
			return nil, err
		}
		findings = append(findings, problems...)
	}
	return findings, nil
}

func repoADRChanged(changed []string) bool {
	return slices.ContainsFunc(changed, func(name string) bool { return strings.HasPrefix(name, adrDirectory+"/") })
}

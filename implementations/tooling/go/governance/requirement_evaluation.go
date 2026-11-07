package governance

import (
	"context"
	"slices"
	"strings"
)

type requirementFact struct {
	id, uid any
	status  string
}

type requirementAuthority interface {
	get(ctx context.Context, project, uid string) (requirementFact, error)
	links(ctx context.Context, id any) ([]requirementLink, error)
}

type repositoryAuthority struct{ reader requirementReader }

func (a *repositoryAuthority) get(ctx context.Context, _ string, uid string) (requirementFact, error) {
	if err := ctx.Err(); err != nil {
		return requirementFact{}, err
	}
	record, err := a.reader.load(uid)
	return requirementFact{id: record.uid, uid: record.uid, status: record.status}, err
}

func (a *repositoryAuthority) links(ctx context.Context, id any) ([]requirementLink, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	uid, ok := id.(string)
	if !ok {
		return nil, requirementError("Requirement identity is not a canonical UID.")
	}
	record, err := a.reader.load(uid)
	return record.links, err
}

func evaluateRequirement(ctx context.Context, policy *requirementPolicy, authority requirementAuthority, uid string, changed []string) ([]Finding, error) {
	fact, err := authority.get(ctx, policy.project, uid)
	if err != nil {
		return nil, err
	}
	if fact.status == requirementArchived || fact.status == requirementDeprecated {
		return []Finding{finding("requirement-invalid-status", uid+" is "+fact.status+" and is not valid for implementation work", "")}, nil
	}
	phase, err := matchRequirementPhase(ctx, policy, uid)
	if err != nil {
		return nil, err
	}
	if phase == nil {
		return []Finding{finding("requirement-policy-missing", uid+" is not mapped in "+requirementPolicyPath, "")}, nil
	}
	findings, err := requirementPredecessors(ctx, policy, authority, phase)
	if err != nil {
		return nil, err
	}
	findings = append(findings, requirementOwnership(policy, phase, uid, changed)...)
	links, err := authority.links(ctx, fact.id)
	if err != nil {
		return nil, err
	}
	return append(findings, requirementTraceabilityFindings(policy, fact, links, changed)...), nil
}

func matchRequirementPhase(ctx context.Context, policy *requirementPolicy, uid string) (*requirementPhase, error) {
	for i := range policy.phases {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		phase := &policy.phases[i]
		if slices.Contains(phase.uids, uid) {
			return phase, nil
		}
		for _, pattern := range phase.patterns {
			match := pattern.FindStringIndex(uid)
			if err := ctx.Err(); err != nil {
				return nil, err
			}
			if match != nil && match[0] == 0 {
				return phase, nil
			}
		}
	}
	return nil, nil //nolint:nilnil // No phase match is a valid policy lookup result.
}

func requirementPredecessors(ctx context.Context, policy *requirementPolicy, authority requirementAuthority, phase *requirementPhase) ([]Finding, error) {
	findings := []Finding{}
	for _, id := range phase.blockers {
		index := slices.IndexFunc(policy.phases, func(candidate requirementPhase) bool { return candidate.id == id })
		predecessor := &policy.phases[index]
		if predecessor.manual {
			findings = append(findings, finding("requirement-order-blocked", phase.id+" remains deferred until "+id+" is explicitly released", ""))
			continue
		}
		incomplete, err := incompleteRequirements(ctx, policy.project, authority, predecessor.uids)
		if err != nil {
			return nil, err
		}
		if len(incomplete) > 0 {
			findings = append(findings, finding("requirement-order-blocked", phase.id+" is blocked until "+id+" is complete; incomplete prerequisites: "+strings.Join(incomplete, ", "), ""))
		}
	}
	return findings, nil
}

func incompleteRequirements(ctx context.Context, project string, authority requirementAuthority, uids []string) ([]string, error) {
	incomplete := []string{}
	for _, uid := range uids {
		fact, err := authority.get(ctx, project, uid)
		if err != nil {
			return nil, err
		}
		if fact.status != "ACTIVE" {
			incomplete = append(incomplete, uid+" ("+fact.status+")")
		}
	}
	return incomplete, nil
}

func requirementOwnership(policy *requirementPolicy, phase *requirementPhase, uid string, changed []string) []Finding {
	roots := policy.ownership[phase.id]
	if len(roots) == 0 {
		return nil
	}
	owner := "docs/requirements/" + uid + "/requirement.md"
	findings := []Finding{}
	for _, name := range changed {
		if governedPath(name) && name != owner && !pathMatchesAny(name, roots) {
			findings = append(findings, finding("requirement-ownership-mismatch", phase.id+" changes must stay within the mapped ownership roots for that phase", name))
		}
	}
	return findings
}

func governedPath(name string) bool {
	for _, root := range []string{"implementations/", "contracts/", "specs/", "docs/"} {
		if strings.HasPrefix(name, root) {
			return true
		}
	}
	return false
}

func pathMatchesAny(name string, roots []string) bool {
	for _, root := range roots {
		if pathPrefix(name, root) {
			return true
		}
	}
	return false
}

func requirementTraceabilityFindings(policy *requirementPolicy, fact requirementFact, links []requirementLink, changed []string) []Finding {
	checks := []struct {
		kind, artifact, rule, message string
		roots                         []string
	}{
		{"IMPLEMENTS", "CODE_FILE", "traceability-missing-implements", pythonStr(fact.uid) + " is missing an IMPLEMENTS traceability link for this code file", policy.codeRoots},
		{"TESTS", "TEST", "traceability-missing-tests", pythonStr(fact.uid) + " is missing a TESTS traceability link for this test file", policy.testRoots},
	}
	findings := []Finding{}
	for _, name := range changed {
		for _, check := range checks {
			if strings.HasSuffix(name, ".py") && pathMatchesAny(name, check.roots) && !hasRequirementLink(links, check.kind, check.artifact, name) {
				findings = append(findings, finding(check.rule, check.message, name))
			}
		}
	}
	return findings
}

func hasRequirementLink(links []requirementLink, kind, artifact, name string) bool {
	for _, link := range links {
		if link.kind == kind && link.artifact == artifact && link.identifier == name {
			return true
		}
	}
	return false
}

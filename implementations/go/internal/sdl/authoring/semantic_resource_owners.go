package authoring

import (
	"fmt"
	"strings"
)

type semanticResourceBudget struct {
	Owners map[string]semanticResourceOwner `json:"owners"`
}
type semanticResourceOwner struct {
	Kind string `json:"kind"`
	Ref  string `json:"ref"`
}
type semanticResourceScope struct {
	model                                                 *semanticModel
	participants, targets, targetTenants, declaredTenants map[string]bool
	permissions                                           map[[2]string]bool
}

func (m *semanticModel) checkResourceOwners(c *semanticCollector) {
	for _, row := range m.behaviors {
		if row.autonomous == nil || row.autonomous.Budget == nil {
			continue
		}
		scope := m.resourceScope(row)
		for _, id := range m.keys(behaviorSection, row.name, "autonomous_execution", "resource_budget", "owners") {
			owner := row.autonomous.Budget.Owners[id]
			if detail := scope.ownerIssue(owner); detail != "" {
				c.report(semanticOwner{behaviorSection, row.name}, fmt.Sprintf("Behavior specification '%s' resource-budget owner '%s' %s", row.name, id, detail))
			}
		}
	}
}
func (m *semanticModel) resourceScope(row semanticBehavior) semanticResourceScope {
	scope := semanticResourceScope{model: m, participants: map[string]bool{}, targets: map[string]bool{}, targetTenants: map[string]bool{}, declaredTenants: map[string]bool{}, permissions: map[[2]string]bool{}}
	for _, ref := range row.participants {
		scope.participants[strings.TrimPrefix(ref, "agents.")] = true
	}
	for _, ref := range row.autonomous.Actions {
		action := fieldValue(m.transport.ActionContracts)[strings.TrimPrefix(ref, "action_contracts.")]
		for _, effect := range fieldValue(action.Effects) {
			for _, target := range fieldValue(effect.TargetRefs) {
				scope.targets[target] = true
			}
		}
	}
	for _, owner := range row.autonomous.Budget.Owners {
		if owner.Kind == termDeploymentTenant {
			scope.declaredTenants[strings.TrimPrefix(owner.Ref, deploymentTenantPrefix)] = true
		}
	}
	scope.tenantTargets()
	return scope
}
func (s *semanticResourceScope) tenantTargets() {
	nodes := map[string]bool{}
	for ref := range s.targets {
		if node, qualified := strings.CutPrefix(ref, nodesPrefix); qualified {
			node, _, _ = strings.Cut(node, ".services.")
			nodes[node] = true
		}
	}
	for _, cell := range fieldValue(s.model.transport.DeploymentCells) {
		for _, ref := range fieldValue(cell.NodeRefs) {
			if nodes[strings.TrimPrefix(ref, nodesPrefix)] {
				s.targetTenants[strings.TrimPrefix(fieldValue(cell.TenantRef), deploymentTenantPrefix)] = true
			}
		}
	}
	for _, relationship := range s.model.relationships {
		if relationship.kind != usesSharedServiceType {
			continue
		}
		tenant := strings.TrimPrefix(relationship.source, deploymentTenantPrefix)
		s.permissions[[2]string{tenant, relationship.target}] = true
		if s.targets[relationship.target] {
			s.targetTenants[tenant] = true
		}
	}
}
func (s *semanticResourceScope) ownerIssue(owner semanticResourceOwner) string {
	ref := owner.Ref
	switch owner.Kind {
	case participantField:
		if !s.participants[strings.TrimPrefix(ref, "agents.")] {
			return fmt.Sprintf("participant ref '%s' is outside the policy participant scope", ref)
		}
	case termDeploymentTenant:
		tenant := strings.TrimPrefix(ref, deploymentTenantPrefix)
		if !s.model.definitions[deploymentTenantsField][tenant] {
			return fmt.Sprintf("deployment tenant ref '%s' is undefined", ref)
		}
		if !s.targetTenants[tenant] {
			return fmt.Sprintf("deployment tenant ref '%s' does not own an authorized action target", ref)
		}
	case sharedServiceField:
		return s.sharedServiceIssue(ref)
	}
	return ""
}
func (s *semanticResourceScope) sharedServiceIssue(ref string) string {
	if s.model.serviceNode(ref) == "" {
		return fmt.Sprintf("shared service ref '%s' is undefined", ref)
	}
	if !s.targets[ref] {
		return fmt.Sprintf("shared service ref '%s' is not an exact execution target", ref)
	}
	for tenant := range s.declaredTenants {
		if s.permissions[[2]string{tenant, ref}] {
			return ""
		}
	}
	return fmt.Sprintf("shared service ref '%s' lacks an authorized tenant uses_shared_service edge", ref)
}

package authoring

import "strings"

type resourceOwnerScope struct {
	root                                                  materializedChecks
	participants, targets, targetTenants, declaredTenants map[string]bool
	permissions                                           map[[2]string]bool
}

func (a autonomousChecks) resourceOwners() error {
	budget := object(a.policy["resource_budget"])
	if budget == nil {
		return nil
	}
	scope := resourceOwnerScope{root: a.root, participants: map[string]bool{}, targets: map[string]bool{}, targetTenants: map[string]bool{}, declaredTenants: map[string]bool{}, permissions: map[[2]string]bool{}}
	for _, ref := range array(a.spec[participantRefsField]) {
		scope.participants[strings.TrimPrefix(text(ref), "agents.")] = true
	}
	actions := array(a.policy["action_order"])
	if len(actions) == 0 {
		for _, raw := range object(a.policy["action_candidates"]) {
			actions = append(actions, object(raw)["action_ref"])
		}
	}
	scope.actionTargets(actions)
	scope.tenantTargets()
	for _, raw := range object(budget["owners"]) {
		owner := object(raw)
		if owner["kind"] == "deployment_tenant" {
			scope.declaredTenants[strings.TrimPrefix(text(owner["ref"]), deploymentTenantPrefix)] = true
		}
	}
	for _, raw := range object(budget["owners"]) {
		if err := scope.owner(object(raw)); err != nil {
			return err
		}
	}
	return nil
}
func (s *resourceOwnerScope) actionTargets(refs []any) {
	for _, ref := range refs {
		action := object(object(s.root.value[actionsSection])[strings.TrimPrefix(text(ref), "action_contracts.")])
		for _, raw := range array(action["effects"]) {
			for _, target := range array(object(raw)["target_refs"]) {
				s.targets[text(target)] = true
			}
		}
	}
}
func (s *resourceOwnerScope) tenantTargets() {
	nodes := map[string]bool{}
	for target := range s.targets {
		if node, present := strings.CutPrefix(target, nodesPrefix); present {
			node, _, _ = strings.Cut(node, ".services.")
			nodes[node] = true
		}
	}
	for _, raw := range object(s.root.value[deploymentCellsField]) {
		cell := object(raw)
		for _, ref := range array(cell["node_refs"]) {
			if nodes[strings.TrimPrefix(text(ref), nodesPrefix)] {
				s.targetTenants[strings.TrimPrefix(text(cell["tenant_ref"]), deploymentTenantPrefix)] = true
			}
		}
	}
	for _, raw := range object(s.root.value[relationshipsField]) {
		relation := object(raw)
		if relation["type"] != usesSharedServiceType {
			continue
		}
		tenant, target := strings.TrimPrefix(text(relation[sourceField]), deploymentTenantPrefix), text(relation[targetField])
		s.permissions[[2]string{tenant, target}] = true
		if s.targets[target] {
			s.targetTenants[tenant] = true
		}
	}
}
func (s *resourceOwnerScope) owner(owner map[string]any) error {
	ref := text(owner["ref"])
	switch owner["kind"] {
	case participantField:
		if !s.participants[strings.TrimPrefix(ref, "agents.")] {
			return semanticInvalid()
		}
	case "deployment_tenant":
		tenant := strings.TrimPrefix(ref, deploymentTenantPrefix)
		if object(s.root.value[deploymentTenantsField])[tenant] == nil || !s.targetTenants[tenant] {
			return semanticInvalid()
		}
	case sharedServiceField:
		if s.root.namedServiceNode(ref) == "" || !s.targets[ref] {
			return semanticInvalid()
		}
		permitted := false
		for tenant := range s.declaredTenants {
			permitted = permitted || s.permissions[[2]string{tenant, ref}]
		}
		if !permitted {
			return semanticInvalid()
		}
	}
	return nil
}

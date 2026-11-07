package authoring

import "encoding/json"

func (c materializedChecks) interactiveAccess() error {
	for _, raw := range object(c.value[agentsSection]) {
		if err := c.participantAccess(object(raw)); err != nil {
			return err
		}
	}
	return nil
}
func (c materializedChecks) participantAccess(agent map[string]any) error {
	starting, unresolved := c.startingAccessAccounts(agent)
	seen := map[[2]string]bool{}
	for _, raw := range object(agent["interactive_access"]) {
		access := object(raw)
		node, err := c.accessTarget(text(access["target_ref"]))
		if err != nil {
			return err
		}
		if err = c.accessAccount(access, node, starting, unresolved); err != nil {
			return err
		}
		if node == "" || variable(access["channel"]) {
			continue
		}
		channel, err := accessChannel(access["channel"])
		if err != nil {
			return err
		}
		endpoint := [2]string{node, channel}
		if seen[endpoint] {
			return semanticInvalid()
		}
		seen[endpoint] = true
	}
	return nil
}
func accessChannel(raw any) (string, error) {
	if binding := object(raw); binding != nil {
		// Construction has already bounded and admitted this JSON coordinate.
		encoded, err := json.Marshal(binding["coordinate"])
		if err != nil {
			return "", semanticInvalid()
		}
		return string(encoded), nil
	}
	return text(raw), nil
}
func (c materializedChecks) accessTarget(ref string) (string, error) {
	if variable(ref) {
		return "", nil
	}
	node, ok := sectionRef(ref, nodesSection, object(c.value[nodesSection]))
	if !ok || object(object(c.value[nodesSection])[node])["type"] != computeType {
		return "", semanticInvalid()
	}
	return node, nil
}
func (c materializedChecks) startingAccessAccounts(agent map[string]any) (map[string]bool, bool) {
	starting, unresolved := map[string]bool{}, false
	for _, raw := range array(agent["starting_accounts"]) {
		if variable(raw) {
			unresolved = true
			continue
		}
		if name, ok := sectionRef(text(raw), accountsSection, object(c.value[accountsSection])); ok {
			starting[name] = true
		}
	}
	return starting, unresolved
}
func (c materializedChecks) accessAccount(access map[string]any, target string, starting map[string]bool, unresolved bool) error {
	ref := text(access["account_ref"])
	if ref == "" || variable(ref) {
		return nil
	}
	accounts := object(c.value[accountsSection])
	name, ok := sectionRef(ref, accountsSection, accounts)
	if !ok || !starting[name] && !unresolved {
		return semanticInvalid()
	}
	nodeRef := text(object(accounts[name])["node"])
	if variable(nodeRef) {
		return nil
	}
	node, present := sectionRef(nodeRef, nodesSection, object(c.value[nodesSection]))
	if present && target != "" && node != target {
		return semanticInvalid()
	}
	return nil
}

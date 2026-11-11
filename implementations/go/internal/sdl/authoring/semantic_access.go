package authoring

import (
	"encoding/json"
	"fmt"
	"strings"
)

type semanticAccess struct {
	name, channel string
	Target        string          `json:"target_ref"`
	Account       *string         `json:"account_ref"`
	Channel       json.RawMessage `json:"channel"`
}

func (m *semanticModel) accessFacts(name string) ([]semanticAccess, error) {
	values := fieldValue(fieldValue(m.transport.Agents)[name].InteractiveAccess)
	var result []semanticAccess
	for _, id := range m.keys(agentsSection, name, "interactive_access") {
		row := semanticAccess{name: id}
		if err := json.Unmarshal(values[id], &row); err != nil {
			return nil, invalid()
		}
		var err error
		row.channel, err = semanticAccessChannel(row.Channel)
		if err != nil {
			return nil, err
		}
		row.Channel = nil
		result = append(result, row)
	}
	return result, nil
}
func semanticAccessChannel(raw json.RawMessage) (string, error) {
	if len(raw) == 0 || raw[0] != '{' {
		return scalarText(raw, "")
	}
	var profile struct {
		Coordinate struct {
			Namespace string `json:"namespace"`
			Authority string `json:"authority"`
			Profile   string `json:"profile_id"`
			Revision  string `json:"revision"`
			Digest    string `json:"definition_digest"`
		} `json:"coordinate"`
	}
	if err := json.Unmarshal(raw, &profile); err != nil {
		return "", invalid()
	}
	coordinate := profile.Coordinate
	var result strings.Builder
	result.WriteByte('{')
	for i, field := range []struct{ key, value string }{{"namespace", coordinate.Namespace}, {termAuthority, coordinate.Authority}, {"profile_id", coordinate.Profile}, {termRevision, coordinate.Revision}, {"definition_digest", coordinate.Digest}} {
		if i > 0 {
			result.WriteByte(',')
		}
		result.WriteString(`"` + field.key + `":`)
		// Canonical string encoding retains Unicode and does not introduce HTML
		// escapes. Object member order follows the coordinate model's order.
		encoded, err := canonicalSemanticJSON(json.Marshal(field.value))
		if err != nil {
			return "", err
		}
		result.Write(encoded)
	}
	result.WriteByte('}')
	return result.String(), nil
}
func (m *semanticModel) checkInteractiveAccess(c *semanticCollector) {
	for _, agent := range m.agents {
		m.checkAgentAccess(c, agent)
	}
}
func (m *semanticModel) checkAgentAccess(c *semanticCollector, agent semanticAgent) {
	starting, unresolved := map[string]bool{}, false
	for _, ref := range agent.starting {
		if variable(ref) {
			unresolved = true
			continue
		}
		if name, known := m.sectionReference(ref, accountsSection); known {
			starting[name] = true
		}
	}
	seen := map[[2]string]string{}
	owner := semanticOwner{agentsSection, agent.name}
	for _, access := range agent.accesses {
		label := fmt.Sprintf("Agent '%s' interactive_access '%s'", agent.name, access.name)
		target := m.accessTarget(c, owner, label, access.Target)
		m.accessAccount(c, owner, label, access.Account, target, starting, unresolved)
		node, known := m.node(target)
		if !known || node.kind != computeType || variable(access.channel) {
			continue
		}
		endpoint := [2]string{target, access.channel}
		if prior, present := seen[endpoint]; present {
			c.report(owner, fmt.Sprintf("%s duplicates interactive_access target/channel '%s'/'%s' declared by '%s'", label, target, access.channel, prior))
		} else {
			seen[endpoint] = access.name
		}
	}
}
func (m *semanticModel) accessTarget(c *semanticCollector, owner semanticOwner, label, ref string) string {
	if variable(ref) {
		return ""
	}
	name, known := m.sectionReference(ref, nodesSection)
	if !known {
		c.report(owner, fmt.Sprintf("%s target_ref '%s' does not reference a declared compute node", label, ref))
		return ""
	}
	if m.nodes[m.nodeIndex[name]].kind != computeType {
		c.report(owner, fmt.Sprintf("%s target_ref '%s' must reference a compute node", label, ref))
	}
	return name
}
func (m *semanticModel) accessAccount(c *semanticCollector, owner semanticOwner, label string, ref *string, target string, starting map[string]bool, unresolved bool) {
	if ref == nil || variable(*ref) {
		return
	}
	name, known := m.sectionReference(*ref, accountsSection)
	if !known {
		c.report(owner, fmt.Sprintf("%s account_ref '%s' does not reference a declared account", label, *ref))
		return
	}
	nodeRef := fieldValue(fieldValue(m.transport.Accounts)[name].Node)
	if !variable(nodeRef) {
		if node, present := m.sectionReference(nodeRef, nodesSection); present && target != "" && node != target {
			c.report(owner, fmt.Sprintf("%s account_ref '%s' belongs to node '%s', not target '%s'", label, *ref, node, target))
		}
	}
	if !starting[name] && !unresolved {
		c.report(owner, fmt.Sprintf("%s account_ref '%s' is not in starting_accounts", label, *ref))
	}
}

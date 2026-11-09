package authoring

import (
	"encoding/json"
	"fmt"
	"strconv"
)

type semanticRelationshipServices struct {
	database    *semanticDatabaseAccess
	mail        *semanticMailAccess
	forward     *semanticForwardEdge
	integration *semanticServiceIntegration
}
type semanticDatabaseAccess struct {
	Role string `json:"role_ref"`
}
type semanticMailAccess struct {
	Listener string `json:"listener_ref"`
	Mailbox  string `json:"mailbox_ref"`
	Domain   string `json:"domain_ref"`
}
type semanticForwardEdge struct {
	Agent    string `json:"forwarder_ref"`
	Protocol string `json:"protocol"`
}
type semanticServiceIntegration struct {
	Consumer  string `json:"consumer_ref"`
	Engine    string `json:"engine_ref"`
	Principal string `json:"auth_principal_ref"`
}

func (m *semanticModel) relationshipServices(name string, services *semanticRelationshipServices) error {
	raw := fieldValue(m.transport.Relationships)[name]
	if hasField(raw.DatabaseAccess) {
		if json.Unmarshal(fieldValue(raw.DatabaseAccess), &services.database) != nil {
			return invalid()
		}
	}
	if hasField(raw.MailAccess) {
		if json.Unmarshal(fieldValue(raw.MailAccess), &services.mail) != nil {
			return invalid()
		}
	}
	if hasField(raw.ForwardingEdge) {
		if json.Unmarshal(fieldValue(raw.ForwardingEdge), &services.forward) != nil {
			return invalid()
		}
	}
	if hasField(raw.ServiceIntegration) {
		if json.Unmarshal(fieldValue(raw.ServiceIntegration), &services.integration) != nil {
			return invalid()
		}
	}
	return nil
}

// The declaration index retains structural source tokens independently of the
// rendered address. Use its collection position to select the typed owner.
func (m *semanticModel) runtimeCollection(ref, collection string) (*semanticRuntime, int) {
	entry, known := m.index.declarations[ref]
	if !known || len(entry.tokens) < 6 || entry.tokens[0] != nodesSection || entry.tokens[2] != runtimeField || entry.tokens[3] != collection {
		return nil, 0
	}
	node, present := m.nodeIndex[entry.node]
	if !present || m.nodes[node].runtime == nil {
		return nil, 0
	}
	index, err := strconv.Atoi(entry.tokens[4])
	if err != nil || index < 0 {
		return nil, 0
	}
	return m.nodes[node].runtime, index
}
func (m *semanticModel) databaseReference(ref string) *semanticDatabaseService {
	entry, known := m.index.declarations[ref]
	if !known || !referenceDatabase.permits(entry) {
		return nil
	}
	runtime, index := m.runtimeCollection(ref, databaseServicesField)
	if runtime != nil && index < len(runtime.Databases) {
		return &runtime.Databases[index]
	}
	return nil
}
func (m *semanticModel) mailReference(ref string) *semanticMailService {
	entry, known := m.index.declarations[ref]
	if !known || !referenceMail.permits(entry) {
		return nil
	}
	runtime, index := m.runtimeCollection(ref, mailServicesField)
	if runtime != nil && index < len(runtime.Mail) {
		return &runtime.Mail[index]
	}
	return nil
}
func (m *semanticModel) checkRelationshipDatabases(c *semanticCollector) {
	for _, row := range m.relationships {
		if row.services.database == nil {
			continue
		}
		owner, label := semanticOwner{relationshipsField, row.name}, fmt.Sprintf("Relationship '%s'", row.name)
		entry := m.index.declarations[row.source]
		if !variable(row.source) && m.applicationReference(row.source, entry.node) == nil {
			c.report(owner, fmt.Sprintf("%s has database_access but source '%s' does not resolve to a runtime application", label, row.source))
		}
		service := m.databaseReference(row.target)
		if service == nil {
			if !variable(row.target) {
				c.report(owner, fmt.Sprintf("%s has database_access but target '%s' does not resolve to a database service or database", label, row.target))
			}
			continue
		}
		m.databaseAccessRole(c, owner, label, row.services.database.Role, *service)
	}
}
func (m *semanticModel) databaseAccessRole(c *semanticCollector, owner semanticOwner, label, ref string, service semanticDatabaseService) {
	if !concreteReference(ref) {
		return
	}
	for _, role := range service.Roles {
		if role.ID == ref {
			return
		}
	}
	c.report(owner, fmt.Sprintf("%s database_access role_ref '%s' is not a role in database service '%s'", label, ref, service.ID))
}
func (m *semanticModel) checkRelationshipMail(c *semanticCollector) {
	for _, row := range m.relationships {
		if row.services.mail == nil {
			continue
		}
		owner, label := semanticOwner{relationshipsField, row.name}, fmt.Sprintf("Relationship '%s'", row.name)
		service := m.mailReference(row.target)
		if service == nil {
			if !variable(row.target) {
				c.report(owner, fmt.Sprintf("%s has mail_access but target '%s' does not resolve to a mail service", label, row.target))
			}
			continue
		}
		ids, access := service.ids(), row.services.mail
		label += " mail_access"
		c.mailReference(owner, label, "listener_ref", access.Listener, ids.listeners)
		c.mailReference(owner, label, "mailbox_ref", access.Mailbox, ids.mailboxes)
		c.mailReference(owner, label, "domain_ref", access.Domain, ids.domains)
	}
}
func (m *semanticModel) checkRelationshipForwarding(c *semanticCollector) {
	for _, row := range m.relationships {
		if row.services.forward == nil || !concreteReference(row.services.forward.Agent) {
			continue
		}
		m.relationshipForwarding(c, row)
	}
}
func (m *semanticModel) relationshipForwarding(c *semanticCollector, row semanticRelationship) {
	edge := row.services.forward
	owner, label := semanticOwner{relationshipsField, row.name}, fmt.Sprintf("Relationship '%s' forwarding_edge", row.name)
	var matches []semanticForwarder
	for _, agent := range m.forwarders {
		if agent.ID == edge.Agent {
			matches = append(matches, agent)
		}
	}
	switch len(matches) {
	case 0:
		c.report(owner, fmt.Sprintf("%s forwarder_ref '%s' does not resolve to a forwarding agent on any node or in scenario forwarding_agents", label, edge.Agent))
	case 1:
		if !forwardingProtocolsAgree(edge.Protocol, matches[0].Targets) {
			c.report(owner, fmt.Sprintf("%s protocol does not match any ship_target protocol on forwarding agent '%s'", label, edge.Agent))
		}
	default:
		c.report(owner, fmt.Sprintf("%s forwarder_ref '%s' resolves to multiple forwarding agents; forwarding_agent_id values must be unique across scenario forwarding_agents and node runtimes", label, edge.Agent))
	}
}
func forwardingProtocolsAgree(protocol string, targets []semanticForwardTarget) bool {
	if !concreteReference(protocol) || protocol == unknownTerm || len(targets) == 0 {
		return true
	}
	for _, target := range targets {
		if target.protocol() == unknownTerm || variable(target.protocol()) || target.protocol() == protocol {
			return true
		}
	}
	return false
}

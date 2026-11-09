package authoring

import "fmt"

type semanticMailService struct {
	ID         string                         `json:"mail_service_id"`
	Service    string                         `json:"service"`
	Components []semanticRuntimeComponent     `json:"components"`
	Listeners  []semanticRuntimeChildListener `json:"listeners"`
	Domains    []struct {
		ID string `json:"domain_id"`
	} `json:"domains"`
	Stores []struct {
		ID string `json:"store_id"`
	} `json:"mailbox_stores"`
	Mailboxes []semanticMailbox `json:"mailboxes"`
	Aliases   []struct {
		ID      string   `json:"alias_id"`
		Domain  string   `json:"domain_ref"`
		Targets []string `json:"target_refs"`
	} `json:"aliases"`
	Rules []struct {
		ID     string `json:"rule_id"`
		Source string `json:"source_ref"`
		Target string `json:"target_ref"`
	} `json:"routing_rules"`
	Settings []semanticRuntimeSetting `json:"settings"`
}
type semanticMailbox struct {
	ID      string `json:"mailbox_id"`
	Domain  string `json:"domain_ref"`
	Store   string `json:"store_ref"`
	Account string `json:"account_ref"`
	User    string `json:"local_user_ref"`
}
type semanticMailIDs struct{ components, listeners, domains, stores, mailboxes, aliases, recipients, routing map[string]bool }

func (s semanticMailService) ids() semanticMailIDs {
	ids := semanticMailIDs{map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]bool{}}
	for _, item := range s.Components {
		ids.components[item.ID] = true
	}
	for _, item := range s.Listeners {
		ids.listeners[item.ID] = true
	}
	for _, item := range s.Domains {
		ids.domains[item.ID] = true
		ids.routing[item.ID] = true
	}
	for _, item := range s.Stores {
		ids.stores[item.ID] = true
	}
	for _, item := range s.Mailboxes {
		ids.mailboxes[item.ID] = true
		ids.recipients[item.ID] = true
		ids.routing[item.ID] = true
	}
	for _, item := range s.Aliases {
		ids.aliases[item.ID] = true
		ids.recipients[item.ID] = true
		ids.routing[item.ID] = true
	}
	return ids
}
func (c *semanticCollector) mailReference(owner semanticOwner, label, field, ref string, ids map[string]bool) {
	if concreteReference(ref) && !ids[ref] {
		c.report(owner, fmt.Sprintf("%s %s '%s' does not resolve inside mail service", label, field, ref))
	}
}
func (m *semanticModel) checkRuntimeMail(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		for _, service := range node.runtime.Mail {
			check.mailService(service)
		}
	}
}
func (r semanticRuntimeCheck) mailService(s semanticMailService) {
	label := fmt.Sprintf("Node '%s' runtime mail service '%s'", r.node.name, s.ID)
	r.ownedService(label, s.Service)
	ids := s.ids()
	owner := semanticOwner{nodesSection, r.node.name}
	for _, listener := range s.Listeners {
		child := label + " listener '" + listener.ID + "'"
		r.ownedService(child, listener.Service)
		r.collector.mailReference(owner, child, "component_ref", listener.Component, ids.components)
	}
	for _, mailbox := range s.Mailboxes {
		r.mailbox(label+" mailbox '"+mailbox.ID+"'", mailbox, ids)
	}
	for _, alias := range s.Aliases {
		child := label + " alias '" + alias.ID + "'"
		r.collector.mailReference(owner, child, "domain_ref", alias.Domain, ids.domains)
		for _, ref := range alias.Targets {
			r.collector.mailReference(owner, child, "target_ref", ref, ids.recipients)
		}
	}
	for _, rule := range s.Rules {
		child := label + " routing rule '" + rule.ID + "'"
		r.collector.mailReference(owner, child, "source_ref", rule.Source, ids.routing)
		r.collector.mailReference(owner, child, "target_ref", rule.Target, ids.routing)
	}
	r.mailSettings(label, s.Settings, ids.components)
}
func (r semanticRuntimeCheck) mailbox(label string, box semanticMailbox, ids semanticMailIDs) {
	owner := semanticOwner{nodesSection, r.node.name}
	r.collector.mailReference(owner, label, "domain_ref", box.Domain, ids.domains)
	r.collector.mailReference(owner, label, "store_ref", box.Store, ids.stores)
	if concreteReference(box.Account) && !r.model.definitions[accountsSection][box.Account] {
		r.reportf(label, "account_ref '%s' does not resolve to a top-level account", box.Account)
	}
	users := r.node.runtime.localUsers()
	if concreteReference(box.User) && len(users) > 0 && !users[box.User] {
		r.reportf(label, "local_user_ref '%s' does not resolve to a runtime.local_identity user", box.User)
	}
}
func (r semanticRuntimeCheck) mailSettings(label string, settings []semanticRuntimeSetting, components map[string]bool) {
	for _, setting := range settings {
		child := label + " setting '" + setting.ID + "'"
		r.collector.mailReference(semanticOwner{nodesSection, r.node.name}, child, "component_ref", setting.Component, components)
		if concreteReference(setting.Path) && len(r.node.paths) > 0 && !r.node.paths[setting.Path] {
			r.reportf(child, "source_path '%s' does not resolve to an observed file", setting.Path)
		}
	}
}

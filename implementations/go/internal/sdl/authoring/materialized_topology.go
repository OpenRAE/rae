package authoring

import "strings"

type domainTopology struct {
	root        materializedChecks
	controllers map[string]map[string]bool
	memberships map[string]map[string]uint8
	joins       []map[string]any
	pairs       map[[3]string]bool
}

func sectionRef(reference, section string, declarations map[string]any) (string, bool) {
	if _, present := declarations[reference]; present {
		return reference, true
	}
	qualified, prefixed := strings.CutPrefix(reference, section+".")
	_, present := declarations[qualified]
	return qualified, prefixed && present
}

func (c materializedChecks) topology() error {
	t := domainTopology{root: c, controllers: map[string]map[string]bool{}, memberships: map[string]map[string]uint8{}, pairs: map[[3]string]bool{}}
	for _, raw := range object(c.value[relationshipsField]) {
		if err := t.relationship(object(raw)); err != nil {
			return err
		}
	}
	for domain := range object(c.value[identityDomainsField]) {
		if len(t.controllers[domain]) == 0 {
			return semanticInvalid()
		}
	}
	if err := t.joinControllers(); err != nil {
		return err
	}
	if err := t.membershipRules(); err != nil {
		return err
	}
	return t.accounts()
}

func relationshipDetail(relationship map[string]any, kinds map[string]string) error {
	kind := text(relationship["type"])
	if variable(kind) {
		return nil
	}
	for expected, field := range kinds {
		if (kind == expected) != (relationship[field] != nil) {
			return semanticInvalid()
		}
	}
	return nil
}

func (t *domainTopology) relationship(relationship map[string]any) error {
	if err := relationshipDetail(relationship, map[string]string{domainControllerType: "domain_controller", joinsDomainType: "domain_join"}); err != nil {
		return err
	}
	kind := text(relationship["type"])
	if kind != domainControllerType && kind != joinsDomainType || variable(relationship[sourceField]) || variable(relationship[targetField]) {
		return nil
	}
	nodes, domains := object(t.root.value[nodesSection]), object(t.root.value[identityDomainsField])
	node, nodeOK := sectionRef(text(relationship[sourceField]), nodesSection, nodes)
	domain, domainOK := sectionRef(text(relationship[targetField]), identityDomainsField, domains)
	if !nodeOK || !domainOK || text(object(nodes[node])["type"]) != computeType {
		return semanticInvalid()
	}
	identity := [3]string{kind, node, domain}
	if t.pairs[identity] {
		return semanticInvalid()
	}
	t.pairs[identity] = true
	if t.memberships[node] == nil {
		t.memberships[node] = map[string]uint8{}
	}
	if kind == joinsDomainType {
		t.memberships[node][domain] |= 2
		t.joins = append(t.joins, map[string]any{"domain": domain, "refs": object(relationship["domain_join"])["controller_refs"]})
	} else {
		t.memberships[node][domain] |= 1
		if t.controllers[domain] == nil {
			t.controllers[domain] = map[string]bool{}
		}
		t.controllers[domain][node] = true
	}
	return nil
}

func (t *domainTopology) joinControllers() error {
	for _, join := range t.joins {
		for _, ref := range array(join["refs"]) {
			if variable(ref) {
				continue
			}
			node, ok := sectionRef(text(ref), nodesSection, object(t.root.value[nodesSection]))
			if !ok || !t.controllers[text(join["domain"])][node] {
				return semanticInvalid()
			}
		}
	}
	return nil
}

func (t *domainTopology) membershipRules() error {
	for _, bindings := range t.memberships {
		activeDirectory := 0
		for domain, roles := range bindings {
			if roles == 3 {
				return semanticInvalid()
			}
			if text(object(object(t.root.value[identityDomainsField])[domain])["profile"]) == "active_directory" {
				activeDirectory++
			}
		}
		if activeDirectory > 1 {
			return semanticInvalid()
		}
	}
	return nil
}

func (t *domainTopology) accounts() error {
	bound := map[string]string{}
	for name, raw := range object(t.root.value[accountsSection]) {
		account := object(raw)
		ref := text(account["domain_ref"])
		if ref == "" && text(account["spn"]) != "" {
			return semanticInvalid()
		}
		if ref == "" || variable(ref) {
			continue
		}
		domain, ok := sectionRef(ref, identityDomainsField, object(t.root.value[identityDomainsField]))
		if !ok {
			return semanticInvalid()
		}
		if node, known := sectionRef(text(account["node"]), nodesSection, object(t.root.value[nodesSection])); known {
			if t.memberships[node][domain] == 0 {
				return semanticInvalid()
			}
			bound[name] = domain
		}
	}
	return t.authorities(bound)
}

func (t *domainTopology) authorities(bound map[string]string) error {
	accounts := object(t.root.value[accountsSection])
	for domain, raw := range object(t.root.value[identityDomainsField]) {
		reference := text(object(raw)["authority_account_ref"])
		if variable(reference) {
			continue
		}
		name, ok := sectionRef(reference, accountsSection, accounts)
		if !ok {
			return semanticInvalid()
		}
		node, known := sectionRef(text(object(accounts[name])["node"]), nodesSection, object(t.root.value[nodesSection]))
		if !known || !t.controllers[domain][node] || bound[name] != "" && bound[name] != domain {
			return semanticInvalid()
		}
		bound[name] = domain
	}
	return nil
}

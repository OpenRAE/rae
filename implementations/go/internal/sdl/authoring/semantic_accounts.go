package authoring

import (
	"encoding/json"
	"fmt"
)

type semanticAccount struct {
	name, node, method string
	bindings           []semanticCredential
}
type semanticCredential struct{ id, purpose, method string }

func scalarText(raw json.RawMessage, fallback string) (string, error) {
	if len(raw) == 0 {
		return fallback, nil
	}
	var value string
	if err := json.Unmarshal(raw, &value); err != nil {
		return "", invalid()
	}
	return value, nil
}
func (m *semanticModel) accountFacts() error {
	accounts, _ := m.transport.Accounts.Value()
	for _, name := range m.keys(accountsSection) {
		raw := accounts[name]
		method, err := scalarText(fieldValue(raw.AuthMethod), "password")
		if err != nil {
			return err
		}
		account := semanticAccount{name: name, node: fieldValue(raw.Node), method: method}
		for _, row := range fieldValue(raw.CredentialBindings) {
			purpose, err := scalarText(fieldValue(row.Purpose), "")
			if err != nil {
				return err
			}
			method, err := scalarText(fieldValue(row.AuthMethod), "")
			if err != nil {
				return err
			}
			account.bindings = append(account.bindings, semanticCredential{fieldValue(row.CredentialId), purpose, method})
		}
		m.accounts = append(m.accounts, account)
	}
	return nil
}

func (m *semanticModel) checkContentAndAccounts(c *semanticCollector) {
	m.checkContent(c)
	m.checkAccounts(c)
}
func (m *semanticModel) checkContent(c *semanticCollector) {
	content, _ := m.transport.Content.Value()
	for _, name := range m.keys(contentField) {
		target := fieldValue(content[name].Target)
		m.checkContentTarget(c, name, target)
		for _, finding := range m.serviceContent[name] {
			c.report(semanticOwner{finding.Owner.Section, finding.Owner.Name}, finding.Message)
		}
	}
}
func (m *semanticModel) checkContentTarget(c *semanticCollector, name, target string) {
	if target == "" || variable(target) {
		return
	}
	if node, present := m.node(target); !present {
		c.report(semanticOwner{contentField, name}, fmt.Sprintf("Content '%s' targets undefined node '%s'", name, target))
	} else if node.kind != computeType {
		c.report(semanticOwner{contentField, name}, fmt.Sprintf("Content '%s' target '%s' must be a compute node", name, target))
	}
}
func (m *semanticModel) checkAccounts(c *semanticCollector) {
	for _, account := range m.accounts {
		owner := semanticOwner{accountsSection, account.name}
		if account.node != "" && !variable(account.node) {
			if node, present := m.node(account.node); !present {
				c.report(owner, fmt.Sprintf("Account '%s' references undefined node '%s'", account.name, account.node))
			} else if node.kind != computeType {
				c.report(owner, fmt.Sprintf("Account '%s' node '%s' must be a compute node", account.name, account.node))
			}
		}
		for _, issue := range credentialIssues(account) {
			c.report(owner, "Account '"+account.name+"' "+issue)
		}
	}
}

func credentialIssues(account semanticAccount) []string {
	if len(account.bindings) == 0 {
		return nil
	}
	ids, pairs := map[string]bool{}, map[[2]string]bool{}
	duplicateID, duplicatePair, unresolved := false, false, false
	var primary []semanticCredential
	for _, binding := range account.bindings {
		duplicateID = duplicateID || ids[binding.id]
		ids[binding.id] = true
		if variable(binding.purpose) || variable(binding.method) {
			unresolved = true
			continue
		}
		pair := [2]string{binding.purpose, binding.method}
		duplicatePair = duplicatePair || pairs[pair]
		pairs[pair] = true
		if binding.purpose == "primary_authentication" {
			primary = append(primary, binding)
		}
	}
	var issues []string
	if duplicateID {
		issues = append(issues, "credential bindings must use unique credential_id values")
	}
	if duplicatePair {
		issues = append(issues, "credential bindings contain a duplicate credential purpose and authentication method")
	}
	if !unresolved && len(primary) != 1 {
		issues = append(issues, "credential bindings must contain exactly one primary credential binding")
	} else if len(primary) == 1 && !variable(account.method) && account.method != primary[0].method {
		issues = append(issues, "primary credential binding authentication method must match account auth_method posture")
	}
	return issues
}

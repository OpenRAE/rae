package authoring

import (
	"fmt"
	"strings"
)

type semanticLocalIdentity struct {
	Users []struct {
		Username string `json:"username"`
	} `json:"users"`
}

func (runtime *semanticRuntime) localUsers() map[string]bool {
	users := map[string]bool{}
	if runtime.Identity != nil {
		for _, user := range runtime.Identity.Users {
			if user.Username != "" {
				users[user.Username] = true
			}
		}
	}
	return users
}

type semanticSSHServer struct {
	ID      string `json:"ssh_server_id"`
	Service string `json:"service"`
	Rules   []struct {
		ID       string `json:"match_id"`
		Criteria []struct {
			Kind    string `json:"kind"`
			Pattern string `json:"pattern"`
		} `json:"criteria"`
	} `json:"match_rules"`
}

func (m *semanticModel) checkRuntimeSSH(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		users := node.runtime.localUsers()
		for _, server := range node.runtime.SSH {
			check.ssh(server, users)
		}
	}
}
func (r semanticRuntimeCheck) ssh(server semanticSSHServer, users map[string]bool) {
	label := fmt.Sprintf("Node '%s' runtime ssh_server '%s'", r.node.name, server.ID)
	r.ownedService(label, server.Service)
	if len(users) == 0 {
		return
	}
	for _, rule := range server.Rules {
		for _, criterion := range rule.Criteria {
			if criterion.Kind != "local_user" || variable(criterion.Pattern) || strings.ContainsAny(criterion.Pattern, "*?!,") {
				continue
			}
			if !users[criterion.Pattern] {
				r.reportf(label, "match rule '%s' references local user '%s' not present in runtime.local_identity.users", rule.ID, criterion.Pattern)
			}
		}
	}
}

type semanticAuthorization struct {
	Principals []struct {
		ID string `json:"principal_id"`
	} `json:"principals"`
	ID     string                 `json:"app_authorization_id"`
	Roles  []semanticDatabaseRole `json:"roles"`
	Grants []struct {
		ID   string `json:"grant_id"`
		Role string `json:"role_ref"`
	} `json:"permission_grants"`
	Mappings []struct {
		ID   string `json:"mapping_id"`
		Role string `json:"role_ref"`
	} `json:"role_mappings"`
}

func (m *semanticModel) checkRuntimeAuthorizations(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		for _, authorization := range node.runtime.Authorizations {
			check.authorization(authorization)
		}
	}
}
func (r semanticRuntimeCheck) authorization(auth semanticAuthorization) {
	label := fmt.Sprintf("Node '%s' runtime app_authorization '%s'", r.node.name, auth.ID)
	roles := map[string]bool{}
	for _, role := range auth.Roles {
		roles[role.ID] = true
	}
	for _, grant := range auth.Grants {
		r.authorizationRole(label+" permission_grant '"+grant.ID+"'", grant.Role, roles)
	}
	for _, mapping := range auth.Mappings {
		r.authorizationRole(label+" role_mapping '"+mapping.ID+"'", mapping.Role, roles)
	}
}
func (r semanticRuntimeCheck) authorizationRole(label, ref string, roles map[string]bool) {
	if concreteReference(ref) && !roles[ref] {
		r.reportf(label, "role_ref '%s' is not a role in the authorization", ref)
	}
}

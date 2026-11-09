package authoring

type semanticCloudScope struct {
	ID       string `json:"scope_id"`
	Provider string `json:"provider"`
	Parent   string `json:"parent_ref"`
}
type semanticCloudSubject struct {
	ID    string `json:"subject_id"`
	Kind  string `json:"kind"`
	Scope string `json:"resource_scope_ref"`
}
type semanticCloudPolicy struct {
	ID      string               `json:"policy_id"`
	Applies []string             `json:"applies_to_refs"`
	Access  *semanticCloudAccess `json:"resource_access"`
}
type semanticCloudAccess struct {
	Attachment string `json:"attachment_ref"`
	Source     string `json:"inherited_from_ref"`
	Bindings   []struct {
		Principals []string `json:"principal_refs"`
		Resources  []string `json:"resource_refs"`
		Role       string   `json:"role_ref"`
	} `json:"bindings"`
}
type semanticCloudUse struct {
	ID        string `json:"use_id"`
	Workload  string `json:"workload_ref"`
	Principal string `json:"principal_ref"`
	Source    string `json:"source_principal_ref"`
}
type semanticCloudObservation struct {
	ID        string   `json:"observation_id"`
	Principal string   `json:"principal_ref"`
	Resource  string   `json:"resource_ref"`
	Contexts  []string `json:"context_refs"`
}
type semanticCloudSecret struct {
	ID        string                 `json:"secret_id"`
	Scope     string                 `json:"resource_scope_ref"`
	Key       string                 `json:"encryption_key_ref"`
	Reset     string                 `json:"reset_owner_ref"`
	Deletion  string                 `json:"deletion_owner_ref"`
	Versions  []semanticCloudVersion `json:"versions"`
	Consumers []struct {
		Workload string `json:"consumer_ref"`
		Version  string `json:"version_ref"`
		Resolved string `json:"resolved_version_ref"`
	} `json:"consumers"`
}
type semanticCloudVersion struct {
	ID      string `json:"version_id"`
	Payload string `json:"payload_content_ref"`
}
type semanticCloudItem struct {
	authority *semanticIdentityAuthority
	subject   *semanticCloudSubject
	policy    *semanticCloudPolicy
	app       *semanticPlatform
	secret    *semanticCloudSecret
}
type semanticCloud struct {
	model                   *semanticModel
	collector               *semanticCollector
	scopes                  map[string]*semanticCloudScope
	subjects                map[string]*semanticCloudSubject
	policies                map[string]*semanticCloudPolicy
	secrets                 map[string]*semanticCloudSecret
	versions                map[string]*semanticCloudVersion
	versionOwners           map[*semanticCloudVersion]*semanticCloudSecret
	scopeOrder, policyOrder []string
	items                   []semanticCloudItem
}

func newSemanticCloud(m *semanticModel, c *semanticCollector) *semanticCloud {
	cloud := &semanticCloud{model: m, collector: c, scopes: map[string]*semanticCloudScope{}, subjects: map[string]*semanticCloudSubject{}, policies: map[string]*semanticCloudPolicy{}, secrets: map[string]*semanticCloudSecret{}, versions: map[string]*semanticCloudVersion{}, versionOwners: map[*semanticCloudVersion]*semanticCloudSecret{}}
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		base := nodesPrefix + node.name + ".runtime."
		for i := range node.runtime.Authorities {
			cloud.addAuthority(base, &node.runtime.Authorities[i])
		}
		for i := range node.runtime.Platforms {
			cloud.addPlatform(base, &node.runtime.Platforms[i])
		}
	}
	return cloud
}
func (c *semanticCloud) addAuthority(base string, a *semanticIdentityAuthority) {
	base += "identity_authorities." + a.ID
	c.items = append(c.items, semanticCloudItem{authority: a})
	for i := range a.Subjects {
		item := &a.Subjects[i]
		c.subjects[base+".subjects."+item.ID] = item
		c.items = append(c.items, semanticCloudItem{subject: item})
	}
	for i := range a.Policies {
		item := &a.Policies[i]
		address := base + ".policies." + item.ID
		if c.policies[address] == nil {
			c.policyOrder = append(c.policyOrder, address)
		}
		c.policies[address] = item
		c.items = append(c.items, semanticCloudItem{policy: item})
	}
	for i := range a.Scopes {
		item := &a.Scopes[i]
		address := base + ".resource_scopes." + item.ID
		if c.scopes[address] == nil {
			c.scopeOrder = append(c.scopeOrder, address)
		}
		c.scopes[address] = item
	}
}
func (c *semanticCloud) addPlatform(base string, app *semanticPlatform) {
	base += platformApplicationsField + "." + app.ID
	c.items = append(c.items, semanticCloudItem{app: app})
	for i := range app.Secrets {
		secret := &app.Secrets[i]
		address := base + ".secrets." + secret.ID
		c.secrets[address] = secret
		c.items = append(c.items, semanticCloudItem{secret: secret})
		for j := range secret.Versions {
			version := &secret.Versions[j]
			c.versions[address+".versions."+version.ID] = version
			c.versionOwners[version] = secret
		}
	}
}

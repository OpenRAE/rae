package authoring

func (c *semanticCloud) secret(secret *semanticCloudSecret) {
	c.scope(secret.Scope, "secret scope")
	for _, field := range []struct{ label, ref string }{{"encryption_key_ref", secret.Key}, {"reset_owner_ref", secret.Reset}, {"deletion_owner_ref", secret.Deletion}} {
		if field.ref != "" {
			c.resource(field.ref, field.label, false)
		}
	}
	for _, version := range secret.Versions {
		c.payload(version.Payload)
	}
	for _, consumer := range secret.Consumers {
		c.resource(consumer.Workload, "secret consumer reference", true)
		for _, ref := range []string{consumer.Version, consumer.Resolved} {
			if ref != "" {
				c.selectedVersion(secret, ref)
			}
		}
	}
}
func (c *semanticCloud) payload(ref string) {
	if !concreteReference(ref) {
		return
	}
	entry, known := c.model.index.declarations[ref]
	if !known || entry.kind != contentField {
		c.report("cloud-reference: payload content reference must name exact content")
	}
}
func (c *semanticCloud) selectedVersion(secret *semanticCloudSecret, ref string) {
	if c.exactModel(ref, cloudVersions, "selected version reference") {
		if version := c.versions[ref]; version != nil && c.versionOwners[version] != secret {
			c.report("cloud-version: selected version belongs to another secret")
		}
	}
}

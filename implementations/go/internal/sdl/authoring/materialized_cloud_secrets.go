package authoring

func (c cloudChecks) secret(address string, value map[string]any) error {
	if err := c.optionalScope(value); err != nil {
		return err
	}
	for _, field := range []string{"encryption_key_ref", "reset_owner_ref", "deletion_owner_ref"} {
		if ref := text(value[field]); ref != "" {
			if err := c.resource(ref, false); err != nil {
				return err
			}
		}
	}
	for _, raw := range array(value["consumers"]) {
		if err := c.consumer(address, object(raw)); err != nil {
			return err
		}
	}
	return nil
}

func (c cloudChecks) consumer(owner string, consumer map[string]any) error {
	if err := c.resource(text(consumer["consumer_ref"]), true); err != nil {
		return err
	}
	for _, field := range []string{"version_ref", "resolved_version_ref"} {
		if ref := text(consumer[field]); ref != "" {
			if err := c.selectedVersion(owner, ref); err != nil {
				return err
			}
		}
	}
	return nil
}

func (c cloudChecks) selectedVersion(owner, reference string) error {
	version, err := c.model(reference, cloudVersions)
	if err != nil {
		return err
	}
	if version.value != nil && version.parent != owner {
		return semanticInvalid()
	}
	return nil
}

func (c cloudChecks) payload(reference string) error {
	if reference == "" || variable(reference) {
		return nil
	}
	if entry := c.root.index.aliases[reference][reference]; entry.kind != contentField {
		return semanticInvalid()
	}
	return nil
}

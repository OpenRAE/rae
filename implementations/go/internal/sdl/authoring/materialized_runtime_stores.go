package authoring

import "strings"

func (d *declarationIndex) canonicalKind(reference, kind string) bool {
	entry, present := d.aliases[reference][reference]
	return present && entry.kind == kind
}
func (c runtimeChecks) fileServices() error {
	users := runtimeIDs(c.runtime, "local_identity.users.*.username")
	for _, service := range array(c.runtime["file_services"]) {
		if err := c.filePrincipals(service, users); err != nil {
			return err
		}
		if err := fileAccessRules(service); err != nil {
			return err
		}
	}
	return nil
}
func fileAccessRules(service any) error {
	shares, subjects := runtimeIDs(service, "shares.*.share_id"), runtimeIDs(service, "principals.*.principal_id")
	subjects["anonymous"], subjects["guest"] = true, true
	for _, collection := range []string{"access_rules", accessObservationsField} {
		for _, raw := range array(object(service)[collection]) {
			if err := runtimeReference(text(object(raw)["subject_ref"]), subjects); err != nil {
				return err
			}
			reference := text(object(raw)["resource_ref"])
			if reference != "" && !variable(reference) {
				share, _, _ := strings.Cut(reference, ":")
				if !shares[share] {
					return semanticInvalid()
				}
			}
		}
	}
	return nil
}
func (c runtimeChecks) filePrincipals(service any, users map[string]bool) error {
	for _, raw := range array(object(service)["principals"]) {
		principal := object(raw)
		if len(users) > 0 {
			if err := runtimeReference(text(principal["local_user_ref"]), users); err != nil {
				return err
			}
		}
		reference := text(principal["directory_subject_ref"])
		if reference != "" && !variable(reference) && !c.root.index.canonicalKind(reference, "identity_authorities.subjects") {
			return semanticInvalid()
		}
	}
	return nil
}
func runtimeLocalRelations(value any, specs [][2]string) error {
	for _, spec := range specs {
		if err := runtimeOptionalReferences(value, spec[0], runtimeIDs(value, spec[1])); err != nil {
			return err
		}
	}
	return nil
}
func (c runtimeChecks) mailServices() error {
	users := runtimeIDs(c.runtime, "local_identity.users.*.username")
	accounts := map[string]bool{}
	for name := range object(c.root.value[accountsSection]) {
		accounts[name] = true
	}
	for _, service := range array(c.runtime["mail_services"]) {
		if err := c.mailLocalReferences(service); err != nil {
			return err
		}
		if err := c.mailGlobalReferences(service, users, accounts); err != nil {
			return err
		}
	}
	return nil
}
func (c runtimeChecks) mailGlobalReferences(service any, users, accounts map[string]bool) error {
	if err := runtimeOptionalReferences(service, "mailboxes.*.account_ref", accounts); err != nil {
		return err
	}
	if len(users) > 0 {
		if err := runtimeOptionalReferences(service, "mailboxes.*.local_user_ref", users); err != nil {
			return err
		}
	}
	for _, setting := range array(object(service)[settingsField]) {
		if source := text(object(setting)["source_path"]); source != "" {
			if err := c.observedFiles([]any{source}); err != nil {
				return err
			}
		}
	}
	return nil
}
func (c runtimeChecks) mailLocalReferences(service any) error {
	if err := runtimeLocalRelations(service, [][2]string{
		{"listeners.*.component_ref", runtimeComponentIDs}, {"mailboxes.*.domain_ref", runtimeMailDomainIDs}, {"mailboxes.*.store_ref", "mailbox_stores.*.store_id"}, {"aliases.*.domain_ref", runtimeMailDomainIDs}, {"settings.*.component_ref", runtimeComponentIDs},
	}); err != nil {
		return err
	}
	for _, raw := range runtimeValues(service, "listeners.*.service") {
		if err := c.ownedService(text(raw)); err != nil {
			return err
		}
	}
	targets := runtimeIDs(service, "mailboxes.*.mailbox_id")
	for name := range runtimeIDs(service, "aliases.*.alias_id") {
		targets[name] = true
	}
	if err := runtimeOptionalReferences(service, "aliases.*.target_refs.*", targets); err != nil {
		return err
	}
	for name := range runtimeIDs(service, runtimeMailDomainIDs) {
		targets[name] = true
	}
	for _, path := range []string{"routing_rules.*.source_ref", "routing_rules.*.target_ref"} {
		if err := runtimeOptionalReferences(service, path, targets); err != nil {
			return err
		}
	}
	return nil
}
func (c runtimeChecks) sensorNetworks() error {
	attached := runtimeIDs(c.runtime, "network.endpoints.*.network")
	for _, reference := range runtimeValues(c.runtime, "network_sensors.*.monitored_network_refs.*") {
		if err := c.root.switchReference(text(reference)); err != nil {
			return err
		}
		if len(attached) > 0 {
			if err := runtimeReference(text(reference), attached); err != nil {
				return err
			}
		}
	}
	for _, reference := range runtimeValues(c.runtime, "network_detection_engines.*.network_sets.*.network_refs.*") {
		if err := c.root.switchReference(text(reference)); err != nil {
			return err
		}
	}
	return nil
}

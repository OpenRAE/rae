package admission

func (r *materializationInventory) lineage() error {
	if !boolean(at(r.report, "complete")) || len(array(at(r.report, "unavailable_evidence"))) > 0 {
		return invalid()
	}
	old, current := controlRows(at(r.preceding, "descendants"), "address"), controlRows(at(r.report, "descendants"), "address")
	if r.preceding != nil && !numericGreater(at(r.report, "sequence"), at(r.preceding, "sequence")) {
		return invalid()
	}
	if !subset(mapKeys(old), keySet(current)) {
		return invalid()
	}
	for address, entry := range current {
		if err := r.descendantIdentity(address, entry, old, current); err != nil {
			return err
		}
	}
	return nil
}
func materializationRetainedIdentity(before, entry any) error {
	if !matchingFields(before, entry, "address", "parent_address", "parent_instance_index", "source_address", "native_identity_digest", "creation") {
		return invalid()
	}
	from, to := stringAt(before, "state"), stringAt(entry, "state")
	allowed := map[string]map[string]bool{termActive: {termActive: true, termTerminated: true, termAutoremoved: true}, termTerminated: {termTerminated: true, termAutoremoved: true}, termAutoremoved: {termAutoremoved: true}}
	return require(allowed[from][to] && (from != to || equal(at(before, "lifecycle"), at(entry, "lifecycle"))))
}
func (r *materializationInventory) ancestry(entry any, current map[string]any) error {
	seen := map[string]bool{stringAt(entry, "address"): true}
	descendant := entry
	source := stringAt(entry, "source_address")
	for r.originals[stringAt(descendant, "parent_address")] == nil {
		parent := current[stringAt(descendant, "parent_address")]
		if parent == nil || seen[stringAt(parent, "address")] || len(seen) >= 64 || stringAt(parent, "source_address") != source || !numericEqual(at(descendant, "parent_instance_index"), jsonZero) {
			return invalid()
		}
		seen[stringAt(parent, "address")] = true
		descendant = parent
	}
	resource := r.execution.current.resources[source]
	if stringAt(descendant, "parent_address") != source || resource == nil || !subset([]string{stringAt(resource, "resource_type")}, map[string]bool{termNode: true, termNetwork: true}) {
		return invalid()
	}
	count := at(resource, "payload", "count")
	if count == nil || numericEqual(count, jsonZero) {
		count = jsonOne
	}
	return require(numericGreater(count, at(descendant, "parent_instance_index")))
}

func (r *materializationInventory) descendantIdentity(address string, entry any, old, current map[string]any) error {
	before := old[address]
	if r.originals[address] != nil || r.originals[stringAt(entry, "source_address")] == nil {
		return invalid()
	}
	if before == nil && object(at(r.execution.previous, "entries"))[address] != nil {
		return invalid()
	}
	if before != nil {
		if err := materializationRetainedIdentity(before, entry); err != nil {
			return err
		}
	}
	if at(entry, "lifecycle") != nil && (before == nil || !equal(entry, before)) && (!equal(at(entry, "lifecycle", "operation_id"), at(r.execution.plan, "operation_id")) || !equal(at(entry, "lifecycle", "attempt_id"), at(r.report, "attempt_id"))) {
		return invalid()
	}
	if err := r.ancestry(entry, current); err != nil {
		return err
	}
	return nil
}

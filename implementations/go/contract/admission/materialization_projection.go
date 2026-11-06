package admission

import (
	"maps"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
)

func (r *materializationInventory) project() error {
	if err := r.descriptionCoverage(); err != nil {
		return err
	}
	r.entries = maps.Clone(object(at(r.execution.actual, "entries")))
	for _, record := range array(at(r.report, "descendants")) {
		key := stringAt(record, "address")
		resource := r.execution.current.resources[key]
		if stringAt(record, "state") == termAutoremoved {
			if resource != nil {
				return invalid()
			}
			delete(r.entries, key)
			continue
		}
		if err := materializationDescendantResource(resource, key); err != nil {
			return err
		}
		entry := maps.Clone(object(resource))
		entry["status"] = termReady
		if stringAt(record, "state") == termTerminated {
			entry["status"] = termTerminated
		}
		r.entries[key] = entry
	}
	return nil
}
func materializationDescendantResource(resource any, key string) error {
	kind := stringAt(resource, "resource_type")
	if resource == nil || stringAt(resource, "domain") != termProvisioning || kind != termNode && kind != termNetwork {
		return invalid()
	}
	prefix := "provision.node."
	if kind == termNetwork {
		prefix = "provision.network."
	}
	name := stringAt(resource, "payload", "name")
	if !address.Valid(key) || key != prefix+name || !strings.HasPrefix(key, prefix) || len(array(at(resource, "profile_bindings"))) > 0 {
		return invalid()
	}
	count := at(resource, "payload", "count")
	return require(count == nil || numericEqual(count, jsonZero) || numericEqual(count, jsonOne))
}

func (r *materializationInventory) descriptionCoverage() error {
	old := rowSet(at(r.preceding, "descendants"), "address")
	declared := map[string]bool{}
	for _, entry := range array(at(r.report, "descendants")) {
		if stringAt(entry, "state") != termAutoremoved {
			declared[stringAt(entry, "address")] = true
		}
	}
	described := keySet(materializationScope(r.execution.current.resources, termProvisioning))
	for original := range r.originals {
		delete(described, original)
	}
	foreign := map[string]bool{}
	for key := range materializationScope(object(at(r.execution.actual, "entries")), termProvisioning) {
		if r.originals[key] == nil && !old[key] {
			foreign[key] = true
		}
	}
	for key := range foreign {
		declared[key] = true
	}
	if !equalSet(described, declared) {
		return invalid()
	}
	return nil
}

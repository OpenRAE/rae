package authoring

import (
	"slices"
	"strings"
)

type runtimeChecks struct {
	root          materializedChecks
	name          string
	node, runtime map[string]any
	services      map[string]any
	paths         map[string]bool
}

func indexServiceOwners(value map[string]any) map[string]map[string]bool {
	owners := map[string]map[string]bool{}
	for name, raw := range object(value[nodesSection]) {
		for _, service := range array(object(raw)[servicesField]) {
			if key := text(object(service)[nameField]); key != "" {
				address := "nodes." + name + ".services." + key
				if owners[address] == nil {
					owners[address] = map[string]bool{}
				}
				owners[address][name] = true
			}
		}
	}
	return owners
}

func (c materializedChecks) runtimeServices() error {
	for name, raw := range object(c.value[nodesSection]) {
		node := object(raw)
		if runtime := object(node["runtime"]); runtime != nil {
			check := newRuntimeChecks(c, name, node, runtime)
			for _, pass := range []func() error{check.applications, check.serviceUnits, check.processSelectors, check.familyReferences, check.databaseReferences, check.authorizationReferences, check.sshReferences, check.fileServices, check.mailServices, check.sensorNetworks, check.listeners, check.identityAuthorities, check.securityMonitoring} {
				if err := pass(); err != nil {
					return err
				}
			}
		}
	}
	return nil
}
func newRuntimeChecks(root materializedChecks, name string, node, runtime map[string]any) runtimeChecks {
	check := runtimeChecks{root: root, name: name, node: node, runtime: runtime, services: map[string]any{}, paths: map[string]bool{}}
	for _, service := range array(node[servicesField]) {
		if name := text(object(service)[nameField]); name != "" {
			check.services[name] = service
		}
	}
	for _, entry := range array(runtime["filesystem_inventory"]) {
		if path := text(object(entry)["path"]); path != "" {
			check.paths[path] = true
		}
	}
	build := object(object(node[sourceField])["build"])
	for _, field := range []string{"copied_sources", "source_inputs"} {
		for _, entry := range array(build[field]) {
			if path := text(object(entry)["destination_path"]); path != "" {
				check.paths[path] = true
			}
		}
	}
	return check
}
func (c runtimeChecks) ownedService(reference string) error {
	if reference == "" || variable(reference) {
		return nil
	}
	if strings.HasPrefix(reference, "nodes.") {
		if c.root.serviceOwners[reference][c.name] {
			return nil
		}
	} else if _, present := c.services[reference]; present {
		return nil
	}
	return semanticInvalid()
}
func (c runtimeChecks) observedFiles(values []any) error {
	if len(c.paths) == 0 {
		return nil
	}
	for _, raw := range values {
		path := text(raw)
		if !variable(path) && !c.paths[path] {
			return semanticInvalid()
		}
	}
	return nil
}
func (c runtimeChecks) applications() error {
	for _, raw := range array(c.runtime[applicationsField]) {
		application := object(raw)
		if err := c.ownedService(text(application["service"])); err != nil {
			return err
		}
		for _, rawRoute := range array(application["routes"]) {
			route := object(rawRoute)
			for _, field := range []string{"templates", "static_assets"} {
				if err := c.observedFiles(array(route[field])); err != nil {
					return err
				}
			}
			if err := c.upstream(object(route["upstream_target"])); err != nil {
				return err
			}
		}
	}
	return nil
}
func (c runtimeChecks) upstream(target map[string]any) error {
	if target == nil {
		return nil
	}
	node, service := text(target["target_node_ref"]), text(target["target_service"])
	if node != "" && !variable(node) && object(c.root.value[nodesSection])[node] == nil {
		return semanticInvalid()
	}
	if service == "" || variable(service) {
		return nil
	}
	if len(c.root.serviceOwners[service]) > 0 {
		return c.upstreamQualified(node, service)
	}
	if node == "" || variable(node) {
		return semanticInvalid()
	}
	return c.serviceOnNode(node, service)
}
func (c runtimeChecks) serviceOnNode(name, reference string) error {
	if reference != "" && c.root.serviceOwners["nodes."+name+".services."+reference][name] {
		return nil
	}
	return semanticInvalid()
}
func (c runtimeChecks) upstreamQualified(expected, reference string) error {
	owners := c.root.serviceOwners[reference]
	if expected != "" && !variable(expected) && owners[expected] || (expected == "" || variable(expected)) && len(owners) > 0 {
		return nil
	}
	return semanticInvalid()
}
func (c runtimeChecks) serviceUnits() error {
	for _, raw := range array(c.runtime["service_manager_units"]) {
		unit := object(raw)
		if err := c.ownedService(text(unit["service"])); err != nil {
			return err
		}
		if path := text(unit["unit_file_path"]); path != "" {
			if err := c.observedFiles([]any{path}); err != nil {
				return err
			}
		}
	}
	return nil
}
func (c runtimeChecks) processSelectors() error {
	processes := array(c.runtime["processes"])
	names := map[string]bool{}
	for _, process := range processes {
		if name := text(object(process)[nameField]); name != "" && !variable(name) {
			names[name] = true
		}
	}
	if len(names) > 0 {
		for _, raw := range array(object(c.runtime["linux_capabilities"])["process_overrides"]) {
			name := text(object(object(raw)["subject"])[nameField])
			if name != "" && !variable(name) && !names[name] {
				return semanticInvalid()
			}
		}
	}
	limits := object(object(c.runtime["operational_policy"])["resource_limits"])
	for _, raw := range array(limits["process_limits"]) {
		selector := object(object(raw)["subject"])
		if !slices.ContainsFunc(processes, func(process any) bool { return processSelectorMatches(selector, object(process)) }) {
			return semanticInvalid()
		}
	}
	return nil
}
func processSelectorMatches(selector, candidate map[string]any) bool {
	for _, field := range []string{nameField, "pid", "parent_pid", "user", "group", "working_directory", roleTerm, "command_redacted", commandField} {
		value := selector[field]
		if value == nil || value == "" || value == false || field == roleTerm && value == "other" || field == commandField && len(array(value)) == 0 {
			continue
		}
		if field == commandField {
			if !slices.EqualFunc(array(value), array(candidate[field]), scalarEqual) {
				return false
			}
		} else if !scalarEqual(value, candidate[field]) && (value != true || candidate[field] != true) {
			return false
		}
	}
	return true
}

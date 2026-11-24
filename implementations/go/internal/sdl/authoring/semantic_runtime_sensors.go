package authoring

import (
	"fmt"
	"slices"
	"strings"
)

type semanticRuntimeCheck struct {
	model     *semanticModel
	collector *semanticCollector
	node      semanticNode
}

func (r semanticRuntimeCheck) reportf(label, format string, args ...any) {
	r.collector.report(semanticOwner{nodesSection, r.node.name}, label+" "+fmt.Sprintf(format, args...))
}
func (r semanticRuntimeCheck) files(label, field string, refs []string) {
	if len(r.node.paths) == 0 {
		return
	}
	for _, ref := range refs {
		if !variable(ref) && !r.node.paths[ref] {
			r.reportf(label, "%s ref '%s' does not resolve to an observed file on the node", field, ref)
		}
	}
}
func (r semanticRuntimeCheck) fileGroups(label string, configuration, logs, evidence []string) {
	r.files(label, "configuration_file_refs", configuration)
	r.files(label, "log_file_refs", logs)
	r.files(label, evidenceRefsField, evidence)
}
func (m *semanticModel) checkRuntimeSensors(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		attached := runtimeEndpointNetworks(node.runtime)
		for _, sensor := range node.runtime.Sensors {
			label := fmt.Sprintf("Node '%s' runtime network sensor '%s'", node.name, sensor.ID)
			check.fileGroups(label, sensor.Configuration, sensor.Logs, sensor.Evidence)
			for _, ref := range sensor.Networks {
				check.sensorNetwork(label, ref, attached)
			}
		}
	}
}
func (r semanticRuntimeCheck) sensorNetwork(label, ref string, attached map[string]bool) {
	if variable(ref) {
		return
	}
	if !r.model.definitions[infrastructureField][ref] {
		r.reportf(label, "monitored_network_ref '%s' references undefined network", ref)
		return
	}
	if !r.model.isSwitch(ref) {
		r.reportf(label, "monitored_network_ref '%s' must reference a switch/network entry", ref)
		return
	}
	if len(attached) > 0 && !attached[ref] {
		r.reportf(label, "monitored_network_ref '%s' is not attached to node '%s'", ref, r.node.name)
	}
}
func (m *semanticModel) checkRuntimeDetection(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		sensors := map[string]bool{}
		for _, sensor := range node.runtime.Sensors {
			sensors[sensor.ID] = true
		}
		for _, engine := range node.runtime.Engines {
			check.detection(engine, sensors)
		}
	}
}
func (r semanticRuntimeCheck) detection(engine semanticDetectionEngine, sensors map[string]bool) {
	label := fmt.Sprintf("Node '%s' runtime network detection engine '%s'", r.node.name, engine.ID)
	if engine.Sensor != "" && !variable(engine.Sensor) && !sensors[engine.Sensor] {
		r.reportf(label, "sensor_ref '%s' does not resolve to a same-node network sensor", engine.Sensor)
	}
	r.fileGroups(label, engine.Configuration, engine.Logs, engine.Evidence)
	for _, source := range engine.Sources {
		r.files(label+" rule_source '"+source.ID+"'", "file_refs", source.Files)
	}
	for _, set := range engine.Networks {
		for _, ref := range set.References {
			r.detectionNetwork(label+" network_set '"+set.ID+"'", ref)
		}
	}
	for _, output := range engine.Outputs {
		if output.Path != "" {
			r.files(label+" output_stream '"+output.ID+"'", "path", []string{output.Path})
		}
	}
	for _, channel := range engine.Channels {
		channelLabel := label + " control_channel '" + channel.ID + "'"
		r.ownedService(channelLabel, channel.Service)
		if channel.Path != "" {
			r.files(channelLabel, "path", []string{channel.Path})
		}
	}
}
func (r semanticRuntimeCheck) detectionNetwork(label, ref string) {
	if variable(ref) {
		return
	}
	if !r.model.definitions[infrastructureField][ref] {
		r.reportf(label, "network_ref '%s' references undefined network", ref)
		return
	}
	if !r.model.isSwitch(ref) {
		r.reportf(label, "network_ref '%s' must reference a switch/network entry", ref)
	}
}
func (r semanticRuntimeCheck) ownedService(label, ref string) (string, bool) {
	if ref == "" || variable(ref) {
		return "", false
	}
	name := ref
	if strings.HasPrefix(ref, nodesPrefix) {
		node, service, known := r.model.findService(ref)
		if !known {
			r.reportf(label, "service ref '%s' must be a bare service name or 'nodes.<node>.services.<name>'", ref)
			return "", false
		}
		if node != r.node.name {
			r.reportf(label, "service ref '%s' must reference a service on the same node", ref)
			return "", false
		}
		name = service
	}
	if !slices.Contains(r.node.services, name) {
		r.reportf(label, "references undefined service '%s'", name)
		return "", false
	}
	return name, true
}
func (m *semanticModel) checkRuleSourceGenerators(c *semanticCollector) {
	agents := map[string]bool{}
	for _, agent := range m.forwarders {
		agents[agent.address] = true
	}
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		for _, engine := range node.runtime.Engines {
			check.ruleSourceGenerators(engine, agents)
		}
	}
}
func (r semanticRuntimeCheck) ruleSourceGenerators(engine semanticDetectionEngine, agents map[string]bool) {
	for _, source := range engine.Sources {
		if source.Generator == "" || variable(source.Generator) {
			continue
		}
		matches := 0
		for address := range r.model.index.aliases[source.Generator] {
			if agents[address] {
				matches++
			}
		}
		if matches != 1 {
			r.reportf(fmt.Sprintf("Node '%s' runtime network detection engine '%s' rule_source '%s'", r.node.name, engine.ID, source.ID), "generated_by '%s' does not resolve to a declared forwarding agent", source.Generator)
		}
	}
}

func runtimeEndpointNetworks(runtime *semanticRuntime) map[string]bool {
	attached := map[string]bool{}
	if runtime.Network != nil {
		for _, endpoint := range runtime.Network.Endpoints {
			if endpoint.Network != "" {
				attached[endpoint.Network] = true
			}
		}
	}
	return attached
}

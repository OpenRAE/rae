package authoring

import "strings"

func knownListenerProtocol(value any) string {
	protocol := lower(text(value))
	if protocol == unknownTerm || protocol == "other" || variable(value) {
		return ""
	}
	return protocol
}
func publishedPortKey(value any) [4]string {
	row := object(value)
	protocol, present := row[protocolField]
	if !present {
		protocol = tcpProtocol
	}
	return [4]string{text(row["host_ip"]), pythonScalar(row["host_port"]), pythonScalar(row["container_port"]), text(protocol)}
}
func (c runtimeChecks) listeners() error {
	processes := map[string]bool{}
	for _, raw := range array(c.runtime["processes"]) {
		process := object(raw)
		if name := text(process[nameField]); name != "" {
			processes[name] = true
		}
		if process["pid"] != nil {
			processes[pythonScalar(process["pid"])] = true
		}
	}
	published := map[[4]string]bool{}
	for _, raw := range array(object(c.runtime["network"])["published_ports"]) {
		published[publishedPortKey(raw)] = true
	}
	for _, raw := range array(c.runtime["service_listeners"]) {
		listener := object(raw)
		if err := c.listenerService(listener); err != nil {
			return err
		}
		if err := runtimeReference(text(listener["process_ref"]), processes); err != nil {
			return err
		}
		if err := listenerPublishedRefs(listener, published); err != nil {
			return err
		}
	}
	return nil
}
func (c runtimeChecks) listenerService(listener map[string]any) error {
	protocol := knownListenerProtocol(listener[protocolField])
	if protocol == tcpProtocol && (text(listener["socket_path"]) != "" || listener["address_family"] == "unix" || listener["scope"] == "local_socket") {
		return semanticInvalid()
	}
	reference := text(listener["service"])
	if err := c.ownedService(reference); err != nil {
		return err
	}
	if reference == "" || variable(reference) {
		return nil
	}
	if strings.HasPrefix(reference, nodesPrefix) {
		reference = strings.TrimPrefix(reference, nodesPrefix+c.name+".services.")
	}
	service := object(c.services[reference])
	serviceProtocol, present := service[protocolField]
	if !present {
		serviceProtocol = tcpProtocol
	}
	if variable(service["port"]) || variable(serviceProtocol) {
		return nil
	}
	if port, supplied := listener["port"]; supplied && port != nil && !variable(port) && !scalarEqual(port, service["port"]) {
		return semanticInvalid()
	}
	if protocol != "" && protocol != lower(text(serviceProtocol)) {
		return semanticInvalid()
	}
	return nil
}
func listenerPublishedRefs(listener map[string]any, published map[[4]string]bool) error {
	port, portSupplied := listener["port"]
	protocol := knownListenerProtocol(listener[protocolField])
	for _, raw := range array(listener["published_port_refs"]) {
		ref := object(raw)
		if containsVariable(ref) {
			continue
		}
		if portSupplied && port != nil && !variable(port) && !scalarEqual(ref["container_port"], port) {
			return semanticInvalid()
		}
		refProtocol, present := ref[protocolField]
		if !present {
			refProtocol = tcpProtocol
		}
		if protocol != "" && refProtocol != protocol {
			return semanticInvalid()
		}
		if !published[publishedPortKey(ref)] {
			return semanticInvalid()
		}
	}
	return nil
}

package authoring

import (
	"encoding/json"
	"fmt"
	"strings"
)

type semanticService struct {
	name, protocol string
	port           semanticInteger
}
type semanticListener struct {
	ID        string                  `json:"service_listener_id"`
	Service   string                  `json:"service"`
	Port      semanticInteger         `json:"port"`
	Protocol  *string                 `json:"protocol"`
	Family    string                  `json:"address_family"`
	Scope     string                  `json:"scope"`
	Socket    string                  `json:"socket_path"`
	Process   string                  `json:"process_ref"`
	Published []semanticPublishedPort `json:"published_port_refs"`
}
type semanticPublishedPort struct {
	HostIP    string          `json:"host_ip"`
	Host      semanticInteger `json:"host_port"`
	Container semanticInteger `json:"container_port"`
	Protocol  *string         `json:"protocol"`
}

func (m *semanticModel) nodeServiceFacts(name string, node *semanticNode) error {
	node.serviceDetails = map[string]semanticService{}
	for _, service := range fieldValue(fieldValue(m.transport.Nodes)[name].Services) {
		serviceName, err := scalarText(fieldValue(service.Name), "")
		if err != nil {
			return err
		}
		node.services = append(node.services, serviceName)
		record := semanticService{name: serviceName, protocol: tcpProtocol}
		if service.Protocol.Present() {
			record.protocol = fieldValue(service.Protocol)
		}
		if err := json.Unmarshal(fieldValue(service.Port), &record.port); err != nil {
			return invalid()
		}
		if serviceName != "" {
			node.serviceDetails[serviceName] = record
		}
	}
	return nil
}
func (number semanticInteger) key() string {
	if number.integer != nil {
		return "n:" + number.integer.String()
	}
	if number.variable != "" {
		return "v:" + number.variable
	}
	return nullType
}
func (port semanticPublishedPort) protocol() string {
	if port.Protocol == nil {
		return tcpProtocol
	}
	return *port.Protocol
}
func (port semanticPublishedPort) key() [4]string {
	return [4]string{port.HostIP, port.Host.key(), port.Container.key(), port.protocol()}
}
func (port semanticPublishedPort) unresolved() bool {
	return variable(port.HostIP) || port.Host.variable != "" || port.Container.variable != "" || variable(port.protocol())
}
func (listener semanticListener) knownProtocol() string {
	protocol := tcpProtocol
	if listener.Protocol != nil {
		protocol = *listener.Protocol
	}
	if protocol == "" || variable(protocol) {
		return ""
	}
	protocol = strings.ToLower(protocol)
	if protocol == unknownTerm || protocol == otherTerm {
		return ""
	}
	return protocol
}
func (m *semanticModel) checkRuntimeListeners(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		processes := check.processReferences()
		published := map[[4]string]bool{}
		if node.runtime.Network != nil {
			for _, port := range node.runtime.Network.Published {
				published[port.key()] = true
			}
		}
		for _, listener := range node.runtime.Listeners {
			check.listener(listener, processes, published)
		}
	}
}
func (r semanticRuntimeCheck) processReferences() map[string]bool {
	refs := map[string]bool{}
	for _, process := range r.node.runtime.Processes {
		if process.Name != "" && !variable(process.Name) {
			refs[process.Name] = true
		}
		if process.PID.integer != nil {
			refs[process.PID.integer.String()] = true
		}
	}
	return refs
}
func (r semanticRuntimeCheck) listener(listener semanticListener, processes map[string]bool, published map[[4]string]bool) {
	label := fmt.Sprintf("Node '%s' runtime service listener '%s'", r.node.name, listener.ID)
	if listener.Protocol != nil && listener.knownProtocol() == tcpProtocol && (listener.Socket != "" || listener.Family == "unix" || listener.Scope == "local_socket") {
		r.reportf(label, "supplied TCP protocol contradicts Unix listener facts")
	}
	if name, known := r.ownedService(label, listener.Service); known {
		r.listenerService(label, listener, r.node.serviceDetails[name])
	}
	if listener.Process != "" && !variable(listener.Process) && !processes[listener.Process] {
		r.reportf(label, "process_ref '%s' does not resolve to a runtime process name or pid", listener.Process)
	}
	r.listenerPublished(label, listener, published)
}
func (r semanticRuntimeCheck) listenerService(label string, listener semanticListener, service semanticService) {
	if service.port.variable != "" || variable(service.protocol) {
		return
	}
	// A nullable port has no non-null default. Its active value therefore also
	// proves suppliedness for these authored/materialized comparisons.
	portMismatch := listener.Port.active() && listener.Port.variable == "" && !listener.Port.equal(service.port)
	protocol := listener.knownProtocol()
	protocolMismatch := listener.Protocol != nil && protocol != "" && protocol != strings.ToLower(service.protocol)
	if portMismatch || protocolMismatch {
		r.reportf(label, "port/protocol must match service '%s'", service.name)
	}
}
func (r semanticRuntimeCheck) listenerPublished(label string, listener semanticListener, published map[[4]string]bool) {
	protocol := listener.knownProtocol()
	for _, ref := range listener.Published {
		if ref.unresolved() {
			continue
		}
		portMismatch := listener.Port.active() && listener.Port.variable == "" && !ref.Container.equal(listener.Port)
		protocolMismatch := listener.Protocol != nil && protocol != "" && ref.protocol() != protocol
		if portMismatch || protocolMismatch {
			r.reportf(label, "published_port_refs entry must match listener port/protocol")
			continue
		}
		if !published[ref.key()] {
			r.reportf(label, "published_port_refs entry does not resolve to runtime.network.published_ports")
		}
	}
}

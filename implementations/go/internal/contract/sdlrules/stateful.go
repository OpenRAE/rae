// Package sdlrules owns SDL reference predicates shared by contract and SDL
// admission. Callers bound and construct normalized input before reporting.
package sdlrules

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// Owner retains a declaration's section and key without parsing its address.
type Owner struct{ Section, Name string }

// Finding is one ordered domain finding, before source locations are attached.
type Finding struct {
	Owner   Owner
	Message string
}

// StatefulReferences reports every stateful-resource reference violation in
// constructed normalized SDL. Order supplies mapping keys by JSON pointer;
// absent order entries use lexical order. The input and order are not mutated.
func StatefulReferences(data []byte, order map[string][]string) ([]Finding, error) {
	m, err := decodeStateful(data, order)
	if err != nil {
		return nil, err
	}
	m.check()
	return m.findings, nil
}
func projectionInvalid() error {
	return fault.New(fault.InvalidInput, "sdl-stateful-projection-invalid", nil)
}
func (m *statefulModel) report(owner Owner, message string) {
	m.findings = append(m.findings, Finding{owner, message})
}
func (m *statefulModel) check() {
	for _, row := range m.resources {
		if row.owner.Section == generatedSection && len(row.consumers) > 0 {
			m.consumed[row.owner.Name] = true
		}
		m.consumers(row)
		m.dependencies(row)
	}
	for _, node := range m.nodes {
		for _, binding := range node.bindings {
			m.valueBinding(binding)
		}
	}
	for _, binding := range m.content {
		m.valueBinding(binding)
	}
	for _, binding := range m.propositions {
		m.valueBinding(binding)
	}
	m.orphanedArtifacts()
	m.mountConflicts()
}
func (m *statefulModel) orphanedArtifacts() {
	for _, row := range m.resources {
		if row.owner.Section == generatedSection && len(row.consumers) == 0 && !m.consumed[row.owner.Name] {
			m.report(row.owner, generatedSection+"."+row.owner.Name+" is declared but no file consumer, environment binding, or content binding consumes it")
		}
	}
}
func (m *statefulModel) mountConflicts() {
	for _, node := range m.nodes {
		for _, target := range node.mounts {
			if previous := m.occupied[[2]string{node.name, target}]; previous != "" {
				m.report(Owner{nodesSection, node.name}, fmt.Sprintf("runtime mount target %s on node %s is already consumed by %s", quoted(target), quoted(node.name), previous))
			}
		}
	}
}
func (m *statefulModel) consumers(row resource) {
	label := row.owner.Section + "." + row.owner.Name
	for _, consumer := range row.consumers {
		name := strings.TrimPrefix(consumer.node, nodesSection+".")
		index, present := m.nodeIndex[name]
		if !present {
			m.report(row.owner, fmt.Sprintf("%s consumer node reference %s is missing", label, quoted(consumer.node)))
			continue
		}
		if m.nodes[index].os == "windows" {
			m.report(row.owner, fmt.Sprintf("%s uses a POSIX mount_destination for Windows consumer node %s", label, quoted(name)))
		}
		key := [2]string{name, consumer.destination}
		if previous := m.occupied[key]; previous != "" {
			m.report(row.owner, fmt.Sprintf("%s mount_destination %s on node %s is already consumed by %s", label, quoted(consumer.destination), quoted(name), previous))
		} else {
			m.occupied[key] = label
		}
	}
}
func (m *statefulModel) dependencies(row resource) {
	for _, ref := range row.dependencies {
		candidates := m.dependencyCandidates(ref)
		label := row.owner.Section + "." + row.owner.Name
		switch len(candidates) {
		case 0:
			m.report(row.owner, fmt.Sprintf("%s dependency reference %s is missing", label, quoted(ref)))
		case 2:
			m.report(row.owner, fmt.Sprintf("%s dependency reference %s is ambiguous; use one of: %s", label, quoted(ref), strings.Join(candidates, ", ")))
		}
	}
}
func (m *statefulModel) dependencyCandidates(ref string) []string {
	var result []string
	for _, section := range []string{generatedSection, volumesSection} {
		name := ref
		if strings.HasPrefix(ref, generatedSection+".") || strings.HasPrefix(ref, volumesSection+".") {
			var matched bool
			name, matched = strings.CutPrefix(ref, section+".")
			if !matched {
				continue
			}
		}
		present := m.generated[name] != nil
		if section == volumesSection {
			present = m.volumes[name]
		}
		if present {
			result = append(result, section+"."+name)
		}
	}
	return result
}
func (m *statefulModel) valueBinding(binding artifactBinding) {
	if binding.wrongBasis {
		m.report(binding.owner, binding.label+" requires an observed_state proposition basis")
	}
	name := strings.TrimPrefix(binding.source.Artifact, generatedSection+".")
	artifact := m.generated[name]
	if artifact == nil {
		m.report(binding.owner, fmt.Sprintf("%s references generated artifact %s which is missing", binding.label, quoted(binding.source.Artifact)))
		return
	}
	m.consumed[name] = true
	output, issue := consumableOutput(*artifact, binding.source.Output, binding.classification)
	if issue != "" {
		m.report(binding.owner, binding.label+" "+issue+" on "+generatedSection+"."+name)
		return
	}
	if binding.sensitiveFalse && output.sensitivity == "secret" {
		m.report(binding.owner, binding.label+" binds a secret generated output; content must be marked sensitive")
	}
}
func consumableOutput(artifact resource, name string, classification *string) (artifactOutput, string) {
	for _, output := range artifact.outputs {
		if output.name != name {
			continue
		}
		if output.disposition == "producer_private" {
			return artifactOutput{}, "cannot consume a producer_private generated artifact output"
		}
		if output.sensitivity == "secret" && classification != nil && *classification != "redacted" {
			return artifactOutput{}, "generated secret output requires redacted runtime environment classification"
		}
		return output, ""
	}
	return artifactOutput{}, "selects unknown generated artifact output " + quoted(name)
}
func textScalar(raw json.RawMessage) (string, error) {
	if len(raw) == 0 {
		return "", nil
	}
	var result string
	if json.Unmarshal(raw, &result) != nil {
		return "", projectionInvalid()
	}
	return result, nil
}

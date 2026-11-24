package sdlrules

import (
	"encoding/json"
	"fmt"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type serviceContentModel struct {
	input    binding.SdlAuthoringInputV1
	order    map[string][]string
	services map[string]string
	defined  map[string]map[string]bool
	findings []Finding
}
type serviceContent struct {
	Coordinate   json.RawMessage `json:"coordinate"`
	Target       string          `json:"target_service_ref"`
	Ordering     []string        `json:"ordering_content_refs"`
	Evidence     []string        `json:"evidence_requirement_refs"`
	Assertions   []string        `json:"readback_assertion_refs"`
	Boundaries   []string        `json:"observation_boundary_refs"`
	Relationship string          `json:"shared_service_relationship_ref"`
}

// ServiceMaterialization reports service-owned content reference violations
// in constructed normalized SDL. It preserves content and reference order.
func ServiceMaterialization(data []byte, order map[string][]string) ([]Finding, error) {
	m := serviceContentModel{order: order, services: map[string]string{}}
	if json.Unmarshal(data, &m.input) != nil {
		return nil, projectionInvalid()
	}
	m.defined = map[string]map[string]bool{
		contentSection:           declaredNames(fieldValue(m.input.Content)),
		"evidence_requirements":  declaredNames(fieldValue(m.input.EvidenceRequirements)),
		"observation_boundaries": declaredNames(fieldValue(m.input.ObservationBoundaries)),
	}
	if err := m.serviceFacts(); err != nil {
		return nil, err
	}
	values := fieldValue(m.input.Content)
	for _, name := range orderedKeys(values, order, contentSection) {
		raw := fieldValue(values[name].ServiceMaterialization)
		if len(raw) == 0 || string(raw) == jsonNull {
			continue
		}
		var row serviceContent
		if json.Unmarshal(raw, &row) != nil {
			return nil, projectionInvalid()
		}
		// The constructed union's profile variant always carries a coordinate,
		// including when schema_version was omitted and took its model default.
		if len(row.Coordinate) > 0 {
			continue
		}
		if err := m.content(name, fieldValue(values[name].Target), row); err != nil {
			return nil, err
		}
	}
	return m.findings, nil
}
func declaredNames[T any](values map[string]T) map[string]bool {
	result := make(map[string]bool, len(values))
	for name := range values {
		result[name] = true
	}
	return result
}
func (m *serviceContentModel) serviceFacts() error {
	values := fieldValue(m.input.Nodes)
	for _, name := range orderedKeys(values, m.order, nodesSection) {
		for _, service := range fieldValue(values[name].Services) {
			id, err := textScalar(fieldValue(service.Name))
			if err != nil {
				return err
			}
			address := nodesSection + "." + name + ".services." + id
			if _, present := m.services[address]; id != "" && !present {
				m.services[address] = name
			}
		}
	}
	return nil
}
func (m *serviceContentModel) report(name, message string) {
	m.findings = append(m.findings, Finding{Owner{contentSection, name}, "Content '" + name + "' service_materialization " + message})
}
func (m *serviceContentModel) references(name, field string, refs []string, section string) {
	for _, ref := range refs {
		if !unresolved(ref) && !m.defined[section][ref] {
			m.report(name, fmt.Sprintf("%s '%s' not in %s section", field, ref, section))
		}
	}
}
func (m *serviceContentModel) content(name, target string, row serviceContent) error {
	if node, present := m.services[row.Target]; present {
		if node != target {
			m.report(name, fmt.Sprintf("target_service_ref must belong to content target node '%s'", target))
		}
	} else if !unresolved(row.Target) {
		m.report(name, fmt.Sprintf("target_service_ref '%s' must resolve to a named compute service", row.Target))
	}
	m.references(name, "ordering_content_ref", row.Ordering, contentSection)
	if slices.Contains(row.Ordering, name) {
		m.report(name, "cannot order content after itself")
	}
	m.references(name, "evidence_requirement_ref", row.Evidence, "evidence_requirements")
	for _, ref := range row.Assertions {
		m.readback(name, ref, row.Evidence)
	}
	m.references(name, "observation_boundary_ref", row.Boundaries, "observation_boundaries")
	boundaries := fieldValue(m.input.ObservationBoundaries)
	for _, ref := range row.Boundaries {
		if boundary, present := boundaries[ref]; present && !contentSubject(fieldValue(boundary.ObservableRefs), name) {
			m.report(name, fmt.Sprintf("observation boundary '%s' must expose the exact content subject", ref))
		}
	}
	return m.tenancy(name, row)
}
func (m *serviceContentModel) readback(name, ref string, evidence []string) {
	if unresolved(ref) {
		return
	}
	assertion, present := fieldValue(m.input.Assertions)[ref]
	if !present {
		m.report(name, fmt.Sprintf("readback_assertion_ref '%s' not in assertions section", ref))
		return
	}
	if string(fieldValue(assertion.Role)) != "postcondition" {
		m.report(name, fmt.Sprintf("readback assertion '%s' must be a postcondition", ref))
	}
	proposition, present := fieldValue(m.input.Propositions)[fieldValue(assertion.Proposition)]
	if !present {
		return
	}
	if string(fieldValue(proposition.Basis)) != "observed_state" {
		m.report(name, fmt.Sprintf("readback assertion '%s' must use an observed-state proposition", ref))
	}
	if !contentSubject(fieldValue(proposition.Subjects), name) {
		m.report(name, fmt.Sprintf("readback assertion '%s' must observe the exact content subject", ref))
	}
	if !referenceSubset(evidence, fieldValue(proposition.EvidenceRequirements)) {
		m.report(name, fmt.Sprintf("readback assertion '%s' must require the bound readback evidence", ref))
	}
}
func contentSubject(refs []string, name string) bool {
	return slices.Contains(refs, name) || slices.Contains(refs, "content."+name)
}
func referenceSubset(refs, allowed []string) bool {
	set := map[string]bool{}
	for _, ref := range allowed {
		set[ref] = true
	}
	for _, ref := range refs {
		if !set[ref] {
			return false
		}
	}
	return true
}
func (m *serviceContentModel) tenancy(name string, row serviceContent) error {
	ref := row.Relationship
	if ref == "" || unresolved(ref) {
		return nil
	}
	relationship, present := fieldValue(m.input.Relationships)[ref]
	if !present {
		m.report(name, fmt.Sprintf("shared_service_relationship_ref '%s' not in relationships section", ref))
		return nil
	}
	raw := fieldValue(relationship.SharedService)
	if string(fieldValue(relationship.Type)) != "uses_shared_service" || len(raw) == 0 || string(raw) == jsonNull {
		m.report(name, fmt.Sprintf("relationship '%s' must be a typed uses_shared_service relationship", ref))
		return nil
	}
	if fieldValue(relationship.Target) != row.Target {
		m.report(name, fmt.Sprintf("relationship '%s' must target the same named service", ref))
	}
	var detail struct {
		Owner string `json:"mutable_state_owner"`
		Reset string `json:"reset_generation_owner"`
	}
	if json.Unmarshal(raw, &detail) != nil {
		return projectionInvalid()
	}
	if detail.Owner == "none" || detail.Reset == "none" {
		m.report(name, fmt.Sprintf("relationship '%s' must assign mutable-state and reset ownership", ref))
	}
	return nil
}

// Only whole-field variable references defer membership checks. Embedded
// strings retain their declared field meaning.
func unresolved(value string) bool {
	if !strings.HasPrefix(value, "${") || !strings.HasSuffix(value, "}") {
		return false
	}
	parts := strings.Split(value[2:len(value)-1], ".")
	for i, part := range parts {
		if part == "__private" && i < len(parts)-1 {
			continue
		}
		if len(part) == 0 || len(part) > 64 || !identifierInitial(part[0]) || strings.Trim(part, "abcdefghijklmnopqrstuvwxyz0123456789_-") != "" {
			return false
		}
	}
	return true
}
func identifierInitial(value byte) bool {
	return value >= 'a' && value <= 'z' || value >= '0' && value <= '9'
}

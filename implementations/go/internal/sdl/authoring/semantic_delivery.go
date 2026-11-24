package authoring

import (
	"encoding/json"
	"fmt"
	"slices"
)

type semanticDelivery struct {
	id          string
	Participant string `json:"participant_ref"`
	Inject      string `json:"inject_ref"`
	Occurrence  struct {
		Event  string `json:"event_ref"`
		Script string `json:"script_ref"`
		Story  string `json:"story_ref"`
	} `json:"occurrence"`
	Source   string `json:"source_item_ref"`
	Result   string `json:"result_item_ref"`
	Boundary string `json:"observation_boundary_ref"`
	Kind     string `json:"delivery_kind"`
	Policy   struct {
		Revision   string `json:"policy_revision"`
		Visibility string `json:"visibility_basis_ref"`
		Disclosure string `json:"disclosure_basis_ref"`
	} `json:"delivery_policy"`
	Constraints  []string                 `json:"temporal_constraint_refs"`
	Requirements []string                 `json:"evidence_requirement_refs"`
	Transition   *string                  `json:"control_transition_ref"`
	Controller   string                   `json:"controller_ref"`
	Authority    []string                 `json:"control_authority_scope_refs"`
	Effective    json.Number              `json:"control_effective_order"`
	From         json.Number              `json:"control_valid_from_order"`
	Until        json.Number              `json:"control_valid_until_order"`
	Evidence     []string                 `json:"control_evidence_refs"`
	Control      *semanticDeliveryControl `json:"control"`
}
type semanticDeliveryControl struct {
	Semantics  string   `json:"semantics"`
	Revision   string   `json:"policy_revision"`
	Transition string   `json:"permitted_transition_ref"`
	Controller string   `json:"controller_ref"`
	Authority  []string `json:"authority_scope_refs"`
	Evidence   []string `json:"evidence_refs"`
}
type semanticDeliveryCheck struct {
	model     *semanticModel
	collector *semanticCollector
	row       semanticBehavior
	binding   semanticDelivery
}

func (m *semanticModel) deliveryFacts(name string) ([]semanticDelivery, error) {
	values := fieldValue(fieldValue(m.transport.BehaviorSpecifications)[name].ParticipantInjectDeliveries)
	var result []semanticDelivery
	for _, id := range m.keys(behaviorSection, name, participantInjectDeliveriesField) {
		row := semanticDelivery{id: id}
		if err := json.Unmarshal(values[id], &row); err != nil {
			return nil, invalid()
		}
		result = append(result, row)
	}
	return result, nil
}
func (m *semanticModel) checkDeliveries(c *semanticCollector) {
	for _, row := range m.behaviors {
		for _, binding := range row.deliveries {
			check := semanticDeliveryCheck{m, c, row, binding}
			check.participant()
			check.occurrence()
			check.items()
			check.registries()
			check.control()
		}
	}
}
func (d semanticDeliveryCheck) label() string {
	return fmt.Sprintf("Behavior specification '%s' participant inject delivery '%s'", d.row.name, d.binding.id)
}
func (d semanticDeliveryCheck) reportf(format string, args ...any) {
	d.collector.report(semanticOwner{behaviorSection, d.row.name}, d.label()+" "+fmt.Sprintf(format, args...))
}
func (d semanticDeliveryCheck) reference(field, ref string, purpose semanticPurpose) {
	d.model.namedReference(d.collector, semanticOwner{behaviorSection, d.row.name}, d.label(), field, ref, purpose)
}
func (d semanticDeliveryCheck) participant() {
	b := d.binding
	if variable(b.Participant) {
		return
	}
	agent, known := fieldValue(d.model.transport.Agents)[b.Participant]
	if !known {
		d.reportf("participant_ref '%s' does not reference a declared agent", b.Participant)
		return
	}
	if !slices.Contains(d.row.participants, b.Participant) {
		d.reportf("participant_ref '%s' is outside the owning behavior specification", b.Participant)
	}
	if variable(b.Boundary) {
		return
	}
	if !slices.Contains(d.row.boundaries, b.Boundary) {
		d.reportf("observation_boundary_ref '%s' is outside the owning behavior specification", b.Boundary)
	}
	if !slices.Contains(fieldValue(agent.ObservationBoundaries), b.Boundary) {
		d.reportf("observation_boundary_ref '%s' is outside participant '%s'", b.Boundary, b.Participant)
	}
}
func (d semanticDeliveryCheck) occurrence() {
	b := d.binding
	missing := false
	for _, ref := range []struct{ field, value, section string }{{"inject_ref", b.Inject, injectsSection}, {"event_ref", b.Occurrence.Event, eventsSection}, {"script_ref", b.Occurrence.Script, scriptsField}, {"story_ref", b.Occurrence.Story, storiesField}} {
		if variable(ref.value) {
			missing = true
			continue
		}
		if !d.model.definitions[ref.section][ref.value] {
			d.reportf("%s '%s' does not reference a declared %s", ref.field, ref.value, ref.field[:len(ref.field)-4])
			missing = true
		}
	}
	if missing {
		return
	}
	if !slices.Contains(fieldValue(fieldValue(d.model.transport.Events)[b.Occurrence.Event].Injects), b.Inject) {
		d.reportf("event_ref '%s' does not contain inject '%s'", b.Occurrence.Event, b.Inject)
	}
	if _, known := fieldValue(fieldValue(d.model.transport.Scripts)[b.Occurrence.Script].Events)[b.Occurrence.Event]; !known {
		d.reportf("script_ref '%s' does not contain event '%s'", b.Occurrence.Script, b.Occurrence.Event)
	}
	if !slices.Contains(fieldValue(fieldValue(d.model.transport.Stories)[b.Occurrence.Story].Scripts), b.Occurrence.Script) {
		d.reportf("story_ref '%s' does not contain script '%s'", b.Occurrence.Story, b.Occurrence.Script)
	}
}
func (d semanticDeliveryCheck) items() {
	d.reference("source_item_ref", d.binding.Source, referenceTarget)
	d.reference("result_item_ref", d.binding.Result, referenceTarget)
	d.observation()
}
func (d semanticDeliveryCheck) observation() {
	b := d.binding
	if variable(b.Boundary) {
		return
	}
	_, known := fieldValue(d.model.transport.ObservationBoundaries)[b.Boundary]
	if !known {
		d.reportf("observation_boundary_ref '%s' does not reference a declared boundary", b.Boundary)
		return
	}
	if variable(b.Result) {
		return
	}
	matching, policy := false, false
	for _, rule := range d.model.boundaryRules[b.Boundary] {
		disposition := rule.disposition
		if disposition != "observable" && disposition != "disclosed" {
			continue
		}
		if d.model.referencesOverlap(rule.information, b.Result) {
			matching = true
			policy = policy || rule.visibility == b.Policy.Visibility && rule.disclosure == b.Policy.Disclosure
		}
	}
	if !matching {
		d.reportf("result_item_ref '%s' must be disclosed or observable through observation_boundary_ref '%s'", b.Result, b.Boundary)
		return
	}
	if !policy {
		d.reportf("delivery policy visibility/disclosure basis does not agree with observation_boundary_ref '%s'", b.Boundary)
	}
}
func (m *semanticModel) referencesOverlap(left, right string) bool {
	rightAliases := m.index.aliases[right]
	for address := range m.index.aliases[left] {
		if _, known := rightAliases[address]; known {
			return true
		}
	}
	return false
}
func (d semanticDeliveryCheck) registries() {
	for _, ref := range d.binding.Constraints {
		row, known := fieldValue(d.model.transport.TemporalConstraints)[ref]
		d.registryReference("temporal_constraint_ref", ref, fieldValue(row.SubjectRefs), known)
	}
	for _, ref := range d.binding.Requirements {
		row, known := fieldValue(d.model.transport.EvidenceRequirements)[ref]
		d.registryReference("evidence_requirement_ref", ref, fieldValue(row.SourceRefs), known)
	}
}
func (d semanticDeliveryCheck) registryReference(field, ref string, subjects []string, known bool) {
	if variable(ref) {
		return
	}
	if !known {
		d.reportf("%s '%s' does not reference a declared resource", field, ref)
		return
	}
	address := behaviorSection + "." + d.row.name + "." + participantInjectDeliveriesField + "." + d.binding.id
	for _, subject := range subjects {
		if d.model.referencesOverlap(address, subject) {
			return
		}
	}
	d.reportf("%s '%s' does not bind this delivery declaration", field, ref)
}

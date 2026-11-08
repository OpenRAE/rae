package authoring

import (
	"fmt"
	"slices"
)

func (r *semanticParticipantRelationCheck) uniqueNamed(field string, refs []string, operating bool) {
	seen := map[string]bool{}
	for _, ref := range refs {
		if variable(ref) {
			continue
		}
		var resolved map[string]bool
		if operating {
			resolved = r.model.operatingReferences([]string{ref})
		} else {
			resolved = r.model.purposeReferences([]string{ref}, referenceAuthorityAnchor)
		}
		if len(resolved) != 1 {
			continue
		}
		for address := range resolved {
			if seen[address] {
				r.report(field + " repeats a canonical reference")
			}
			seen[address] = true
		}
	}
}
func (r *semanticParticipantRelationCheck) authority() {
	r.uniqueNamed("authority_basis_refs", r.detail.Authority, false)
	anchors := fieldValue(fieldValue(r.model.transport.Agents)[r.source].AuthorityAnchors)
	allowed := r.model.purposeReferences(anchors, referenceAuthorityAnchor)
	for _, ref := range r.detail.Authority {
		if variable(ref) {
			continue
		}
		r.model.namedReference(r.collector, semanticOwner{relationshipsField, r.row.name}, r.label(), "authority_basis_refs", ref, referenceAuthorityAnchor)
		if r.source != "" && !hasVariableReference(anchors) && !refsWithin(r.model.purposeReferences([]string{ref}, referenceAuthorityAnchor), allowed) {
			r.report("authority_basis_refs must not widen source authority")
		}
	}
}
func (r *semanticParticipantRelationCheck) scope() {
	r.uniqueNamed(scopeRefsField, r.detail.Scope, true)
	for _, ref := range r.detail.Scope {
		if variable(ref) {
			continue
		}
		r.model.checkOperatingScope(r.collector, semanticOwner{relationshipsField, r.row.name}, r.label(), ref)
		for _, name := range []string{r.source, r.target} {
			if name == "" {
				continue
			}
			refs := fieldValue(fieldValue(r.model.transport.Agents)[name].OperatingScope)
			if !hasVariableReference(refs) && !refsWithin(r.model.operatingReferences([]string{ref}), r.model.operatingReferences(refs)) {
				r.report(fmt.Sprintf("scope_refs must stay within participant '%s' operating_scope", name))
			}
		}
	}
}
func (r *semanticParticipantRelationCheck) visibility() {
	if r.source == "" {
		return
	}
	available := fieldValue(fieldValue(r.model.transport.Agents)[r.source].ObservationBoundaries)
	if hasVariableReference(available) {
		return
	}
	for _, ref := range r.detail.Boundaries {
		if variable(ref) {
			continue
		}
		name, known := r.model.sectionReference(ref, boundariesSection)
		if known && !slices.Contains(available, name) {
			r.report("observation_boundary_refs must be available to the source participant")
		}
	}
}
func (r *semanticParticipantRelationCheck) control() {
	ref := r.detail.Control
	if ref == nil || variable(*ref) {
		return
	}
	name, known := r.model.sectionReference(*ref, behaviorSection)
	if !known {
		r.report("control_specification_ref must reference declared behavior_specifications")
		return
	}
	policy := r.model.behaviorNamed(name).mixed
	if policy == nil {
		r.report("control_specification_ref requires an existing mixed_control declaration")
		return
	}
	r.controlScope(policy)
}
func (r *semanticParticipantRelationCheck) controlScope(policy *semanticMixed) {
	if r.source == "" || r.target == "" {
		return
	}
	controlled, controller := r.target, r.source
	if r.detail.Kind == "delegation" {
		controlled, controller = r.source, r.target
	}
	var refs []string
	matched := false
	if policy.Participant == controlled {
		for _, state := range policy.States {
			if state.Controller == controller && state.Status == "active" {
				matched = true
				refs = append(refs, state.Scope...)
			}
		}
	}
	if !matched {
		r.report("control_specification_ref contradicts participant/controller direction")
		return
	}
	allowed := r.model.operatingReferences(refs)
	for _, ref := range r.detail.Scope {
		if !variable(ref) && !refsWithin(r.model.operatingReferences([]string{ref}), allowed) {
			r.report("control_specification_ref must cover the selected relationship scope")
		}
	}
}
func (m *semanticModel) behaviorNamed(name string) semanticBehavior {
	if index, known := m.behaviorIndex[name]; known {
		return m.behaviors[index]
	}
	return semanticBehavior{}
}

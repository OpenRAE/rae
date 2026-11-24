package authoring

import (
	"fmt"
	"maps"
	"slices"
)

type semanticParticipantRelation struct {
	Kind          string   `json:"kind"`
	SourceActions []string `json:"source_action_refs"`
	TargetActions []string `json:"target_action_refs"`
	Objectives    []string `json:"objective_refs"`
	Behaviors     []string `json:"behavior_specification_refs"`
	Authority     []string `json:"authority_basis_refs"`
	Scope         []string `json:"scope_refs"`
	Boundaries    []string `json:"observation_boundary_refs"`
	Control       *string  `json:"control_specification_ref"`
}
type semanticParticipantSelections struct{ sourceActions, targetActions, objectives, behaviors map[string]bool }
type semanticParticipantRelationCheck struct {
	model          *semanticModel
	collector      *semanticCollector
	row            semanticRelationship
	detail         semanticParticipantRelation
	source, target string
	selected       semanticParticipantSelections
}

func (r *semanticParticipantRelationCheck) label() string { return "Relationship '" + r.row.name + "'" }
func (r *semanticParticipantRelationCheck) report(message string) {
	r.collector.report(semanticOwner{relationshipsField, r.row.name}, r.label()+" "+message)
}
func (m *semanticModel) checkParticipantRelationship(c *semanticCollector, row semanticRelationship) {
	check := semanticParticipantRelationCheck{model: m, collector: c, row: row, detail: *row.participant}
	check.source = check.endpoint(sourceField, row.source)
	check.target = check.endpoint(targetField, row.target)
	if check.source != "" && check.source == check.target {
		check.report("requires distinct participants")
	}
	check.selected = semanticParticipantSelections{
		sourceActions: check.sectionRefs("source_action_refs", actionsSection, check.detail.SourceActions),
		targetActions: check.sectionRefs("target_action_refs", actionsSection, check.detail.TargetActions),
		objectives:    check.sectionRefs("objective_refs", objectivesSection, check.detail.Objectives),
		behaviors:     check.sectionRefs("behavior_specification_refs", behaviorSection, check.detail.Behaviors),
	}
	check.sectionRefs(boundaryRefsField, boundariesSection, check.detail.Boundaries)
	check.actions()
	check.behaviors()
	check.authority()
	check.scope()
	check.visibility()
	check.control()
}
func (r *semanticParticipantRelationCheck) endpoint(field, ref string) string {
	if variable(ref) {
		return ""
	}
	result := r.model.referenceResult(ref, []semanticPurpose{referenceParticipant})
	if len(result.domain) != 1 || len(result.eligible) != 1 {
		r.report(field + " participant endpoint must resolve unambiguously to a declared agent")
		return ""
	}
	return r.model.index.aliases[ref][result.domain[0]].tokens[1]
}
func (r *semanticParticipantRelationCheck) sectionRefs(field, section string, refs []string) map[string]bool {
	resolved := map[string]bool{}
	for _, ref := range refs {
		if variable(ref) {
			continue
		}
		name, known := r.model.sectionReference(ref, section)
		switch {
		case !known:
			r.report(field + " must reference declared " + section)
		case resolved[name]:
			r.report(field + " repeats a canonical reference")
		default:
			resolved[name] = true
		}
	}
	return resolved
}
func hasVariableReference(refs []string) bool {
	return slices.ContainsFunc(refs, func(ref string) bool { return variable(ref) })
}
func referenceSet(refs []string) map[string]bool {
	result := map[string]bool{}
	for _, ref := range refs {
		result[ref] = true
	}
	return result
}
func (r *semanticParticipantRelationCheck) actions() {
	for _, side := range []struct {
		field, participant string
		refs               map[string]bool
	}{{"source_action_refs", r.source, r.selected.sourceActions}, {"target_action_refs", r.target, r.selected.targetActions}} {
		if side.participant == "" {
			continue
		}
		available := fieldValue(fieldValue(r.model.transport.Agents)[side.participant].Actions)
		if !hasVariableReference(available) && !refsWithin(side.refs, referenceSet(available)) {
			r.report(fmt.Sprintf("%s must be available to participant '%s'", side.field, side.participant))
		}
	}
	if r.detail.Kind != "coordination" {
		return
	}
	for _, name := range slices.Sorted(maps.Keys(r.selected.sourceActions)) {
		related := r.coordinationActions(name)
		if !hasVariableReference(related) && !refsWithin(r.selected.targetActions, referenceSet(related)) {
			r.report("coordination refinements must agree with an action interaction")
		}
	}
}
func (r *semanticParticipantRelationCheck) coordinationActions(name string) []string {
	var related []string
	action := fieldValue(r.model.transport.ActionContracts)[name]
	for _, interaction := range fieldValue(action.Interactions) {
		if fieldValue(interaction.InteractionClass) != "coordination" {
			continue
		}
		peer, known := r.model.sectionReference(fieldValue(interaction.Target), agentsSection)
		if r.target != "" && known && peer != r.target {
			continue
		}
		related = append(related, fieldValue(interaction.RelatedActions)...)
	}
	return related
}
func (r *semanticParticipantRelationCheck) behaviors() {
	if r.source == "" || r.target == "" {
		return
	}
	roles := []string{r.model.roles[r.source], r.model.roles[r.target]}
	for _, name := range slices.Sorted(maps.Keys(r.selected.behaviors)) {
		selected := r.behaviorSelected(name, roles)
		if !selected {
			r.report("behavior_specification_refs must include a relationship endpoint")
		}
	}
	for _, objective := range r.model.objectives {
		if r.selected.objectives[objective.name] && !variable(objective.Participant) && objective.Participant != r.source && objective.Participant != r.target {
			r.report("objective_refs must be assigned to a relationship endpoint")
		}
	}
}

func (r *semanticParticipantRelationCheck) behaviorSelected(name string, roles []string) bool {
	row := fieldValue(r.model.transport.BehaviorSpecifications)[name]
	participants, selectedRoles := fieldValue(row.ParticipantRefs), fieldValue(row.ParticipantRoleRefs)
	if hasVariableReference(participants) || hasVariableReference(selectedRoles) {
		return true
	}
	selected := slices.Contains(participants, r.source) || slices.Contains(participants, r.target) || slices.Contains(selectedRoles, roles[0]) || slices.Contains(selectedRoles, roles[1])
	if len(selectedRoles) > 0 && hasVariableReference(roles) {
		selected = true
	}
	return selected
}

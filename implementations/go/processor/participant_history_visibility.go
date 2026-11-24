package processor

import (
	"fmt"
	"maps"
	"math/big"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/internal/base/pyrepr"
)

type participantObservationAnchor struct{ instance, boundary string }
type participantHistoryAnchors struct {
	attempts, transitions map[string]int
	observations          map[participantObservationAnchor]int
}
type participantHistoryBoundary struct {
	address  string
	boundary participantBoundary
}

func (analysis *participantHistoryAnalysis) boundaries() []participantHistoryBoundary {
	result := []participantHistoryBoundary{}
	for _, resource := range analysis.model.view.ParticipantResources {
		if resource.Kind == termObservationBoundary {
			result = append(result, participantHistoryBoundary{resource.Address, analysis.model.participants.boundaries[resource.Address]})
		}
	}
	return result
}
func (analysis *participantHistoryAnalysis) anchors() participantHistoryAnchors {
	result := participantHistoryAnchors{attempts: map[string]int{}, transitions: map[string]int{}, observations: map[participantObservationAnchor]int{}}
	for index, event := range analysis.events {
		switch event.Type {
		case termActionAttempted:
			if _, present := result.attempts[event.Instance]; !present {
				result.attempts[event.Instance] = index
			}
		case termStateTransitionRecorded:
			if _, present := result.transitions[event.Instance]; !present {
				result.transitions[event.Instance] = index
			}
		case termObservationEmitted:
			key := participantObservationAnchor{event.Instance, participantText(event.Boundary)}
			if _, present := result.observations[key]; !present {
				result.observations[key] = index
			}
		}
	}
	return result
}
func (anchors participantHistoryAnchors) index(transition compiledViewTransition, boundary string) (int, bool) {
	switch transition.eventType {
	case termActionAttempted:
		index, present := anchors.attempts[transition.actionInstance]
		return index, present
	case termStateTransitionRecorded:
		index, present := anchors.transitions[transition.actionInstance]
		return index, present
	case termObservationEmitted:
		index, present := anchors.observations[participantObservationAnchor{transition.actionInstance, boundary}]
		return index, present
	default:
		return 0, false
	}
}
func (analysis *participantHistoryAnalysis) anchorViolations() {
	anchors := analysis.anchors()
	closed := analysis.episodes.closes(analysis.events)
	for _, record := range analysis.boundaries() {
		for _, transition := range record.boundary.transitions {
			if !analysis.violations.spend(1) {
				return
			}
			pointer := record.address + ".view_transitions." + transition.id
			if message := participantAnchorViolation(transition, record.address, anchors, closed); message != "" {
				analysis.add(pointer, message)
			}
		}
	}
}
func participantAnchorViolation(transition compiledViewTransition, address string, anchors participantHistoryAnchors, closed bool) string {
	if transition.eventType == "episode_close" {
		if !closed {
			return "visibility transition anchor does not resolve to a terminal participant episode history event"
		}
		return ""
	}
	if transition.actionInstance == "" {
		return "visibility transition anchors require action_instance_id"
	}
	if !slices.Contains([]string{termActionAttempted, termStateTransitionRecorded, termObservationEmitted}, transition.eventType) {
		return "visibility transition anchor has unknown history_event_type " + pyrepr.Quote(transition.eventType)
	}
	if _, present := anchors.index(transition, address); present {
		return ""
	}
	article := "a"
	if transition.eventType == termObservationEmitted {
		article = "an"
	}
	return "visibility transition anchor does not resolve to " + article + " " + transition.eventType + " event"
}
func (analysis *participantHistoryAnalysis) effectiveRelation(boundary participantBoundary, address string, observationIndex int, anchors participantHistoryAnchors) (map[string]string, string) {
	relation := analysis.initialRelation(boundary)
	effective := big.NewInt(-1)
	for _, transition := range boundary.transitions {
		if !analysis.violations.work.spend(1) {
			analysis.violations.err = participantContractInput()
			return nil, ""
		}
		index, present := anchors.index(transition, address)
		if !present || index > observationIndex || transition.informationRef != "" && transition.from != "" && relation[transition.informationRef] != transition.from {
			continue
		}
		if transition.informationRef != "" && transition.to != "" {
			relation[transition.informationRef] = transition.to
		}
		if transition.integerOrder.Cmp(effective) > 0 {
			effective = transition.integerOrder
		}
	}
	return relation, effective.String()
}
func (analysis *participantHistoryAnalysis) initialRelation(boundary participantBoundary) map[string]string {
	relation := map[string]string{}
	for _, snapshot := range boundary.ViewRelationTimeline {
		order, ok := new(big.Int).SetString(string(snapshot.EffectiveOrder), 10)
		if ok && order.Sign() < 0 {
			if !analysis.violations.spend(len(snapshot.ViewRelation)) {
				return nil
			}
			relation = maps.Clone(snapshot.ViewRelation)
		}
	}
	return relation
}
func participantResolvedRef(boundary participantBoundary, ref string) (string, bool) {
	matches, present := boundary.ReferenceAliases[ref]
	if !present {
		return ref, true
	}
	if len(matches) != 1 {
		return "", false
	}
	return matches[0], true
}
func participantDisposition(boundary participantBoundary, relation map[string]string, ref string) (string, bool) {
	resolved, valid := participantResolvedRef(boundary, ref)
	if !valid {
		return "ambiguous", true
	}
	disposition, present := relation[resolved]
	if !present && boundary.hiddenSet[resolved] {
		return "hidden", true
	}
	return disposition, present
}
func participantVisible(disposition string) bool {
	return slices.Contains([]string{"observable", "discovered", "inferred", termDisclosed, "deceptive"}, disposition)
}
func participantEvidenceAuthorized(boundary participantBoundary, relation map[string]string, ref string) bool {
	resolved, valid := participantResolvedRef(boundary, ref)
	disposition, _ := participantDisposition(boundary, relation, ref)
	return valid && boundary.evidenceSet[resolved] || disposition == "evidence_only"
}
func participantDispositionSuffix(disposition string, present bool) string {
	if !present {
		return ""
	}
	return ": disposition " + pyrepr.Quote(disposition)
}
func (analysis *participantHistoryAnalysis) visibilityViolations() {
	anchors := analysis.anchors()
	analysis.detailVisibilityViolations(anchors)

	for index, event := range analysis.events {
		if event.Type != termObservationEmitted || event.Result == nil && len(event.Attributions)+len(event.Outcomes) == 0 {
			continue
		}
		boundary, present := analysis.model.participants.boundaries[participantText(event.Boundary)]
		if !present {
			continue
		}
		relation, order := analysis.effectiveRelation(boundary, participantText(event.Boundary), index, anchors)
		pointer := participantEventLocator(index)
		analysis.resultVisibility(pointer, event, boundary, relation, order)
		analysis.attributionVisibility(pointer, event, boundary, relation, order)
		analysis.outcomeVisibility(pointer, event, boundary, relation, order)
	}
}
func (analysis *participantHistoryAnalysis) detailVisibilityViolations(anchors participantHistoryAnchors) {
	for index, event := range analysis.events {
		if event.Type != termObservationEmitted {
			continue
		}
		boundary, present := analysis.model.participants.boundaries[participantText(event.Boundary)]
		if !present {
			continue
		}
		pointer := participantEventLocator(index)
		for _, message := range event.details.errors {
			analysis.add(pointer, message)
		}
		if len(event.details.errors) > 0 {
			continue
		}
		if len(event.details.visible)+len(event.details.disclosed)+len(event.details.evidence) == 0 {
			continue
		}
		relation, order := analysis.effectiveRelation(boundary, participantText(event.Boundary), index, anchors)
		analysis.detailVisibility(pointer, event.details, boundary, relation, order)
	}
}
func (analysis *participantHistoryAnalysis) detailVisibility(pointer string, details participantHistoryDetails, boundary participantBoundary, relation map[string]string, order string) {
	for _, field := range []struct {
		name, label string
		refs        []string
	}{{termVisibleRefs, "participant-visible", details.visible}, {termDisclosedRefs, termDisclosed, details.disclosed}} {
		for _, ref := range field.refs {
			disposition, present := participantDisposition(boundary, relation, ref)
			if field.name == termVisibleRefs && participantVisible(disposition) || field.name == termDisclosedRefs && disposition == termDisclosed {
				continue
			}
			repr := termPythonNone
			if present {
				repr = pyrepr.Quote(disposition)
			}
			analysis.add(pointer, fmt.Sprintf("observation %s may only contain %s refs at effective_order %s: %s has disposition %s", field.name, field.label, order, pyrepr.Quote(ref), repr))
		}
	}
	for _, ref := range details.evidence {
		if !participantEvidenceAuthorized(boundary, relation, ref) {
			analysis.add(pointer, fmt.Sprintf("observation evidence_refs may only contain boundary evidence refs at effective_order %s: %s", order, pyrepr.Quote(ref)))
		}
	}
}

type participantVisibilityCut struct {
	boundary participantBoundary
	relation map[string]string
	order    string
}

func (analysis *participantHistoryAnalysis) resultRefsVisibility(pointer, owner, field string, refs []string, evidence bool, cut participantVisibilityCut) {
	if owner != "" {
		owner = " " + owner
	}
	for _, ref := range refs {
		disposition, present := participantDisposition(cut.boundary, cut.relation, ref)
		if evidence {
			if !participantEvidenceAuthorized(cut.boundary, cut.relation, ref) {
				analysis.add(pointer, fmt.Sprintf("action_result%s %s %s is not authorized evidence at effective_order %s%s", owner, field, pyrepr.Quote(ref), cut.order, participantDispositionSuffix(disposition, present)))
			}
		} else if present && !participantVisible(disposition) {
			analysis.add(pointer, fmt.Sprintf("action_result%s %s %s is not participant-visible at effective_order %s: disposition %s", owner, field, pyrepr.Quote(ref), cut.order, pyrepr.Quote(disposition)))
		}
	}
}
func (analysis *participantHistoryAnalysis) resultVisibility(pointer string, event participantHistoryEvent, boundary participantBoundary, relation map[string]string, order string) {
	if event.Result == nil {
		return
	}
	cut := participantVisibilityCut{boundary: boundary, relation: relation, order: order}
	for _, record := range event.Result.Preconditions {
		owner := "precondition " + pyrepr.Quote(record.ID)
		analysis.resultRefsVisibility(pointer, owner, "support_ref", record.SupportRefs, false, cut)
		analysis.resultRefsVisibility(pointer, owner, "evidence_ref", record.EvidenceRefs, true, cut)
	}
	for _, record := range event.Result.Effects {
		owner := "effect " + pyrepr.Quote(record.ID)
		analysis.resultRefsVisibility(pointer, owner, "target_ref", record.TargetRefs, false, cut)
		analysis.resultRefsVisibility(pointer, owner, "evidence_ref", record.EvidenceRefs, true, cut)
	}
	analysis.resultRefsVisibility(pointer, "", "evidence_ref", event.Result.EvidenceRefs, true, cut)
}
func (analysis *participantHistoryAnalysis) attributionVisibility(pointer string, event participantHistoryEvent, boundary participantBoundary, relation map[string]string, order string) {
	for _, edge := range event.Attributions {
		analysis.attributionEvidence(pointer, edge.ID, edge.Evidence, boundary, relation, order)
		for _, candidate := range []participantAttributionCandidate{edge.Cause, edge.Effect} {
			if candidate.Kind == "action" {
				continue
			}
			if candidate.Kind == "evidence" {
				analysis.attributionEvidence(pointer, edge.ID, []string{candidate.Ref}, boundary, relation, order)
				continue
			}
			disposition, present := participantDisposition(boundary, relation, candidate.Ref)
			if present && !participantVisible(disposition) {
				analysis.add(pointer, fmt.Sprintf("attribution edge %s %s candidate %s is not participant-visible at effective_order %s: disposition %s", pyrepr.Quote(edge.ID), candidate.Kind, pyrepr.Quote(candidate.Ref), order, pyrepr.Quote(disposition)))
			}
		}
	}
}
func (analysis *participantHistoryAnalysis) attributionEvidence(pointer, id string, refs []string, boundary participantBoundary, relation map[string]string, order string) {
	for _, ref := range refs {
		if !participantEvidenceAuthorized(boundary, relation, ref) {
			disposition, present := participantDisposition(boundary, relation, ref)
			analysis.add(pointer, fmt.Sprintf("attribution edge %s evidence_ref %s is not authorized evidence at effective_order %s%s", pyrepr.Quote(id), pyrepr.Quote(ref), order, participantDispositionSuffix(disposition, present)))
		}
	}
}
func (analysis *participantHistoryAnalysis) outcomeEvidence(pointer, id string, refs []string, provenance bool, boundary participantBoundary, relation map[string]string, order string) {
	for _, ref := range refs {
		if participantEvidenceAuthorized(boundary, relation, ref) {
			continue
		}
		disposition, present := participantDisposition(boundary, relation, ref)
		if provenance {
			if !slices.Contains([]string{"hidden", "concealed", "deceptive", "ambiguous"}, disposition) {
				continue
			}
			analysis.add(pointer, fmt.Sprintf("outcome interpretation %s provenance_ref %s exposes a hidden participant-boundary ref at effective_order %s%s", pyrepr.Quote(id), pyrepr.Quote(ref), order, participantDispositionSuffix(disposition, present)))
		} else {
			analysis.add(pointer, fmt.Sprintf("outcome interpretation %s evidence_ref %s is not authorized evidence at effective_order %s%s", pyrepr.Quote(id), pyrepr.Quote(ref), order, participantDispositionSuffix(disposition, present)))
		}
	}
}
func (analysis *participantHistoryAnalysis) outcomeVisibility(pointer string, event participantHistoryEvent, boundary participantBoundary, relation map[string]string, order string) {
	for _, record := range event.Outcomes {
		analysis.outcomeEvidence(pointer, record.ID, record.EvidenceRefs, false, boundary, relation, order)
		for _, source := range record.Sources {
			analysis.outcomeEvidence(pointer, record.ID, source.EvidenceRefs, false, boundary, relation, order)
			analysis.outcomeEvidence(pointer, record.ID, source.ProvenanceRefs, true, boundary, relation, order)
		}
		for _, target := range record.Targets {
			analysis.outcomeEvidence(pointer, record.ID, target.EvidenceRefs, false, boundary, relation, order)
		}
	}
}

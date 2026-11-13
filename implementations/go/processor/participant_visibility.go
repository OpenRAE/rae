package processor

import (
	"encoding/json"
	"maps"
	"math/big"
	"slices"
)

type participantBoundary struct {
	transitions            []compiledViewTransition
	evidenceSet, hiddenSet map[string]bool
	Name                   string              `json:"name"`
	Spec                   json.RawMessage     `json:"spec"`
	BoundaryName           string              `json:"boundary_name"`
	ProjectionBasis        string              `json:"projection_basis"`
	HiddenRefs             []string            `json:"hidden_refs"`
	ObservableRefs         []string            `json:"observable_refs"`
	EvidenceRefs           []string            `json:"evidence_refs"`
	DisclosedRefs          []string            `json:"disclosed_refs"`
	EvidenceOnlyRefs       []string            `json:"evidence_only_refs"`
	DiscoveredRefs         []string            `json:"discovered_refs"`
	InferredRefs           []string            `json:"inferred_refs"`
	ConcealedRefs          []string            `json:"concealed_refs"`
	DeceptiveRefs          []string            `json:"deceptive_refs"`
	ViewTransitions        []json.RawMessage   `json:"view_transitions"`
	ViewRelationTimeline   []viewSnapshot      `json:"view_relation_timeline"`
	RealizedViewDisclosure string              `json:"realized_view_disclosure"`
	ReferenceAliases       map[string][]string `json:"reference_aliases"`
}
type compiledViewTransition struct {
	raw                                                                          json.RawMessage
	informationRef, from, to, id, effectiveFrom, kind, eventType, actionInstance string
	order                                                                        json.Number
	integerOrder                                                                 *big.Int
}
type viewSnapshot struct {
	TransitionID     string            `json:"transition_id"`
	EffectiveFrom    string            `json:"effective_from"`
	EffectiveOrder   json.Number       `json:"effective_order"`
	ViewRelation     map[string]string `json:"view_relation"`
	VisibleRefs      []string          `json:"visible_refs"`
	HiddenRefs       []string          `json:"hidden_refs"`
	EvidenceOnlyRefs []string          `json:"evidence_only_refs"`
	DisclosedRefs    []string          `json:"disclosed_refs"`
	DiscoveredRefs   []string          `json:"discovered_refs"`
	InferredRefs     []string          `json:"inferred_refs"`
	ConcealedRefs    []string          `json:"concealed_refs"`
	DeceptiveRefs    []string          `json:"deceptive_refs"`
	TransitionKind   *string           `json:"transition_kind,omitempty"`
	InformationRef   *string           `json:"information_ref,omitempty"`
	HistoryEventType *string           `json:"history_event_type,omitempty"`
	ActionInstanceID *string           `json:"action_instance_id,omitempty"`
}

func (state *compilerState) visibilityIndex() map[string][]string {
	result := map[string][]string{}
	for alias, candidates := range state.input.aliases {
		addressable := false
		for _, candidate := range candidates {
			if state.runtimeDeclaration(candidate) != "" {
				addressable = true
				break
			}
		}
		if !addressable {
			continue
		}
		addresses := []string{}
		for _, candidate := range candidates {
			address := state.runtimeDeclaration(candidate)
			if address == "" {
				address = candidate
			}
			addresses = append(addresses, address)
		}
		result[alias] = sortedTerms(addresses)
	}
	identities := []string{}
	for _, targets := range result {
		identities = append(identities, targets...)
	}
	for _, address := range identities {
		result[address] = sortedTerms(append(result[address], address))
	}
	return result
}
func (state *compilerState) visibilityReference(ref string, index map[string][]string) string {
	matches := index[ref]
	if len(matches) > 1 {
		state.err = invalidCompiled()
		return ""
	}
	if len(matches) == 1 {
		return matches[0]
	}
	return ref
}
func viewRelationRefs(relation map[string]string, dispositions ...string) []string {
	result := []string{}
	for _, ref := range slices.Sorted(maps.Keys(relation)) {
		if slices.Contains(dispositions, relation[ref]) {
			result = append(result, ref)
		}
	}
	return result
}
func viewRelationSnapshot(relation map[string]string, transition *compiledViewTransition) viewSnapshot {
	result := viewSnapshot{TransitionID: "initial", EffectiveFrom: "initial", EffectiveOrder: "-1", ViewRelation: maps.Clone(relation), VisibleRefs: viewRelationRefs(relation, "observable", "discovered", "inferred", "disclosed", "deceptive"), HiddenRefs: viewRelationRefs(relation, "hidden"), EvidenceOnlyRefs: viewRelationRefs(relation, "evidence_only"), DisclosedRefs: viewRelationRefs(relation, "disclosed"), DiscoveredRefs: viewRelationRefs(relation, "discovered"), InferredRefs: viewRelationRefs(relation, "inferred"), ConcealedRefs: viewRelationRefs(relation, "concealed"), DeceptiveRefs: viewRelationRefs(relation, "deceptive")}
	if transition != nil {
		result.TransitionID = transition.id
		result.EffectiveFrom = transition.effectiveFrom
		result.EffectiveOrder = transition.order
		result.TransitionKind = &transition.kind
		result.InformationRef = &transition.informationRef
		result.HistoryEventType = &transition.eventType
		result.ActionInstanceID = &transition.actionInstance
	}
	return result
}
func (state *compilerState) compileObservationBoundaries() {
	boundaries := fieldValue(state.input.model.ObservationBoundaries)
	index := state.visibilityIndex()
	aliasesByAddress := visibilityAliasesByAddress(index)
	state.boundaries = map[string]participantBoundary{}
	for _, name := range orderedNames(boundaries, state.names(termObservationBoundaries)) {
		state.compileObservationBoundary(name, index, aliasesByAddress)
		if state.err != nil {
			return
		}
	}
}

func visibilityAliasesByAddress(index map[string][]string) map[string]map[string][]string {
	aliasesByAddress := map[string]map[string][]string{}
	for alias, targets := range index {
		if len(targets) == 1 && targets[0] == alias {
			continue
		}
		for _, target := range targets {
			if aliasesByAddress[target] == nil {
				aliasesByAddress[target] = map[string][]string{}
			}
			aliasesByAddress[target][alias] = targets
		}
	}
	return aliasesByAddress
}
func (state *compilerState) compileObservationBoundary(name string, index map[string][]string, aliasesByAddress map[string]map[string][]string) {
	source := fieldValue(state.input.model.ObservationBoundaries)[name]
	resolve := func(refs []string) []string { return state.visibilityReferences(refs, index) }
	hidden, observable, evidence := resolve(fieldValue(source.HiddenRefs)), resolve(fieldValue(source.ObservableRefs)), resolve(fieldValue(source.EvidenceRefs))
	references := append([]string{}, hidden...)
	references = append(references, observable...)
	references = append(references, evidence...)
	relation, ruleReferences := state.compileViewRelations(name, index)
	if state.err != nil {
		return
	}
	references = append(references, ruleReferences...)
	output := participantBoundary{Name: name, Spec: rawJSON(source), BoundaryName: name, ProjectionBasis: fieldValue(source.ProjectionBasis), HiddenRefs: hidden, ObservableRefs: observable, EvidenceRefs: evidence, DisclosedRefs: viewRelationRefs(relation, "disclosed"), EvidenceOnlyRefs: viewRelationRefs(relation, "evidence_only"), DiscoveredRefs: viewRelationRefs(relation, "discovered"), InferredRefs: viewRelationRefs(relation, "inferred"), ConcealedRefs: viewRelationRefs(relation, "concealed"), DeceptiveRefs: viewRelationRefs(relation, "deceptive"), ViewTransitions: []json.RawMessage{}, ViewRelationTimeline: []viewSnapshot{viewRelationSnapshot(relation, nil)}, RealizedViewDisclosure: rawString(fieldValue(source.RealizedViewDisclosure)), ReferenceAliases: map[string][]string{}}
	transitions, transitionReferences := state.compiledViewTransitions(name, index)
	if state.err != nil {
		return
	}
	references = append(references, transitionReferences...)
	state.compileBoundaryTimeline(&output, relation, transitions)
	if state.err != nil {
		return
	}
	for _, ref := range sortedTerms(references) {
		maps.Copy(output.ReferenceAliases, aliasesByAddress[ref])
	}
	address := state.address(termParticipant, termObservationBoundary, name)
	output.evidenceSet = map[string]bool{}
	for _, ref := range output.EvidenceRefs {
		output.evidenceSet[ref] = true
	}
	output.hiddenSet = map[string]bool{}
	for _, ref := range output.HiddenRefs {
		output.hiddenSet[ref] = true
	}
	state.boundaries[address] = output
	state.model.ParticipantResources = append(state.model.ParticipantResources, Resource{Address: address, Name: name, Domain: termParticipant, Kind: termObservationBoundary, Payload: state.payload(output)})
}

func (state *compilerState) visibilityReferences(refs []string, index map[string][]string) []string {
	output := []string{}
	for _, ref := range refs {
		output = append(output, state.visibilityReference(ref, index))
	}
	return dedupe(output)
}
func (state *compilerState) compileViewRelations(name string, index map[string][]string) (map[string]string, []string) {
	source := fieldValue(state.input.model.ObservationBoundaries)[name]
	relation := map[string]string{}
	references := []string{}
	for _, rule := range fieldValue(source.ViewRules) {
		ref := state.visibilityReference(fieldValue(rule.InformationRef), index)
		disposition := string(fieldValue(rule.Disposition))
		if previous, present := relation[ref]; present && previous != disposition {
			state.err = invalidCompiled()
			return nil, nil
		}
		relation[ref] = disposition
		references = append(references, ref)
	}
	return relation, references
}
func (state *compilerState) compiledViewTransitions(name string, index map[string][]string) ([]compiledViewTransition, []string) {
	source := fieldValue(state.input.model.ObservationBoundaries)[name]
	references := []string{}
	transitions := []compiledViewTransition{}
	for _, transition := range fieldValue(source.ViewTransitions) {
		ref := state.visibilityReference(fieldValue(transition.InformationRef), index)
		order := fieldValue(transition.EffectiveOrder)
		integer, valid := new(big.Int).SetString(string(order), 10)
		if !valid {
			state.err = invalidCompiled()
			return nil, nil
		}
		var wire map[string]json.RawMessage
		if err := json.Unmarshal(rawJSON(transition), &wire); err != nil {
			state.err = invalidCompiled()
			return nil, nil
		}
		wire["information_ref"] = rawJSON(ref)
		item := compiledViewTransition{raw: rawJSON(wire), informationRef: ref, from: string(fieldValue(transition.FromDisposition)), to: string(fieldValue(transition.ToDisposition)), id: fieldValue(transition.TransitionId), effectiveFrom: fieldValue(transition.EffectiveFrom), kind: string(fieldValue(transition.TransitionKind)), eventType: string(fieldValue(transition.HistoryEventType)), actionInstance: rawString(fieldValue(transition.ActionInstanceId)), order: order, integerOrder: integer}
		transitions = append(transitions, item)
		references = append(references, ref)
	}
	return transitions, references
}
func (state *compilerState) compileBoundaryTimeline(output *participantBoundary, relation map[string]string, transitions []compiledViewTransition) {
	slices.SortStableFunc(transitions, func(left, right compiledViewTransition) int { return left.integerOrder.Cmp(right.integerOrder) })
	output.transitions = slices.Clone(transitions)
	for i := range transitions {
		transition := &transitions[i]
		output.ViewTransitions = append(output.ViewTransitions, transition.raw)
		if transition.informationRef == "" || transition.to == "" {
			continue
		}
		if previous, present := relation[transition.informationRef]; present && previous != transition.from {
			state.err = invalidCompiled()
			return
		}
		relation[transition.informationRef] = transition.to
		output.ViewRelationTimeline = append(output.ViewRelationTimeline, viewRelationSnapshot(relation, transition))
	}
}

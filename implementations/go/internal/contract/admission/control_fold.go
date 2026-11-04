package admission

import (
	"encoding/json"
	"strconv"
)

type controlProducedTarget struct {
	revision any
	event    string
}
type controlLifecycle struct{ superseded, decided, replaced bool }
type controlEpisodeFold struct {
	policy                              any
	states, transitions, steps, records map[string]any
	stateRef                            string
	stateRevision                       json.Number
	lastOrder                           any
	cursor                              int
	produced                            map[string]controlProducedTarget
	lifecycles                          map[string]controlLifecycle
	proposals, decisions, completions   map[string]bool
	stepRecords                         map[string]string
	available                           []AvailableControlTarget
}

func newControlEpisodeFold(policy any, available []AvailableControlTarget) *controlEpisodeFold {
	fold := &controlEpisodeFold{policy: policy, stateRef: stringAt(policy, "initial_state_ref"), stateRevision: jsonZero, states: map[string]any{}, transitions: map[string]any{}, steps: map[string]any{}, records: map[string]any{}, produced: map[string]controlProducedTarget{}, lifecycles: map[string]controlLifecycle{}, proposals: map[string]bool{}, decisions: map[string]bool{}, completions: map[string]bool{}, stepRecords: map[string]string{}, available: available}
	for _, state := range array(at(policy, "states")) {
		fold.states[stringAt(state, "state_ref")] = state
	}
	for _, transition := range array(at(policy, termTransitions)) {
		fold.transitions[stringAt(transition, termTransitionRef)] = transition
	}
	for _, step := range array(at(policy, "script_steps")) {
		fold.steps[stringAt(step, "step_ref")] = step
	}
	return fold
}

func (f *controlEpisodeFold) apply(record any) error {
	if !matchingFields(record, f.policy, fieldParticipantAddress, fieldEpisodeID, "semantics") || !equal(at(record, termPolicy), at(f.policy, "pin")) {
		return invalid()
	}
	occurrence := at(record, "occurrence")
	if stringAt(occurrence, "disposition") == termRejected {
		return f.rejected(occurrence)
	}
	transition := f.transitions[stringAt(occurrence, "permitted_transition_ref")]
	if transition == nil || stringAt(f.policy, "order_strategy") != "total-effective-order" || !equal(at(transition, termKind), at(occurrence, termKind)) || stringAt(transition, "from_state_ref") != f.stateRef || stringAt(occurrence, "prior_state_ref") != f.stateRef || !numericEqual(at(occurrence, termExpectedStateRevision), f.stateRevision) || !equal(at(transition, "to_state_ref"), at(occurrence, "resulting_state_ref")) {
		return invalid()
	}
	if err := f.script(occurrence); err != nil {
		return err
	}
	if err := f.authority(occurrence, transition); err != nil {
		return err
	}
	if err := f.order(occurrence, transition); err != nil {
		return err
	}
	if err := f.identities(occurrence); err != nil {
		return err
	}
	if err := f.target(occurrence); err != nil {
		return err
	}
	if err := f.transformation(record); err != nil {
		return err
	}
	f.advance(record)
	return nil
}

func (f *controlEpisodeFold) rejected(v any) error {
	observed := at(v, basisObserved)
	if stringAt(observed, "state_ref") != f.stateRef || !numericEqual(at(observed, "state_revision"), f.stateRevision) || !equal(at(observed, "last_accepted_order"), f.lastOrder) || !numericSuccessor(at(v, "occurrence_revision"), at(observed, "history_head")) {
		return invalid()
	}
	return require(f.transitions[stringAt(v, "attempted", "permitted_transition_ref")] != nil || stringAt(v, "reason_code") == "unknown-transition")
}

func (f *controlEpisodeFold) script(v any) error {
	if stringAt(f.policy, "pin", "form") != termFiniteScript {
		return require(at(v, "script_step_ref") == nil)
	}
	steps := array(at(f.policy, "script_steps"))
	if f.cursor >= len(steps) {
		return invalid()
	}
	step := steps[f.cursor]
	return require(equal(at(step, "step_ref"), at(v, "script_step_ref")) && equal(at(step, termTransitionRef), at(v, "permitted_transition_ref")) && (at(step, termExpectedStateRevision) == nil || equal(at(step, termExpectedStateRevision), at(v, termExpectedStateRevision))))
}

func (f *controlEpisodeFold) authority(v, transition any) error {
	source, destination := f.states[stringAt(transition, "from_state_ref")], f.states[stringAt(transition, "to_state_ref")]
	if !matchingFields(v, source, "controller_ref", "authority_basis_refs") || !subset(stringsOf(at(v, "controlled_scope_refs")), set(at(source, "scope_refs"))) || !subset(stringsOf(at(v, "controlled_scope_refs")), set(at(f.policy, "behavior_scope_refs"))) {
		return invalid()
	}
	return require(stringAt(source, "authority_status") != termRevoked && stringAt(destination, "authority_status") != termRevoked)
}

func (f *controlEpisodeFold) bounds(v, transition any) ([2]any, error) {
	windows := []any{transition, f.states[stringAt(transition, "from_state_ref")], f.states[stringAt(transition, "to_state_ref")]}
	if step := f.steps[stringAt(v, "script_step_ref")]; at(step, termValidFromOrder) != nil && at(step, termValidUntilOrder) != nil {
		windows = append(windows, step)
	}
	low, high := at(transition, termValidFromOrder), at(transition, termValidUntilOrder)
	for _, window := range windows {
		if numericGreater(at(window, termValidFromOrder), low) {
			low = at(window, termValidFromOrder)
		}
		if numericGreater(high, at(window, termValidUntilOrder)) {
			high = at(window, termValidUntilOrder)
		}
	}
	if numericGreater(low, high) {
		return [2]any{}, invalid()
	}
	return [2]any{low, high}, nil
}

func (f *controlEpisodeFold) order(v, transition any) error {
	if f.lastOrder != nil && !numericGreater(at(v, "effective_order"), f.lastOrder) {
		return invalid()
	}
	bounds, err := f.bounds(v, transition)
	if err != nil {
		return err
	}
	return require(!numericGreater(bounds[0], at(v, "effective_order")) && !numericGreater(at(v, "effective_order"), bounds[1]) && equal(bounds[0], at(v, termValidFromOrder)) && equal(bounds[1], at(v, termValidUntilOrder)))
}

func (f *controlEpisodeFold) identities(v any) error {
	var identity string
	switch stringAt(v, termKind) {
	case termProposal:
		identity = stringAt(v, "proposal_id")
	case termApproval, termDenial:
		identity = stringAt(v, termDecisionRef)
	case termHandoff:
		return require(!f.completions[stringAt(v, "completion_evidence_ref")])
	default:
		return nil
	}
	return require(!f.proposals[identity] && !f.decisions[identity] && f.transitions[identity] == nil)
}

func (f *controlEpisodeFold) transformation(record any) error {
	v := at(record, "occurrence")
	if stringAt(v, termKind) != termProposal || at(v, "source_proposal_ref") == nil {
		return nil
	}
	produced, exists := f.produced[join(termProposal, stringAt(v, "source_proposal_ref"))]
	if !exists {
		return nil
	}
	source := f.records[produced.event]
	return require(subset([]string{stringAt(source, "event_id"), stringAt(v, termTransformationRef)}, set(at(record, "provenance_refs"))) && subset(stringsOf(at(source, "object_marking_refs")), set(at(record, "object_marking_refs"))))
}

func (f *controlEpisodeFold) advance(record any) {
	v := at(record, "occurrence")
	event := stringAt(record, "event_id")
	f.citedLifecycle(v)
	f.produced[join(messageControl, event)] = controlProducedTarget{at(v, "occurrence_revision"), event}
	f.lifecycles[event] = controlLifecycle{}
	switch stringAt(v, termKind) {
	case termProposal:
		id := stringAt(v, "proposal_id")
		f.produced[join(termProposal, id)] = controlProducedTarget{jsonOne, event}
		f.proposals[id] = true
	case termApproval, termDenial:
		id := stringAt(v, termDecisionRef)
		f.produced[join(termDecision, id)] = controlProducedTarget{jsonOne, event}
		f.decisions[id] = true
	case termHandoff:
		f.completions[stringAt(v, "completion_evidence_ref")] = true
	}
	if at(v, "script_step_ref") != nil {
		f.stepRecords[stringAt(v, "script_step_ref")] = event
	}
	f.records[event] = record
	f.stateRef = stringAt(v, "resulting_state_ref")
	// Published ControlCount is at most one million, so this exact integer
	// conversion is bounded and independent of a JSON number's spelling.
	revision, _ := integer(at(v, "resulting_state_revision"))
	f.stateRevision = json.Number(strconv.Itoa(revision))
	f.lastOrder = at(v, "effective_order")
	if stringAt(f.policy, "pin", "form") == termFiniteScript {
		f.cursor++
	}
}

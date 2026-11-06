package admission

import "slices"

func mixedStagePosition(kind string) int {
	switch kind {
	case "time-grant":
		return 1
	case termExecution, "handoff":
		return 2
	case "delivery", "owner-readback":
		return 3
	case "observation":
		return 4
	default:
		return 0
	}
}

func (s *mixedStages) check() error {
	bySequence, err := s.ordered()
	if err != nil {
		return err
	}

	sequences := make([]int, 0, len(bySequence))
	for sequence := range bySequence {
		sequences = append(sequences, sequence)
	}
	slices.Sort(sequences)
	for _, sequence := range sequences {
		stage := at(bySequence[sequence], "stage")
		kind := stringAt(stage, "stage")
		if err = s.prerequisite(stage); err != nil {
			return err
		}
		if !equal(at(stage, "producer"), s.producer(kind)) {
			return invalid()
		}
		if err = s.identity(stage); err != nil {
			return err
		}
		s.seen[kind] = stage
	}
	if err = s.outcome(); err != nil {
		return err
	}
	return s.citedReports()
}

func (s *mixedStages) prerequisite(stage any) error {
	edge := map[string]string{termTimeGrant: "", termExecution: termTimeGrant, termDelivery: termExecution, termObservation: termDelivery}
	handoff := map[string]string{termTimeGrant: "", termHandoff: termTimeGrant, termOwnerReadback: termHandoff}
	prerequisites := edge
	if stringAt(s.subject, "kind") == termHandoff {
		prerequisites = handoff
	}
	prior, ok := prerequisites[stringAt(stage, "stage")]
	if !ok {
		return invalid()
	}
	if prior != "" && s.seen[prior] == nil {
		return invalid()
	}
	if prior == termTimeGrant && (!s.history.accepted || stringAt(s.seen[prior], "comparison") != "ordered") {
		return invalid()
	}
	return require(stringAt(stage, "stage") != termDelivery || stringAt(s.seen[termExecution], "status") != outcomeFailed)
}

func (s *mixedStages) producer(kind string) any {
	if kind == termTimeGrant {
		return at(s.subject, "time", "coordinator")
	}
	field := map[string]string{termExecution: "bridge", termDelivery: "delivery_reader", termObservation: "observation_reader", termHandoff: "transfer", termOwnerReadback: "owner_reader"}[kind]
	return at(s.subject, field)
}

func (s *mixedStages) identity(stage any) error {
	switch stringAt(stage, "stage") {
	case termTimeGrant:
		return s.grant(stage)
	case termExecution:
		return require(matchingFields(stage, s.subject, "source_action_address", "destination_action_address") && equalSet(set(at(stage, "mapping_loss_refs")), map[string]bool{stringAt(s.subject, "mapping_loss", "limitation_ref"): true}))
	case termDelivery:
		return require(equal(at(stage, "destination_component_id"), at(s.subject, "owner_component_id")))
	case termObservation:
		return require(matchingFields(stage, s.subject, "participant_address", "audience_scope_ref"))
	case termHandoff:
		return require(equal(at(stage, "order_ref"), at(s.seen[termTimeGrant], "order_ref")) && equal(at(stage, "predecessor_history_head"), at(s.fence, "history_head")) && equal(at(stage, "phase_revision"), at(s.fence, "phase_revision")) && subset(stringsOf(at(s.subject, "required_evidence_refs")), set(at(stage, "evidence_refs"))))
	default:
		return nil
	}
}

func (s *mixedStages) grant(v any) error {
	required := at(s.subject, "time")
	if !matchingFields(v, required, "mapping_ref", "ordering_basis") || !equal(at(v, "source_coordinate"), s.before[0]) || !equal(at(v, "destination_coordinate"), s.before[1]) {
		return invalid()
	}
	evidence := set(at(v, "mapping_evidence_refs"))
	for _, ref := range stringsOf(at(v, "timing_evidence_refs")) {
		evidence[ref] = true
	}
	if !subset(stringsOf(at(s.subject, "required_evidence_refs")), evidence) {
		return invalid()
	}
	return require(stringAt(v, "comparison") != "ordered" || mixedMappedOrder(required, s.model, s.before[0], s.before[1]))
}

func (s *mixedStages) ordered() (map[int]any, error) {
	digest, err := jsonDigest(s.request)
	if err != nil {
		return nil, err
	}
	bySequence := map[int]any{}
	for _, report := range s.reports {
		sequence, ok := integer(at(report, "sequence"))
		kind := stringAt(report, "stage", "stage")
		if !ok || sequence != mixedStagePosition(kind) || !equal(at(report, "binding"), at(s.request, "binding")) || stringAt(report, "request_digest") != digest {
			return nil, invalid()
		}
		if previous := bySequence[sequence]; previous != nil && !equal(previous, report) {
			return nil, invalid()
		}
		bySequence[sequence] = report
	}
	return bySequence, nil
}

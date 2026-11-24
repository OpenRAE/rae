package processor

import "encoding/json"

type participantTimeSource struct {
	ClockRef                string  `json:"clock_ref"`
	ConstraintRef           string  `json:"constraint_ref"`
	EventPoint              string  `json:"event_point"`
	EvidenceMode            string  `json:"evidence_mode"`
	ConditionPreconditionID *string `json:"condition_precondition_id"`
	ObservationBoundaryRef  *string `json:"observation_boundary_ref"`
}

func (state *compilerState) participantTemporalBindings(actionRefs []string) []participantTemporalBinding {
	result := []participantTemporalBinding{}
	contracts := fieldValue(state.input.model.ActionContracts)
	for _, ref := range dedupe(actionRefs) {
		name := state.sectionName(ref, termActionContracts)
		contract, exists := contracts[name]
		if !exists {
			state.err = invalidCompiled()
			return nil
		}
		for index := range fieldValue(contract.TemporalContracts) {
			binding := state.participantTemporalBinding(name, index)
			if state.err != nil {
				return nil
			}
			if binding != nil {
				result = append(result, *binding)
			}
		}
	}
	return result
}

func (state *compilerState) participantTemporalBinding(name string, index int) *participantTemporalBinding {
	contract := fieldValue(state.input.model.ActionContracts)[name]
	temporal := fieldValue(contract.TemporalContracts)[index]
	raw := fieldValue(temporal.SharedTimeBinding)
	if len(raw) == 0 || string(raw) == termNull {
		return nil
	}
	var authored participantTimeSource
	if err := json.Unmarshal(raw, &authored); err != nil {
		state.err = invalidCompiled()
		return nil
	}
	clockName := state.sectionName(authored.ClockRef, "clocks")
	constraintName := state.sectionName(authored.ConstraintRef, "temporal_constraints")
	clock := fieldValue(state.input.model.Clocks)[clockName]
	constraint := fieldValue(state.input.model.TemporalConstraints)[constraintName]
	domain := fieldValue(state.input.model.TimeDomains)[state.sectionName(fieldValue(clock.TimeDomainRef), "time_domains")]
	actionAddress := state.address(termParticipant, termActionContract, name)
	// This map is the published digest boundary, not compiler state.
	digestInput := map[string]any{termAction: actionAddress, "temporal_contract": temporal, "clock": clock, "time_domain": domain, "constraint": constraint}
	var boundaryAddress *string
	if authored.ObservationBoundaryRef != nil {
		boundaryAddress = state.participantTemporalBoundary(name, authored, digestInput)
		if state.err != nil {
			return nil
		}
	}
	end := state.participantCoordinate(fieldValue(constraint.End))
	if end == nil {
		state.err = invalidCompiled()
		return nil
	}
	points := []string{}
	for _, point := range fieldValue(temporal.EventPoints) {
		points = append(points, string(point))
	}
	return &participantTemporalBinding{Profile: "participant-shared-time/v1", ActionContractAddress: actionAddress, TemporalID: fieldValue(temporal.TemporalId), TemporalKind: string(fieldValue(temporal.TemporalKind)), ClockAddress: state.address("time", "clock", clockName), ConstraintAddress: state.address("time", "constraint", constraintName), EventPoint: authored.EventPoint, EvidenceMode: authored.EvidenceMode, Start: state.participantCoordinate(fieldValue(constraint.Start)), End: *end, ConditionPreconditionID: authored.ConditionPreconditionID, ObservationBoundaryAddress: boundaryAddress, ContractDigest: state.canonicalDigest(rawJSON(digestInput)), TimeDomain: string(fieldValue(temporal.TimeDomain)), ClockAuthority: fieldValue(temporal.ClockAuthority), EventPoints: points, BackendDisclosureRefs: nonNilStrings(fieldValue(temporal.BackendDisclosureRefs)), ResetBoundary: rawString(fieldValue(temporal.ResetBoundary)), ReplayBoundary: rawString(fieldValue(temporal.ReplayBoundary))}
}

func (state *compilerState) participantTemporalBoundary(name string, authored participantTimeSource, digestInput map[string]any) *string {
	boundary := state.sectionName(*authored.ObservationBoundaryRef, termObservationBoundaries)
	address := state.address(termParticipant, termObservationBoundary, boundary)
	boundaryAddress := &address
	digestInput["observation_boundary"] = fieldValue(state.input.model.ObservationBoundaries)[boundary]
	found := false
	for _, condition := range fieldValue(fieldValue(state.input.model.ActionContracts)[name].Preconditions) {
		if authored.ConditionPreconditionID != nil && fieldValue(condition.PreconditionId) == *authored.ConditionPreconditionID {
			digestInput["condition"] = condition
			found = true
			break
		}
	}
	if !found {
		state.err = invalidCompiled()
		return nil
	}
	return boundaryAddress
}

func (state *compilerState) participantCoordinate(raw json.RawMessage) *participantCoordinate {
	if len(raw) == 0 || string(raw) == termNull {
		return nil
	}
	coordinate := participantCoordinate{Segment: "0", Microstep: "0"}
	if err := json.Unmarshal(raw, &coordinate); err != nil {
		state.err = invalidCompiled()
		return nil
	}
	return &coordinate
}

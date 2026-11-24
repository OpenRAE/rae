package admission

import (
	"math/big"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func (e *Validator) mixedStageTrusted(binding any, s *mixedStages, snapshot MixedBackendStageSnapshot) error {
	required := at(s.subject, "time")
	if snapshot.TimeModelRef != stringAt(required, "time_model_ref") || snapshot.TimeModelDigest != stringAt(required, "time_model_digest") {
		return invalid()
	}
	model, err := e.flowAdmittedDocument(termTimeModelV1, snapshot.TimeModel)
	if err != nil {
		return err
	}
	timeFactoryDefaults(model)
	s.model = model
	before, err := e.flowAdmittedDocument(termTimeRuntimeStateV1, snapshot.TimeState)
	if err != nil {
		return err
	}
	if err = timeRuntimeDeclaration(model, before); err != nil {
		return err
	}
	s.before, err = mixedBoundCoordinates(required, before)
	if err != nil {
		return err
	}
	if err = e.mixedStageReadback(s, snapshot); err != nil {
		return err
	}

	if len(snapshot.CompositionState) > 0 {
		s.fence, err = e.flowOwnerFragment(termRuntimeSnapshotV1, "MixedCompositionRuntimeStateModel", snapshot.CompositionState)
		if err != nil {
			return err
		}
	}
	return s.compositionFence(binding)
}

func timeRuntimeDeclaration(model, state any) error {
	canonical, err := sortedJSON(model)
	if err != nil {
		return err
	}
	if stringAt(state, "declaration_digest") != digest.SHA256([]byte(canonical)) || !equalSet(keySet(at(model, "clocks")), keySet(at(state, "clocks"))) {
		return invalid()
	}
	policies := map[string]any{}
	for _, policy := range object(at(model, "progression_policies")) {
		policies[stringAt(policy, "clock_address")] = at(policy, "address")
	}
	for address, clock := range object(at(state, "clocks")) {
		declared := at(model, "clocks", address)
		if !matchingFields(clock, declared, "time_domain_address", "authority_kind", "authority_ref") || !equal(at(clock, "progression_policy_address"), policies[address]) {
			return invalid()
		}
	}
	return nil
}

func mixedBoundCoordinates(required, state any) ([]any, error) {
	source, destination := at(state, "clocks", stringAt(required, "source_clock_address")), at(state, "clocks", stringAt(required, "destination_clock_address"))
	if source == nil || destination == nil {
		return nil, invalid()
	}
	return []any{at(source, "coordinate"), at(destination, "coordinate")}, nil
}

func (s *mixedStages) compositionFence(binding any) error {
	if s.fence == nil {
		return require(stringAt(s.subject, "kind") != termHandoff)
	}
	if stringAt(s.request, "binding", "context", "run_scope") != "run:"+stringAt(s.fence, "run_id") || !matchingFields(s.fence, binding, termProfileID, "profile_digest") {
		return invalid()
	}
	if stringAt(s.subject, "kind") == "edge" {
		return require(set(at(s.fence, "active_edge_ids"))[stringAt(s.subject, "edge_id")])
	}
	active := set(at(s.fence, "active_component_ids"))
	return require(active[stringAt(s.subject, "source_component_id")] && !active[stringAt(s.subject, "destination_component_id")])
}

func mixedMappedOrder(required, model, source, destination any) bool {
	source, destination = coordinateView(source), coordinateView(destination)
	if object(source) == nil || object(destination) == nil {
		return false
	}
	mapping := at(model, "mappings", stringAt(required, "mapping_ref"))
	if mapping == nil || !equal(at(source, "segment"), at(destination, "segment")) {
		return false
	}
	tick, sok := number(at(source, "tick"))
	target, tok := number(at(destination, "tick"))
	scale, nok := number(at(mapping, "scale", "numerator"))
	denominator, dok := number(at(mapping, "scale", "denominator"))
	offset, ook := number(at(mapping, "offset_ticks"))
	if !sok || !tok || !nok || !dok || !ook || denominator.Sign() == 0 {
		return false
	}
	mapped := new(big.Rat).Add(new(big.Rat).Mul(tick, new(big.Rat).Quo(scale, denominator)), offset)
	comparison := mapped.Cmp(target)
	return comparison < 0 || comparison == 0 && !numericGreater(at(source, termMicrostep), at(destination, termMicrostep))
}

func (e *Validator) mixedStageReadback(s *mixedStages, snapshot MixedBackendStageSnapshot) error {
	if snapshot.PostTimeState.ContractID() != "" {
		after, readErr := e.flowAdmittedDocument(termTimeRuntimeStateV1, snapshot.PostTimeState)
		if readErr != nil {
			return readErr
		}
		if err := timeRuntimeDeclaration(s.model, after); err != nil {
			return err
		}
		coordinates, readErr := mixedBoundCoordinates(at(s.subject, "time"), after)
		if readErr != nil {
			return readErr
		}
		s.confirmed = true
		for index, coordinate := range coordinates {
			order, ok := fullCoordinateCompare(coordinate, s.before[index])
			s.confirmed = s.confirmed && ok && order >= 0
		}
	}
	return nil
}

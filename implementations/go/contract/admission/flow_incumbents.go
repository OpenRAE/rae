package admission

func (f *flowControl) incumbents() error {
	index, err := f.owner.crossingContextIndex(f.context)
	if err != nil {
		return err
	}
	for _, record := range index.records {
		if err = index.common(record); err != nil {
			return err
		}
		if err = index.stage(record); err != nil {
			return err
		}
	}
	if err = index.transformations(); err != nil {
		return err
	}
	f.crossings = index
	f.controls, err = f.owner.checkedControlRecords(f.context)
	return err
}

func (e *Validator) checkedControlRecords(context ControlOccurrenceContext) (map[string]any, error) {
	declarations, targets := context.ControlDeclarations(), context.ControlTargets()
	if len(declarations) > 4096 || len(targets) > 4096 {
		return nil, invalid()
	}
	index := controlOccurrenceIndex{declarations: map[string]any{}, records: map[string]any{}, proposals: map[string]any{}, targets: map[string]any{}, decisions: map[string]bool{}}
	if err := index.authorities(declarations, targets); err != nil {
		return nil, err
	}
	records, err := e.experimentDocuments(termParticipantControlOccurrenceV1, context.ControlOccurrences())
	if err != nil {
		return nil, err
	}
	for _, record := range records {
		v, err := e.defaulted(termParticipantControlOccurrenceV1, record)
		if err != nil {
			return nil, err
		}
		if err = index.register(v); err != nil {
			return nil, err
		}
	}
	for _, record := range index.records {
		if err := index.validate(record); err != nil {
			return nil, err
		}
	}
	return index.records, nil
}

func flowResolutionShape(participant, episode, disposition string) bool {
	return participant != "" && episode != "" && map[string]bool{termPermit: true, termDeny: true, statusUnsupported: true, termStale: true, termUnresolved: true}[disposition]
}

func (f *flowControl) resolutionShapes() error {
	for ref, resolution := range f.snapshot.ActionResolutions {
		admission := f.admissions[ref]
		if ref != resolution.Reference || admission == nil || !flowResolutionShape(resolution.ParticipantAddress, resolution.EpisodeID, resolution.Disposition) || stringAt(admission, "participant_address") != resolution.ParticipantAddress || stringAt(admission, "action_contract_address") != resolution.ActionContractAddress || stringAt(admission, "action_instance_id") != resolution.ActionInstanceID {
			return invalid()
		}
	}
	for ref, resolution := range f.snapshot.CapabilityResolutions {
		if ref != resolution.Reference || !flowResolutionShape(resolution.ParticipantAddress, resolution.EpisodeID, resolution.Disposition) {
			return invalid()
		}
	}
	seen := map[string]bool{}
	for _, resolution := range f.snapshot.HistoryResolutions {
		if !flowResolutionShape(resolution.ParticipantAddress, resolution.EpisodeID, resolution.Disposition) || len(resolution.Heads) == 0 || !flowUniqueReferences(resolution.Heads) || !sortedUnique(resolution.Heads) {
			return invalid()
		}
		key := flowHistoryKey(resolution.ParticipantAddress, resolution.EpisodeID, resolution.Sink, resolution.Heads)
		if seen[key] {
			return invalid()
		}
		seen[key] = true
	}
	return nil
}

func flowHistoryKey(participant, episode string, sink FlowSink, heads []string) string {
	return join(participant, episode, sink.Kind, sink.Reference, sink.Destination, sink.Audience, join(heads...))
}

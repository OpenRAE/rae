package admission

// ParticipantRuntimeBaseEnvelopeModel uses these empty collection factories.
// JSON Schema does not publish a default annotation for a default_factory.
// Full occurrence equality compares model values; the admitted bytes stay exact.
func eventFactoryDefaults(id string, view any) bool {
	switch id {
	case termParticipantControlOccurrenceV1, termParticipantControlOccurrenceV2, termParticipantCrossingOccurrenceV1:
	default:
		return false
	}
	changed := false
	fields := object(view)
	for _, key := range []string{"predecessor_event_refs", "marking_definition_refs", "markings"} {
		if _, present := fields[key]; !present {
			fields[key] = []any{}
			changed = true
		}
	}
	if _, present := fields["granular_markings"]; !present {
		fields["granular_markings"] = map[string]any{}
		changed = true
	}
	return changed
}

package admission

import "github.com/OpenRAE/rae/implementations/go/internal/contract/validation"

func (e *Validator) factRules() map[string]definition {
	return map[string]definition{"runtime-fact-binding-references-resolve": {check: e.factPlane}}
}
func indexRows(rows any, field string) (map[string]any, error) {
	if !unique(rowIDs(rows, field)) {
		return nil, invalid()
	}
	indexed := map[string]any{}
	for _, row := range array(rows) {
		indexed[stringAt(row, field)] = row
	}
	return indexed, nil
}
func (e *Validator) factPlane(i validation.Invocation) error {
	v, err := e.defaulted("runtime-fact-binding-plane-v1", i.Instance)
	if err != nil {
		return err
	}
	declarations, err := indexRows(at(v, "declarations"), "fact_id")
	if err != nil {
		return err
	}
	sinks, err := indexRows(at(v, "sinks"), "sink_id")
	if err != nil {
		return err
	}
	versions, err := indexRows(at(v, "versions"), "version_id")
	if err != nil {
		return err
	}
	if !unique(rowIDs(at(v, "events"), "event_id")) {
		return invalid()
	}
	if err := factDeclarations(declarations); err != nil {
		return err
	}
	if err := factSinks(sinks); err != nil {
		return err
	}
	if err := factVersions(versions, declarations); err != nil {
		return err
	}
	for _, event := range array(at(v, "events")) {
		if err := factEvent(event, sinks, declarations, versions); err != nil {
			return err
		}
	}
	return factProjections(at(v, "projections"), versions)
}

func factProjections(projections any, versions map[string]any) error {
	for _, projection := range array(projections) {
		version := versions[stringAt(projection, "fact_version_id")]
		if version == nil {
			return invalid()
		}
		if err := factProjection(projection, version); err != nil {
			return err
		}
	}
	return nil
}
func matchingFields(a, b any, fields ...string) bool {
	for _, field := range fields {
		if !equal(at(a, field), at(b, field)) {
			return false
		}
	}
	return true
}
func factVersions(versions, declarations map[string]any) error {
	sequences := map[string]map[int64]bool{}
	for _, version := range versions {
		id := stringAt(version, "fact_id")
		declaration := declarations[id]
		if declaration == nil || !matchingFields(version, declaration, "value_type", "source_kind", "sensitivity") {
			return invalid()
		}
		if err := factVersionShape(version); err != nil {
			return err
		}
		sequence, ok := number(at(version, "sequence"))
		if !ok || !sequence.IsInt() || !sequence.Num().IsInt64() {
			return invalid()
		}
		n := sequence.Num().Int64()
		if sequences[id] == nil {
			sequences[id] = map[int64]bool{}
		}
		if n < 1 || sequences[id][n] {
			return invalid()
		}
		sequences[id][n] = true
	}
	return contiguousSequences(sequences)
}

func contiguousSequences(sequences map[string]map[int64]bool) error {
	for _, group := range sequences {
		for n := range group {
			if n > int64(len(group)) {
				return invalid()
			}
		}
	}
	return nil
}
func factEvent(event any, sinks, declarations, versions map[string]any) error {
	sink := sinks[stringAt(event, "sink_id")]
	if sink == nil || !matchingFields(event, sink, "target_field", "action_contract_address") {
		return invalid()
	}
	bound := stringAt(event, "disposition") == "bound"
	if bound && (at(event, "fact_id") == nil || at(event, "fact_version_id") == nil) {
		return invalid()
	}
	if at(event, "fact_version_id") == nil {
		return nil
	}
	version := versions[stringAt(event, "fact_version_id")]
	if version == nil || !matchingFields(event, version, "fact_id", "sensitivity", fieldEvidenceRefs, "provenance_refs") || boolean(at(event, "redacted")) != (stringAt(version, "sensitivity") == sensitivitySecret) {
		return invalid()
	}
	if bound {
		return boundFactEvent(event, sink, version, declarations[stringAt(version, "fact_id")])
	}
	return nil
}
func boundFactEvent(event, sink, version, declaration any) error {
	if !equal(at(version, "value_type"), at(sink, "value_type")) || !set(at(sink, "allowed_source_kinds"))[stringAt(version, "source_kind")] || !set(at(sink, "allowed_scope_kinds"))[stringAt(version, "scope", termKind)] || !set(at(sink, "allowed_sensitivities"))[stringAt(version, "sensitivity")] {
		return invalid()
	}
	if !equal(at(event, termRunID), at(version, "scope", termRunID)) {
		return invalid()
	}
	for _, field := range []string{fieldParticipantAddress, fieldEpisodeID, fieldWorkflowAddress} {
		if at(version, "scope", field) != nil && !equal(at(version, "scope", field), at(event, field)) {
			return invalid()
		}
	}
	authorizations := set(at(event, "authorization_refs"))
	if !subset(stringsOf(at(declaration, "authority_refs")), authorizations) || !subset(stringsOf(at(sink, "authority_refs")), authorizations) {
		return invalid()
	}
	audience := stringAt(sink, "audience")
	visible := set(at(declaration, "visibility", "participant_addresses"))[stringAt(event, fieldParticipantAddress)]
	if audience == "workflow" {
		visible = set(at(declaration, "visibility", "workflow_addresses"))[stringAt(event, fieldWorkflowAddress)]
	}
	return require(visible && (stringAt(version, "sensitivity") != sensitivitySecret || audience == "protected_sink"))
}
func factProjection(projection, version any) error {
	if !matchingFields(projection, version, "fact_id", "value_type", "source_kind", "sensitivity", "scope", "observed_at", fieldEvidenceRefs, "provenance_refs") || !referenceScalarEqual(at(projection, "confidence"), at(version, "confidence")) {
		return invalid()
	}
	secret := stringAt(version, "sensitivity") == sensitivitySecret
	if boolean(at(projection, "redacted")) != secret || boolean(at(projection, "secret_reference_present")) != secret {
		return invalid()
	}
	if secret {
		return require(at(projection, "value") == nil)
	}
	return require(at(projection, "value") != nil && referenceScalarEqual(at(projection, "value"), at(version, "value")))
}

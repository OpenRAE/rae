package admission

import (
	"maps"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) runTimeModel(i validation.Invocation) error {
	run := i.Instance
	provenance := at(run, "realized_time_model")
	if provenance == nil {
		return nil
	}
	v, err := e.defaulted(termRealizedTimeModelV1, provenance)
	if err != nil {
		return err
	}
	if !equal(at(v, termRunID), at(run, termRunID)) {
		return invalid()
	}
	declared, realized := at(v, "declared_model"), at(v, "realized_model")
	for _, model := range []any{declared, realized} {
		timeFactoryDefaults(model)
		if checkErr := timeDeclaration(model); checkErr != nil {
			return checkErr
		}
	}
	canonical, err := sortedJSON(declared)
	if err != nil {
		return err
	}
	if digest.SHA256([]byte(canonical)) != stringAt(v, "declaration_digest") {
		return invalid()
	}
	return timeProvenanceBindings(v, declared, realized)
}

func timeProvenanceBindings(v, declared, realized any) error {
	known := map[string]bool{}
	for _, section := range []string{"domains", "clocks", fieldMappings, fieldProgressionPolicies, "temporal_constraints"} {
		if !equalSet(keySet(at(declared, section)), keySet(at(realized, section))) {
			return invalid()
		}
		maps.Copy(known, keySet(at(declared, section)))
	}
	bindings := at(v, "apparatus_bindings")
	if !keyed(bindings, "address") {
		return invalid()
	}
	if !subset(mapKeys(at(declared, "clocks")), keySet(bindings)) || !subset(mapKeys(at(declared, fieldProgressionPolicies)), keySet(bindings)) || !subset(mapKeys(bindings), known) {
		return invalid()
	}
	for _, limit := range array(at(v, "timing_limits")) {
		if !known[stringAt(limit, "subject_address")] {
			return invalid()
		}
	}
	return require(equal(declared, realized) || len(array(at(v, "deviations"))) > 0)
}

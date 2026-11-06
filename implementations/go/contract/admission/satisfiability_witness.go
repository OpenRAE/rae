package admission

import (
	"encoding/json"
	"reflect"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// Witness phase admission belongs to the same native SDL/compiler owner used
// for materialization. That owner returns phase facts; the contract keeps its
// own source, model, solver and canonical witness joins.
func (e *Validator) checkSatisfiabilityWitness(id string, data []byte, limits ingress.Limits, context any) error {
	if id != "scenario-satisfiability-evidence-v1" {
		return nil
	}
	root, err := ingress.Parse(data, limits, ingress.Object)
	if err != nil {
		return err
	}
	witness := at(root, "witness")
	if witness == nil {
		return nil
	}
	owner, ok := context.(MaterializationCompiler)
	if !ok || witnessCompilerMissing(owner) {
		return invalid()
	}
	supplied := at(witness, "snapshot", kindScenario)
	source, err := json.Marshal(supplied)
	if err != nil {
		return invalid()
	}
	compiled, err := e.materializationCompile(owner, MaterializationCompileRequest{ContractID: termInstantiatedScenarioV1, Source: source})
	if err != nil {
		return err
	}
	if !materializationSupplied(supplied, compiled.full) {
		return invalid()
	}
	actual, err := jsonDigest(map[string]any{"profile": "raes-sdl-instantiated-snapshot/v2", kindScenario: compiled.full})
	if err != nil || actual != stringAt(witness, "snapshot_digest") {
		return invalid()
	}
	return nil
}

func witnessCompilerMissing(owner MaterializationCompiler) bool {
	if owner == nil {
		return true
	}
	v := reflect.ValueOf(owner)
	kind := v.Kind()
	return (kind == reflect.Chan || kind == reflect.Func || kind == reflect.Interface || kind == reflect.Map || kind == reflect.Pointer || kind == reflect.Slice) && v.IsNil()
}

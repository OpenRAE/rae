package sdl

import (
	"bytes"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// ParameterDerivationImage retains the SDL owner's finite image of one public
// scalar substitution. Found with a nil image means an unenumerated input.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func ParameterDerivationImage(scenario Scenario, fieldPointer string) (admission.Fragment, bool, error) {
	input, err := nativeScenario(scenario)
	if err != nil {
		return nil, false, err
	}
	raw, found, err := input.document.ParameterDerivationImage(fieldPointer)
	if err != nil || !found || raw == nil {
		return nil, found, err
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var values any
	if decoder.Decode(&values) != nil {
		return nil, true, invalidScenario()
	}
	owner, err := fragmentOwner()
	if err != nil {
		return nil, true, err
	}
	result, err := admission.AdmitFragment(owner, admission.RealizationValue, values, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
	return result, true, err
}

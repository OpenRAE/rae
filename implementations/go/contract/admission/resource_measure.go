package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// ParticipantResourceMeasureSupported admits pinned quantity semantics through
// the existing offline owner. Built-in kinds need no profile authority.
func ParticipantResourceMeasureSupported(v *Validator, kind Fragment, unit, accountingMode, meterProfileRef, reset string, context *binding.DomainProfileResolutionContextV1) (bool, error) {
	if v == nil || CheckFragment(kind, RealizationValue) != nil {
		return false, fragmentInvalid()
	}
	quantity := map[string]any{termResourceKind: kind.Document(), "unit": unit, "accounting_mode": accountingMode, "meter_profile_ref": meterProfileRef, "reset": reset}
	if value.Validate(quantity, value.Default()) != nil {
		return false, fragmentInvalid()
	}
	if _, builtin := quantity[termResourceKind].(string); builtin {
		return true, nil
	}
	if !v.definitionCheck(termBackendManifestV2, "DomainProfileCoordinateModel")(quantity[termResourceKind]) {
		return false, fragmentInvalid()
	}
	if context == nil {
		return false, nil
	}
	input, err := profileInput(v, profileContextContract, *context)
	if err != nil {
		return false, err
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return false, fragmentInvalid()
	}
	return v.resourceMeasureSupported(quantity, reset, raw), nil
}

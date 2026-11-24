package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// ProjectProcessIdentity checks a constructed native process identity and
// returns the existing owner's lossless selector projection.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func ProjectProcessIdentity(v *Validator, input Fragment) (Fragment, error) {
	return projectProcessModel(v, input, "RuntimeProcessIdentity", func(value any) any { return sdlProcessProjection(value) })
}

// ProjectProcessResourceLimit checks a constructed native limit and preserves
// its semantic identity and bounds through the existing shared owner.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func ProjectProcessResourceLimit(v *Validator, input Fragment) (Fragment, error) {
	return projectProcessModel(v, input, "RuntimeProcessResourceLimit", func(value any) any { return sdlProcessLimitProjection(value) })
}

// ProcessResourceLimitCapabilityAdmits validates the native capability and
// complete finite domains before applying the existing owner's relation.
func ProcessResourceLimitCapabilityAdmits(v *Validator, capability Fragment, resource, scope string, soft, hard Fragment) (bool, error) {
	if v == nil || CheckFragment(capability, RealizationValue) != nil || CheckFragment(soft, RealizationValue) != nil || CheckFragment(hard, RealizationValue) != nil || len(resource) > 128 || len(scope) > 128 {
		return false, fragmentInvalid()
	}
	owned, err := nativeFragment(capability, RealizationValue)
	if err != nil {
		return false, err
	}
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}
	if err := v.CheckModelFragment("backend-manifest-v2", schemaDefinitionsPrefix+"ProcessResourceLimitCapabilityModel", owned.data, limits); err != nil {
		return false, err
	}
	softValues, softOK := soft.Document().([]any)
	hardValues, hardOK := hard.Document().([]any)
	if !softOK || !hardOK {
		return false, fragmentInvalid()
	}
	return sdlProcessLimitDomainAdmits(capability.Document(), resource, scope, softValues, hardValues), nil
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func projectProcessModel(v *Validator, input Fragment, model string, project func(any) any) (Fragment, error) {
	if v == nil || CheckFragment(input, RealizationValue) != nil {
		return nil, fragmentInvalid()
	}
	document := input.Document()
	raw, err := json.Marshal(document)
	if err != nil {
		return nil, fragmentInvalid()
	}
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}
	if err := v.CheckSDLConstruction("sdl-authoring-input-v1", schemaDefinitionsPrefix+model, raw, limits); err != nil {
		return nil, err
	}
	return AdmitFragment(v, RealizationValue, project(document), limits)
}

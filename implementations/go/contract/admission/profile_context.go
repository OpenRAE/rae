package admission

import (
	"encoding/json"
	"reflect"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

const planProfileContract = "plan-realization-profiles-v1"
const profileContextContract = "domain-profile-resolution-context-v1"

func profileInput(v *Validator, contract string, input any) (map[string]any, error) {
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}
	if v == nil || CheckTransport(input, limits) != nil {
		return nil, fragmentInvalid()
	}
	if checkProfileValues(input) != nil {
		return nil, fragmentInvalid()
	}
	raw, err := json.Marshal(input)
	if err != nil || v.CheckPortable(contract, raw, limits) != nil {
		return nil, fragmentInvalid()
	}
	return v.low.DefaultedObjectFragment(contract, "#", raw, limits)
}

// The reference profile host applies the shared realization-value budget to
// the complete carrier, in addition to byte/depth and published schema checks.
func checkProfileValues(inputs ...any) error {
	projection := transportProjection{limits: value.Default(), bytes: 8 << 20}
	root := reflect.ValueOf(inputs)
	if len(inputs) == 1 {
		root = reflect.ValueOf(inputs[0])
	}
	return value.ValidateProjected(transportValue{root, true}, projection.limits, projection.project)
}

func profileDigest(input any) (string, error) {
	raw, err := json.Marshal(input)
	if err != nil {
		return "", fragmentInvalid()
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return "", fragmentInvalid()
	}
	return digest.SHA256(canonical), nil
}

// DomainProfileContextDigest commits to local definition admission, operation
// support and limits. A context grants no authority outside its exact bindings.
func DomainProfileContextDigest(v *Validator, context binding.DomainProfileResolutionContextV1) (string, error) {
	input, err := profileInput(v, profileContextContract, context)
	if err != nil {
		return "", err
	}
	return profileDigest(map[string]any{"host": planProfileContract, "context": input})
}

// CheckDomainProfileBindings reuses the bounded offline profile owner. It
// checks generated carriers before serialization and never acquires a schema.
func CheckDomainProfileBindings(v *Validator, bindings []binding.DomainProfileBindingV1, context binding.DomainProfileResolutionContextV1, policy binding.DomainProfileAdmissionPolicyV1) (bool, error) {
	if len(bindings) > 256 {
		return false, fragmentInvalid()
	}
	input, err := profileInput(v, profileContextContract, context)
	if err != nil {
		return false, err
	}
	if _, checkErr := profileInput(v, "domain-profile-admission-policy-v1", policy); checkErr != nil {
		return false, checkErr
	}
	for _, item := range bindings {
		if _, checkErr := profileInput(v, "domain-profile-binding-v1", item); checkErr != nil {
			return false, checkErr
		}
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return false, fragmentInvalid()
	}
	report, err := v.owners.AdmitDomainBindings(bindings, raw, policy)
	return err == nil && report.Admitted(), err
}

package admission

import (
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// ValueFreeAccountPlacement copies the canonical credential path and retains
// only material presence. The original native input remains immutable.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func ValueFreeAccountPlacement(input Fragment) (Fragment, error) {
	if err := CheckFragment(input, RealizationValue); err != nil {
		return nil, err
	}
	document := input.Document()
	payload := object(document)
	if payload == nil {
		return nil, fragmentInvalid()
	}
	spec := object(payload["spec"])
	if spec == nil {
		return input, nil
	}
	bindings, known := spec["credential_bindings"].([]any)
	if !known {
		return input, nil
	}
	result := make([]any, len(bindings))
	for i, entry := range bindings {
		projected, err := valueFreeCredential(entry)
		if err != nil {
			return nil, err
		}
		result[i] = projected
	}
	spec["credential_bindings"] = result
	data, err := value.Encode(document, value.Runtime())
	if err != nil {
		return nil, err
	}
	return fragment{profile: RealizationValue, data: data}, nil
}

func credentialTextWithin(minimum, maximum int) nativeCheck {
	return func(v any) bool {
		text, ok := v.(string)
		return ok && utf8.RuneCountInString(text) >= minimum && utf8.RuneCountInString(text) <= maximum
	}
}

func valueFreeCredential(entry any) (map[string]any, error) {
	binding := object(entry)
	material, err := valueFreeCredentialMaterial(object(at(entry, "material")))
	if binding == nil || err != nil {
		return nil, fragmentInvalid()
	}
	projected := map[string]any{"credential_id": binding["credential_id"], "purpose": binding["purpose"], "auth_method": binding["auth_method"], "material": material}
	shape := nativeShape{required: map[string]nativeCheck{"credential_id": credentialTextWithin(1, 64), "purpose": credentialTextWithin(1, 256), "auth_method": credentialTextWithin(1, 256), "material": isObject}}
	if !shape.holds(projected) {
		return nil, fragmentInvalid()
	}
	return projected, nil
}

func valueFreeCredentialMaterial(material map[string]any) (map[string]any, error) {
	if material == nil {
		return nil, fragmentInvalid()
	}
	classification := stringAt(material, "classification")
	safe := map[string]any{"classification": classification}
	switch classification {
	case "secret_fixture":
		_, present := material["value"]
		if !present && material["value_present"] != true {
			return nil, fragmentInvalid()
		}
		safe["value_present"] = true
	case termOperatorSecret:
		_, present := material["reference_id"]
		if !present && material["reference_present"] != true {
			return nil, fragmentInvalid()
		}
		safe["reference_present"] = true
	default:
		return nil, fragmentInvalid()
	}
	return safe, nil
}

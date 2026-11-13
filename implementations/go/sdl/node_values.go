package sdl

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// NormalizeNodeValue applies the native whole-node constructor and returns
// typed child presence. It grants no scenario or sibling-reference authority.
//
//nolint:ireturn // The native normalization boundary returns an opaque value fragment.
func NormalizeNodeValue(node admission.Fragment) (admission.Fragment, map[string][]string, error) {
	if err := admission.CheckFragment(node, admission.RealizationValue); err != nil {
		return nil, nil, err
	}
	raw, err := json.Marshal(node.Document())
	if err != nil {
		return nil, nil, err
	}
	parser, err := scenarioParser(DefaultLimits())
	if err != nil {
		return nil, nil, err
	}
	normalized, presence, err := parser.NormalizeNodeValue(raw)
	if err != nil {
		return nil, nil, err
	}
	data, err := ingress.Parse(normalized, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return nil, nil, err
	}
	owner, err := fragmentOwner()
	if err != nil {
		return nil, nil, err
	}
	output, err := admission.AdmitFragment(owner, admission.RealizationValue, data, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
	return output, presence, err
}

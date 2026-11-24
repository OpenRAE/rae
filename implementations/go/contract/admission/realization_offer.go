package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// RealizationOfferAdmits compares a bounded native value with an independently
// checked configured offer. Presence comes from native typed construction;
// caller-supplied presence alone grants no selection or target authority.
func RealizationOfferAdmits(v *Validator, envelope binding.RealizationEnvelopeV1, fieldPath string, projection Fragment, presence map[string][]string) (bool, error) {
	if v == nil || len(fieldPath) == 0 || len(fieldPath) > 4096 || !envelopePath.MatchString(fieldPath) || CheckFragment(projection, RealizationValue) != nil {
		return false, invalid()
	}
	input := projection.Document()
	if err := offerProjectionBounds(input, presence); err != nil {
		return false, err
	}
	document, err := realizationOfferEnvelope(v, envelope)
	if err != nil {
		return false, err
	}
	// The expression and source carrier were independently admitted above.
	// A refusal from the shared bounded relation cannot establish membership.
	return materializationOfferIn(input, fieldPath, presence, document["expression"]) == nil, nil
}

func realizationOfferEnvelope(v *Validator, envelope binding.RealizationEnvelopeV1) (map[string]any, error) {
	if v == nil {
		return nil, invalid()
	}
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
	if err := CheckTransport(envelope, limits); err != nil {
		return nil, err
	}
	raw, err := json.Marshal(envelope)
	if err != nil || v.CheckPortable(termRealizationEnvelopeV1, raw, limits) != nil {
		return nil, invalid()
	}
	document, err := v.low.DefaultedObjectFragment(termRealizationEnvelopeV1, "#", raw, limits)
	if err != nil {
		return nil, err
	}
	return document, nil
}
func offerProjectionBounds(input any, presence map[string][]string) error {
	if len(presence) > value.Runtime().MaxMembers {
		return value.ErrLimit
	}
	projected := make(map[string]any, len(presence))
	for path, fields := range presence {
		if len(fields) > value.Runtime().MaxMembers {
			return value.ErrLimit
		}
		children := make([]any, len(fields))
		for i, field := range fields {
			children[i] = field
		}
		projected[path] = children
	}
	return value.Validate(map[string]any{termProjection: input, termPresence: projected}, value.Runtime())
}

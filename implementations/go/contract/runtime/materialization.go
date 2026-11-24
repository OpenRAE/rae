// Package runtime owns portable backend requests and proposed results.
// It does not grant execution authority or own live runtime state.
package runtime

import (
	"slices"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// MaterializationSubmission carries bounded source text for downstream admission.
type MaterializationSubmission struct {
	ContractID string
	SDL        []byte
}

// NewMaterializationSubmission bounds and copies UTF-8 source text.
// This does not parse SDL or establish delivery evidence.
func NewMaterializationSubmission(sdl []byte) (MaterializationSubmission, error) {
	if len(sdl) == 0 || len(sdl) > 4<<20 || !utf8.Valid(sdl) {
		return MaterializationSubmission{}, fault.New(fault.InvalidInput, "materialization-submission-invalid", nil)
	}
	return MaterializationSubmission{ContractID: "backend-materialization-attestation-v1", SDL: slices.Clone(sdl)}, nil
}

package processor

import (
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

// ResolveRealization keeps the effective view under the compiled model owner.
// Callers supply target context, never a replacement compiled representation.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func ResolveRealization(model RuntimeModel, options realization.ResolveOptions) (RuntimeModel, realization.Resolution, error) {
	original, err := nativeRuntimeModel(model)
	if err != nil {
		return nil, realization.Resolution{}, err
	}
	resolved, err := realization.Resolve(original.view.RealizationRequirements, original.view.RealizationAuthority, options)
	if err != nil {
		return nil, realization.Resolution{}, err
	}
	view := copyCompiledScenario(original.view)
	view.RealizationRequirements = resolved.Requirements
	// The model retains compiled posture and delegation origin. Resolved plan
	// authority is returned separately, as in the reference pipeline.
	type identity struct{ address, path, kind string }
	opened := map[identity]bool{}
	for _, authority := range resolved.Authority {
		if authority.Posture == "open" {
			opened[identity{authority.Address, authority.FieldPath, authority.Concern}] = true
		}
	}
	for i := range view.RealizationAuthority {
		authority := &view.RealizationAuthority[i]
		if opened[identity{authority.Address, authority.FieldPath, authority.Concern}] && !authority.Delegated {
			authority.Posture = "open"
		}
	}
	view = copyCompiledScenario(view)
	document, err := compiledProjection(view)
	if err != nil {
		return nil, realization.Resolution{}, err
	}
	return &runtimeModel{view: view, document: document, participants: original.participants}, resolved, nil
}

package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// MixedFeatureDowngrade binds one exact weaker feature claim to its owner grant.
type MixedFeatureDowngrade struct {
	ProfileID, ComponentID, Feature, RequiredLevel, AllowedLevel, PolicyRef, ProvenanceRef string
}

// MixedCompositionSnapshot contains independently resolved compiler and owner
// coordinates. Pair keys are profile ID and the corresponding record ID.
type MixedCompositionSnapshot struct {
	ScenarioSnapshots                           map[string][]byte
	CompiledTargets                             map[string]string
	Components, Allocations, Edges, Transitions map[[2]string][]byte
	FeatureDowngrades                           []MixedFeatureDowngrade
	TimeModels                                  map[string]validation.Value
	TimeModelDigests                            map[string]string
	EvidenceSatisfaction                        map[[2]string][]string
	NestedProfiles                              map[string][]byte
	TrialAdmission                              bool
	AllocationEffects                           map[[2]string][]string
	ResourceRefs                                map[string][]string
	ProjectionMembership                        map[[2]string]bool
}

// MixedCompositionContext supplies finite trusted relationships. The feature
// resolver checks only installed feature support; it cannot admit a profile.
type MixedCompositionContext interface {
	MixedCompositionSnapshot() MixedCompositionSnapshot
	ResolveMixedFeature(profileID, componentID string, requirement json.RawMessage) error
}

type mixedResolution struct {
	owner                                       *Validator
	context                                     MixedCompositionContext
	snapshot                                    MixedCompositionSnapshot
	scenarios, times                            map[string]any
	components, allocations, edges, transitions map[[2]string]any
	profiles                                    map[string]any
	visited, visiting                           map[string]bool
	work                                        int
}

func (e *Validator) mixedContextRules() map[string]definition {
	return map[string]definition{"mixed-composition-trusted-context-required": {check: e.mixedResolvedContext, contextual: true, requiresContext: true}}
}

func (e *Validator) mixedResolvedContext(i validation.Invocation) (err error) {
	defer func() {
		if recover() != nil {
			err = invalid()
		}
	}()
	context, ok := i.Context.(MixedCompositionContext)
	if !ok {
		return contextRequired()
	}
	r, err := e.mixedResolution(context)
	if err != nil {
		return err
	}
	v, err := e.defaulted(termMixedParticipantCompositionProfileV1, i.Instance)
	if err != nil {
		return err
	}
	return r.visit(v)
}

func (e *Validator) mixedResolution(context MixedCompositionContext) (*mixedResolution, error) {
	r := &mixedResolution{owner: e, context: context, snapshot: context.MixedCompositionSnapshot(), profiles: map[string]any{}, visited: map[string]bool{}, visiting: map[string]bool{}}
	if err := r.load(); err != nil {
		return nil, err
	}
	return r, nil
}

func (r *mixedResolution) charge() error {
	r.work++
	return require(r.work <= 100000)
}

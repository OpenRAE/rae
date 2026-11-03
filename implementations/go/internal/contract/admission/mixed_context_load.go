package admission

import "github.com/OpenRAE/rae/implementations/go/internal/base/ingress"

func (r *mixedResolution) fragment(name string, data []byte) (any, error) {
	return r.owner.low.DefaultedObjectFragment(termMixedParticipantCompositionProfileV1, "#/$defs/"+name, data, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
}

func (r *mixedResolution) load() error {
	s := r.snapshot
	for _, count := range []int{len(s.ScenarioSnapshots), len(s.CompiledTargets), len(s.Components), len(s.Allocations), len(s.Edges), len(s.Transitions), len(s.FeatureDowngrades), len(s.TimeModels), len(s.TimeModelDigests), len(s.EvidenceSatisfaction), len(s.NestedProfiles), len(s.AllocationEffects), len(s.ResourceRefs), len(s.ProjectionMembership)} {
		if count > 4096 {
			return invalid()
		}
	}
	r.scenarios, r.times = map[string]any{}, map[string]any{}
	remaining := 64 * 1048576
	var err error
	r.scenarios, err = r.scenarioIndex(s.ScenarioSnapshots)
	if err != nil {
		return err
	}

	for key, model := range s.TimeModels {
		raw := model.JSON()
		if len(raw) > remaining {
			return invalid()
		}
		remaining -= len(raw)
		v, modelErr := r.owner.flowAdmittedDocument(termTimeModelV1, model)
		if modelErr != nil {
			return modelErr
		}
		r.times[key] = v
	}
	r.components, err = r.index("MixedCompositionComponentModel", s.Components)
	if err != nil {
		return err
	}
	r.allocations, err = r.index("MixedCompositionAllocationModel", s.Allocations)
	if err != nil {
		return err
	}
	r.edges, err = r.index("MixedCompositionEdgeModel", s.Edges)
	if err != nil {
		return err
	}
	r.transitions, err = r.index("MixedCompositionTransitionModel", s.Transitions)
	if err != nil {
		return err
	}
	return nil
}

func (r *mixedResolution) index(name string, raw map[[2]string][]byte) (map[[2]string]any, error) {
	result := map[[2]string]any{}
	remaining := 64 * 1048576
	for key, data := range raw {
		if len(data) > remaining {
			return nil, invalid()
		}
		remaining -= len(data)
		v, err := r.fragment(name, data)
		if err != nil {
			return nil, err
		}
		result[key] = v
	}
	return result, nil
}

func (r *mixedResolution) visit(v any) error {
	if err := r.charge(); err != nil {
		return err
	}
	id := stringAt(v, termProfileID)
	if r.visiting[id] {
		return invalid()
	}
	if r.visited[id] {
		return nil
	}
	if len(r.visited) >= 64 {
		return invalid()
	}
	r.visiting[id] = true
	for field, limit := range map[string]int{termComponents: 64, termAllocations: 1024, termEdges: 1024, termPhases: 256, termTransitions: 512, "nested_profile_refs": 64} {
		if len(object(at(v, field))) > limit {
			return invalid()
		}
	}
	if err := r.profile(v); err != nil {
		return err
	}
	if r.snapshot.TrialAdmission {
		if err := r.trial(v); err != nil {
			return err
		}
	}
	r.profiles[id] = v
	for child, digest := range object(at(v, "nested_profile_refs")) {
		if err := r.child(child, text(digest)); err != nil {
			return err
		}
	}
	delete(r.visiting, id)
	r.visited[id] = true
	return nil
}

func (r *mixedResolution) child(id, digest string) error {
	if err := r.charge(); err != nil {
		return err
	}
	raw, ok := r.snapshot.NestedProfiles[id]
	if !ok {
		return invalid()
	}
	v, err := r.owner.contextDocument(termMixedParticipantCompositionProfileV1, raw)
	if err != nil {
		return err
	}
	v, err = r.owner.defaulted(termMixedParticipantCompositionProfileV1, v)
	if err != nil {
		return err
	}
	if stringAt(v, termProfileID) != id || stringAt(v, "profile_digest") != digest {
		return invalid()
	}
	return r.visit(v)
}

func (r *mixedResolution) scenarioIndex(values map[string][]byte) (map[string]any, error) {
	remaining := 64 * 1048576
	result := map[string]any{}
	for key, data := range values {
		if len(data) > remaining {
			return nil, invalid()
		}
		remaining -= len(data)
		v, err := r.fragment("ExperimentReferenceModel", data)
		if err != nil {
			return nil, err
		}
		result[key] = v
	}
	return result, nil
}

package admission

import "github.com/OpenRAE/rae/implementations/go/internal/base/graph"

type controlEffectSet struct {
	variants    []any
	byID, byKey map[string][]any
	ancestors   map[string]map[string]bool
	newKeys     map[string]bool
}

func controlEffectBlockers(request any, results, realizations []any) (map[string]bool, error) {
	blockers := map[string]bool{}
	effects, err := controlEffects(request, results, blockers)
	if err != nil {
		return nil, err
	}
	if err := effects.retained(at(request, "context"), blockers); err != nil {
		return nil, err
	}
	if err := effects.bounds(at(request, "context"), at(request, "selection", "bounds")); err != nil {
		return nil, err
	}
	for index, left := range effects.variants {
		for _, right := range effects.variants[index+1:] {
			if controlEffectPair(left, right, effects.ancestors, at(request, "context")) {
				blockers[reasonEffectConflict] = true
			}
		}
	}
	if len(rowSet(realizations, "effect_id")) != len(realizations) {
		return nil, invalid()
	}
	for _, realization := range realizations {
		if len(effects.byID[stringAt(realization, "effect_id")]) == 0 {
			return nil, invalid()
		}
	}
	return blockers, nil
}

func controlEffects(request any, results []any, blockers map[string]bool) (*controlEffectSet, error) {
	effects := &controlEffectSet{byID: map[string][]any{}, byKey: map[string][]any{}, newKeys: map[string]bool{}}
	seen := map[string]bool{}
	for _, result := range results {
		if err := effects.addResult(request, result, seen, blockers); err != nil {
			return nil, err
		}
	}
	var err error
	effects.ancestors, err = controlEffectAncestors(effects.byID)
	if err != nil {
		return nil, err
	}
	return effects, nil
}

func controlEffectAncestors(byID map[string][]any) (map[string]map[string]bool, error) {
	edges := map[string][]string{}
	for id, variants := range byID {
		dependencies := map[string]bool{}
		for _, effect := range variants {
			for _, predecessor := range stringsOf(at(effect, "predecessor_effect_ids")) {
				dependencies[predecessor] = true
			}
		}
		edges[id] = boolKeys(dependencies)
	}
	if graph.HasCycle(edges) {
		return nil, invalid()
	}
	ordered, err := graph.Order(edges, nil)
	if err != nil {
		return nil, invalid()
	}
	ancestors := map[string]map[string]bool{}
	for _, id := range ordered {
		ancestors[id] = map[string]bool{}
		for _, dependency := range edges[id] {
			ancestors[id][dependency] = true
			for prior := range ancestors[dependency] {
				ancestors[id][prior] = true
			}
		}
	}
	return ancestors, nil
}

func boolKeys(values map[string]bool) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	return keys
}

func (effects *controlEffectSet) retained(context any, blockers map[string]bool) error {
	priorKeys, priorIDs := map[string]any{}, map[string]any{}
	for _, claim := range array(at(context, "prior_effect_claims")) {
		key, err := controlDigest(at(claim, "key"))
		if err != nil {
			return err
		}
		priorKeys[key], priorIDs[stringAt(claim, "effect_id")] = claim, claim
	}
	for key, variants := range effects.byKey {
		prior := priorKeys[key]
		if prior == nil {
			effects.newKeys[key] = true
		}
		for _, effect := range variants {
			if err := controlRetainedEffect(effect, prior, priorIDs, blockers); err != nil {
				return err
			}
		}
	}
	return nil
}

func (effects *controlEffectSet) bounds(context, bounds any) error {
	epochs := map[string]map[string]bool{}
	for _, firing := range array(at(context, "rule_firings")) {
		epochs[join(stringAt(firing, "rule_id"), stringAt(firing, "rule_revision"))] = set(at(firing, "firing_epochs"))
	}
	for key, variants := range effects.byKey {
		for _, effect := range variants {
			if err := controlBoundEffect(effect, effects.newKeys[key], epochs, context, bounds); err != nil {
				return err
			}
		}
	}
	for _, values := range epochs {
		if len(values) > countAt(bounds, "max_firings_per_rule") {
			return invalid()
		}
	}
	if len(effects.newKeys) > 0 && !numericGreater(at(bounds, "max_depth"), at(context, "depth")) {
		return invalid()
	}
	return require(len(effects.newKeys) <= countAt(bounds, "max_fanout") && len(effects.newKeys)+countAt(context, "effects_consumed") <= countAt(bounds, "max_effects"))
}

func controlEffectWindow(target, context, bounds any) error {
	kind := stringAt(target, termKind)
	if kind != termDelay && kind != "request-review" {
		return nil
	}
	if !equal(at(target, "clock"), at(context, "clock")) || numericGreater(at(context, "order"), at(target, "expiry_order")) || numericGreater(at(target, "expiry_order"), at(bounds, "expires_at_order")) {
		return invalid()
	}
	return require(kind != termDelay || !numericGreater(at(context, "order"), at(target, "latest_order")))
}

func (effects *controlEffectSet) addResult(request, result any, seen, blockers map[string]bool) error {
	effect := at(result, "payload")
	if stringAt(effect, termKind) != termEffectRequest {
		return nil
	}
	digest, err := controlDigest(effect)
	if err != nil {
		return err
	}
	if seen[digest] {
		return nil
	}
	seen[digest] = true
	effects.variants = append(effects.variants, effect)
	if !equal(at(effect, "key", "run_ref"), at(request, "context", "run", "ref")) || !equal(at(effect, "key", "trigger_root"), at(request, "context", "trigger_root")) {
		return invalid()
	}
	key, err := controlDigest(at(effect, "key"))
	if err != nil {
		return err
	}
	id := stringAt(effect, "effect_id")
	effects.byID[id] = append(effects.byID[id], effect)
	effects.byKey[key] = append(effects.byKey[key], effect)
	if len(effects.byID[id]) > 1 || len(effects.byKey[key]) > 1 {
		blockers[reasonEffectConflict] = true
	}
	if stringAt(effect, "phase") == termRequiredPredecessor {
		blockers["predecessor:"+id] = true
	}

	return nil
}

func controlRetainedEffect(effect, prior any, priorIDs map[string]any, blockers map[string]bool) error {
	digest, err := controlDigest(effect)
	if err != nil {
		return err
	}
	if prior != nil && (!equal(at(prior, "effect_id"), at(effect, "effect_id")) || stringAt(prior, "content_digest") != digest) {
		blockers[reasonEffectConflict] = true
	}
	if previous := priorIDs[stringAt(effect, "effect_id")]; previous != nil && !equal(at(previous, "key"), at(effect, "key")) {
		blockers[reasonEffectConflict] = true
	}

	return nil
}

func controlBoundEffect(effect any, newKey bool, epochs map[string]map[string]bool, context, bounds any) error {
	rule := join(stringAt(effect, "key", "rule_id"), stringAt(effect, "key", "rule_revision"))
	if epochs[rule] == nil {
		epochs[rule] = map[string]bool{}
	}
	epochs[rule][stringAt(effect, "key", "firing_epoch")] = true
	if newKey {
		if err := controlEffectWindow(at(effect, "target"), context, bounds); err != nil {
			return err
		}
	}

	return nil
}

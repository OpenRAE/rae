package admission

func controlEffectBudgetV2(v any) error {
	request := at(v, "request")
	results := []any{}
	for _, effect := range array(at(v, "effect_plan", termEffects)) {
		results = append(results, map[string]any{"payload": effect})
	}
	effects, err := controlEffects(request, results, map[string]bool{})
	if err != nil {
		return err
	}
	prior := controlRows(at(request, "context", "prior_effect_claims"), "effect_id")
	for _, claim := range array(at(v, "continuation", "realized_claims")) {
		prior[stringAt(claim, "effect_id")] = claim
	}
	for _, id := range stringsOf(at(v, "effect_plan", "realized_effect_ids")) {
		variants := effects.byID[id]
		if len(variants) != 1 || prior[id] == nil {
			return invalid()
		}
		digest, err := controlDigest(variants[0])
		if err != nil {
			return err
		}
		if !equal(at(prior[id], "key"), at(variants[0], "key")) || stringAt(prior[id], "content_digest") != digest {
			return invalid()
		}
	}
	if err := controlEffectLifecycleOrder(effects, at(request, "context")); err != nil {
		return err
	}
	blockers := map[string]bool{}
	if err := effects.retained(at(request, "context"), blockers); err != nil {
		return err
	}
	if len(blockers) > 0 {
		return invalid()
	}
	return effects.bounds(at(request, "context"), at(request, "selection", "bounds"))
}

func controlEffectLifecycleOrder(effects *controlEffectSet, context any) error {
	for index, left := range effects.variants {
		for _, right := range effects.variants[index+1:] {
			if controlLifecycleInvalidates(at(left, "target"), at(right, "target"), context) && !effects.ancestors[stringAt(left, "effect_id")][stringAt(right, "effect_id")] || controlLifecycleInvalidates(at(right, "target"), at(left, "target"), context) && !effects.ancestors[stringAt(right, "effect_id")][stringAt(left, "effect_id")] {
				return invalid()
			}
		}
	}
	return nil
}

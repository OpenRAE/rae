package admission

import (
	"maps"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func equalSet(a, b map[string]bool) bool { return maps.Equal(a, b) }
func digestMatches(v any, field string) error {
	digest, err := jsonDigest(at(v, field))
	if err != nil {
		return err
	}
	return require(digest == stringAt(v, field+"_digest"))
}

func opacityEvidenceClaim(v any, model bool) error {
	claim := at(v, "claim")
	for _, field := range []string{fieldTaxonomyID, fieldTaxonomyRevision, fieldRelationID} {
		if !equal(at(v, field), at(claim, field)) {
			return invalid()
		}
	}
	if !equal(at(v, termProfileID), at(claim, "relation_parameter_profile_ref")) || !equal(at(v, "profile_revision"), at(claim, "relation_parameter_profile_revision")) {
		return invalid()
	}
	return opacityClaimScope(claim, at(v, fieldAssumptions), model)
}

func opacityPayloads(v any) error {
	outcome := stringAt(v, messageOutcome)
	if (outcome == outcomeCounterexample) != (at(v, "counterexample") != nil) || (outcome == outcomeVacuous || outcome == statusUnsupported) != (at(v, statusUnsupported) != nil) {
		return invalid()
	}
	if at(v, statusUnsupported) != nil {
		codes := stringsOf(at(v, statusUnsupported, "reason_codes"))
		if !sortedUnique(codes) || !equalSet(set(at(v, statusUnsupported, "reason_codes")), rowSet(at(v, "diagnostics"), "code")) {
			return invalid()
		}
	}
	return nil
}

func (e *Validator) opacityEvidence(i validation.Invocation) error {
	v, err := e.defaulted("participant-opacity-analysis-evidence-v1", i.Instance)
	if err != nil {
		return err
	}
	checked, secret := countAt(v, "checked_points"), countAt(v, "checked_secret_points")
	outcome := stringAt(v, messageOutcome)
	decided := outcome == outcomeCounterexample || outcome == "no-counterexample-within-declared-finite-bounds"
	if secret > checked || decided && (checked == 0 || secret == 0 || len(array(at(v, "diagnostics"))) > 0) || outcome == outcomeVacuous && secret != 0 {
		return invalid()
	}
	if err := digestMatches(v, "checker_configuration"); err != nil {
		return err
	}
	if err := opacityPayloads(v); err != nil {
		return err
	}
	if err := opacityEvidenceClaim(v, false); err != nil {
		return err
	}
	return opacityCounterexample(v)
}

func opacityCounterexample(v any) error {
	if counter := at(v, "counterexample"); counter != nil {
		payload := map[string]any{"normalized_model_digest": at(v, "normalized_model_digest")}
		for _, field := range []string{"safe_ref", "actual_point_ordinal", "examined_cell_size"} {
			payload[field] = at(counter, field)
		}
		digest, err := jsonDigest(payload)
		if err != nil {
			return err
		}
		if digest != stringAt(counter, "counterexample_digest") {
			return invalid()
		}
	}
	return nil
}

func (e *Validator) opacityModelEvidence(i validation.Invocation) error {
	v, err := e.defaulted("participant-opacity-model-check-evidence-v1", i.Instance)
	if err != nil {
		return err
	}
	if err := opacityAssumptions(at(v, fieldAssumptions)); err != nil {
		return err
	}
	for _, field := range []string{fieldAssumptions, "checker_configuration"} {
		if err := digestMatches(v, field); err != nil {
			return err
		}
	}
	if err := opacityEvidenceClaim(v, true); err != nil {
		return err
	}
	if err := opacityCoverage(v); err != nil {
		return err
	}
	if err := opacityPayloads(v); err != nil {
		return err
	}
	outcome := stringAt(v, messageOutcome)
	coverage := at(v, "coverage")
	decided := outcome == "holds-on-exact-complete-finite-model" || outcome == outcomeCounterexample
	if decided && (!boolean(at(coverage, "complete_fixed_point")) || len(array(at(v, "diagnostics"))) > 0 || countAt(coverage, "reachable_evaluation_points") == 0 || countAt(coverage, "reachable_secret_points") == 0) {
		return invalid()
	}
	if outcome == outcomeVacuous && countAt(coverage, "reachable_secret_points") != 0 {
		return invalid()
	}
	if counter := at(v, "counterexample"); counter != nil {
		return opacityModelCounterexample(v, counter)
	}
	return nil
}

func opacityCoverage(v any) error {
	c := at(v, "coverage")
	declared := at(c, "declared")
	assumptions := at(v, fieldAssumptions)
	if countAt(c, "explored_states") > countAt(declared, "states") || countAt(c, "explored_transitions") > countAt(declared, termTransitions) || countAt(c, "reachable_evaluation_points") > countAt(c, "explored_states") || countAt(c, "reachable_secret_points") > countAt(c, "reachable_evaluation_points") {
		return invalid()
	}
	if !orderedRows(at(c, "strategy_coverage"), fieldStrategyRef) {
		return invalid()
	}
	for _, field := range []string{"explored_states", "explored_transitions", "reachable_evaluation_points", "reachable_secret_points"} {
		sum := 0
		for _, strategy := range array(at(c, "strategy_coverage")) {
			sum += countAt(strategy, field)
		}
		if !countEqual(at(c, field), sum) {
			return invalid()
		}
	}
	if !countEqual(at(declared, "strategies"), len(array(at(assumptions, "strategy_refs")))) || !countEqual(at(declared, "scheduler_environment_pairs"), len(array(at(assumptions, "scheduler_refs")))*len(array(at(assumptions, "environment_refs")))) || !countEqual(at(declared, "order_variants"), len(array(at(assumptions, "order_refs")))) {
		return invalid()
	}
	if boolean(at(c, "complete_fixed_point")) {
		if !equalSet(rowSet(at(c, "strategy_coverage"), fieldStrategyRef), set(at(assumptions, "strategy_refs"))) || !numericEqual(at(c, "explored_scheduler_environment_pairs"), at(declared, "scheduler_environment_pairs")) || !numericEqual(at(c, "explored_order_variants"), at(declared, "order_variants")) {
			return invalid()
		}
	}
	return nil
}

func opacityModelCounterexample(v, counter any) error {
	declared := at(v, "coverage", "declared")
	if countAt(counter, "actual_state_ordinal") >= countAt(declared, "states") {
		return invalid()
	}
	for _, value := range array(at(counter, "actual_path_transition_ordinals")) {
		n, ok := integer(value)
		if !ok || n >= countAt(declared, termTransitions) {
			return invalid()
		}
	}
	payload := map[string]any{}
	for _, field := range []string{"safe_ref", "actual_state_ordinal", "actual_path_transition_ordinals", fieldStrategyRef, "examined_cell_size"} {
		payload[field] = at(counter, field)
	}
	for _, field := range []string{"model_digest", "profile_digest", "derived_carrier_digest"} {
		payload[field] = at(v, field)
	}
	digest, err := jsonDigest(payload)
	if err != nil {
		return err
	}
	return require(digest == stringAt(counter, "counterexample_digest"))
}

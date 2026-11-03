package admission

import (
	"time"

	"github.com/OpenRAE/rae/implementations/go/internal/base/timestamp"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func runDifficulty(i validation.Invocation) error {
	run := i.Instance
	provenance := at(run, "difficulty_provenance")
	if provenance == nil {
		return nil
	}
	if err := difficultyProvenance(provenance); err != nil {
		return err
	}
	start, err := timestamp.ParseRFC3339("started_at", stringAt(run, "started_at"))
	if err != nil {
		return invalid()
	}
	end, err := timestamp.ParseRFC3339("ended_at", stringAt(run, "ended_at"))
	if err != nil {
		return invalid()
	}
	decisions := map[string]time.Time{}
	for _, decision := range array(at(provenance, "decisions")) {
		at, err := difficultyTime(run, decision, "decided_at", start.Instant(), end.Instant())
		if err != nil {
			return err
		}
		decisions[stringAt(decision, termDecisionID)] = at
	}
	for _, intervention := range array(at(provenance, "interventions")) {
		at, err := difficultyTime(run, intervention, "occurred_at", start.Instant(), end.Instant())
		if err != nil {
			return err
		}
		decision, ok := decisions[stringAt(intervention, termDecisionID)]
		if !ok || at.Before(decision) {
			return invalid()
		}
	}
	return nil
}
func difficultyTime(run, record any, field string, start, end time.Time) (time.Time, error) {
	if !equal(at(record, termRunID), at(run, termRunID)) {
		return time.Time{}, invalid()
	}
	instant, err := timestamp.ParseRFC3339(field, stringAt(record, field))
	if err != nil || instant.Instant().Before(start) || instant.Instant().After(end) {
		return time.Time{}, invalid()
	}
	return instant.Instant(), nil
}
func difficultyProvenance(v any) error {
	ref := at(v, "design_ref")
	policy := at(v, termPolicy)
	if stringAt(ref, fieldRefKind) != termAuthoringInput || at(ref, fieldRefVersion) == nil || at(ref, "ref_digest") == nil || at(ref, "ref_path") != nil || !equal(at(v, "baseline_variant_id"), at(policy, "baseline_variant_id")) {
		return invalid()
	}
	condition := stringAt(policy, "condition")
	disposition := stringAt(v, "comparison_disposition")
	if condition == conditionFixed {
		return require(len(array(at(v, "decisions"))) == 0 && len(array(at(v, "interventions"))) == 0 && disposition == "fixed-baseline")
	}
	expected := map[string]string{"adaptive": "adaptation-is-treatment", "scaffolded": "scaffold-exposure-is-treatment"}[condition]
	if disposition != expected && disposition != "descriptive-only" {
		return invalid()
	}
	if err := difficultyDecisions(v, policy); err != nil {
		return err
	}
	return difficultyInterventions(v, policy)
}
func difficultyDecisions(v, policy any) error {
	decisions := array(at(v, "decisions"))
	if len(rowSet(decisions, termDecisionID)) != len(decisions) || len(rowSet(decisions, termRunID)) > 1 {
		return invalid()
	}
	var priorHead, priorCut any
	for _, decision := range decisions {
		cut := at(decision, "state_cut", "coordinate")
		if priorCut != nil && !numericGreater(cut, priorCut) || !equal(at(decision, "prior_history_head"), priorHead) {
			return invalid()
		}
		priorCut = cut
		priorHead = at(decision, "history_head")
		if !matchingFields(decision, policy, "policy_id", "policy_version", "policy_digest", "validity_effect") {
			return invalid()
		}
		if err := difficultySelectedDecision(decision, policy); err != nil {
			return err
		}
		if err := difficultyObservations(decision, policy); err != nil {
			return err
		}
	}
	return nil
}
func difficultyObservations(decision, policy any) error {
	observations := array(at(decision, "observation_refs"))
	sources := at(policy, "observation_sources")
	if !equalSet(rowSet(observations, "source_id"), keySet(sources)) {
		return invalid()
	}
	for _, observation := range observations {
		source := at(sources, stringAt(observation, "source_id"))
		if !equal(at(observation, "source_ref"), at(source, "source_ref")) {
			return invalid()
		}
		current, cok := number(at(decision, "state_cut", "coordinate"))
		observed, ook := number(at(observation, "observed_cut", "coordinate"))
		age, aok := number(at(source, "maximum_age"))
		if !cok || !ook || !aok || current.Sub(current, observed).Cmp(age) > 0 {
			return invalid()
		}
	}
	return nil
}
func difficultyInterventions(v, policy any) error {
	decisions := map[string]any{}
	for _, decision := range array(at(v, "decisions")) {
		decisions[stringAt(decision, termDecisionID)] = decision
	}
	interventions := array(at(v, "interventions"))
	if len(rowSet(interventions, "intervention_id")) != len(interventions) {
		return invalid()
	}
	for _, intervention := range interventions {
		decision := decisions[stringAt(intervention, termDecisionID)]
		action := at(policy, termActions, stringAt(intervention, "action_id"))
		if decision == nil || action == nil || !equal(at(decision, "selected_action_id"), at(intervention, "action_id")) || !equal(at(action, "affected_refs"), at(intervention, "affected_refs")) || !equal(at(decision, termRunID), at(intervention, termRunID)) {
			return invalid()
		}
		follow := stringAt(action, "action_kind") == "follow-up-trial"
		if follow != (at(intervention, "follow_up_run_ref") != nil) || follow && equal(at(intervention, "follow_up_run_ref", fieldRefID), at(intervention, termRunID)) {
			return invalid()
		}
	}
	return nil
}

func difficultySelectedDecision(decision, policy any) error {
	if stringAt(decision, "disposition") == termSelected {
		rule := at(policy, "threshold_rules", stringAt(decision, "trigger_rule_id"))
		action := at(policy, termActions, stringAt(decision, "selected_action_id"))
		if rule == nil || action == nil || !equal(at(rule, "action_id"), at(decision, "selected_action_id")) || !equal(at(action, "affected_refs"), at(decision, "affected_refs")) {
			return invalid()
		}
	}
	return nil
}

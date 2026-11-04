package admission

import (
	"maps"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) trialPlanRules() map[string]definition {
	return map[string]definition{
		"admitted-trial-entry-resolved-and-integrity-bound": {check: e.trialEntry},
		"admitted-trial-plan-identity-joins-and-integrity":  {check: e.trialPlan},
	}
}

func (e *Validator) trialEntry(i validation.Invocation) error {
	v := i.Instance
	if equal(at(v, termRunID), at(v, "plan_entry_id")) || !unique(rowIDs(at(v, "selections"), "variation_point_id")) || !matchingFields(v, at(v, "instantiation_provenance"), "plan_entry_id", termRunID) {
		return invalid()
	}
	for _, draw := range array(at(v, "stochastic_draws")) {
		if boolean(at(draw, "rejection_exhausted")) {
			return invalid()
		}
	}
	if err := entryConfigurations(v); err != nil {
		return err
	}
	return e.trialDigest(i, "entry_digest")
}

func trialProjection(v any) {
	switch value := v.(type) {
	case []any:
		for _, child := range value {
			trialProjection(child)
		}

	case map[string]any:
		for _, child := range value {
			trialProjection(child)
		}
		trialModelProjection(value)
	}
}

func (e *Validator) trialDigest(i validation.Invocation, field string) error {
	root, err := e.defaulted(i.Key.ContractID, invocationRoot(i))
	if err != nil {
		return err
	}
	trialProjection(root)
	v, ok := pointerAt(root, i.Path)
	if !ok {
		return invalid()
	}
	content := maps.Clone(object(v))
	delete(content, field)
	digest, err := jsonDigest(content)
	if err != nil {
		return err
	}
	return require(stringAt(v, field) == digest)
}

func (e *Validator) trialPlan(i validation.Invocation) error {
	v := i.Instance
	if err := trialReplacement(v); err != nil {
		return err
	}
	if !keyed(at(v, "entries"), "plan_entry_id") || !keyed(at(v, "cleanup_plans"), "plan_id") || !keyed(at(v, "stochastic_controls"), "control_id") || !countEqual(at(v, termAdmission, "entry_count"), len(object(at(v, "entries")))) {
		return invalid()
	}
	if err := trialIdentities(v); err != nil {
		return err
	}
	if err := trialProfileJoins(v); err != nil {
		return err
	}
	if err := trialCleanupJoins(v); err != nil {
		return err
	}
	if err := trialIsolation(v); err != nil {
		return err
	}
	if err := trialTreatments(v); err != nil {
		return err
	}
	if err := trialAllocation(v, i.Source, i.Path); err != nil {
		return err
	}
	return e.trialDigest(i, "plan_digest")
}

func trialReplacement(v any) error {
	origin, policy := at(v, "replacement_origin"), at(v, "replacement_policy")
	if strings.HasPrefix(stringAt(v, "profiles", "compiler_profile"), "trial-compiler-replacement-") != (origin != nil) {
		return invalid()
	}
	if origin == nil {
		return nil
	}
	if policy == nil || numericGreater(at(origin, "ordinal"), at(policy, "max_replacements")) || len(object(at(v, "entries"))) != 1 || stringAt(v, "plan_id") == stringAt(origin, "root_plan_id") || stringAt(v, "plan_id") == stringAt(origin, "parent_plan_id") {
		return invalid()
	}
	for _, entry := range object(at(v, "entries")) {
		if equal(at(entry, termRunID), at(origin, "parent_run_id")) {
			return invalid()
		}
	}
	return nil
}

func trialIdentities(v any) error {
	entries, runs, coordinates := object(at(v, "entries")), map[string]bool{}, map[string]bool{}
	for _, entry := range entries {
		run := stringAt(entry, termRunID)
		coordinate := join(stringAt(entry, "coordinate", "condition_id"), stringAt(entry, "coordinate", "block_id"), stringAt(entry, "coordinate", "replicate_id"))
		if runs[run] || entries[run] != nil || run == stringAt(v, "plan_id") || coordinates[coordinate] {
			return invalid()
		}
		runs[run], coordinates[coordinate] = true, true
		provenance := at(entry, "instantiation_provenance")
		if !equal(at(provenance, "plan_id"), at(v, "plan_id")) || !equal(at(provenance, "scenario_family_id"), at(v, "input_refs", "scenario_family_ref", "ref_id")) {
			return invalid()
		}
	}
	for _, control := range object(at(v, "stochastic_controls")) {
		if at(control, "executable_binding") != nil && !equal(at(control, "executable_binding", "profile_ref", "ref_id"), at(v, "profiles", "random_stream_profile")) {
			return invalid()
		}
	}
	return nil
}

func trialProfileJoins(v any) error {
	mixed := false
	used := map[string]bool{}
	for _, entry := range object(at(v, "entries")) {
		apparatus := at(entry, termApparatus)
		if stringAt(apparatus, "realization_kind") != "mixed-composition" {
			continue
		}
		mixed = true
		ref := at(apparatus, "profile_ref")
		used[join(stringAt(ref, "ref_id"), stringAt(ref, "ref_version"), stringAt(ref, "ref_digest"))] = true
		if equal(at(apparatus, "source_trial", "plan_id"), at(v, "plan_id")) {
			return invalid()
		}
	}
	profiles := at(v, "profiles")
	if mixed != strings.HasSuffix(stringAt(profiles, "compiler_profile"), "mixed-composition-v1") {
		return invalid()
	}
	entryProfile, runProfile := "trial-entry-identity-v1", "archival-run-identity-v1"
	if mixed {
		entryProfile, runProfile = "trial-entry-identity-mixed-composition-v1", "archival-run-identity-mixed-composition-v1"
	}
	if stringAt(profiles, "entry_identity_profile") != entryProfile || stringAt(profiles, "run_identity_profile") != runProfile {
		return invalid()
	}
	declared := rowTupleSet(at(v, "input_refs", "mixed_composition_profile_refs"), "ref_id", "ref_version", "ref_digest")
	return require(equalSet(used, declared))
}

func trialCleanupJoins(v any) error {
	used := map[string]bool{}
	for _, entry := range object(at(v, "entries")) {
		id := stringAt(entry, "execution_controls", "cleanup_plan_ref")
		cleanup := at(v, "cleanup_plans", id)
		if cleanup == nil || !matchingFields(entry, cleanup, "plan_entry_id", termRunID) {
			return invalid()
		}
		used[id] = true
		if err := trialEntryDraws(v, entry); err != nil {
			return err
		}
	}
	return require(sameKeys(at(v, "cleanup_plans"), used))
}

func trialEntryDraws(plan, entry any) error {
	for _, draw := range array(at(entry, "stochastic_draws")) {
		binding := at(plan, "stochastic_controls", stringAt(draw, "control_id"), "executable_binding")
		if binding == nil || !equal(at(binding, "namespace"), at(draw, "address", "namespace")) || !equal(at(entry, "coordinate"), at(draw, "address", "trial_coordinate")) {
			return invalid()
		}
	}
	return nil
}

func trialIsolation(v any) error {
	proof := at(v, "isolation_proof")
	if proof == nil {
		return nil
	}
	if !subset(stringsOf(at(proof, "plan_entry_ids")), keySet(at(v, "entries"))) {
		return invalid()
	}
	if !numericGreater(at(proof, "requested_parallelism"), jsonOne) {
		return nil
	}
	owned := map[string]bool{}
	for _, id := range stringsOf(at(proof, "plan_entry_ids")) {
		cleanup := at(v, "cleanup_plans", stringAt(v, "entries", id, "execution_controls", "cleanup_plan_ref"))
		resources := map[string]bool{}
		for _, boundary := range object(at(cleanup, "resource_boundaries")) {
			for _, ref := range stringsOf(at(boundary, "resource_refs")) {
				resources[ref] = true
			}
		}
		for ref := range resources {
			if owned[ref] {
				return invalid()
			}
			owned[ref] = true
		}
	}
	return nil
}

func trialModelProjection(value map[string]any) {
	if _, ok := value["authoring_input_ref"]; ok {
		if _, present := value["capture_spec_refs"]; !present {
			value["capture_spec_refs"] = []any{}
		}
	}
	if _, ok := value["target_id"]; ok && value["control_context_selection"] == nil {
		delete(value, "control_context_selection")
	}
	if _, ok := value["entry_digest"]; ok && len(array(value["participant_configurations"])) == 0 {
		delete(value, "participant_configurations")
	}
	trialProfileProjection(value)
	if _, ok := value["authoring_input_ref"]; ok && len(array(value["mixed_composition_profile_refs"])) == 0 {
		delete(value, "mixed_composition_profile_refs")
	}
	if _, ok := value["realization_envelope"]; ok && len(array(value["participant_manifest_refs"])) == 0 {
		delete(value, "participant_manifest_refs")
	}
	if stringAt(value, "realization_kind") == "mixed-composition" && len(array(value["participant_manifest_refs"])) == 0 {
		delete(value, "participant_manifest_refs")
	}
	trialOptionalProjection(value)
}

func trialProfileProjection(value map[string]any) {
	if _, ok := value["compiler_profile"]; ok {
		if stringAt(value, "allocation_profile") == postureNone {
			delete(value, "allocation_profile")
		}
		if value["treatment_profile"] == nil {
			delete(value, "treatment_profile")
		}
	}
}

func trialOptionalProjection(value map[string]any) {
	if _, ok := value["origin_policy_id"]; ok && value["treatment"] == nil {
		delete(value, "treatment")
	}
	if _, ok := value["entries"]; ok {
		for _, key := range []string{"replacement_policy", "replacement_origin", "allocation"} {
			if value[key] == nil {
				delete(value, key)
			}
		}
	}
}

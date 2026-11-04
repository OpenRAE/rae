package admission

func contextSourceBindings(v any) error {
	sources := array(at(v, "source_layers"))
	if len(rowSet(sources, "source_id")) != len(sources) || !subset(stringsOf(at(v, "transformation", "input_source_ids")), rowSet(sources, "source_id")) {
		return invalid()
	}
	refs := set(at(v, "derived_from_refs"))
	refs[stringAt(v, "source_snapshot_ref")] = true
	for _, source := range sources {
		if !refs[stringAt(source, "ref")] {
			return invalid()
		}
	}
	return nil
}

func jointActionModel(v any) error {
	if err := jointActionMembers(v); err != nil {
		return err
	}
	exact, unsupported := boolean(at(v, "exact_concurrency_claim")), boolean(at(v, "unsupported_disclosure"))
	if exact && (unsupported || at(v, "time_management_context_ref") == nil) {
		return invalid()
	}
	policy := stringAt(v, "conflict_policy")
	if policy == "unsupported" {
		return require(unsupported && !exact)
	}
	conflict := jointActionConflict(array(at(v, "access_sets")))
	if !unsupported && stringAt(v, "conflict_class") != conflict || stringAt(v, "conflict_class") == postureNone && conflict != postureNone {
		return invalid()
	}
	return jointActionConflictPolicy(v, conflict)
}

func jointActionConflict(access []any) string {
	conflict := postureNone
	for index, left := range access {
		leftWrites := jointActionWrites(left)
		for _, right := range access[index+1:] {
			rightWrites := jointActionWrites(right)
			if !disjoint(boolKeys(leftWrites), rightWrites) {
				return "write_write"
			}
			if !disjoint(boolKeys(leftWrites), set(at(right, "shared_state_read_refs"))) || !disjoint(stringsOf(at(left, "shared_state_read_refs")), rightWrites) {
				conflict = "read_write"
			}
		}
	}
	return conflict
}

func jointActionWrites(access any) map[string]bool {
	writes := set(at(access, "shared_state_write_refs"))
	for _, ref := range stringsOf(at(access, "exclusive_resource_refs")) {
		writes["resource:"+ref] = true
	}
	return writes
}

func localOutcomeReport(v any) error {
	if at(v, "rule_spec", "local_outcome") == nil || !equal(at(v, "category"), at(v, "rule_spec", "local_outcome", "category")) || (stringAt(v, "knowledge") == "conflicting" || stringAt(v, "knowledge") == "withheld") && stringAt(v, "attainment") != "undetermined" || numericEqual(at(v, "revision"), jsonOne) != (at(v, "predecessor_event_ref") == nil) {
		return invalid()
	}
	refs := array(at(v, "observation_refs"))
	excluded := stringsOf(at(v, "excluded_observation_refs"))
	return require(len(rowSet(refs, "observation_point")) == len(refs) && fieldsUnique(v, "excluded_observation_refs") && subset(excluded, rowSet(refs, "observation_point")) && (len(excluded) == 0 || at(v, "correction_basis") != nil))
}

func observationSelectorModel(v any) error {
	if !fieldsUnique(v, "excluded_scopes", "component_refs", "names", "window_refs") || !paired(v, "coverage_profile", "max_items") {
		return invalid()
	}
	scope := stringAt(v, "semantic_scope")
	for _, excluded := range stringsOf(at(v, "excluded_scopes")) {
		if excluded == scope || !pointerContains(scope, excluded) {
			return invalid()
		}
	}
	return nil
}

func reusableFamilyPolicy(v any) error {
	signature := false
	for _, requirement := range array(at(v, "evidence_requirements")) {
		enforcement := stringAt(requirement, "enforcement")
		if stringAt(requirement, "evidence_class") == "authenticity_signature" && (enforcement == requirementRequired || enforcement == "recommended") {
			signature = true
		}
	}
	return require(signature == (at(v, "authenticity_policy") != nil))
}

func jointActionMembers(v any) error {
	members := set(at(v, "member_event_refs"))
	access := array(at(v, "access_sets"))
	order := array(at(v, "realized_order"))
	if !fieldsUnique(v, "member_event_refs") || len(access) != len(members) || !equalSet(rowSet(access, "member_event_ref"), members) || len(order) > 0 && (!fieldsUnique(v, "realized_order") || len(order) != len(members) || !equalSet(set(order), members)) {
		return invalid()
	}

	return nil
}

func jointActionConflictPolicy(v any, conflict string) error {
	order := array(at(v, "realized_order"))
	policy := stringAt(v, "conflict_policy")
	if (stringAt(v, "isolation_guarantee") == "serializable" || policy == "serialize") && len(order) == 0 || policy == termRetry && (at(v, "retry_limit") == nil || len(array(at(v, "rollback_event_refs"))) == 0) || policy == postureNone && conflict != postureNone {
		return invalid()
	}
	return require(stringAt(v, "atomicity_scope") != "multi_object" || conflict == postureNone || len(order) > 0 || len(array(at(v, "rollback_event_refs"))) > 0)
}

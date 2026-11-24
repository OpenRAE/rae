package admission

import "github.com/OpenRAE/rae/implementations/go/internal/base/graph"

func flowSubjectKey(v any) string {
	return join(stringAt(v, "subject_kind"), stringAt(v, "subject_ref"), stringAt(v, "subject_revision"), stringAt(v, "participant_address"), stringAt(v, "episode_id"))
}

func flowRelation(v any) error {
	indexes, err := flowIndexes(v)
	if err != nil {
		return err
	}
	labels, releases := indexes[termLabels], indexes[termReleases]
	edges := map[string][]string{}
	produced := map[string]bool{}
	for _, derivation := range indexes[termDerivations] {
		if err := flowDerivationEdge(derivation, labels, produced, edges); err != nil {
			return err
		}
	}
	for _, release := range releases {
		if err := flowReleaseEdge(release, labels, produced, edges); err != nil {
			return err
		}
	}
	if graph.HasCycle(edges) {
		return invalid()
	}
	for _, decision := range indexes[termSinkDecisions] {
		if err := flowSinkLocal(decision, labels, releases); err != nil {
			return err
		}
	}
	for _, binding := range indexes[termBindings] {
		if err := flowBindingTarget(binding, indexes); err != nil {
			return err
		}
	}
	return nil
}

func flowBindingTarget(v any, indexes map[string]map[string]any) error {
	field := map[string]string{"label": termLabels, "derivation": termDerivations, "release": termReleases, termSinkDecision: termSinkDecisions}[stringAt(v, "relation_target", "target_kind")]
	target := indexes[field][stringAt(v, "relation_target", "target_ref")]
	if target == nil || !equal(at(v, "policy"), at(target, "policy")) {
		return invalid()
	}
	if field != termLabels {
		return nil
	}
	if !equal(at(v, "target_participant_address"), at(target, "subject", "participant_address")) || !equal(at(v, "target_episode_id"), at(target, "subject", "episode_id")) {
		return invalid()
	}
	source := stringAt(v, "event_id")
	switch stringAt(v, termKind) {
	case "runtime-fact":
		source = stringAt(v, "fact_version_ref")
	case "action-argument":
		source = stringAt(v, "proposal_ref") + ":" + stringAt(v, "normalized_argument_name")
	}
	return require(set(at(target, "influence_refs"))[source])
}

func flowSinkLocal(v any, labels, releases map[string]any) error {
	label := labels[stringAt(v, "label_ref")]
	if label == nil || !equal(at(label, "subject"), at(v, "subject")) || !equal(at(label, "policy"), at(v, "policy")) {
		return invalid()
	}
	var prior any
	for _, ref := range stringsOf(at(v, "release_refs")) {
		release := releases[ref]
		if release == nil || !matchingFields(release, at(v, "sink"), "sink_ref", "destination_ref", "audience_scope_ref") || prior != nil && !equal(at(prior, "result_label_ref"), at(release, "source_label_ref")) {
			return invalid()
		}
		prior = release
	}
	return require(prior == nil || equal(at(prior, "result_label_ref"), at(v, "label_ref")))
}

func flowDerivationEdge(derivation any, labels map[string]any, produced map[string]bool, edges map[string][]string) error {
	if err := flowDerivation(derivation, labels); err != nil {
		return err
	}
	key := flowSubjectKey(at(derivation, "result_subject"))
	if produced[key] {
		return invalid()
	}
	produced[key] = true
	for _, input := range array(at(derivation, "inputs")) {
		edges[flowSubjectKey(at(input, "subject"))] = append(edges[flowSubjectKey(at(input, "subject"))], key)
	}
	return nil
}

func flowReleaseEdge(release any, labels map[string]any, produced map[string]bool, edges map[string][]string) error {
	if err := flowRelease(release, labels); err != nil {
		return err
	}
	key := flowSubjectKey(at(release, "result_subject"))
	if produced[key] {
		return invalid()
	}
	produced[key] = true
	source := flowSubjectKey(at(release, "source_subject"))
	edges[source] = append(edges[source], key)
	return nil
}

func flowIndexes(v any) (map[string]map[string]any, error) {
	indexes := map[string]map[string]any{}
	for field, id := range map[string]string{termLabels: "label_id", termDerivations: "derivation_id", termReleases: "release_id", termSinkDecisions: termDecisionID, termBindings: termBindingID} {
		rows := array(at(v, field))
		indexes[field] = controlRows(rows, id)
		if len(indexes[field]) != len(rows) {
			return nil, invalid()
		}
		for _, row := range rows {
			if !equal(at(row, "profile"), at(v, "profile")) {
				return nil, invalid()
			}
		}
	}

	return indexes, nil
}

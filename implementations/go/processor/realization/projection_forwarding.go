package realization

import (
	"maps"
	"slices"
	"strings"
)

const termTransforms = "transforms"

func withoutAnnotations(record map[string]any) map[string]any {
	result := maps.Clone(record)
	for _, field := range []string{termDescription, termEvidenceRefs, termReadiness} {
		delete(result, field)
	}
	return result
}
func projectNestedRecords(value any, identity string, recursive bool) ([]any, error) {
	items, ok := value.([]any)
	if !ok {
		return nil, invalidRealization()
	}
	result := make([]any, 0, len(items))
	for _, item := range items {
		record, ok := item.(map[string]any)
		if !ok {
			return nil, invalidRealization()
		}
		result = append(result, withoutAnnotations(record))
	}
	if !recursive {
		slices.SortStableFunc(result, func(a, b any) int {
			l, _ := scalarSortText(fieldDefault(ownedProjection[map[string]any](a), identity, ""))
			r, _ := scalarSortText(fieldDefault(ownedProjection[map[string]any](b), identity, ""))
			return strings.Compare(l, r)
		})
	}
	return result, nil
}

func projectForwarding(value any, observed, recursive bool) ([]any, error) {
	items, ok := value.([]any)
	if !ok {
		return nil, invalidRealization()
	}
	result := make([]any, 0, len(items))
	for _, item := range items {
		record, ok := item.(map[string]any)
		if !ok {
			return nil, invalidRealization()
		}
		agent, err := projectForwardingAgent(record, observed, recursive)
		if err != nil {
			return nil, err
		}
		result = append(result, agent)
	}
	if !recursive {
		slices.SortStableFunc(result, func(a, b any) int {
			return strings.Compare(ownedProjection[string](ownedProjection[map[string]any](a)["forwarding_agent_id"]), ownedProjection[string](ownedProjection[map[string]any](b)["forwarding_agent_id"]))
		})
	}
	return result, nil
}
func projectForwardingAgent(record map[string]any, observed, recursive bool) (map[string]any, error) {
	id, ok := record["forwarding_agent_id"].(string)
	if !ok || id == "" {
		return nil, invalidRealization()
	}
	agent := withoutAnnotations(record)
	delete(agent, "ownership_role")
	for _, group := range []struct{ field, identity string }{{termSources, "source_id"}, {termTransforms, "transform_id"}, {termShipTargets, "target_id"}, {termReloadChannels, "reload_channel_id"}} {
		entries, err := projectNestedRecords(fieldDefault(record, group.field, []any{}), group.identity, recursive)
		if err != nil {
			return nil, err
		}
		agent[group.field] = entries
	}
	settings, err := projectForwardingSettings(fieldDefault(record, "settings", []any{}), id, observed, recursive)
	if err != nil {
		return nil, err
	}
	agent["settings"] = settings
	agent["buffer_policy"] = nil
	if buffer := record["buffer_policy"]; buffer != nil {
		row, ok := buffer.(map[string]any)
		if !ok {
			return nil, invalidRealization()
		}
		agent["buffer_policy"] = withoutAnnotations(row)
	}
	return agent, nil
}
func projectForwardingSettings(value any, agentID string, observed, recursive bool) ([]any, error) {
	settings, ok := value.([]any)
	if !ok {
		return nil, invalidRealization()
	}
	projected := make([]any, 0, len(settings))
	for _, item := range settings {
		setting, ok := item.(map[string]any)
		if !ok {
			return nil, invalidRealization()
		}
		entry, err := projectForwardingSetting(setting, agentID, observed)
		if err != nil {
			return nil, err
		}
		projected = append(projected, entry)
	}
	if !recursive {
		slices.SortStableFunc(projected, func(a, b any) int {
			return strings.Compare(ownedProjection[string](ownedProjection[map[string]any](a)[termSettingID]), ownedProjection[string](ownedProjection[map[string]any](b)[termSettingID]))
		})
	}
	return projected, nil
}
func projectForwardingSetting(setting map[string]any, agentID string, observed bool) (map[string]any, error) {
	id, ok := setting[termSettingID].(string)
	if !ok || id == "" {
		return nil, invalidRealization()
	}
	entry := map[string]any{termSettingID: id, termName: fieldDefault(setting, termName, ""), termProvenance: fieldDefault(setting, termProvenance, termUnknown), termClassification: fieldDefault(setting, termClassification, "plain")}
	commitment, err := committedValue(setting, termForwardingAgents, agentID+":"+id, termClassification, observed)
	if err != nil {
		return nil, err
	}
	maps.Copy(entry, commitment)
	return entry, nil
}
func validateForwardingObservation(value any) error {
	items, ok := value.([]any)
	if !ok {
		return invalidRealization()
	}
	for _, item := range items {
		record, ok := item.(map[string]any)
		if !ok {
			return invalidRealization()
		}
		restored, err := restoreForwardingSettings(fieldDefault(record, "settings", []any{}))
		if err != nil {
			return err
		}
		candidate := maps.Clone(record)
		candidate["settings"] = restored
		if _, err := normalizeConcernValue(termForwardingAgents, []any{candidate}); err != nil {
			return err
		}
	}
	return nil
}
func restoreForwardingSettings(value any) ([]any, error) {
	settings, ok := value.([]any)
	if !ok {
		return nil, invalidRealization()
	}
	restored := make([]any, 0, len(settings))
	for _, item := range settings {
		setting, ok := item.(map[string]any)
		if !ok {
			return nil, invalidRealization()
		}
		entry, err := restoreCommittedRecord(setting, []string{termSettingID, termName, termProvenance, termClassification}, termClassification)
		if err != nil {
			return nil, err
		}
		restored = append(restored, entry)
	}
	return restored, nil
}

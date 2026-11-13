package realization

import (
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func projectionDigest(value any) (string, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return "", invalidRealization()
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return "", invalidRealization()
	}
	return digest.SHA256(canonical), nil
}
func sortProjectionRecords(records []any) error {
	type keyed struct {
		value  any
		digest string
	}
	ordered := make([]keyed, len(records))
	for i, record := range records {
		digest, err := projectionDigest(record)
		if err != nil {
			return err
		}
		ordered[i] = keyed{record, digest}
	}
	slices.SortStableFunc(ordered, func(a, b keyed) int { return strings.Compare(a.digest, b.digest) })
	for i, record := range ordered {
		records[i] = record.value
	}
	return nil
}

func sharedProcessProjection(value any, limit bool) (map[string]any, error) {
	owner, err := realizationOwner()
	if err != nil {
		return nil, err
	}
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, value, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
	if err != nil {
		return nil, err
	}
	var projection admission.Fragment
	if limit {
		projection, err = admission.ProjectProcessResourceLimit(owner, fragment)
	} else {
		projection, err = admission.ProjectProcessIdentity(owner, fragment)
	}
	if err != nil {
		return nil, err
	}
	result, ok := projection.Document().(map[string]any)
	if !ok {
		return nil, invalidRealization()
	}
	return result, nil
}

func projectProcessLimits(value any, observed, recursive bool) ([]any, error) {
	items, ok := value.([]any)
	if !ok {
		return nil, invalidRealization()
	}
	result := make([]any, 0, len(items))
	for _, item := range items {
		entry, err := projectProcessLimit(item, observed, recursive)
		if err != nil {
			return nil, err
		}
		result = append(result, entry)
	}
	if !recursive {
		if err := sortProjectionRecords(result); err != nil {
			return nil, err
		}
	}
	return result, nil
}

func projectProcessLimit(item any, observed, recursive bool) (map[string]any, error) {
	normalized, err := normalizeConcernValue(termProcessResourceLimits, []any{item})
	if err != nil {
		return nil, err
	}
	row := ownedProjection[map[string]any](ownedProjection[[]any](normalized)[0])
	if observed {
		if checkErr := checkObservedProcessBounds(row); checkErr != nil {
			return nil, checkErr
		}
	}
	entry, err := sharedProcessProjection(row, true)
	if err != nil {
		return nil, err
	}
	identity := map[string]any{termResource: entry[termResource], termSubject: entry[termSubject], termScope: entry[termScope]}
	if recursive {
		identityDigest, err := projectionDigest(identity)
		if err != nil {
			return nil, err
		}
		entry[termIdentityMarker] = identityDigest
	}
	return entry, nil
}

func checkObservedProcessBounds(row map[string]any) error {
	for _, field := range []string{termSoft, termHard} {
		if text, ok := row[field].(string); ok && strings.HasPrefix(text, "${") && strings.HasSuffix(text, "}") {
			return invalidRealization()
		}
	}
	return nil
}

func sortedScalarStrings(value any, recursive bool) ([]any, error) {
	items, err := stringSequence(value)
	if err != nil {
		return nil, err
	}
	if recursive {
		return scalarSet(items), nil
	}
	slices.SortStableFunc(items, func(a, b any) int { return strings.Compare(ownedProjection[string](a), ownedProjection[string](b)) })
	return items, nil
}

func projectCapabilities(value any, recursive bool) (map[string]any, error) {
	record, ok := value.(map[string]any)
	if !ok {
		return nil, invalidRealization()
	}
	result := map[string]any{}
	for _, field := range []string{termRequired, termEffective, termAdd, termDrop} {
		items, err := sortedScalarStrings(fieldDefault(record, field, []any{}), recursive)
		if err != nil {
			return nil, err
		}
		result[field] = items
	}
	overrides, err := projectCapabilityOverrides(fieldDefault(record, "process_overrides", []any{}), recursive)
	if err != nil {
		return nil, err
	}
	result["process_overrides"] = overrides
	return result, nil
}
func projectCapabilityOverrides(value any, recursive bool) ([]any, error) {
	overrides, ok := value.([]any)
	if !ok {
		return nil, invalidRealization()
	}
	projected := make([]any, 0, len(overrides))
	for _, item := range overrides {
		override, ok := item.(map[string]any)
		if !ok {
			return nil, invalidRealization()
		}
		entry, err := projectCapabilityOverride(override, recursive)
		if err != nil {
			return nil, err
		}
		projected = append(projected, entry)
	}
	if !recursive {
		if err := sortProjectionRecords(projected); err != nil {
			return nil, err
		}
	}
	return projected, nil
}
func projectCapabilityOverride(override map[string]any, recursive bool) (map[string]any, error) {
	subject, err := projectCapabilitySubject(override[termSubject])
	if err != nil {
		return nil, err
	}
	entry := map[string]any{termSubject: subject, termScope: fieldDefault(override, termScope, "process")}
	for _, field := range []string{termEffective, termAdd, termDrop} {
		items, err := sortedScalarStrings(fieldDefault(override, field, []any{}), recursive)
		if err != nil {
			return nil, err
		}
		entry[field] = items
	}
	if recursive {
		identity, err := projectionDigest(subject)
		if err != nil {
			return nil, err
		}
		entry[termIdentityMarker] = identity
	}
	return entry, nil
}
func projectCapabilitySubject(value any) (map[string]any, error) {
	// Only subject construction belongs to the SDL type at this seam.
	normalized, err := normalizeConcernValue("runtime-processes", []any{value})
	if err != nil {
		return nil, err
	}
	rows, ok := normalized.([]any)
	if !ok || len(rows) != 1 {
		return nil, invalidRealization()
	}
	subject, ok := rows[0].(map[string]any)
	if !ok {
		return nil, invalidRealization()
	}
	projected, err := sharedProcessProjection(subject, false)
	if err != nil {
		return nil, err
	}
	if projected["command_redacted"] == true {
		projected["command"] = []any{}
	}
	return projected, nil
}

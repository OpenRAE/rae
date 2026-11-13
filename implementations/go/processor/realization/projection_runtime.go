package realization

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/pyrepr"
)

func runtimeLocalIdentity(record map[string]any) string {
	keys := []string{}
	for key := range record {
		if strings.HasSuffix(key, "_id") {
			keys = append(keys, key)
		}
	}
	slices.Sort(keys)
	keys = append(keys, "path", termTarget, termName, "username", "unit_name", termNetwork)
	for _, key := range keys {
		switch item := record[key].(type) {
		case string:
			if item != "" {
				return key + ":" + item
			}
		case json.Number:
			if !strings.ContainsAny(string(item), ".eE") {
				return key + ":" + string(item)
			}
		case bool:
			text, _ := scalarSortText(item)
			return key + ":" + text
		}
	}
	return ""
}

func hasSensitiveValue(value any) bool {
	if emptySensitive(value) {
		return false
	}
	if items, ok := value.([]any); ok && len(items) == 0 {
		return false
	}
	return true
}
func projectSensitiveField(record map[string]any, field string, classification any, kind, identity string, observed bool) (map[string]any, error) {
	var fallback any = ""
	if field == termValues {
		fallback = []any{}
	}
	raw := fieldDefault(record, field, fallback)
	protected, err := protectedClassification(classification)
	if err != nil {
		return nil, err
	}
	if (protected || observed && classification == "secret_fixture") && hasSensitiveValue(raw) {
		return nil, invalidRealization()
	}
	presenceKey, commitmentKey := field+"_present", field+"_commitment"
	if commitment := record[commitmentKey]; commitment != nil {
		if hasSensitiveValue(raw) || !validCommitment(commitment) {
			return nil, invalidRealization()
		}
		return map[string]any{presenceKey: true, commitmentKey: commitment}, nil
	}
	if presenceErr := checkSensitivePresence(record, field, observed, protected); presenceErr != nil {
		return nil, presenceErr
	}

	if !hasSensitiveValue(raw) {
		return map[string]any{presenceKey: protected}, nil
	}
	commitment, err := valueCommitment(kind, identity, raw)
	if err != nil {
		return nil, err
	}
	return map[string]any{presenceKey: true, commitmentKey: commitment}, nil
}

func checkSensitivePresence(record map[string]any, field string, observed, protected bool) error {
	presence, supplied := record[field+"_present"]
	if observed && protected && !supplied {
		return invalidRealization()
	}
	if supplied {
		actual, ok := presence.(bool)
		if !ok || actual != protected {
			return invalidRealization()
		}
	}
	return nil
}

type runtimeProjector struct {
	kind                string
	excluded            []string
	observed, recursive bool
}

func projectRuntimeValue(value any, kind string, excluded []string, observed, recursive bool, path []string) (any, error) {
	projector := runtimeProjector{kind: kind, excluded: excluded, observed: observed, recursive: recursive}
	return projector.project(value, path)
}
func (p runtimeProjector) project(value any, path []string) (any, error) {
	switch input := value.(type) {
	case map[string]any:
		return p.mapping(input, path)
	case []any:
		return p.sequence(input, path)
	default:
		return value, nil
	}
}
func runtimeSensitiveFields(input map[string]any) map[string]any {
	sensitive := map[string]any{}
	for _, field := range []struct {
		name    string
		classes []string
	}{
		{termValue, []string{termValueClassification, termClassification, "sensitivity"}},
		{termValues, []string{termValueClassification}},
		{termBindSource, []string{"bind_source_sensitivity"}},
	} {
		_, raw := input[field.name]
		_, marker := input[field.name+"_present"]
		if !raw && !marker {
			continue
		}
		for _, class := range field.classes {
			if classification, present := input[class]; present {
				sensitive[field.name] = classification
				break
			}
		}
	}
	return sensitive
}
func (p runtimeProjector) mapping(input map[string]any, path []string) (any, error) {
	semanticPath := slices.Clone(path)
	if local := runtimeLocalIdentity(input); local != "" {
		semanticPath = append(semanticPath, local)
	}
	sensitive := runtimeSensitiveFields(input)
	output := map[string]any{}
	for key, item := range input {
		if p.excludedField(key, sensitive) {
			continue
		}
		projected, err := p.project(item, append(slices.Clone(semanticPath), key))
		if err != nil {
			return nil, err
		}
		output[key] = projected
	}
	for _, field := range []string{termValue, termValues, termBindSource} {
		classification, present := sensitive[field]
		if !present {
			continue
		}
		projected, err := projectSensitiveField(input, field, classification, p.kind, strings.Join(semanticPath, ":"), p.observed)
		if err != nil {
			return nil, err
		}
		maps.Copy(output, projected)
	}
	return output, nil
}
func (p runtimeProjector) excludedField(key string, sensitive map[string]any) bool {
	if slices.Contains(p.excluded, key) {
		return true
	}
	if _, present := sensitive[key]; present {
		return true
	}
	base := strings.TrimSuffix(strings.TrimSuffix(key, "_present"), "_commitment")
	_, marker := sensitive[base]
	return marker && base != key
}
func (p runtimeProjector) sequence(input []any, path []string) (any, error) {
	output := make([]any, len(input))
	records := len(input) > 0
	for i, item := range input {
		projected, err := p.project(item, path)
		if err != nil {
			return nil, err
		}
		output[i] = projected
		if _, ok := projected.(map[string]any); !ok {
			records = false
		}
	}
	if !p.recursive && records {
		if err := sortRuntimeRecords(output); err != nil {
			return nil, err
		}
	}
	return output, nil
}
func sortRuntimeRecords(output []any) error {
	type keyed struct {
		record           any
		identity, digest string
	}
	ordered := make([]keyed, len(output))
	for i, item := range output {
		hash, err := projectionDigest(item)
		if err != nil {
			return err
		}
		ordered[i] = keyed{item, runtimeLocalIdentity(ownedProjection[map[string]any](item)), hash}
	}
	slices.SortStableFunc(ordered, func(a, b keyed) int {
		if order := strings.Compare(a.identity, b.identity); order != 0 {
			return order
		}
		return strings.Compare(a.digest, b.digest)
	})
	for i, item := range ordered {
		output[i] = item.record
	}
	return nil
}

func projectTypedRuntime(kind string, value any, observed, recursive bool) (any, error) {
	return projectTypedRuntimeOptions(kind, value, observed, recursive, recursive)
}

func projectTypedRuntimeOptions(kind string, value any, observed, recursive, scalarIdentities bool) (any, error) {
	definition, present := concernDefinitionFor(kind)
	if !present {
		return nil, invalidRealization()
	}
	restored, err := restoreRuntimeMarkers(value)
	if err != nil {
		return nil, err
	}
	normalized, err := normalizeConcernValue(kind, restored)
	if err != nil {
		return nil, err
	}
	normalized, err = overlayRuntimeMarkers(normalized, value)
	if err != nil {
		return nil, err
	}
	if kind == "runtime-service-manager-units" {
		normalized, err = serviceManagerPresence(normalized, value)
		if err != nil {
			return nil, err
		}
	}
	projected, err := projectRuntimeValue(normalized, kind, definition.excluded, observed, recursive, nil)
	if err != nil {
		return nil, err
	}
	if definition.sortScalarSequence && !recursive {
		if err := sortTypedScalarSequence(projected); err != nil {
			return nil, err
		}
	}
	if kind == termRuntimeSoftwareComponents {
		if err := projectSoftwareRepositoryRefs(projected, scalarIdentities); err != nil {
			return nil, err
		}
	}

	return projected, nil
}

func sortTypedScalarSequence(projected any) error {
	items, ok := projected.([]any)
	if !ok {
		return invalidRealization()
	}
	for _, item := range items {
		if _, ok := item.(string); !ok {
			return invalidRealization()
		}
	}
	slices.SortStableFunc(items, func(a, b any) int {
		return strings.Compare(pythonStringRepr(ownedProjection[string](a)), pythonStringRepr(ownedProjection[string](b)))
	})
	return nil
}
func projectSoftwareRepositoryRefs(projected any, scalarIdentities bool) error {
	rows, ok := projected.([]any)
	if !ok {
		return invalidRealization()
	}
	for _, row := range rows {
		record := ownedProjection[map[string]any](row)
		refs, err := stringSequence(record["repository_refs"])
		if err != nil {
			return err
		}
		if scalarIdentities {
			record["repository_refs"] = scalarSet(refs)
			continue
		}
		slices.SortStableFunc(refs, func(a, b any) int { return strings.Compare(ownedProjection[string](a), ownedProjection[string](b)) })
		record["repository_refs"] = refs
	}
	return nil
}

func serviceManagerPresence(normalized, original any) (any, error) {
	rows, ok := normalized.([]any)
	input, sourceOK := original.([]any)
	if !ok || !sourceOK {
		return normalized, nil
	}
	if len(rows) != len(input) {
		return nil, invalidRealization()
	}
	output := make([]any, len(rows))
	for i, row := range rows {
		output[i] = serviceManagerRecord(row, input[i])
	}
	return output, nil
}

func serviceManagerRecord(row, original any) any {
	record, ok := row.(map[string]any)
	source, sourceOK := original.(map[string]any)
	if !ok || !sourceOK {
		return row
	}
	item := map[string]any{}
	for key, value := range record {
		if _, supplied := source[key]; supplied {
			item[key] = value
		}
	}
	manager, known := item["manager_kind"].(string)
	if known && manager != "systemd" && !strings.HasPrefix(manager, "${") {
		for _, field := range []string{"unit_type", "load_state", "active_state", "sub_state", "enabled_state", "result", "exit_code", "status_text", "main_pid", "exec_start"} {
			delete(item, field)
		}
	}
	return item
}

func pythonStringRepr(text string) string { return pyrepr.Quote(text) }

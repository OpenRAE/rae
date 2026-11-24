package authoring

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/sdlrules"
)

type selectedWrite struct {
	path  []string
	value any
}

func (m *semanticModel) selectionWrites(payload map[string]any, outcomes map[string]recordedOutcome) ([]selectedWrite, map[string]any, bool, error) {
	points := map[string]semanticVariation{}
	for _, point := range m.variations {
		points[point.name] = point
	}
	writes := []selectedWrite{}
	parameters := map[string]any{}
	structural := false
	for _, name := range slices.Sorted(maps.Keys(points)) {
		point, outcome := points[name], outcomes[name]
		resolved, err := m.pointWrites(payload, point, outcome)
		if err != nil {
			return nil, nil, false, err
		}
		if point.Target.Kind == termStructural {
			structural = true
		}
		if point.Target.Kind == termVariable {
			parameters[point.Target.Variable] = variationScalar(outcome.Value)
		}
		writes = append(writes, resolved...)
	}
	if err := checkSelectedWrites(writes); err != nil {
		return nil, nil, false, err
	}
	return writes, parameters, structural, nil
}

func (m *semanticModel) pointWrites(payload map[string]any, point semanticVariation, outcome recordedOutcome) ([]selectedWrite, error) {
	if point.Target.Kind == termVariable {
		return []selectedWrite{{[]string{variablesSection, point.Target.Variable}, variationScalar(outcome.Value)}}, nil
	}
	if point.Target.Kind == termStructural {
		return m.structuralWrites(payload, point, point.Alternatives[outcome.Member])
	}
	section, _, _ := strings.Cut(point.Target.Slot, ".")
	owner, err := m.selectedOwner(point.Target.Owner, section)
	if err != nil {
		return nil, err
	}
	path := []string{section, owner, selectionField(point.Target.Slot)}
	var value any
	switch point.Target.Kind {
	case termLogicalTiming:
		value = variationScalar(outcome.Value)
	case termReference:
		value = outcome.Reference
		if outcome.Kind == termMember {
			value = point.Alternatives[outcome.Member].Reference
		}
	case "collection":
		current := object(object(payload[section])[owner])[path[2]]
		value = selectedCollectionValue(current, point, outcome)

	default:
		return nil, selectionInvalid()
	}
	return []selectedWrite{{path, value}}, nil
}

func selectedCollectionValue(current any, point semanticVariation, outcome recordedOutcome) any {
	references := make([]any, len(outcome.Members))
	for i, member := range outcome.Members {
		references[i] = point.Members[member].Reference
	}
	mapping := object(current)
	if mapping == nil {
		return references
	}
	selected := map[string]any{}
	for _, reference := range references {
		key := text(reference)
		value, present := mapping[key]
		if !present {
			value = ""
		}
		selected[key] = value
	}
	return selected
}
func (m *semanticModel) structuralWrites(payload map[string]any, point semanticVariation, member semanticVariationMember) ([]selectedWrite, error) {
	slot := point.Target.Slot
	if slot == "nodes.runtime.network_detection_engines.rule_sources" {
		return m.childInventoryWrite(payload, point, member)
	}
	section, _, _ := strings.Cut(slot, ".")
	owner, err := m.selectedOwner(point.Target.Owner, section)
	if err != nil {
		return nil, err
	}
	switch member.Kind {
	case "declaration-presence":
		if member.Present == nil {
			return nil, selectionInvalid()
		}
		return []selectedWrite{{[]string{section, owner, termPresence}, *member.Present}}, nil
	case "resource-consumers":
		rows := array(object(object(payload[section])[owner])[termConsumers])
		selected := selectedConsumers(rows, member.Consumers)
		return []selectedWrite{{[]string{section, owner, termConsumers}, selected}}, nil
	case "node-presence":
		if member.Present == nil {
			return nil, selectionInvalid()
		}
		writes := []selectedWrite{{[]string{nodesSection, owner, termPresence}, *member.Present}}
		for _, inventory := range slices.Sorted(maps.Keys(member.Inventory)) {
			write, err := m.inventoryWrite(payload, owner, inventory, member.Inventory[inventory])
			if err != nil {
				return nil, err
			}
			writes = append(writes, write)
		}
		return writes, nil
	case "runtime-inventory":
		write, err := m.inventoryWrite(payload, owner, slot, member.References)
		if err != nil {
			return nil, err
		}
		return []selectedWrite{write}, nil
	default:
		return nil, selectionInvalid()
	}
}

func selectedConsumers(rows []any, selectors []semanticConsumerSelector) []any {
	selected := []any{}
	for _, raw := range rows {
		row := object(raw)
		identity := semanticConsumerSelector{Node: strings.TrimPrefix(text(row[termNode]), nodesPrefix), Mount: text(row["mount_destination"])}
		for _, selector := range selectors {
			selector.Node = strings.TrimPrefix(selector.Node, nodesPrefix)
			if identity == selector {
				selected = append(selected, row)
				break
			}
		}
	}
	return selected
}

func (m *semanticModel) inventoryWrite(payload map[string]any, owner, slot string, references []string) (selectedWrite, error) {
	collection := strings.TrimPrefix(slot, "nodes.runtime.")
	selected := map[string]bool{}
	for _, reference := range references {
		entry, exists := m.index.declarations[reference]
		if !exists || entry.node != owner || entry.kind != collection {
			return selectedWrite{}, selectionInvalid()
		}
		selected[reference] = true
	}
	rows := array(object(object(object(payload[nodesSection])[owner])[runtimeField])[collection])
	identity := ""
	for _, spec := range sdlrules.RuntimeFamilies() {
		if spec.Collection == collection {
			identity = spec.Identity
			break
		}
	}
	if identity == "" {
		return selectedWrite{}, selectionInvalid()
	}
	chosen := []any{}
	for _, row := range rows {
		address := "nodes." + owner + ".runtime." + collection + "." + text(object(row)[identity])
		if selected[address] {
			chosen = append(chosen, row)
		}
	}
	return selectedWrite{[]string{nodesSection, owner, runtimeField, collection}, chosen}, nil
}

func (m *semanticModel) childInventoryWrite(payload map[string]any, point semanticVariation, member semanticVariationMember) ([]selectedWrite, error) {
	var selected declaration
	count := 0
	for _, entry := range m.index.aliases[point.Target.Owner] {
		if entry.kind == termNetworkDetectionEngines && len(entry.tokens) == 6 {
			selected = entry
			count++
		}
	}
	if count != 1 {
		return nil, selectionInvalid()
	}
	path := selected.tokens[:len(selected.tokens)-1]
	record, present := provenancePointer(payload, jsonpointer.FromTokens(path))
	if !present {
		return nil, selectionInvalid()
	}
	addresses := map[string]bool{}
	for _, reference := range member.References {
		addresses[reference] = true
	}
	rows := []any{}
	parent := "nodes." + selected.node + ".runtime.network_detection_engines." + text(object(record)["network_detection_engine_id"])
	for _, row := range array(object(record)["rule_sources"]) {
		if addresses[parent+".rule_sources."+text(object(row)["source_id"])] {
			rows = append(rows, row)
		}
	}
	return []selectedWrite{{[]string{nodesSection, selected.node, runtimeField, termNetworkDetectionEngines, text(object(record)["network_detection_engine_id"]), "rule_sources"}, rows}}, nil
}

func checkSelectedWrites(writes []selectedWrite) error {
	fingerprints := map[string]string{}
	absent := map[string]bool{}
	for _, write := range writes {
		raw, err := json.Marshal(write.value)
		if err != nil {
			return selectionInvalid()
		}
		canonical, err := canonjson.JCS(raw)
		if err != nil {
			return selectionInvalid()
		}
		fingerprint := selectedValueKind(write.value) + ":" + string(canonical)
		path := jsonpointer.FromTokens(write.path)
		if prior, exists := fingerprints[path]; exists && prior != fingerprint {
			return selectionInvalid()
		}
		fingerprints[path] = fingerprint
		if len(write.path) == 3 && write.path[2] == termPresence && write.value == false {
			absent[jsonpointer.FromTokens(write.path[:2])] = true
		}
	}
	return checkSelectedWriteOverlap(writes, fingerprints, absent)
}
func checkSelectedWriteOverlap(writes []selectedWrite, fingerprints map[string]string, absent map[string]bool) error {
	for _, write := range writes {
		if len(write.path) >= 3 && absent[jsonpointer.FromTokens(write.path[:2])] && write.path[2] != termPresence {
			return selectionInvalid()
		}
		for length := 3; length < len(write.path); length++ {
			if _, exists := fingerprints[jsonpointer.FromTokens(write.path[:length])]; exists {
				return selectionInvalid()
			}
		}
	}
	return nil
}
func selectedValueKind(value any) string {
	switch value := value.(type) {
	case bool:
		return "boolean"
	case string:
		return "string"
	case json.Number:
		if strings.ContainsAny(value.String(), ".eE") {
			return numberType
		}
		return integerType
	case []any:
		return "array"
	case map[string]any:
		return termObject
	default:
		return "null"
	}
}

func applySelectedWrite(payload map[string]any, write selectedWrite) error {
	path := write.path
	if len(path) == 2 && path[0] == variablesSection {
		return nil
	}
	if len(path) < 3 {
		return selectionInvalid()
	}
	section, owner, field := path[0], path[1], path[2]
	if field == termPresence {
		if write.value == false {
			delete(object(payload[section]), owner)
			if section == nodesSection {
				delete(object(payload[infrastructureField]), owner)
			}
		}
		return nil
	}
	declaration := object(object(payload[section])[owner])
	if declaration == nil {
		return selectionInvalid()
	}
	if field != runtimeField {
		declaration[field] = write.value
		return nil
	}
	return applySelectedRuntimeWrite(declaration, path, write.value)
}
func applySelectedRuntimeWrite(declaration map[string]any, path []string, value any) error {
	runtime := object(declaration[runtimeField])
	if len(path) == 4 {
		runtime[path[3]] = value
		return nil
	}
	if len(path) == 6 {
		for _, row := range array(runtime[path[3]]) {
			if text(object(row)["network_detection_engine_id"]) == path[4] {
				object(row)[path[5]] = value
				return nil
			}
		}
	}
	return selectionInvalid()
}

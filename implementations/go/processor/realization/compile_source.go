package realization

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

// Source projections belong to this lowering boundary. No compiler or planner
// pass exchanges an untyped scenario tree through this record.
type realizationSource struct {
	scenario          sdl.InstantiatedScenario
	model             binding.InstantiatedScenarioV1
	sections          map[string]sourceDeclarations
	fieldOrder        map[string][]string
	explicitness      map[string]explicitnessRecord
	explicitnessPaths []string
	constraints       map[string]capabilityConstraint
}
type sourceDeclarations struct {
	names  []string
	values map[string]json.RawMessage
}

func (d *sourceDeclarations) UnmarshalJSON(raw []byte) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	token, err := decoder.Token()
	if err != nil || token != json.Delim('{') {
		return invalidRealization()
	}
	d.values = map[string]json.RawMessage{}
	for decoder.More() {
		key, checkErr := decoder.Token()
		if checkErr != nil {
			return checkErr
		}
		name := ownedProjection[string](key)
		var value json.RawMessage
		if decodeErr := decoder.Decode(&value); decodeErr != nil {
			return decodeErr
		}
		d.names = append(d.names, name)
		d.values[name] = value
	}
	_, err = decoder.Token()
	return err
}

type explicitnessRecord struct{ Path, Classification, Provenance string }
type capabilityConstraint struct {
	Pointer   string
	Parameter []string
	Values    []json.RawMessage
}

//nolint:ireturn // Each generated instantiation returns its concrete transport type without a runtime interface.
func sourceValue[T any](input binding.Field[T]) T { result, _ := input.Value(); return result }

func loadRealizationSource(scenario sdl.InstantiatedScenario) (*realizationSource, error) {
	raw, err := sdl.ModelBytes(scenario)
	if err != nil {
		return nil, err
	}
	result := &realizationSource{scenario: scenario, sections: map[string]sourceDeclarations{}, explicitness: map[string]explicitnessRecord{}, constraints: map[string]capabilityConstraint{}}
	result.fieldOrder, err = realizationFieldOrder(raw)
	if err != nil {
		return nil, invalidRealization()
	}
	if err := json.Unmarshal(raw, &result.model); err != nil {
		return nil, invalidRealization()
	}
	var sections map[string]json.RawMessage
	if err := json.Unmarshal(raw, &sections); err != nil {
		return nil, invalidRealization()
	}
	for _, section := range []string{termNodes, termContent, "generated_artifacts", "persistent_volumes", "features", "conditions", "injects", "events", "relationships", "identity_domains", "accounts"} {
		if value, present := sections[section]; present {
			var declarations sourceDeclarations
			if err := json.Unmarshal(value, &declarations); err != nil {
				return nil, invalidRealization()
			}
			result.sections[section] = declarations
		}
	}
	provenance := sourceValue(result.model.InstantiationProvenance)
	for _, record := range sourceValue(provenance.Explicitness) {
		path := sourceValue(record.ModelPath)
		result.explicitness[path] = explicitnessRecord{path, string(sourceValue(record.Classification)), string(sourceValue(record.Provenance))}
	}
	for _, record := range sourceValue(provenance.CapabilityConstraints) {
		pointer := sourceValue(record.FieldPointer)
		result.constraints[pointer] = capabilityConstraint{pointer, sourceValue(record.Parameter), sourceValue(record.AllowedValues)}
	}
	result.explicitnessPaths = slices.Sorted(maps.Keys(result.explicitness))
	return result, nil
}

func (s *realizationSource) resourceAddress(section, name string) (string, error) {
	kind := termContent
	if section == termNodes {
		kind = termNode
		if string(sourceValue(sourceValue(s.model.Nodes)[name].Type)) == termSwitch {
			kind = termNetwork
		}
	}
	return address.Render("provision", kind, name)
}
func sourceConcernValue(raw json.RawMessage, path []string) (any, error) {
	for _, token := range path {
		if len(raw) == 0 || bytes.Equal(raw, []byte("null")) {
			return nil, nil //nolint:nilnil // Absence is a valid optional result in this declared relation.
		}
		var fields map[string]json.RawMessage
		if err := json.Unmarshal(raw, &fields); err != nil {
			return nil, invalidRealization()
		}
		raw = fields[token]
	}
	if len(raw) == 0 {
		return nil, nil //nolint:nilnil // Absence is a valid optional result in this declared relation.
	}
	return nativeValue(raw)
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func (s *realizationSource) valueFragment(value any) (admission.Fragment, error) {
	return nativeValueFragment(value)
}
func explicitnessRank(classification string) int {
	switch classification {
	case termOpen:
		return 0
	case termConstrained:
		return 1
	default:
		return 2
	}
}

func pathWithin(parent, path string) bool {
	return path == parent || strings.HasPrefix(path, parent+".") || strings.HasPrefix(path, parent+"[")
}

func (s *realizationSource) semanticRecord(path string, excluded []string) *explicitnessRecord {
	// Search the admitted ordered index. Unrelated declarations do not require
	// repeated whole-scenario scans for each registered concern.
	candidates, parents := s.semanticRecordCandidates(path, excluded)
	var result *explicitnessRecord
	for name, record := range candidates {
		if parents[name] {
			continue
		}
		if result == nil {
			cloned := record
			result = &cloned
		} else {
			if explicitnessRank(record.Classification) < explicitnessRank(result.Classification) {
				result.Classification = record.Classification
			}
			if record.Provenance == termProcessorDerived {
				result.Provenance = record.Provenance
			}
		}
	}
	return result
}

func (s *realizationSource) semanticRecordCandidates(path string, excluded []string) (map[string]explicitnessRecord, map[string]bool) {
	candidates := map[string]explicitnessRecord{}
	parents := map[string]bool{}
	start, _ := slices.BinarySearch(s.explicitnessPaths, path)
	for _, name := range s.explicitnessPaths[start:] {
		if !strings.HasPrefix(name, path) {
			break
		}
		record := s.explicitness[name]
		if !pathWithin(path, name) {
			continue
		}
		if excludedSemanticPath(name[len(path):], excluded) {
			continue
		}

		candidates[name] = record
		for index := len(path); index < len(name); index++ {
			if name[index] == '.' || name[index] == '[' {
				parents[name[:index]] = true
			}
		}
	}
	return candidates, parents
}
func excludedSemanticPath(path string, excluded []string) bool {
	tokens := strings.FieldsFunc(path, func(r rune) bool { return r == '.' || r == '[' || r == ']' })
	for _, token := range tokens {
		if slices.Contains(excluded, token) {
			return true
		}
	}
	return false
}

package authoring

import (
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/concept"
)

type migrationBindings struct {
	bindings  any
	existing  []any
	snapshots []any
	resolved  []concept.SchemeSnapshot
}

func (p *Parser) migrationBinding(raw any) (any, error) {
	if raw == nil {
		return nil, nil //nolint:nilnil // Null represents valid absence in this operation contract.
	}
	encoded, err := json.Marshal(raw)
	if err != nil {
		return nil, err
	}
	value, err := p.models.Validate("external-concept-bindings-v1", encoded, modelLimits(encoded), nil)
	if err != nil {
		return nil, err
	}
	return ingress.Parse(value.JSON(), modelLimits(value.JSON()), ingress.Object)
}

func (p *Parser) migrationBindingContext(raw map[string]any) (migrationBindings, error) {
	result := migrationBindings{existing: []any{}, snapshots: []any{}, resolved: []concept.SchemeSnapshot{}}
	var err error
	result.bindings, err = p.migrationBinding(raw[termBindings])
	if err != nil {
		return result, err
	}
	for _, field := range []string{termExisting, termSnapshots} {
		if value, present := raw[field]; present {
			if _, ok := value.([]any); !ok {
				return result, invalid()
			}
		}
	}
	for _, value := range array(raw[termExisting]) {
		admitted, err := p.migrationBinding(value)
		if err != nil || admitted == nil {
			return result, invalid()
		}
		result.existing = append(result.existing, admitted)
	}
	for _, value := range array(raw[termSnapshots]) {
		normalized, snapshot, err := migrationSnapshot(value)
		if err != nil {
			return result, err
		}
		result.snapshots = append(result.snapshots, normalized)
		result.resolved = append(result.resolved, snapshot)
	}
	return result, nil
}

// Decode only the local wire representation. Concept admission remains with
// the existing authority and treats every locator as inert data.
func migrationSnapshot(raw any) (map[string]any, concept.SchemeSnapshot, error) {
	value := object(raw)
	if !closed(value, []string{"scheme_id", termAuthority, termRevision, "source_locator", termSourceDigest, "concepts"}, nil) {
		return nil, concept.SchemeSnapshot{}, invalid()
	}
	value = maps.Clone(value)
	for _, field := range []string{"scheme_id", termAuthority, termRevision, "source_locator", termSourceDigest} {
		if _, ok := value[field].(string); !ok {
			return nil, concept.SchemeSnapshot{}, invalid()
		}
	}
	terms, ok := value["concepts"].([]any)
	if !ok {
		return nil, concept.SchemeSnapshot{}, invalid()
	}
	snapshot := concept.SchemeSnapshot{SchemeID: text(value["scheme_id"]), Authority: text(value[termAuthority]), Revision: text(value[termRevision]), SourceLocator: text(value["source_locator"]), SourceDigest: text(value[termSourceDigest])}
	terms = slices.Clone(terms)
	for i, raw := range terms {
		term := object(raw)
		if !closed(term, []string{"concept_id"}, []string{termStatus, "successor_concept_ids"}) {
			return nil, snapshot, invalid()
		}
		term = maps.Clone(term)
		if _, present := term[termStatus]; !present {
			term[termStatus] = "current"
		}
		if _, present := term["successor_concept_ids"]; !present {
			term["successor_concept_ids"] = []any{}
		}
		var wire struct {
			ID         string   `json:"concept_id"`
			Status     string   `json:"status"`
			Successors []string `json:"successor_concept_ids"`
		}
		encoded, err := json.Marshal(term)
		if err != nil || json.Unmarshal(encoded, &wire) != nil {
			return nil, snapshot, invalid()
		}
		snapshot.Concepts = append(snapshot.Concepts, concept.SnapshotTerm{ConceptID: wire.ID, Status: wire.Status, SuccessorConceptIDs: wire.Successors})
		terms[i] = term
	}
	value["concepts"] = terms
	return value, snapshot, nil
}

func bindingJSON(documents []any) ([]json.RawMessage, error) {
	result := []json.RawMessage{}
	for _, value := range documents {
		encoded, err := json.Marshal(value)
		if err != nil {
			return nil, err
		}
		result = append(result, encoded)
	}
	return result, nil
}

package realization

import (
	"bytes"
	"encoding/json"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type softwareRefinement struct {
	ID         string                            `json:"refinement_id"`
	Purpose    string                            `json:"purpose"`
	Definition binding.DomainProfileDefinitionV1 `json:"definition"`
	Value      json.RawMessage                   `json:"profile_value"`
}
type refinedSoftwareItem struct {
	ComponentID  string               `json:"component_id"`
	RepositoryID string               `json:"repository_id"`
	TrustID      string               `json:"trust_id"`
	Refinements  []softwareRefinement `json:"refinements"`
}
type softwareAttachment struct {
	node, identity, pointer string
	refinement              softwareRefinement
}

func softwareAttachments(model binding.InstantiatedScenarioV1, order map[string][]string) ([]softwareAttachment, error) {
	result := []softwareAttachment{}
	nodes := sourceValue(model.Nodes)
	for _, name := range order["/nodes"] {
		var runtime struct {
			Components      []refinedSoftwareItem `json:"software_components"`
			RepositoryState *struct {
				Repositories []refinedSoftwareItem `json:"repositories"`
				Trusts       []refinedSoftwareItem `json:"trust_bindings"`
			} `json:"repository_state"`
		}
		if raw := sourceValue(nodes[name].Runtime); len(raw) > 0 && json.Unmarshal(raw, &runtime) != nil {
			return nil, invalidRealization()
		}
		groups := []struct {
			path, field string
			items       []refinedSoftwareItem
		}{{termSoftwareComponents, "component_id", runtime.Components}}
		if runtime.RepositoryState != nil {
			groups = append(groups, struct {
				path, field string
				items       []refinedSoftwareItem
			}{"repository_state/repositories", termRepositoryID, runtime.RepositoryState.Repositories}, struct {
				path, field string
				items       []refinedSoftwareItem
			}{"repository_state/trust_bindings", termTrustID, runtime.RepositoryState.Trusts})
		}
		for _, group := range groups {
			for index, item := range group.items {
				identity := item.identity(group.field)
				for refinementIndex, refinement := range item.Refinements {
					pointer := "/nodes/" + jsonpointer.EscapeToken(name) + "/runtime/" + group.path + "/" + strconv.Itoa(index) + "/refinements/" + strconv.Itoa(refinementIndex) + "/profile_value"
					result = append(result, softwareAttachment{node: name, identity: group.field + ":" + identity, pointer: pointer, refinement: refinement})
				}
			}
		}
	}
	return result, nil
}

func (item refinedSoftwareItem) identity(field string) string {
	switch field {
	case termRepositoryID:
		return item.RepositoryID
	case termTrustID:
		return item.TrustID
	default:
		return item.ComponentID
	}
}

// CompileSoftwareProfiles lowers explicit, bounded public refinements into
// the existing plan profile host. Definitions remain author-supplied data.
func CompileSoftwareProfiles(scenario sdl.Scenario, existing *binding.PlanRealizationProfilesV1) (*binding.PlanRealizationProfilesV1, error) {
	raw, err := sdl.ModelBytes(scenario)
	if err != nil {
		return nil, err
	}
	if _, concrete := scenario.(sdl.InstantiatedScenario); !concrete {
		var phase struct {
			Materialization json.RawMessage `json:"materialization_provenance"`
		}
		if json.Unmarshal(raw, &phase) != nil || len(phase.Materialization) == 0 || bytes.Equal(phase.Materialization, []byte("null")) {
			return nil, invalidRealization()
		}
	}
	var model binding.InstantiatedScenarioV1
	if json.Unmarshal(raw, &model) != nil {
		return nil, invalidRealization()
	}
	order, err := realizationFieldOrder(raw)
	if err != nil {
		return nil, err
	}
	attachments, err := softwareAttachments(model, order)
	if err != nil {
		return nil, err
	}
	owner, err := realizationOwner()
	if err != nil {
		return nil, err
	}
	baseline, err := admission.ResolvePlanProfileAuthority(owner, nil, existing, nil)
	if err != nil || len(attachments) == 0 {
		return baseline, err
	}
	assembly, err := newSoftwareProfileAssembly(scenario, owner, order, baseline)
	if err != nil {
		return nil, err
	}
	for _, attachment := range attachments {
		if err := assembly.include(attachment); err != nil {
			return nil, err
		}
	}
	return assembly.authority()
}

func softwareProfileProjection(input any) (map[string]any, error) {
	if admission.CheckTransport(input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return nil, invalidRealization()
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, invalidRealization()
	}
	projection, err := nativeValue(raw)
	if err != nil {
		return nil, err
	}
	return ownedProjection[map[string]any](projection), nil
}

func softwareProfileMetadata(scenario sdl.Scenario, sourcePointer string, input any, digest string, order map[string][]string) (admission.RealizationNormalizationMetadata, error) {
	pending := []softwareProfileValue{{value: input}}
	metadata := admission.RealizationNormalizationMetadata{Scopes: []admission.RealizationScope{}}
	for len(pending) > 0 {
		item := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		switch item.value.(type) {
		case map[string]any, []any:
		default:
			continue
		}
		closure, err := softwareProfileClosure(scenario, sourcePointer+item.pointer, digest)
		if err != nil {
			return metadata, err
		}
		metadata.Scopes = append(metadata.Scopes, admission.RealizationScope{FieldPointer: item.pointer, Closure: closure})
		pending, err = appendSoftwareProfileChildren(pending, item, sourcePointer, order)
		if err != nil {
			return metadata, err
		}
		if len(metadata.Scopes) > 4096 || len(pending) > 4096 {
			return metadata, invalidRealization()
		}
	}
	return metadata, nil
}

type softwareProfileValue struct {
	pointer string
	value   any
}

func softwareProfileClosure(scenario sdl.Scenario, pointer, digest string) (admission.RealizationClosure, error) {
	designation, err := sdl.ResolveRealizationDesignation(scenario, pointer)
	if err != nil {
		return admission.RealizationClosure{}, err
	}
	demand := ownedProjection[map[string]any](designation.Document())
	if demand["delegated"] == true {
		return admission.RealizationClosure{}, invalidRealization()
	}
	posture := termClosed
	if demand["closure"] == termOpenWorld {
		posture = termOpen
	}
	return admission.RealizationClosure{Posture: posture, Universe: "profile-value", Profile: digest}, nil
}
func appendSoftwareProfileChildren(pending []softwareProfileValue, item softwareProfileValue, sourcePointer string, order map[string][]string) ([]softwareProfileValue, error) {
	switch current := item.value.(type) {
	case map[string]any:
		keys := order[sourcePointer+item.pointer]
		if len(keys) != len(current) {
			return nil, invalidRealization()
		}
		for _, key := range keys {
			pending = append(pending, softwareProfileValue{pointer: item.pointer + "/" + jsonpointer.EscapeToken(key), value: current[key]})
		}
	case []any:
		for index, child := range current {
			pending = append(pending, softwareProfileValue{pointer: item.pointer + "/" + strconv.Itoa(index), value: child})
		}
	}
	return pending, nil
}

type softwareProfileAssembly struct {
	scenario                           sdl.Scenario
	owner                              *admission.Validator
	order                              map[string][]string
	definitions, bindings, constraints []any
	definitionIDs, bindingIDs          map[string]bool
}

func newSoftwareProfileAssembly(scenario sdl.Scenario, owner *admission.Validator, order map[string][]string, baseline *binding.PlanRealizationProfilesV1) (*softwareProfileAssembly, error) {
	assembly := softwareProfileAssembly{scenario: scenario, owner: owner, order: order, definitions: []any{}, bindings: []any{}, constraints: []any{}, definitionIDs: map[string]bool{}, bindingIDs: map[string]bool{}}
	if baseline != nil {
		prior, checkErr := softwareProfileProjection(baseline)
		if checkErr != nil {
			return nil, checkErr
		}
		assembly.definitions, assembly.bindings, assembly.constraints = ownedProjection[[]any](prior["definitions"]), ownedProjection[[]any](prior["bindings"]), ownedProjection[[]any](prior["constraints"])
	}
	for _, item := range assembly.definitions {
		definition := ownedProjection[map[string]any](ownedProjection[map[string]any](item)["definition"])
		assembly.definitionIDs[ownedProjection[string](ownedProjection[map[string]any](definition["coordinate"])["definition_digest"])] = true
	}
	for _, item := range assembly.bindings {
		id := ownedProjection[string](ownedProjection[map[string]any](item)["binding_id"])
		if assembly.bindingIDs[id] {
			return nil, invalidRealization()
		}
		assembly.bindingIDs[id] = true
	}
	return &assembly, nil
}
func (assembly *softwareProfileAssembly) include(attachment softwareAttachment) error {
	refinement := attachment.refinement
	coordinate := sourceValue(refinement.Definition.Coordinate)
	digest := sourceValue(coordinate.DefinitionDigest)
	if err := assembly.includeDefinition(refinement.Definition, digest); err != nil {
		return err
	}
	identity, checkErr := projectionDigest([]any{attachment.node, attachment.identity, refinement.ID})
	if checkErr != nil {
		return checkErr
	}
	id := "software-" + strings.TrimPrefix(identity, "sha256:")
	if assembly.bindingIDs[id] {
		return invalidRealization()
	}
	assembly.bindingIDs[id] = true
	profileValue, checkErr := assembly.includeBinding(attachment, id)
	if checkErr != nil {
		return checkErr
	}
	return assembly.includeConstraint(attachment, profileValue, digest, id)
}
func (assembly *softwareProfileAssembly) includeDefinition(definitionSource binding.DomainProfileDefinitionV1, digest string) error {
	if !assembly.definitionIDs[digest] {
		definition, checkErr := softwareProfileProjection(definitionSource)
		if checkErr != nil {
			return checkErr
		}
		assembly.definitionIDs[digest] = true
		assembly.definitions = append(assembly.definitions, map[string]any{"definition": definition, termProvenance: map[string]any{"source_locator": "urn:raes:authored-software-refinement", "source_digest": digest, "trust_decision_id": "author-constraint-only"}})
	}
	return nil
}
func (assembly *softwareProfileAssembly) includeBinding(attachment softwareAttachment, id string) (any, error) {
	refinement := attachment.refinement
	coordinate := sourceValue(refinement.Definition.Coordinate)
	compiledAddress, checkErr := address.Render("provision", termNode, attachment.node)
	if checkErr != nil {
		return nil, checkErr
	}
	profileValue, checkErr := nativeValue(refinement.Value)
	if checkErr != nil || value.Validate(profileValue, value.Default()) != nil {
		return nil, invalidRealization()
	}
	context, known := map[string]string{"acquisition": "artifact-acquisition", "version-correspondence": "software-version-correspondence", "repository-state": "software-repository-state", "repository-trust": "software-repository-trust"}[refinement.Purpose]
	if !known {
		return nil, invalidRealization()
	}
	coordinateRaw, checkErr := json.Marshal(coordinate)
	if checkErr != nil {
		return nil, invalidRealization()
	}
	coordinateValue, checkErr := nativeValue(coordinateRaw)
	if checkErr != nil {
		return nil, checkErr
	}
	assembly.bindings = append(assembly.bindings, map[string]any{termSchemaVersion: "domain-profile-binding/v1", "binding_id": id, "children": []any{}, "coordinate": coordinateValue, "owner": map[string]any{"owning_contract_id": realizationProfileContract, "canonical_address": "#/resources/" + compiledAddress, "concept_family": "resource-realization", "lifecycle_phase": "planning", "context": context, "use": "constraint"}, termValue: profileValue, termProvenance: map[string]any{"basis": "author-supplied", "source_ref": "software:" + attachment.identity + "/" + refinement.ID, termEvidenceRefs: []any{}}})
	return profileValue, nil
}
func (assembly *softwareProfileAssembly) includeConstraint(attachment softwareAttachment, profileValue any, digest, id string) error {
	metadata, checkErr := softwareProfileMetadata(assembly.scenario, attachment.pointer, profileValue, digest, assembly.order)
	if checkErr != nil {
		return checkErr
	}
	fragment, checkErr := admission.AdmitFragment(assembly.owner, admission.RealizationValue, profileValue, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 32})
	if checkErr != nil {
		return checkErr
	}
	normalized, checkErr := admission.NormalizeRealizationLiteral(fragment, digest, admission.RealizationClosure{}, metadata, admission.DefaultConstraintLimits())
	if checkErr != nil || normalized.Document == nil {
		return invalidRealization()
	}
	commitment, checkErr := admission.RealizationConstraintBinding(normalized.Document, fragment)
	if checkErr != nil {
		return checkErr
	}
	assembly.constraints = append(assembly.constraints, map[string]any{"binding_path": []any{id}, "document": normalized.Document.Document(), "source_binding": commitment})
	return nil
}
func (assembly *softwareProfileAssembly) authority() (*binding.PlanRealizationProfilesV1, error) {
	encoded, err := value.Encode(map[string]any{"contract_id": realizationProfileContract, "definitions": assembly.definitions, "bindings": assembly.bindings, "constraints": assembly.constraints}, value.Default())
	if err != nil || assembly.owner.CheckPortable(realizationProfileContract, encoded, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return nil, invalidRealization()
	}
	var result binding.PlanRealizationProfilesV1
	if json.Unmarshal(encoded, &result) != nil {
		return nil, invalidRealization()
	}
	return &result, nil
}

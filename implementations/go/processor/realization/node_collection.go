package realization

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

const portableNodeProfile = "raes/portable-node-membership/v1"

// NodeCollectionMember contains only portable identity, never a node recipe.
type NodeCollectionMember struct{ Address, Kind, Name string }

func nodeCollectionNamespaces(model binding.InstantiatedScenarioV1) map[string][]string {
	result := map[string][]string{"": {}}
	provenance := sourceValue(model.InstantiationProvenance)
	for _, record := range sourceValue(provenance.Imports) {
		namespace := sourceValue(record.Namespace)
		result[strings.Join(namespace, ".")] = namespace
	}
	for name := range sourceValue(model.Nodes) {
		parts := strings.Split(name, ".")
		prefix := parts[:len(parts)-1]
		result[strings.Join(prefix, ".")] = prefix
	}
	return result
}

func nodeCollectionProjection(members []NodeCollectionMember, namespaces []string) (map[string]any, error) {
	if len(members) > 65536 || len(namespaces) > 4096 {
		return nil, invalidRealization()
	}
	result := map[string]any{}
	for _, namespace := range namespaces {
		result[namespace] = []any{}
	}
	ordered := slices.Clone(members)
	slices.SortFunc(ordered, func(a, b NodeCollectionMember) int { return strings.Compare(a.Address, b.Address) })
	for _, member := range ordered {
		if member.Kind != termNode && member.Kind != termNetwork {
			continue
		}
		namespace := ""
		if at := strings.LastIndexByte(member.Name, '.'); at >= 0 {
			namespace = member.Name[:at]
		}
		collection, _ := result[namespace].([]any)
		result[namespace] = append(collection, map[string]any{termAddress: member.Address, "resource_type": member.Kind, termName: member.Name})
	}
	return result, nil
}

// CompileNodeCollection uses lexical enclosing authority. Child openness
// never grants additional members of the parent collection.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func CompileNodeCollection(scenario sdl.Scenario, members []NodeCollectionMember) (admission.Fragment, error) {
	raw, err := sdl.ModelBytes(scenario)
	if err != nil {
		return nil, err
	}
	if _, concrete := scenario.(sdl.InstantiatedScenario); !concrete {
		return nil, nil //nolint:nilnil // Absence is a valid optional result in this declared relation.
	}
	var model binding.InstantiatedScenarioV1
	if json.Unmarshal(raw, &model) != nil {
		return nil, invalidRealization()
	}
	namespaces := nodeCollectionNamespaces(model)
	keys := slices.Sorted(maps.Keys(namespaces))
	metadata, root, pending, err := nodeCollectionMetadata(scenario, namespaces, keys)
	if err != nil {
		return nil, err
	}
	if pending {
		return nil, nil //nolint:nilnil // Delegated enclosing authority has no node collection projection.
	}
	projection, err := nodeCollectionProjection(members, keys)
	if err != nil {
		return nil, err
	}
	input, err := nativeValueFragment(projection)
	if err != nil {
		return nil, err
	}
	closure := admission.RealizationClosure{Posture: termClosed, Universe: termPortableNode, Profile: portableNodeProfile}
	normalized, err := admission.NormalizeRealizationLiteral(input, portableNodeProfile, closure, metadata, admission.DefaultConstraintLimits())
	if err != nil || normalized.Document == nil {
		return nil, invalidRealization()
	}
	commitment, err := admission.RealizationConstraintBinding(normalized.Document, input)
	if err != nil {
		return nil, err
	}
	source := termLegacyDefault
	if root[termSource] == termScope {
		source = termAuthoredScope
	}
	owner, err := realizationOwner()
	if err != nil {
		return nil, err
	}
	return admission.AdmitFragment(owner, admission.PortableNodeCollectionAuthority, map[string]any{"scope_pointer": "/nodes", termSource: source, termGoverningScope: root[termGoverningScope], "constraint_document": normalized.Document.Document(), "constraint_binding": commitment}, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
}

func nodeCollectionMetadata(scenario sdl.Scenario, namespaces map[string][]string, keys []string) (admission.RealizationNormalizationMetadata, map[string]any, bool, error) {
	metadata := admission.RealizationNormalizationMetadata{CollectionProfiles: []admission.RealizationCollectionProfile{}}
	var root map[string]any
	for _, namespace := range keys {
		resolved, checkErr := sdl.ResolveRealizationDesignationForNamespace(scenario, "/nodes", namespaces[namespace])
		if checkErr != nil {
			return metadata, nil, false, checkErr
		}
		demand, valid := resolved.Document().(map[string]any)
		if !valid {
			return metadata, nil, false, invalidRealization()
		}
		if demand["delegated"] == true {
			return metadata, nil, true, nil
		}
		if namespace == "" {
			root = demand
		}
		posture := termClosed
		if demand["closure"] == termOpenWorld {
			posture = termOpen
		}
		metadata.CollectionProfiles = append(metadata.CollectionProfiles, admission.RealizationCollectionProfile{FieldPointer: jsonpointer.FromTokens([]string{namespace}), CollectionKind: termPortableNode, IdentityFields: []string{termAddress}, Closure: admission.RealizationClosure{Posture: posture, Universe: termPortableNode, Profile: portableNodeProfile}})
	}

	return metadata, root, false, nil
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func nativeValueFragment(input any) (admission.Fragment, error) {
	owner, err := realizationOwner()
	if err != nil {
		return nil, err
	}
	return admission.AdmitFragment(owner, admission.RealizationValue, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
}

// NodeCollectionAdmits checks the exact native authority through the shared
// recursive relation, including namespaces outside the submitted collection.
func NodeCollectionAdmits(authority admission.Fragment, members []NodeCollectionMember) (bool, error) {
	if admission.CheckFragment(authority, admission.PortableNodeCollectionAuthority) != nil {
		return false, invalidRealization()
	}
	document, valid := authority.Document().(map[string]any)
	if !valid {
		return false, invalidRealization()
	}
	constraintValue, valid := document["constraint_document"].(map[string]any)
	if !valid {
		return false, invalidRealization()
	}
	root, valid := constraintValue["root"].(map[string]any)
	if !valid {
		return false, invalidRealization()
	}
	fields, valid := root["fields"].(map[string]any)
	if !valid {
		return false, invalidRealization()
	}
	projection, err := nodeCollectionProjection(members, slices.Sorted(maps.Keys(fields)))
	if err != nil {
		return false, err
	}
	actual, err := nativeValueFragment(projection)
	if err != nil {
		return false, err
	}
	owner, err := realizationOwner()
	if err != nil {
		return false, err
	}
	constraint, err := admission.AdmitFragment(owner, admission.RealizationConstraint, constraintValue, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return false, err
	}
	result, err := admission.EvaluateRealizationConstraint(constraint, actual, admission.DefaultConstraintLimits())
	if err != nil {
		return false, err
	}
	status, valid := result.Document().(map[string]any)
	return valid && status["status"] == termConformant, nil
}

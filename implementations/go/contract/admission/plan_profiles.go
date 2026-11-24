package admission

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/profile"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

type planProfileNode struct {
	path  []string
	data  map[string]any
	order int
}

func planProfileTree(roots []any) (map[string]planProfileNode, error) {
	result := map[string]planProfileNode{}
	pending := make([]planProfileNode, 0, len(roots))
	for _, item := range roots {
		pending = append(pending, planProfileNode{data: object(item)})
	}
	for len(pending) > 0 {
		item := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		item.path = append(slices.Clone(item.path), stringAt(item.data, "binding_id"))
		key := jsonpointer.FromTokens(item.path)
		if item.data == nil || len(item.path) > 16 || len(result) >= 256 {
			return nil, fragmentInvalid()
		}
		if _, present := result[key]; present {
			return nil, fragmentInvalid()
		}
		item.order = len(result)
		result[key] = item
		children := array(at(item.data, "children"))
		if len(children) > 256-len(result)-len(pending) {
			return nil, fragmentInvalid()
		}
		for _, child := range children {
			pending = append(pending, planProfileNode{path: item.path, data: object(child)})
		}
	}
	return result, nil
}

func planProfileOrder(tree map[string]planProfileNode) []string {
	result := slices.Collect(maps.Keys(tree))
	slices.SortFunc(result, func(a, b string) int { return tree[a].order - tree[b].order })
	return result
}

func planProfileAddress(item any) (string, bool) {
	compiled, found := strings.CutPrefix(stringAt(item, "owner", "canonical_address"), "#/resources/")
	return compiled, found && address.Valid(compiled) && strings.HasPrefix(compiled, "provision.")
}

func planProfilePolicy() binding.DomainProfileAdmissionPolicyV1 {
	var policy binding.DomainProfileAdmissionPolicyV1
	_ = json.Unmarshal([]byte(`{"required_operations":["comparison","execution"]}`), &policy)
	return policy
}

func profileBindings(input any) ([]binding.DomainProfileBindingV1, error) {
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, fragmentInvalid()
	}
	var result []binding.DomainProfileBindingV1
	if json.Unmarshal(raw, &result) != nil {
		return nil, fragmentInvalid()
	}
	return result, nil
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func (e *Validator) profileFragment(profile FragmentProfile, input any) (Fragment, error) {
	return AdmitFragment(e, profile, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
}

// CheckPlanProfileAuthority checks complete pinned definitions, recursive
// source commitments, fixed core owners and independent target support.
func CheckPlanProfileAuthority(v *Validator, authority binding.PlanRealizationProfilesV1, context binding.DomainProfileResolutionContextV1) (bool, error) {
	if checkProfileValues(authority, context) != nil {
		return false, fragmentInvalid()
	}
	input, err := profileInput(v, planProfileContract, authority)
	if err != nil {
		return false, err
	}
	ctx, err := profileInput(v, profileContextContract, context)
	if err != nil {
		return false, err
	}
	tree, err := planProfileTree(array(at(input, termBindings)))
	if err != nil {
		return false, nil //nolint:nilerr // This relation reports candidate refusal in its result without failing the enclosing operation.
	}
	constraints, definitions, valid := profileAuthorityDocuments(input)
	if !valid {
		return false, nil
	}
	if len(tree) != len(constraints) {
		return false, nil
	}
	usedDefinitions := map[string]bool{}
	for key, item := range tree {
		constraint, present := constraints[key]
		if !present || !v.planProfileNodeValid(item, tree, constraint) {
			return false, nil
		}
		usedDefinitions[stringAt(item.data, "coordinate", "definition_digest")] = true
	}
	if !v.profileDefinitionsMatch(definitions, usedDefinitions, ctx) {
		return false, nil
	}
	bindings, err := profileBindings(at(input, termBindings))
	if err != nil {
		return false, err
	}
	return CheckDomainProfileBindings(v, bindings, context, planProfilePolicy())
}

func (e *Validator) planProfileNodeValid(item planProfileNode, tree map[string]planProfileNode, constraint any) bool {
	owner := at(item.data, "owner")
	compiled, valid := planProfileAddress(item.data)
	if !valid || stringAt(owner, "owning_contract_id") != planProfileContract || stringAt(owner, "concept_family") != "resource-realization" || stringAt(owner, "lifecycle_phase") != "planning" || stringAt(owner, "use") != termConstraint || stringAt(item.data, "provenance", termBasis) != "author-supplied" {
		return false
	}
	if len(item.path) > 1 {
		parent, present := tree[jsonpointer.FromTokens(item.path[:len(item.path)-1])]
		parentAddress, valid := planProfileAddress(parent.data)
		if !present || !valid || parentAddress != compiled {
			return false
		}
	}
	if stringAt(constraint, "document", termSemanticProfile) != stringAt(item.data, "coordinate", "definition_digest") {
		return false
	}
	document, err := e.profileFragment(RealizationConstraint, at(constraint, "document"))
	if err != nil {
		return false
	}
	source, err := e.profileFragment(RealizationValue, at(item.data, "value"))
	if err != nil {
		return false
	}
	commitment, err := RealizationConstraintBinding(document, source)
	return err == nil && commitment == stringAt(constraint, "source_binding")
}

// CheckPlanProfileSelection conjoins all nested constraints and keeps each
// selected binding's coordinate, owner and backend-selected provenance.
func CheckPlanProfileSelection(v *Validator, authority binding.PlanRealizationProfilesV1, selected []binding.DomainProfileBindingV1, context binding.DomainProfileResolutionContextV1) (bool, error) {
	if checkProfileValues(authority, selected, context) != nil {
		return false, fragmentInvalid()
	}
	admitted, err := CheckPlanProfileAuthority(v, authority, context)
	if err != nil || !admitted {
		return false, err
	}
	if len(selected) > 256 {
		return false, fragmentInvalid()
	}
	input, _ := profileInput(v, planProfileContract, authority)
	original, _ := planProfileTree(array(at(input, termBindings)))
	roots, err := v.profileRoots(selected)
	if err != nil {
		return false, err
	}
	tree, err := planProfileTree(roots)
	if err != nil || len(original) != len(tree) {
		return false, nil //nolint:nilerr // This relation reports candidate refusal in its result without failing the enclosing operation.
	}
	for _, constraint := range array(at(input, "constraints")) {
		key := jsonpointer.FromTokens(stringsOf(at(constraint, "binding_path")))
		before := original[key]
		after, present := tree[key]
		if !present {
			return false, nil
		}
		valid, err := v.profileSelectionConforms(before, after, constraint)
		if err != nil || !valid {
			return false, err
		}
	}
	return CheckDomainProfileBindings(v, selected, context, planProfilePolicy())
}

// ResolvePlanProfileAuthority preserves exact authored selections. Supplied
// authority must contain every authored binding and its exact source constraint.
func ResolvePlanProfileAuthority(v *Validator, authored []binding.DomainProfileBindingV1, supplied *binding.PlanRealizationProfilesV1, context *binding.DomainProfileResolutionContextV1) (*binding.PlanRealizationProfilesV1, error) {
	var suppliedInput map[string]any
	var err error
	if supplied != nil {
		suppliedInput, err = profileInput(v, planProfileContract, supplied)
		if err != nil {
			return nil, err
		}
	}
	if len(authored) == 0 {
		if supplied == nil {
			return nil, nil //nolint:nilnil // Absence is a valid optional result in this declared relation.
		}
		return profileAuthorityTransport(suppliedInput)
	}
	if len(authored) > 256 {
		return nil, fragmentInvalid()
	}
	if checkProfileValues(authored) != nil {
		return nil, fragmentInvalid()
	}
	roots, err := v.profileRoots(authored)
	if err != nil {
		return nil, err
	}
	tree, err := planProfileTree(roots)
	if err != nil {
		return nil, err
	}
	constraints, err := v.authoredProfileConstraints(tree)
	if err != nil {
		return nil, err
	}
	if supplied != nil {
		return v.mergeAuthoredProfileAuthority(suppliedInput, tree, constraints)
	}
	return v.authoredProfileAuthority(roots, tree, constraints, context)
}

func profileConstraintProjection(v *Validator, input any) (map[string]any, error) {
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, fragmentInvalid()
	}
	return v.low.DefaultedObjectFragment(planProfileContract, schemaDefinitionsPrefix+"ProfileBindingConstraint", raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
}

func profileAuthorityTransport(input any) (*binding.PlanRealizationProfilesV1, error) {
	raw, err := value.Encode(input, value.Default())
	if err != nil {
		return nil, fragmentInvalid()
	}
	var result binding.PlanRealizationProfilesV1
	if json.Unmarshal(raw, &result) != nil {
		return nil, fragmentInvalid()
	}
	return &result, nil
}

func profileAuthorityDocuments(input any) (map[string]any, map[string]any, bool) {
	constraints := map[string]any{}
	for _, constraint := range array(at(input, "constraints")) {
		key := jsonpointer.FromTokens(stringsOf(at(constraint, "binding_path")))
		if _, present := constraints[key]; present {
			return nil, nil, false
		}
		constraints[key] = constraint
	}
	definitions := map[string]any{}
	for _, definition := range array(at(input, "definitions")) {
		key := stringAt(definition, "definition", "coordinate", "definition_digest")
		if _, present := definitions[key]; present {
			return nil, nil, false
		}
		definitions[key] = at(definition, "definition")
	}
	return constraints, definitions, true
}

func (e *Validator) profileDefinitionsMatch(definitions map[string]any, usedDefinitions map[string]bool, ctx map[string]any) bool {
	if len(usedDefinitions) != len(definitions) {
		return false
	}
	contextBytes, err := json.Marshal(ctx)
	if err != nil {
		return false
	}
	for key := range usedDefinitions {
		definition, present := definitions[key]
		if !present {
			return false
		}
		coordinate := at(definition, "coordinate")
		resolved, err := e.owners.ResolveDomainProfile(profile.DomainCoordinate{Namespace: stringAt(coordinate, termNamespace), Authority: stringAt(coordinate, termAuthority), ProfileID: stringAt(coordinate, termProfileID), Revision: stringAt(coordinate, termRevision), DefinitionDigest: key}, contextBytes)
		if err != nil || resolved.Outcome != profile.Resolved {
			return false
		}
		actual, err := profileInput(e, "domain-profile-definition-v1", resolved.Definition)
		if err != nil || !equal(definition, actual) {
			return false
		}
	}
	return true
}

func (e *Validator) profileSelectionConforms(before, after planProfileNode, constraint any) (bool, error) {
	if !equal(at(before.data, "coordinate"), at(after.data, "coordinate")) || !equal(at(before.data, "owner"), at(after.data, "owner")) || stringAt(after.data, "provenance", termBasis) != termBackendSelected {
		return false, nil
	}
	document, err := e.profileFragment(RealizationConstraint, at(constraint, "document"))
	if err != nil {
		return false, err
	}
	actual, err := e.profileFragment(RealizationValue, at(after.data, "value"))
	if err != nil {
		return false, err
	}
	result, err := EvaluateRealizationConstraint(document, actual, DefaultConstraintLimits())
	if err != nil || stringAt(result.Document(), "status") != assuranceConformant {
		return false, err
	}
	return true, nil
}

func (e *Validator) authoredProfileConstraints(tree map[string]planProfileNode) ([]any, error) {
	constraints := []any{}
	for _, key := range planProfileOrder(tree) {
		item := tree[key]
		source, err := e.profileFragment(RealizationValue, at(item.data, "value"))
		if err != nil {
			return nil, err
		}
		normalized, err := NormalizeRealizationLiteral(source, stringAt(item.data, "coordinate", "definition_digest"), RealizationClosure{Posture: termClosed, Universe: "profile-value", Profile: "authored-profile-selection/v1"}, RealizationNormalizationMetadata{}, DefaultConstraintLimits())
		if err != nil || normalized.Document == nil {
			return nil, fragmentInvalid()
		}
		commitment, err := RealizationConstraintBinding(normalized.Document, source)
		if err != nil {
			return nil, err
		}
		path := make([]any, len(item.path))
		for i, component := range item.path {
			path[i] = component
		}
		constraints = append(constraints, map[string]any{"binding_path": path, "document": normalized.Document.Document(), "source_binding": commitment})
	}
	return constraints, nil
}

func (e *Validator) mergeAuthoredProfileAuthority(suppliedInput map[string]any, tree map[string]planProfileNode, constraints []any) (*binding.PlanRealizationProfilesV1, error) {
	existing, err := planProfileTree(array(at(suppliedInput, termBindings)))
	if err != nil {
		return nil, err
	}
	byPath := map[string]any{}
	for _, item := range array(at(suppliedInput, "constraints")) {
		key := jsonpointer.FromTokens(stringsOf(at(item, "binding_path")))
		if _, duplicate := byPath[key]; duplicate {
			return nil, fragmentInvalid()
		}
		byPath[key] = item
	}
	for i, key := range planProfileOrder(tree) {
		if !equal(tree[key].data, existing[key].data) {
			return nil, fragmentInvalid()
		}
		expected, err := profileConstraintProjection(e, constraints[i])
		if err != nil || !equal(expected, byPath[key]) {
			return nil, fragmentInvalid()
		}
	}
	return profileAuthorityTransport(suppliedInput)
}

func (e *Validator) authoredProfileAuthority(roots []any, tree map[string]planProfileNode, constraints []any, context *binding.DomainProfileResolutionContextV1) (*binding.PlanRealizationProfilesV1, error) {
	if context == nil {
		return nil, fragmentInvalid()
	}
	ctx, err := profileInput(e, profileContextContract, context)
	if err != nil {
		return nil, err
	}
	needed := map[string]bool{}
	for _, item := range tree {
		needed[stringAt(item.data, "coordinate", "definition_digest")] = true
	}
	definitions := []any{}
	for _, item := range array(at(ctx, "definitions")) {
		if needed[stringAt(item, "definition", "coordinate", "definition_digest")] {
			definitions = append(definitions, item)
		}
	}
	result, err := profileAuthorityTransport(map[string]any{termContractID: planProfileContract, termBindings: roots, "definitions": definitions, "constraints": constraints})
	if err != nil {
		return nil, err
	}
	if _, err := profileInput(e, planProfileContract, result); err != nil {
		return nil, err
	}
	return result, nil
}

func (e *Validator) profileRoots(bindings []binding.DomainProfileBindingV1) ([]any, error) {
	roots := make([]any, len(bindings))
	for i, item := range bindings {
		var err error
		roots[i], err = profileInput(e, "domain-profile-binding-v1", item)
		if err != nil {
			return nil, err
		}
	}
	return roots, nil
}

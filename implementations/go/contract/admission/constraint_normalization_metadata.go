package admission

import (
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

func (n *literalNormalizer) admitMetadata(profile string, closure RealizationClosure) (*RealizationConstraintBuildResult, error) {
	m := n.metadata
	if max(len(m.Scopes), len(m.CollectionProfiles), len(m.Origins), len(m.LeafConstraints), len(m.OptionalFields), len(m.MemberPresence)) > n.limits.MaxMembers {
		result := normalizationFailure("limit-exceeded", "", "Normalization metadata exceeded max_members.")
		return &result, nil
	}
	budget := constraintAdmission{limits: n.limits}
	if !budget.metadata(map[string]any{termSemanticProfile: profile, termDefaultClosure: normalizationClosure(closure)}) {
		n.fail("limit-exceeded", "", "Normalization metadata exceeded bounded work limits.")
	}
	for _, scope := range m.Scopes {
		if !budget.metadata(map[string]any{termFieldPointer: scope.FieldPointer, termClosure: normalizationClosure(scope.Closure), termOrigin: scope.Origin}) {
			n.fail("limit-exceeded", scope.FieldPointer, "Normalization metadata exceeded bounded work limits.")
			break
		}
	}
	if err := n.admitCollectionProfiles(&budget); err != nil {
		return nil, err
	}
	for pointer, origin := range m.Origins {
		if !budget.metadata(map[string]any{termFieldPointer: pointer, termOrigin: origin}) {
			n.fail("limit-exceeded", "", "Normalization metadata exceeded bounded work limits.")
			break
		}
	}
	for _, pointer := range m.OptionalFields {
		if !budget.metadata(pointer) {
			n.fail("limit-exceeded", "", "Normalization metadata exceeded bounded work limits.")
			break
		}
		n.optional[pointer] = true
	}
	n.admitMemberPresence(&budget)
	if err := n.admitLeafConstraints(&budget); err != nil {
		return nil, err
	}
	return n.failure, nil
}

func (n *literalNormalizer) admitCollectionProfiles(budget *constraintAdmission) error {
	for _, profile := range n.metadata.CollectionProfiles {
		if len(profile.IdentityFields) > n.limits.MaxMembers || !budget.metadata(map[string]any{termFieldPointer: profile.FieldPointer, termCollectionKind: profile.CollectionKind, termIdentityFields: stringInterfaces(profile.IdentityFields), termClosure: normalizationClosure(profile.Closure)}) {
			n.fail("limit-exceeded", "", "Normalization metadata exceeded bounded work limits.")
			break
		}
		if _, exists := n.profiles[profile.FieldPointer]; exists {
			n.fail("invalid", "", "Collection profiles must have unique field_pointer values.")
			break
		}
		if len(profile.FieldPointer) > 4096 || profile.FieldPointer != jsonpointer.FromTokens(jsonpointer.Tokens(profile.FieldPointer)) || profile.Closure.Posture != "open" && profile.Closure.Posture != termClosed {
			n.fail("invalid", "", "Collection profile metadata is invalid.")
			break
		}
		owner, err := normalizationOwner()
		if err != nil {
			return err
		}
		probe := map[string]any{termSemanticProfile: "normalization-metadata/v1", "root": map[string]any{termKind: termKeyedCollection, termCollectionKind: profile.CollectionKind, termIdentityFields: stringInterfaces(profile.IdentityFields), "members": []any{}, termClosure: normalizationClosure(profile.Closure)}}
		if _, err := AdmitFragment(owner, RealizationConstraint, probe, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}); err != nil {
			n.fail("invalid", "", "Collection profile metadata is invalid.")
			break
		}
		n.profiles[profile.FieldPointer] = profile
	}
	return nil
}

func (n *literalNormalizer) admitMemberPresence(budget *constraintAdmission) {
	for pointer, presence := range n.metadata.MemberPresence {
		if !budget.metadata(map[string]any{termFieldPointer: pointer, termPresence: presence}) {
			n.fail("limit-exceeded", "", "Normalization metadata exceeded bounded work limits.")
			break
		}
		if presence != termOptional && presence != requirementRequired && presence != termForbidden {
			n.fail("invalid", "", "Normalization presence is invalid.")
			break
		}
	}
}

func (n *literalNormalizer) admitLeafConstraints(budget *constraintAdmission) error {
	for pointer, leaf := range n.metadata.LeafConstraints {
		if err := CheckFragment(leaf, RealizationValue); err != nil {
			return err
		}
		if n.failure != nil {
			continue
		}
		if !budget.metadata(map[string]any{termFieldPointer: pointer, termConstraint: leaf.Document()}) {
			n.fail("limit-exceeded", "", "Leaf metadata exceeds its admitted value bounds.")
			break
		}
	}
	return nil
}

func stringInterfaces(input []string) []any {
	output := make([]any, len(input))
	for i, text := range input {
		output[i] = text
	}
	return output
}

func (n *literalNormalizer) scopes(source any) []any {
	output := make([]any, 0, len(n.metadata.Scopes))
	pointers := map[string]bool{}
	operations := 0
	for _, scope := range n.metadata.Scopes {
		semanticPointer := n.scopePointer(source, scope.FieldPointer, &operations)
		if n.failure != nil {
			return nil
		}
		if pointers[semanticPointer] {
			n.fail("invalid", "", "Scope normalization produced duplicate semantic member addresses.")
			return nil
		}
		pointers[semanticPointer] = true
		origin := scope.Origin
		if origin == "" {
			origin = termAuthor
		}
		output = append(output, map[string]any{termFieldPointer: semanticPointer, termClosure: normalizationClosure(scope.Closure), termOrigin: origin})
	}
	return output
}

func (n *literalNormalizer) scopePointer(source any, pointer string, operations *int) string {
	if pointer != jsonpointer.FromTokens(jsonpointer.Tokens(pointer)) {
		n.fail("invalid", "", "Scope pointers must use canonical JSON Pointer syntax.")
		return ""
	}
	semanticPointer, sourcePointer, current := "", "", source
	for _, token := range jsonpointer.Tokens(pointer) {
		*operations++
		if *operations > n.limits.MaxOperations {
			n.fail("limit-exceeded", pointer, "Scope normalization exceeded max_operations.")
			return ""
		}
		next, nextToken := n.scopeMember(current, sourcePointer, token, pointer)
		if n.failure != nil {
			return ""
		}
		current = next
		semanticPointer = pointerAppend(semanticPointer, nextToken)
		sourcePointer = pointerAppend(sourcePointer, token)
	}
	return semanticPointer
}

func (n *literalNormalizer) scopeMember(current any, sourcePointer, token, pointer string) (any, string) {
	if array, isArray := current.([]any); isArray {
		if profile, profiled := n.profiles[sourcePointer]; profiled {
			return n.profileScopeMember(array, profile, token, pointer)
		}
	}
	switch object := current.(type) {
	case map[string]any:
		return object[token], token
	case []any:
		if index, valid := normalizationIndex(token, len(object)); valid {
			return object[index], token
		}
	}
	return nil, token
}

func (n *literalNormalizer) profileScopeMember(array []any, profile RealizationCollectionProfile, token, pointer string) (any, string) {
	index, valid := normalizationIndex(token, len(array))
	if !valid {
		n.fail("invalid", pointer, "A keyed-collection scope must resolve an authored member position.")
		return nil, ""
	}
	if !n.identity(pointer) {
		return nil, ""
	}
	_, identity, valid := normalizationIdentity(array[index], profile.IdentityFields)
	if !valid {
		n.fail("invalid", pointer, "A keyed-collection scope resolves a member without concrete semantic identity.")
		return nil, ""
	}
	return array[index], "@" + identity
}

func normalizationIndex(token string, length int) (int, bool) {
	index, err := strconv.Atoi(token)
	return index, err == nil && index >= 0 && index < length && strconv.Itoa(index) == token
}

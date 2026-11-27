package admission

import (
	"regexp"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

// semanticPointer is the RFC 6901 pointer grammar of a semantic scope.
var semanticPointer = regexp.MustCompile(`^(?:/(?:[^~/]|~[01])*)*$`)

func (e *Validator) safeStateRules() map[string]definition {
	return map[string]definition{
		"safe-state-safestate":         {check: func(i validation.Invocation) error { return safeState(i.Instance) }},
		"safe-state-safestatescope":    {check: func(i validation.Invocation) error { return safeState(at(i.Instance, "state")) }},
		"safe-state-safestatedocument": {check: safeStateDocument},
		"safe-state-safestateproof":    {check: func(i validation.Invocation) error { return safeStateProof(i.Instance) }},
		"safe-state-resolvedsafestate": {check: resolvedSafeState},
	}
}

// safeState requires a continuing mode exactly for a continuing state and unique assertions.
func safeState(v any) error {
	continuing := stringAt(v, "kind") == "continue"
	return require(continuing == (at(v, "continuing_mode") != nil) && fieldsUnique(v, "assertion_refs"))
}

// safeStateDocument requires unique namespace and scope identities, and no root scope beside a default.
func safeStateDocument(i validation.Invocation) error {
	seen := map[string]bool{}
	for _, rule := range array(at(i.Instance, "scopes")) {
		identity := strings.Join(stringsOf(at(rule, "namespace")), ".") + "#" + stringAt(rule, "scope")
		if seen[identity] {
			return invalid()
		}
		seen[identity] = true
	}
	return require(at(i.Instance, "default") == nil || !seen["#"])
}

// safeStateProof requires a positive observed postcondition over every subject, with exactly the named evidence.
func safeStateProof(v any) error {
	assertion, proposition := at(v, "assertion"), at(v, "proposition")
	polarity := defaultMember(assertion, "polarity", "positive")
	quantifier := defaultMember(proposition, "quantifier", "all")
	if stringAt(assertion, "role") != "postcondition" || polarity != "positive" || stringAt(proposition, "basis") != "observed_state" || quantifier != "all" {
		return invalid()
	}
	declared := set(at(proposition, "evidence_requirements"))
	evidence := mapKeys(at(v, "evidence_requirements"))
	return require(len(declared) == len(evidence) && subset(evidence, declared))
}

// resolvedSafeState binds the proofs to the state, the lexical provenance to the
// namespace, and every proof and evidence requirement to the exact target.
func resolvedSafeState(i validation.Invocation) error {
	v := i.Instance
	state := at(v, "state")
	if err := safeState(state); err != nil {
		return err
	}
	proofs := object(at(v, "proofs"))
	refs := set(at(state, "assertion_refs"))
	if len(proofs) != len(refs) {
		return invalid()
	}
	for ref := range proofs {
		if !refs[ref] {
			return invalid()
		}
	}
	if !safeStateProvenance(v) {
		return invalid()
	}
	return resolvedSafeStateProofs(proofs, stringAt(v, "target_ref"))
}

// safeStateProvenance binds the lexical provenance to the namespace and
// requires the defining scope to contain the target scope.
func safeStateProvenance(v any) bool {
	namespace, defining, found := strings.Cut(stringAt(v, "governing_scope"), "#")
	if defining == "/" {
		defining = ""
	}
	scope := stringAt(v, "scope")
	return found && namespace == strings.Join(stringsOf(at(v, "namespace")), ".") && len(defining) <= 4096 && semanticPointer.MatchString(defining) && semanticPointer.MatchString(scope) && addressContains(defining, scope)
}

// resolvedSafeStateProofs binds every proof and evidence requirement to the exact target.
func resolvedSafeStateProofs(proofs map[string]any, target string) error {
	for _, proof := range proofs {
		if err := safeStateProof(proof); err != nil {
			return err
		}
		if !set(at(proof, "proposition", "subjects"))[target] {
			return invalid()
		}
		for _, requirement := range object(at(proof, "evidence_requirements")) {
			if !set(at(requirement, "source_refs"))[target] && !set(at(requirement, "scope_refs"))[target] {
				return invalid()
			}
		}
	}
	return nil
}

// addressContains reports whether the parent pointer is a token prefix of the child pointer.
func addressContains(parent, child string) bool {
	parentTokens, childTokens := jsonpointer.Tokens(parent), jsonpointer.Tokens(child)
	return len(parentTokens) <= len(childTokens) && slices.Equal(parentTokens, childTokens[:len(parentTokens)])
}

package authoring

import (
	"errors"
	"maps"
	"slices"
	"strings"
	"unicode"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

const (
	safeStateSection        = "safe_state"
	assertionRefsField      = "assertion_refs"
	safeStateMaxTargets     = 4096
	safeStateReferenceBytes = 2048
)

// Resolution failures keep the reference classes: an inconsistent declaration,
// or a proof that exceeds the aggregate plan value limits.
var (
	errSafeStateInvalid = fault.New(fault.InvalidInput, "sdl-safe-state-invalid", nil)
	errSafeStateLimit   = fault.New(fault.InvalidInput, "sdl-safe-state-limit", nil)
)

// ResolvedSafeState binds one eligible declaration to its nearest authored
// safe state and the exact observed proof of each assertion.
type ResolvedSafeState struct {
	TargetRef      string                    `json:"target_ref"`
	Scope          string                    `json:"scope"`
	GoverningScope string                    `json:"governing_scope"`
	Namespace      []string                  `json:"namespace"`
	State          map[string]any            `json:"state"`
	Proofs         map[string]map[string]any `json:"proofs"`
}

type safeStateRule struct {
	namespace []string
	scope     string
	state     map[string]any
}

type safeStateTarget struct {
	address, scope, namespace string
}

// SafeStates resolves every current safe-state target without effects or live-state claims.
func (d *Document) SafeStates() ([]ResolvedSafeState, error) {
	if !d.Validated() {
		return nil, semanticInvalid()
	}
	return d.semantic.resolveSafeStates()
}

// Safe-state scopes select eligible declarations independently of relationship endpoints.
func safeStateEligible(entry declaration) bool {
	switch entry.kind {
	case nodesSection, servicesField, databaseServicesField, "dns_services", "file_services", mailServicesField, "datastore_services":
		return true
	default:
		return false
	}
}

func (m *semanticModel) checkSafeState(c *semanticCollector) {
	document := object(m.root[safeStateSection])
	if document == nil || m.safeStateDeferred(document) {
		return
	}
	if _, err := m.resolveSafeStates(); err != nil {
		if errors.Is(err, errSafeStateLimit) {
			c.report(semanticOwner{}, "Safe-state proof exceeds aggregate plan limits")
			return
		}
		c.report(semanticOwner{}, "Safe-state declaration has invalid scope, assertion, or observed evidence coverage")
	}
}

// safeStateDeferred keeps the language's source-time reference deferral.
// Instantiation rejects every remaining token before compilation.
func (m *semanticModel) safeStateDeferred(document map[string]any) bool {
	rules := safeStateRules(document)
	assertions, propositions, evidence := object(m.root[assertionsSection]), object(m.root[propositionsField]), object(m.root[evidenceRequirementsSection])
	referenced := map[string]bool{}
	for _, rule := range rules {
		if containsVariable(rule.state) {
			return true
		}
		for _, ref := range array(rule.state[assertionRefsField]) {
			referenced[text(ref)] = true
		}
	}
	claims := map[string]bool{}
	for ref := range referenced {
		if assertion, present := assertions[ref]; present {
			if containsVariable(assertion) {
				return true
			}
			claims[text(object(assertion)["proposition"])] = true
		}
	}
	requirements := map[string]bool{}
	for ref := range claims {
		if proposition, present := propositions[ref]; present {
			if containsVariable(proposition) {
				return true
			}
			for _, name := range array(object(proposition)[evidenceRequirementsSection]) {
				requirements[text(name)] = true
			}
		}
	}
	for ref := range requirements {
		if requirement, present := evidence[ref]; present && containsVariable(requirement) {
			return true
		}
	}
	return false
}

func safeStateRules(document map[string]any) []safeStateRule {
	rules := []safeStateRule{}
	for _, raw := range array(document[scopesField]) {
		rule := object(raw)
		rules = append(rules, safeStateRule{namespace: stringItems(array(rule[namespaceField])), scope: text(rule[scopeField]), state: safeStateValue(object(rule["state"]))})
	}
	if state := object(document[defaultField]); state != nil {
		rules = append(rules, safeStateRule{namespace: []string{}, state: safeStateValue(state)})
	}
	return rules
}

// safeStateValue returns the complete state model with its constructor defaults.
func safeStateValue(state map[string]any) map[string]any {
	result := maps.Clone(state)
	if _, present := result["schema_version"]; !present {
		result["schema_version"] = "safe-state/v1"
	}
	if _, present := result["continuing_mode"]; !present {
		result["continuing_mode"] = nil
	}
	return result
}

func (m *semanticModel) resolveSafeStates() ([]ResolvedSafeState, error) {
	document := object(m.root[safeStateSection])
	if document == nil {
		return nil, nil
	}
	// The reference indexes declarations strictly here; a collision is an SDL
	// validation error, which the reference reports in the aggregate-limit class.
	if m.index.collision {
		return nil, errSafeStateLimit
	}
	targets, err := m.safeStateTargets()
	if err != nil {
		return nil, err
	}
	rules := safeStateRules(document)
	if err = checkSafeStateRules(rules, targets); err != nil {
		return nil, err
	}
	inputs, err := m.safeStateProofInputs(rules)
	if err != nil {
		return nil, err
	}
	bindings, err := safeStateBindings(rules, targets, inputs)
	if err != nil {
		return nil, err
	}
	proofs := make(map[string]map[string]any, len(inputs))
	for ref, input := range inputs {
		if proofs[ref], err = m.safeStateProof(input); err != nil {
			return nil, err
		}
	}
	for i := range bindings {
		for ref := range bindings[i].Proofs {
			bindings[i].Proofs[ref] = proofs[ref]
		}
	}
	if !safeStateWithinLimits(bindings) {
		return nil, errSafeStateLimit
	}
	for _, binding := range bindings {
		if err = resolvedSafeStateCoverage(binding); err != nil {
			return nil, err
		}
	}
	return bindings, nil
}

func (m *semanticModel) safeStateTargets() ([]safeStateTarget, error) {
	addresses := []string{}
	for address, entry := range m.index.declarations {
		if safeStateEligible(entry) {
			addresses = append(addresses, address)
		}
	}
	slices.Sort(addresses)
	targets := make([]safeStateTarget, len(addresses))
	for i, address := range addresses {
		query := newScopeQueries(m.parser, m.document.contract, m.root)
		scope, err := query.declarationScope(m.index.declarations[address], m.root)
		if err != nil {
			return nil, errSafeStateInvalid
		}
		targets[i] = safeStateTarget{address: address, scope: scope, namespace: m.scopeNamespace(scope)}
	}
	return targets, nil
}

// checkSafeStateRules requires each defining scope to be a real ancestor of
// an eligible target, never a field or positional alias.
func checkSafeStateRules(rules []safeStateRule, targets []safeStateTarget) error {
	for _, rule := range rules {
		matched := slices.ContainsFunc(targets, func(target safeStateTarget) bool {
			return semanticAddressContains(rule.scope, target.scope) && namespaceOwns(target.namespace, strings.Join(rule.namespace, "."))
		})
		if !matched {
			return errSafeStateInvalid
		}
	}
	return nil
}

// selectSafeStateRule selects one nearest defining scope. Rule identities are unique.
func selectSafeStateRule(rules []safeStateRule, target safeStateTarget) *safeStateRule {
	var selected *safeStateRule
	for i := range rules {
		rule := &rules[i]
		if !namespaceOwns(target.namespace, strings.Join(rule.namespace, ".")) || !semanticAddressContains(rule.scope, target.scope) {
			continue
		}
		if selected == nil || len(rule.namespace) > len(selected.namespace) || len(rule.namespace) == len(selected.namespace) && strings.Count(rule.scope, "/") > strings.Count(selected.scope, "/") {
			selected = rule
		}
	}
	return selected
}

type safeStateProofInput struct {
	assertion, proposition map[string]any
	evidence               map[string]any
}

func (m *semanticModel) safeStateProofInputs(rules []safeStateRule) (map[string]safeStateProofInput, error) {
	refs := map[string]bool{}
	for _, rule := range rules {
		for _, ref := range array(rule.state[assertionRefsField]) {
			refs[text(ref)] = true
		}
	}
	assertions, propositions, evidence := object(m.root[assertionsSection]), object(m.root[propositionsField]), object(m.root[evidenceRequirementsSection])
	inputs := make(map[string]safeStateProofInput, len(refs))
	// Share one model per source definition; do not rebuild a proposition for each assertion.
	models := map[string]map[string]any{}
	for _, ref := range slices.Sorted(maps.Keys(refs)) {
		raw, present := assertions[ref]
		if !present {
			return nil, errSafeStateInvalid
		}
		assertion, err := m.safeStateModel(models, "Assertion", assertionsSection+"."+ref, raw)
		if err != nil {
			return nil, err
		}
		name := text(assertion["proposition"])
		raw, present = propositions[name]
		if !present {
			return nil, errSafeStateInvalid
		}
		proposition, err := m.safeStateModel(models, "Proposition", propositionsField+"."+name, raw)
		if err != nil {
			return nil, err
		}
		requirements := map[string]any{}
		for _, item := range array(proposition[evidenceRequirementsSection]) {
			raw, present = evidence[text(item)]
			if !present {
				return nil, errSafeStateInvalid
			}
			if requirements[text(item)], err = m.safeStateModel(models, "EvidenceRequirement", evidenceRequirementsSection+"."+text(item), raw); err != nil {
				return nil, err
			}
		}
		inputs[ref] = safeStateProofInput{assertion: assertion, proposition: proposition, evidence: requirements}
	}
	return inputs, nil
}

// safeStateModel returns the complete model of one source definition, as the
// reference traverses and publishes it.
func (m *semanticModel) safeStateModel(models map[string]map[string]any, model, key string, raw any) (map[string]any, error) {
	if result, present := models[key]; present {
		return result, nil
	}
	pointer := "#/$defs/" + model
	fill := importDefaultWalk{queries: newScopeQueries(m.parser, m.document.contract, m.root), remaining: compositionJSONWork(m.parser.limits)}
	full, err := fill.value(raw, resolve(m.parser.schemas[m.document.contract], pointer), pointer)
	if err != nil || object(full) == nil {
		return nil, errSafeStateInvalid
	}
	models[key] = object(full)
	return object(full), nil
}

func safeStateBindings(rules []safeStateRule, targets []safeStateTarget, inputs map[string]safeStateProofInput) ([]ResolvedSafeState, error) {
	bindings := []ResolvedSafeState{}
	for _, target := range targets {
		rule := selectSafeStateRule(rules, target)
		if rule == nil {
			continue
		}
		if len(bindings) >= safeStateMaxTargets {
			return nil, errSafeStateInvalid
		}
		governing := rule.scope
		if governing == "" {
			governing = "/"
		}
		proofs := map[string]map[string]any{}
		for _, ref := range array(rule.state[assertionRefsField]) {
			proofs[text(ref)] = nil
		}
		bindings = append(bindings, ResolvedSafeState{TargetRef: target.address, Scope: target.scope, GoverningScope: strings.Join(rule.namespace, ".") + "#" + governing, Namespace: slices.Clone(rule.namespace), State: rule.state, Proofs: proofs})
	}
	if !safeStateSourceWithinLimits(inputs, bindings) {
		return nil, errSafeStateLimit
	}
	return bindings, nil
}

// safeStateSourceWithinLimits bounds the shared proof inputs before any proof copy.
func safeStateSourceWithinLimits(inputs map[string]safeStateProofInput, bindings []ResolvedSafeState) bool {
	definitions := make(map[string]any, len(inputs))
	for ref, input := range inputs {
		definitions[ref] = input.document()
	}
	targets := make([]any, len(bindings))
	for i, binding := range bindings {
		proofs := make(map[string]any, len(binding.Proofs))
		for ref := range binding.Proofs {
			proofs[ref] = definitions[ref]
		}
		targets[i] = map[string]any{"target_ref": binding.TargetRef, "scope": binding.Scope, "namespace": stringValues(binding.Namespace), "governing_scope": binding.GoverningScope, "state": binding.State, "proofs": proofs}
	}
	return value.Validate(map[string]any{"definitions": definitions, "targets": targets}, planValueLimits()) == nil
}

func safeStateWithinLimits(bindings []ResolvedSafeState) bool {
	targets := make([]any, len(bindings))
	for i, binding := range bindings {
		proofs := make(map[string]any, len(binding.Proofs))
		for ref, proof := range binding.Proofs {
			proofs[ref] = proof
		}
		targets[i] = map[string]any{"target_ref": binding.TargetRef, "scope": binding.Scope, "governing_scope": binding.GoverningScope, "namespace": stringValues(binding.Namespace), "state": binding.State, "proofs": proofs}
	}
	return value.Validate(targets, planValueLimits()) == nil
}

// document is the record view that the reference traverses before any proof
// copy. Its model records include each serializer-omitted field.
func (i safeStateProofInput) document() map[string]any {
	proposition := i.proposition
	if predicate := object(proposition["predicate"]); text(predicate["kind"]) == "string" {
		if _, present := predicate["expected_from"]; !present {
			predicate = maps.Clone(predicate)
			predicate["expected_from"] = nil
			proposition = maps.Clone(proposition)
			proposition["predicate"] = predicate
		}
	}
	return map[string]any{"assertion": i.assertion, "proposition": proposition, "evidence_requirements": i.evidence}
}

// planValueLimits is the aggregate budget of planner-produced plans.
func planValueLimits() value.Limits {
	limits := value.Runtime()
	limits.MaxNodes, limits.MaxOperations, limits.MaxTotalScalarBytes = 524288, 4*524288, 16*1048576
	return limits
}

// safeStateProof canonicalizes every proof reference and requires a positive
// observed postcondition over every subject, with exactly the named evidence.
func (m *semanticModel) safeStateProof(input safeStateProofInput) (map[string]any, error) {
	assertion, proposition := input.assertion, maps.Clone(input.proposition)
	subjects, err := m.canonicalSafeStateRefs(array(proposition["subjects"]))
	if err != nil {
		return nil, err
	}
	proposition["subjects"] = subjects
	// The reference serializer omits an absent generated-artifact expectation.
	if predicate := object(proposition["predicate"]); predicate != nil && predicate["expected_from"] == nil {
		if _, present := predicate["expected_from"]; present {
			predicate = maps.Clone(predicate)
			delete(predicate, "expected_from")
			proposition["predicate"] = predicate
		}
	}
	evidence := make(map[string]any, len(input.evidence))
	for name, raw := range input.evidence {
		requirement := maps.Clone(object(raw))
		for _, field := range []string{"source_refs", "scope_refs"} {
			if requirement[field], err = m.canonicalSafeStateRefs(array(requirement[field])); err != nil {
				return nil, err
			}
		}
		evidence[name] = requirement
	}
	if !uniqueStrings(subjects) || text(assertion["role"]) != "postcondition" || defaultText(assertion, "polarity", "positive") != "positive" {
		return nil, errSafeStateInvalid
	}
	if text(proposition["basis"]) != "observed_state" || defaultText(proposition, "quantifier", "all") != "all" {
		return nil, errSafeStateInvalid
	}
	if len(evidence) == 0 || len(evidence) > 64 || len(evidence) != len(array(proposition[evidenceRequirementsSection])) {
		return nil, errSafeStateInvalid
	}
	for name := range evidence {
		if !safeStateReference(name) {
			return nil, errSafeStateInvalid
		}
	}
	return map[string]any{"assertion": assertion, "proposition": proposition, "evidence_requirements": evidence}, nil
}

func (m *semanticModel) canonicalSafeStateRefs(refs []any) ([]any, error) {
	canonical := make([]any, len(refs))
	for i, ref := range refs {
		address, unique := m.observationSubject(text(ref))
		if !unique {
			return nil, errSafeStateInvalid
		}
		canonical[i] = address
	}
	return canonical, nil
}

// resolvedSafeStateCoverage requires every proof and evidence requirement to cover the exact target.
func resolvedSafeStateCoverage(binding ResolvedSafeState) error {
	if !safeStateReference(binding.TargetRef) || len(binding.GoverningScope) > 8192 {
		return errSafeStateInvalid
	}
	for _, proof := range binding.Proofs {
		if !slices.Contains(array(object(proof["proposition"])["subjects"]), any(binding.TargetRef)) {
			return errSafeStateInvalid
		}
		for _, raw := range object(proof["evidence_requirements"]) {
			requirement := object(raw)
			if !slices.Contains(array(requirement["source_refs"]), any(binding.TargetRef)) && !slices.Contains(array(requirement["scope_refs"]), any(binding.TargetRef)) {
				return errSafeStateInvalid
			}
		}
	}
	return nil
}

func safeStateReference(ref string) bool {
	return ref != "" && len(ref) <= safeStateReferenceBytes && !strings.ContainsFunc(ref, pythonSpace)
}

// pythonSpace matches the reference string-pattern whitespace class.
func pythonSpace(r rune) bool { return unicode.IsSpace(r) || r >= 0x1c && r <= 0x1f }

func defaultText(document map[string]any, field, initial string) string {
	if raw, present := document[field]; present && raw != nil {
		return text(raw)
	}
	return initial
}

func stringValues(items []string) []any {
	result := make([]any, len(items))
	for i, item := range items {
		result[i] = item
	}
	return result
}

// semanticAddressContains reports whether the parent pointer is a token prefix of the child pointer.
func semanticAddressContains(parent, child string) bool {
	parentTokens, childTokens := jsonpointer.Tokens(parent), jsonpointer.Tokens(child)
	return len(parentTokens) <= len(childTokens) && slices.Equal(parentTokens, childTokens[:len(parentTokens)])
}

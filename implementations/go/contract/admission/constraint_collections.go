package admission

import (
	"encoding/json"
	"maps"
	"strings"
)

func (e *constraintEvaluation) identity() bool {
	e.identities++
	return e.identities <= e.limits.MaxIdentityChecks
}

func (e *constraintEvaluation) keyedAliases(rule *constraintNode, pointer string) (map[string][]any, constraintResult) {
	aliases := make(map[string][]any, len(rule.Aliases))
	for _, alias := range rule.Aliases {
		if !e.identity() {
			return nil, constraintFailure("limit-exceeded", pointer, "Keyed collection alias evaluation exceeded max_identity_checks.")
		}
		key, err := jsonDigest(alias.Identity)
		if err != nil {
			return nil, constraintFailure("invalid", pointer, "Collection alias identity is invalid.")
		}
		aliases[key] = alias.Target
	}
	return aliases, constraintSuccess()
}

func keyedIdentity(record map[string]any, fields []string) ([]any, bool) {
	identity := make([]any, len(fields))
	for i, name := range fields {
		member, present := record[name]
		valid := present
		switch scalar := member.(type) {
		case string, bool:
		case json.Number:
			valid = !strings.ContainsAny(string(scalar), ".eE")
		default:
			valid = false
		}
		if !valid {
			return nil, false
		}
		identity[i] = member
	}
	return identity, true
}

func (e *constraintEvaluation) keyedRecord(rule *constraintNode, item any, aliases map[string][]any, pointer string) (string, map[string]any, constraintResult) {
	if !e.identity() {
		return "", nil, constraintFailure("limit-exceeded", pointer, "Keyed collection evaluation exceeded max_identity_checks.")
	}
	record, ok := item.(map[string]any)
	if !ok {
		return "", nil, constraintFailure("invalid", pointer, "A keyed collection member has no complete concrete semantic identity.")
	}
	identity, ok := keyedIdentity(record, rule.IdentityFields)
	if !ok {
		return "", nil, constraintFailure("invalid", pointer, "A keyed collection member has no complete concrete semantic identity.")
	}
	key, err := jsonDigest(identity)
	if err != nil {
		return "", nil, constraintFailure("invalid", pointer, "Collection identity cannot be represented.")
	}
	if canonical, aliased := aliases[key]; aliased {
		if !e.identity() {
			return "", nil, constraintFailure("limit-exceeded", pointer, "Keyed collection alias evaluation exceeded max_identity_checks.")
		}
		key, err = jsonDigest(canonical)
		if err != nil {
			return "", nil, constraintFailure("invalid", pointer, "Collection identity cannot be represented.")
		}
		record = maps.Clone(record)
		for i, name := range rule.IdentityFields {
			record[name] = canonical[i]
		}
	}
	return key, record, constraintSuccess()
}

func (e *constraintEvaluation) keyedIndex(rule *constraintNode, actual []any, pointer string) (map[string]any, constraintResult) {
	aliases, failure := e.keyedAliases(rule, pointer)
	if failure.Status != assuranceConformant {
		return nil, failure
	}
	indexed := make(map[string]any, len(actual))
	for _, item := range actual {
		key, record, failure := e.keyedRecord(rule, item, aliases, pointer)
		if failure.Status != assuranceConformant {
			return nil, failure
		}
		if _, duplicate := indexed[key]; duplicate {
			return nil, constraintFailure("invalid", pointer, "A keyed collection contains a duplicate or ambiguous semantic identity.")
		}
		indexed[key] = record
	}
	return indexed, constraintSuccess()
}

func (e *constraintEvaluation) keyedDeclarations(rule *constraintNode, pointer string) (map[string]*constraintNode, []string, constraintResult) {
	declared := make(map[string]*constraintNode, len(rule.Members))
	order := make([]string, 0, len(rule.Members))
	for _, member := range rule.Members {
		if !e.identity() {
			return nil, nil, constraintFailure("limit-exceeded", pointer, "Keyed collection declaration evaluation exceeded max_identity_checks.")
		}
		key, err := jsonDigest(member.Identity)
		if err != nil {
			return nil, nil, constraintFailure("invalid", pointer, "Collection declaration has an invalid identity.")
		}
		declared[key] = member.Constraint
		order = append(order, key)
	}
	return declared, order, constraintSuccess()
}

func (e *constraintEvaluation) keyed(rule *constraintNode, actual any, pointer string, depth int, references []string) constraintResult {
	observed, ok := actual.([]any)
	if !ok {
		return constraintFailure("nonconformant", pointer, "Observed value is not the required keyed collection.")
	}
	maximum := 4096
	if rule.MaxItems != nil {
		maximum = *rule.MaxItems
	}
	if len(observed) < rule.MinItems || len(observed) > maximum {
		return constraintFailure("nonconformant", pointer, "Observed keyed collection violates its declared cardinality.")
	}
	indexed, failure := e.keyedIndex(rule, observed, pointer)
	if failure.Status != assuranceConformant {
		return failure
	}
	declared, order, failure := e.keyedDeclarations(rule, pointer)
	if failure.Status != assuranceConformant {
		return failure
	}
	results := make([]constraintResult, 0, len(order)+1)
	for _, key := range order {
		child := declared[key]
		item, present := indexed[key]
		results = append(results, e.keyedMember(child, item, present, pointer, key, depth, references))
	}
	extras := false
	for key := range indexed {
		extras = extras || declared[key] == nil
	}
	results = append(results, e.closure(rule.Closure, pointer, extras, "keyed collection"))
	return constraintCombine(results, e.limits.MaxDiagnostics)
}

func (e *constraintEvaluation) keyedMember(child *constraintNode, item any, present bool, pointer, key string, depth int, references []string) constraintResult {
	if child.Presence == termForbidden && present || child.Presence != termOptional && child.Presence != termForbidden && !present {
		address := pointer + "/@" + strings.TrimPrefix(key, "sha256:")[:16]
		return e.member(child, item, present, address, depth, references, "collection member")
	}
	if present && child.Presence != termForbidden {
		return e.evaluate(child, item, pointer+"/@"+key, depth+1, references)
	}
	return constraintSuccess()
}

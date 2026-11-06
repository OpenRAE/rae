package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func planModel(v any, domain string) error {
	index, err := indexPlanOperations(v, domain)
	if err != nil {
		return err
	}
	addresses, live, nodes := index.addresses, index.live, index.nodes

	if domain != termProvisioning {
		return require(fieldsUnique(v, "startup_order") && subset(stringsOf(at(v, "startup_order")), addresses))
	}
	constraints, authorities := array(at(v, "realization_constraints")), array(at(v, "realization_authority"))
	if len(rowTupleSet(constraints, "address", "concern")) != len(constraints) || len(rowTupleSet(authorities, "address", "requirement_kind")) != len(authorities) || len(rowTupleSet(authorities, "address", "payload_pointer")) != len(authorities) {
		return invalid()
	}
	for _, constraint := range constraints {
		if !nodes[stringAt(constraint, "address")] {
			return invalid()
		}
	}
	for _, authority := range authorities {
		if !live[stringAt(authority, "address")] {
			return invalid()
		}
	}
	return nil
}

func (e *Validator) plannedSubstrate(v any) error {
	domain := at(v, "value_domain")
	posture := stringAt(v, "posture")
	if posture == "open" {
		return require(domain == nil)
	}
	if domain == nil {
		return invalid()
	}
	var values []any
	switch stringAt(domain, "kind") {
	case postureExact:
		values = []any{at(domain, "value")}
	case "enum":
		values = array(at(domain, "values"))
	case "governed-reference":
		values = array(at(domain, "allowed_refs"))
	default:
		return invalid()
	}
	if posture == postureExact && len(values) != 1 {
		return invalid()
	}
	for _, v := range values {
		if !e.vocabularyTerm("compute-substrates", text(v)) {
			return invalid()
		}
	}
	return nil
}

func augmentationPreparationModel(v any) error {
	content := []byte(stringAt(v, "content"))
	if len(content) > value.MaterializationBytes {
		return invalid()
	}
	parsed, err := ingress.Parse(content, ingress.Limits{MaxBytes: value.MaterializationBytes, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return invalid()
	}
	if err = value.Validate(parsed, value.Runtime()); err != nil {
		return invalid()
	}
	effects := array(at(v, "effects"))
	work := 0
	for _, effect := range effects {
		work += 1 + len(array(at(effect, "requirement_refs"))) + len(array(at(effect, "affected_scopes")))
	}
	if work > 16384 || len(rowSet(effects, "field_pointer")) != len(effects) {
		return invalid()
	}
	return value.Validate(effects, value.Runtime())
}

type planOperationIndex struct{ addresses, live, nodes map[string]bool }

func indexPlanOperations(v any, domain string) (planOperationIndex, error) {
	operations := array(at(v, "operations"))
	if len(rowSet(operations, "address")) != len(operations) {
		return planOperationIndex{}, invalid()
	}
	root := map[string]string{termProvisioning: "provision", termOrchestration: termOrchestration, termEvaluation: termEvaluation}[domain]
	allowed := map[string][]string{
		termProvisioning:  {"network", "node", "feature-binding", "content-placement", "account-placement", "domain-controller-placement", "generated-artifact", "persistent-volume"},
		termOrchestration: {"inject-binding", "inject", "event", "script", "story", termWorkflow},
		termEvaluation:    {"condition-binding", "proposition", "assertion", "objective"},
	}
	addresses, live, nodes := map[string]bool{}, map[string]bool{}, map[string]bool{}
	for _, op := range operations {
		if !strings.HasPrefix(stringAt(op, "address"), root+".") || !set(jsonStrings(allowed[domain]))[stringAt(op, "resource_type")] || domain != termProvisioning && len(array(at(op, "profile_bindings"))) > 0 {
			return planOperationIndex{}, invalid()
		}
		address := stringAt(op, "address")
		addresses[address] = true
		if stringAt(op, "action") != "delete" {
			live[address] = true
			if stringAt(op, "resource_type") == "node" {
				nodes[address] = true
			}
		}
	}
	return planOperationIndex{addresses, live, nodes}, nil
}

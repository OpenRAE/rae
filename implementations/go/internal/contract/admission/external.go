package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/urisafety"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) externalRules() map[string]definition {
	rules := map[string]definition{
		"external-concept-source-locator-safe": {check: func(i validation.Invocation) error {
			if at(i.Instance, "source_locator") == nil {
				return nil
			}
			return require(urisafety.Check(stringAt(i.Instance, "source_locator"), urisafety.Options{ForbiddenSchemes: []string{"file", "data"}, ForbidFragment: true}) == nil)
		}},
		"external-concept-source-pinned": {check: func(i validation.Invocation) error {
			return require(at(i.Instance, "source_locator") != nil || at(i.Instance, "source_digest") != nil)
		}},
		"external-concept-participants-unique": {check: func(i validation.Invocation) error { return require(fieldsUnique(i.Instance, "participant_refs")) }},
		"external-concept-confidence-calibrated": {check: func(i validation.Invocation) error {
			return require((at(i.Instance, "score") == nil) == (at(i.Instance, "calibration_profile_ref") == nil))
		}},
		"external-concept-approximation-loss-consistent": {check: func(i validation.Invocation) error {
			return require((stringAt(i.Instance, "posture") == postureExact) == (len(array(at(i.Instance, "loss_details"))) == 0))
		}},
		"external-concept-review-evidence-consistent": {check: externalReview},
		"external-concept-binding-identities":         {check: externalIdentities},
	}
	paths := map[string][]string{
		"external-concept-source-locator-safe": {"scheme"}, "external-concept-source-pinned": {"scheme"},
		"external-concept-participants-unique":   {"perspective", "participant_availability"},
		"external-concept-confidence-calibrated": {"confidence"}, "external-concept-approximation-loss-consistent": {"approximation"},
		"external-concept-review-evidence-consistent": {"review"},
	}
	for id, path := range paths {
		rule := rules[id]
		rule.check = externalBindingCheck(rule.check, path)
		rules[id] = rule
	}
	return rules
}

func externalReview(i validation.Invocation) error {
	count := len(array(at(i.Instance, "review_refs")))
	switch stringAt(i.Instance, "status") {
	case dispositionAccepted, termRejected, statusSuperseded:
		return require(count > 0)
	case "unreviewed":
		return require(count == 0)
	default:
		return nil // Other published review states impose no evidence condition.
	}
}

func externalIdentities(i validation.Invocation) error {
	bindings := at(i.Instance, termBindings)
	if !keyed(bindings, "binding_id") {
		return invalid()
	}
	identities := make([]string, 0, len(object(bindings)))
	for _, binding := range object(bindings) {
		subject, scheme := at(binding, "subject"), at(binding, "scheme")
		identities = append(identities, join(
			stringAt(subject, "owning_contract_id"), stringAt(subject, "lifecycle_phase"), stringAt(subject, "canonical_ref"), strings.ToLower(stringAt(subject, "artifact_digest")),
			stringAt(scheme, "scheme_id"), stringAt(scheme, termAuthority), stringAt(scheme, termRevision), stringAt(scheme, "concept_id"),
			stringAt(binding, "assertion", "relationship_kind"), stringAt(binding, "perspective", "asserting_party_ref")))
	}
	return require(unique(identities))
}

func externalBindingCheck(check func(validation.Invocation) error, path []string) func(validation.Invocation) error {
	return func(i validation.Invocation) error {
		if i.Key.ContractID == "" {
			return check(i)
		}
		for _, binding := range object(at(i.Instance, termBindings)) {
			nested := i
			nested.Instance = at(binding, path...)
			if err := check(nested); err != nil {
				return err
			}
		}
		return nil
	}
}

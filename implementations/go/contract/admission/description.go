package admission

import (
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func (e *Validator) descriptionRules() map[string]definition {
	return map[string]definition{
		"evidence-description-nonauthoritative": {check: func(i validation.Invocation) error {
			if stringAt(i.Instance, "redaction_state") == termWithheld {
				for _, fact := range array(at(i.Instance, "typed_description", "facts")) {
					if stringAt(fact, termState) == "known" {
						return invalid()
					}
				}
			}
			return description(at(i.Instance, "typed_description"), termExperimentEvidenceRecordV1)
		}},
		"realized-description-nonauthoritative": {check: func(i validation.Invocation) error {
			return description(at(i.Instance, "typed_description"), termExperimentRunV1)
		}},
	}
}
func description(v any, host string) error {
	if v == nil {
		return nil
	}
	if err := value.Validate(v, value.Default()); err != nil {
		return invalid()
	}
	if stringAt(v, "authored_ref", fieldRefVersion) == "" || stringAt(v, "authored_ref", "ref_digest") == "" {
		return invalid()
	}
	if err := descriptionProvenance(at(v, "provenance")); err != nil {
		return err
	}
	facts := array(at(v, "facts"))
	if len(rowSet(facts, "fact_id")) != len(facts) {
		return invalid()
	}
	for _, fact := range facts {
		if err := descriptionFact(v, fact, host); err != nil {
			return err
		}
	}
	return descriptionCoverage(v, facts)
}

func descriptionProvenance(v any) error {
	if err := timestamps(v, "recorded_at"); err != nil {
		return err
	}
	if stringAt(v, "observer_ref", fieldRefVersion) == "" {
		return invalid()
	}
	basis := stringAt(v, "basis")
	return require((basis != basisObserved && basis != "independently-verified") || len(array(at(v, fieldEvidenceRefs))) > 0)
}
func descriptionFact(owner, fact any, host string) error {
	known := stringAt(fact, termState) == "known"
	if known != (at(fact, "value") != nil) || !known && len(array(at(fact, "profile_bindings"))) > 0 {
		return invalid()
	}
	if known {
		if err := descriptiveValue(at(fact, "value")); err != nil {
			return err
		}
	}
	provenance := at(fact, "provenance")
	if provenance == nil {
		provenance = at(owner, "provenance")
	}
	if err := descriptionProvenance(provenance); err != nil {
		return err
	}
	for _, binding := range array(at(fact, "profile_bindings")) {
		if err := descriptionBinding(binding, stringAt(fact, "subject"), host, provenance); err != nil {
			return err
		}
	}
	return nil
}
func semanticContains(parent, child string) bool {
	if parent != "" && !strings.HasPrefix(parent, "/") || child != "" && !strings.HasPrefix(child, "/") {
		return false
	}
	p, c := jsonpointer.Tokens(parent), jsonpointer.Tokens(child)
	return len(p) <= len(c) && slices.Equal(p, c[:len(p)])
}
func descriptionBinding(root any, subject, host string, provenance any) error {
	type item struct {
		binding any
		subject string
	}
	pending := []item{{root, subject}}
	for work := 0; len(pending) > 0; work++ {
		if work >= 4096 {
			return invalid()
		}
		current := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		binding := current.binding
		owner := at(binding, "owner")
		use := stringAt(owner, "use")
		phase := map[string]string{termExperimentEvidenceRecordV1: "capture", termExperimentRunV1: "realization-description"}[host]
		address := stringAt(owner, "canonical_address")
		if use != "typed-report" && use != "opaque-exchange" || stringAt(owner, "owning_contract_id") != host || stringAt(owner, "lifecycle_phase") != phase || !strings.HasPrefix(address, "#") || !semanticContains(current.subject, strings.TrimPrefix(address, "#")) {
			return invalid()
		}
		expected := map[string]string{"backend-selected": "backend-selected", basisObserved: basisObserved, "independently-verified": basisObserved}[stringAt(provenance, "basis")]
		if expected == "" || stringAt(binding, "provenance", "basis") != expected || !subset(stringsOf(at(binding, "provenance", fieldEvidenceRefs)), rowSet(at(provenance, fieldEvidenceRefs), fieldRefID)) {
			return invalid()
		}
		children := array(at(binding, "children"))
		if len(rowSet(children, termBindingID)) != len(children) {
			return invalid()
		}
		for _, child := range children {
			pending = append(pending, item{child, strings.TrimPrefix(address, "#")})
		}
	}
	return nil
}

func descriptionCoverage(v any, facts []any) error {
	for _, coverage := range array(at(v, "coverage")) {
		if err := descriptionCoverageEntry(coverage, facts); err != nil {
			return err
		}
	}
	return nil
}

func descriptionCoverageEntry(coverage any, facts []any) error {
	if !fieldsUnique(coverage, "fact_ids") {
		return invalid()
	}
	if at(coverage, "provenance") != nil {
		if err := descriptionProvenance(at(coverage, "provenance")); err != nil {
			return err
		}
	}
	for _, id := range stringsOf(at(coverage, "fact_ids")) {
		found := false
		for _, fact := range facts {
			if stringAt(fact, "fact_id") == id && semanticContains(stringAt(coverage, "subject"), stringAt(fact, "subject")) {
				found = true
			}
		}
		if !found {
			return invalid()
		}
	}

	return nil
}

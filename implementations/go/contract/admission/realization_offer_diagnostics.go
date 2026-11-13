package admission

import (
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
)

// RealizationOpenOfferDiagnostics compares open paths through the existing
// bounded envelope owner without constructing a second envelope evaluator.
func RealizationOpenOfferDiagnostics(v *Validator, envelope binding.RealizationEnvelopeV1, paths []string) ([]diagnostic.Diagnostic, error) {
	input := make([]any, len(paths))
	for index, path := range paths {
		if len(path) == 0 || len(path) > 4096 || !envelopePath.MatchString(path) {
			return nil, invalid()
		}
		input[index] = path
	}
	if err := offerProjectionBounds(input, nil); err != nil {
		return nil, err
	}
	document, err := realizationOfferEnvelope(v, envelope)
	if err != nil {
		return nil, err
	}
	offer, err := materializationOfferFor(at(document, "expression"))
	if err != nil {
		return nil, err
	}
	selected := slices.Clone(paths)
	slices.Sort(selected)
	selected = slices.Compact(selected)
	findings := []diagnostic.Diagnostic{}
	for _, path := range selected {
		if _, restricted := offer.leaves[path]; restricted {
			findings = append(findings, realizationOfferFinding("subsumption.requested-unconstrained", path, "requested leaves a path open that offered constrains"))
		}
	}
	excluded, err := offer.excludesOpenPath(selected)
	if err != nil {
		return nil, err
	}
	if excluded {
		findings = append(findings, realizationOfferFinding("subsumption.closure-mismatch", "<scenario>", "offered is closed-world where requested is open-world"))
	}
	return findings, nil
}

// RealizationMemberDiagnostics compares native values and independently derived
// typed presence. Native SDL admission and source binding belong to the caller.
func RealizationMemberDiagnostics(v *Validator, envelope binding.RealizationEnvelopeV1, projection Fragment, presence map[string][]string) ([]diagnostic.Diagnostic, error) {
	if admissionErr := CheckFragment(projection, RealizationValue); admissionErr != nil {
		return nil, admissionErr
	}
	input := projection.Document()
	if err := offerProjectionBounds(input, presence); err != nil {
		return nil, err
	}
	document, err := realizationOfferEnvelope(v, envelope)
	if err != nil {
		return nil, err
	}
	order, err := realizationOfferRecordOrder(envelope)
	if err != nil {
		return nil, err
	}
	offer, err := materializationOfferForOrdered(at(document, "expression"), order)
	if err != nil {
		return nil, err
	}
	findings, err := offer.memberConstraintDiagnostics(input)
	if err != nil {
		return nil, err
	}
	return append(findings, offer.memberClosedDiagnostics(input, presence)...), nil
}

func realizationOfferFinding(code, path, message string) diagnostic.Diagnostic {
	return diagnostic.Diagnostic{Code: "realization-envelope." + code, Domain: "realization-envelope", Address: path, Message: message, Severity: termError}
}

func realizationOfferRecordOrder(envelope binding.RealizationEnvelopeV1) (map[string][]string, error) {
	expression, _ := envelope.Expression.Value()
	domains, _ := expression.Domains.Value()
	order := make(map[string][]string, len(domains))
	for name, raw := range domains {
		// The admitted raw domain preserves its fields' object order. Reuse the
		// existing bounded standard JSON token scanner for that single member.
		fields, err := trialSourceMemberOrder(string(raw), "/fields")
		if err != nil {
			return nil, err
		}
		order[name] = fields
	}
	return order, nil
}

func (o *materializationOffer) excludesOpenPath(paths []string) (bool, error) {
	for _, path := range paths {
		for scope, allowed := range o.closed {
			o.remaining--
			if o.remaining < 0 {
				return false, invalid()
			}
			if materializationOfferClosed(nil, path, nil, scope, allowed) != nil {
				return true, nil //nolint:nilerr // The shared closed-scope refusal is the negative subsumption result.
			}
		}
	}
	return false, nil
}

func (o *materializationOffer) memberConstraintDiagnostics(input any) ([]diagnostic.Diagnostic, error) {
	findings := []diagnostic.Diagnostic{}
	for _, path := range o.leafOrder {
		leaf := o.leaves[path]
		actual, present := materializationOfferAt(input, path)
		if !present || actual == nil {
			findings = append(findings, realizationOfferFinding("membership.path-absent", path, "constrained path is unspecified in the instance"))
			continue
		}
		descriptor, err := envelopeDomain(leaf.descriptor)
		if err != nil {
			return nil, err
		}
		admitted, err := domain.In(actual, descriptor)
		if err != nil {
			return nil, err
		}
		if !admitted {
			findings = append(findings, realizationOfferFinding("membership.domain-mismatch", path, "value is not in the "+stringAt(leaf.descriptor, termKind)+" domain"))
		}
	}
	return findings, nil
}

func (o *materializationOffer) memberClosedDiagnostics(input any, presence map[string][]string) []diagnostic.Diagnostic {
	findings := []diagnostic.Diagnostic{}
	for _, path := range slices.Sorted(maps.Keys(o.closed)) {
		actual, present := materializationOfferAt(input, path)
		if !present {
			continue
		}
		children, typed := presence[path]
		if !typed {
			children = mapKeys(actual)
		}
		ordered := slices.Clone(children)
		slices.Sort(ordered)
		for _, child := range ordered {
			if !o.closed[path][child] {
				findings = append(findings, realizationOfferFinding("membership.closed-world-extra", strings.TrimPrefix(path+"."+child, "."), "closed-world scope admits no unspecified realizable dimension"))
			}
		}
	}
	return findings
}

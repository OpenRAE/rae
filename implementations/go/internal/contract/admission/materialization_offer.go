package admission

import (
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
)

type materializationOfferLeaf struct {
	descriptor   any
	overrideable bool
}
type materializationOffer struct {
	domains   map[string]any
	leaves    map[string]materializationOfferLeaf
	closed    map[string]map[string]bool
	remaining int
}

func materializationOfferIn(node any, prefix string, presence map[string][]string, expression any) error {
	offer := materializationOffer{domains: object(at(expression, "domains")), leaves: map[string]materializationOfferLeaf{}, closed: map[string]map[string]bool{}, remaining: 100000}
	bindings := slices.Clone(array(at(expression, "bindings")))
	slices.SortStableFunc(bindings, materializationOfferOrder)
	for _, binding := range bindings {
		if err := offer.binding(binding); err != nil {
			return err
		}
	}
	if err := offer.closures(expression); err != nil {
		return err
	}
	for path, leaf := range offer.leaves {
		if !materializationOfferContains(prefix, path) {
			continue
		}
		relative := strings.TrimPrefix(strings.TrimPrefix(path, prefix), ".")
		actual, present := materializationOfferAt(node, relative)
		if !present || actual == nil {
			return invalid()
		}
		descriptor, err := envelopeDomain(leaf.descriptor)
		if err != nil {
			return err
		}
		matches, err := domain.In(actual, descriptor)
		if err != nil || !matches {
			return invalid()
		}
	}
	return offer.checkClosed(node, prefix, presence)
}
func materializationOfferOrder(a, b any) int {
	if order := len(materializationOfferTokens(stringAt(a, "path"))) - len(materializationOfferTokens(stringAt(b, "path"))); order != 0 {
		return order
	}
	return strings.Compare(scopeRank(at(a, "scope")), scopeRank(at(b, "scope")))
}
func (o *materializationOffer) binding(binding any) error {
	path := stringAt(binding, "path")
	if stringAt(binding, "posture") == termOpen {
		for previous, leaf := range o.leaves {
			if materializationOfferContains(path, previous) {
				if !leaf.overrideable {
					return invalid()
				}
				delete(o.leaves, previous)
			}
		}
		return nil
	}
	return o.expand(path, o.domains[stringAt(binding, "domain")], boolean(at(binding, "overrideable")), 0)
}
func (o *materializationOffer) expand(path string, descriptor any, override bool, depth int) error {
	o.remaining--
	if o.remaining < 0 || depth > 64 || descriptor == nil {
		return invalid()
	}
	if stringAt(descriptor, "kind") == termRecord {
		for field, target := range object(at(descriptor, "fields")) {
			if err := o.expand(path+"."+field, o.domains[text(target)], override, depth+1); err != nil {
				return err
			}
		}
		return nil
	}
	if prior, ok := o.leaves[path]; ok && !prior.overrideable && !materializationDomainSubset(descriptor, prior.descriptor) {
		return invalid()
	}
	o.leaves[path] = materializationOfferLeaf{descriptor, override}
	return nil
}
func (o *materializationOffer) checkClosed(node any, prefix string, presence map[string][]string) error {
	for path, allowed := range o.closed {
		if err := materializationOfferClosed(node, prefix, presence, path, allowed); err != nil {
			return err
		}
	}
	return nil
}

func materializationDomainSubset(sub, sup any) bool {
	left, right := stringAt(sub, "kind"), stringAt(sup, "kind")
	if left == termGovernedReference || right == termGovernedReference {
		return left == right && equal(at(sub, termAuthority), at(sup, termAuthority)) && subset(stringsOf(at(sub, "allowed_refs")), set(at(sup, "allowed_refs")))
	}
	if left == termNumericInterval {
		return materializationIntervalSubset(sub, sup)
	}
	var values []any
	switch left {
	case postureExact:
		values = []any{at(sub, "value")}
	case termEnum:
		values = array(at(sub, "values"))
	case "boolean":
		if at(sub, "value") == nil {
			values = []any{true, false}
		} else {
			values = []any{at(sub, "value")}
		}
	default:
		return false
	}
	descriptor, err := envelopeDomain(sup)
	if err != nil {
		return false
	}
	for _, value := range values {
		matches, matchErr := domain.In(value, descriptor)
		if matchErr != nil || !matches {
			return false
		}
	}
	return true
}
func materializationIntervalSubset(sub, sup any) bool {
	lower, upper := at(sub, "lower"), at(sub, "upper")
	if numericEqual(lower, upper) {
		return materializationSingletonSubset(sub, sup, lower)
	}
	if stringAt(sup, "kind") != termNumericInterval || stringAt(sup, "numeric_type") == termInteger && stringAt(sub, "numeric_type") == "number" {
		return false
	}
	lowerOK := numericGreater(lower, at(sup, "lower")) || numericEqual(lower, at(sup, "lower")) && (boolean(defaultMember(sup, "lower_closed", true)) || !boolean(defaultMember(sub, "lower_closed", true)))
	upperOK := numericGreater(at(sup, "upper"), upper) || numericEqual(upper, at(sup, "upper")) && (boolean(defaultMember(sup, "upper_closed", true)) || !boolean(defaultMember(sub, "upper_closed", true)))
	return lowerOK && upperOK
}

func materializationSingletonSubset(sub, sup, lower any) bool {
	if stringAt(sub, "numeric_type") == termInteger {
		n, ok := number(lower)
		if !ok || !n.IsInt() {
			return false
		}
		lower = json.Number(n.Num().String())
	}
	descriptor, err := envelopeDomain(sup)
	if err != nil {
		return false
	}
	ok, err := domain.In(lower, descriptor)
	return err == nil && ok
}

func materializationOfferClosed(node any, prefix string, presence map[string][]string, path string, allowed map[string]bool) error {
	if !materializationOfferContains(prefix, path) && !materializationOfferContains(path, prefix) {
		return nil
	}
	if materializationOfferContains(path, prefix) && path != prefix {
		remainder := materializationOfferTokens(prefix)[len(materializationOfferTokens(path)):]
		if len(remainder) > 0 && !strings.HasPrefix(remainder[0], "[") && !allowed[remainder[0]] {
			return invalid()
		}
		return nil
	}
	relative := strings.TrimPrefix(strings.TrimPrefix(path, prefix), ".")
	actual, present := materializationOfferAt(node, relative)
	if !present {
		return nil
	}
	children, typed := presence[relative]
	if !typed {
		children = mapKeys(actual)
	}
	if !subset(children, allowed) {
		return invalid()
	}
	return nil
}

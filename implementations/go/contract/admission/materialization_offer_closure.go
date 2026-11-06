package admission

import (
	"regexp"
	"slices"
	"strconv"
	"strings"
)

var materializationOfferToken = regexp.MustCompile(`[^.\[\]]+|\[\d+\]`)

func materializationOfferTokens(path string) []string {
	return materializationOfferToken.FindAllString(path, -1)
}
func materializationOfferContains(parent, child string) bool {
	left, right := materializationOfferTokens(parent), materializationOfferTokens(child)
	return len(left) <= len(right) && slices.Equal(left, right[:len(left)])
}
func materializationOfferAt(root any, path string) (any, bool) {
	current := root
	for _, token := range materializationOfferTokens(path) {
		if strings.HasPrefix(token, "[") {
			index, err := strconv.Atoi(strings.Trim(token, "[]"))
			items, ok := current.([]any)
			if err != nil || !ok || index < 0 || index >= len(items) {
				return nil, false
			}
			current = items[index]
		} else {
			var ok bool
			current, ok = object(current)[token]
			if !ok {
				return nil, false
			}
		}
	}
	return current, true
}
func materializationOfferPath(tokens []string) string {
	result := ""
	for _, token := range tokens {
		if result != "" && !strings.HasPrefix(token, "[") {
			result += "."
		}
		result += token
	}
	return result
}
func (o *materializationOffer) closures(expression any) error {
	for _, binding := range array(at(expression, "bindings")) {
		if at(binding, "domain") != nil {
			if err := o.recordClosure(stringAt(binding, "path"), o.domains[stringAt(binding, "domain")], 0); err != nil {
				return err
			}
		}
	}
	overlays := slices.Clone(array(at(expression, "closure")))
	slices.SortStableFunc(overlays, materializationOfferOrder)
	for _, overlay := range overlays {
		if err := o.closureOverlay(overlay, expression); err != nil {
			return err
		}
	}
	return nil
}
func (o *materializationOffer) recordClosure(path string, descriptor any, depth int) error {
	o.remaining--
	if o.remaining < 0 || depth > 64 || descriptor == nil {
		return invalid()
	}
	if stringAt(descriptor, "kind") != termRecord {
		return nil
	}
	if !boolean(at(descriptor, "extra")) {
		o.closed[path] = keySet(at(descriptor, "fields"))
	}
	for field, target := range object(at(descriptor, "fields")) {
		if err := o.recordClosure(path+"."+field, o.domains[text(target)], depth+1); err != nil {
			return err
		}
	}
	return nil
}
func (o *materializationOffer) openClosure(path string) {
	for key := range o.closed {
		if materializationOfferContains(path, key) {
			delete(o.closed, key)
		}
	}
	ancestors := make([]string, 0, len(o.closed))
	for key := range o.closed {
		if materializationOfferContains(key, path) {
			ancestors = append(ancestors, key)
		}
	}
	tokens := materializationOfferTokens(path)
	for _, ancestor := range ancestors {
		o.openClosureAncestor(ancestor, tokens)
	}
}

func (o *materializationOffer) closureOverlay(overlay, expression any) error {
	path := stringAt(overlay, "path")
	if stringAt(overlay, "closure") == "closed-world" {
		if o.closed[path] == nil {
			o.closed[path] = map[string]bool{}
		}
		tokens := materializationOfferTokens(path)
		for _, binding := range array(at(expression, "bindings")) {
			child := materializationOfferTokens(stringAt(binding, "path"))
			if materializationOfferContains(path, stringAt(binding, "path")) && len(child) > len(tokens) && !strings.HasPrefix(child[len(tokens)], "[") {
				o.closed[path][child[len(tokens)]] = true
			}
		}
	} else {
		o.openClosure(path)
	}
	return nil
}

func (o *materializationOffer) openClosureAncestor(ancestor string, tokens []string) {
	current := materializationOfferTokens(ancestor)
	remaining := tokens[len(current):]
	for index, token := range remaining {
		key := materializationOfferPath(current)
		if o.closed[key] == nil {
			o.closed[key] = map[string]bool{}
		}
		if !strings.HasPrefix(token, "[") {
			o.closed[key][token] = true
		}
		current = append(current, token)
		if index < len(remaining)-1 {
			key = materializationOfferPath(current)
			if o.closed[key] == nil {
				o.closed[key] = map[string]bool{}
			}
		}
	}
}

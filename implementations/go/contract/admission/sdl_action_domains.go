package admission

import (
	"encoding/json"
	"math/big"
	"slices"
	"strings"
	"unicode/utf8"
)

const (
	sdlArgumentReference = "reference"
	sdlArgumentMaximum   = "maximum"
	sdlArgumentMinimum   = "minimum"
)

func sdlActionArgument(v any) error {
	if !nonblankSDLFields(v, "normalization_disclosure_ref", "omission_disclosure_ref", "loss_disclosure_ref") || at(v, "default_disclosure_ref") != nil && sdlBlank(stringAt(v, "default_disclosure_ref")) {
		return invalid()
	}
	if err := sdlArgumentBounds(v); err != nil {
		return err
	}
	allowed, err := sdlArgumentValues(v, array(at(v, "allowed_values")), true)
	if err != nil {
		return err
	}
	value := at(v, termDefault)
	if stringAt(v, "omission") != "use_default" {
		return require(value == nil && at(v, "default_disclosure_ref") == nil)
	}
	if value == nil || at(v, "default_disclosure_ref") == nil {
		return invalid()
	}
	return sdlArgumentDefault(v, value, allowed)
}

func sdlArgumentDefault(v, value any, allowed map[string]bool) error {
	values := []any{value}
	if text(defaultMember(v, "cardinality", "one")) == "many" {
		var ok bool
		values, ok = value.([]any)
		if !ok || !sdlArgumentLength(v, len(values), "min_items", "max_items") {
			return invalid()
		}
	} else if array(value) != nil {
		return invalid()
	}
	keys, err := sdlArgumentValues(v, values, boolean(defaultMember(v, "unique_items", true)))
	if err != nil {
		return err
	}
	return require(len(allowed) == 0 || equalSubset(keys, allowed))
}

func sdlArgumentBounds(v any) error {
	kind := stringAt(v, "value_type")
	for _, pair := range [][2]string{{sdlArgumentMinimum, sdlArgumentMaximum}, {"min_length", "max_length"}, {"min_items", "max_items"}} {
		minimum, maximum := at(v, pair[0]), at(v, pair[1])
		present := minimum != nil || maximum != nil
		if present && !sdlArgumentBoundAllowed(v, pair[0]) {
			return invalid()
		}
		if minimum != nil && maximum != nil {
			if order, ok := referenceNumberCompare(minimum, maximum); !ok || order > 0 {
				return invalid()
			}
		}
	}
	return require(kind != sdlArgumentReference || stringAt(v, "normalization") == "identity")
}

func sdlArgumentBoundAllowed(v any, field string) bool {
	kind := stringAt(v, "value_type")
	switch field {
	case sdlArgumentMinimum:
		return kind == termInteger || kind == typeNumber
	case "min_length":
		return kind == typeString || kind == sdlArgumentReference
	default:
		return text(defaultMember(v, "cardinality", "one")) == "many"
	}
}

func sdlArgumentLength(v any, length int, low, high string) bool {
	for _, bound := range []struct {
		name string
		low  bool
	}{{low, true}, {high, false}} {
		if at(v, bound.name) == nil {
			continue
		}
		n, ok := number(at(v, bound.name))
		if !ok || !n.IsInt() {
			return false
		}
		order := n.Num().Cmp(big.NewInt(int64(length)))
		if bound.low && order > 0 || !bound.low && order < 0 {
			return false
		}
	}
	return true
}

func sdlArgumentValues(v any, values []any, unique bool) (map[string]bool, error) {
	keys := map[string]bool{}
	for _, value := range values {
		key, err := sdlArgumentValue(v, value)
		if err != nil || unique && keys[key] {
			return nil, invalid()
		}
		keys[key] = true
	}
	return keys, nil
}

func sdlArgumentValue(v, value any) (string, error) {
	kind := stringAt(v, "value_type")
	if !scalarMatches(value, kind) {
		return "", invalid()
	}
	if s, ok := value.(string); ok {
		if stringAt(v, "normalization") == "trim" {
			s = strings.TrimFunc(s, sdlWhitespace)
		}
		return "s:" + s, require(sdlArgumentLength(v, utf8.RuneCountInString(s), "min_length", "max_length"))
	}
	if n, ok := value.(json.Number); ok {
		return sdlArgumentNumber(v, n)
	}
	if boolean(value) {
		return "b:true", nil
	}
	return "b:false", nil
}

func sdlArgumentNumber(v any, value json.Number) (string, error) {
	floating := strings.ContainsAny(string(value), ".eE")
	if stringAt(v, "value_type") == termInteger && floating {
		return "", invalid()
	}
	for _, bound := range []string{sdlArgumentMinimum, sdlArgumentMaximum} {
		if at(v, bound) == nil {
			continue
		}
		order, valid := referenceNumberCompare(value, at(v, bound))
		if !valid || bound == sdlArgumentMinimum && order < 0 || bound == sdlArgumentMaximum && order > 0 {
			return "", invalid()
		}
	}
	number, valid := referenceNumber(value)
	if !valid {
		return "", invalid()
	}
	prefix := "i:"
	if floating {
		prefix = "f:"
	}
	return prefix + number.RatString(), nil
}

func sdlInteraction(v any) error {
	if !nonblankSDLFields(v, "target", "rationale") || at(v, "merge_rule_ref") != nil && (sdlBlank(stringAt(v, "merge_rule_ref")) || boolean(at(v, "commutative"))) {
		return invalid()
	}
	for _, field := range []string{"related_actions", "shared_state_refs"} {
		if slices.ContainsFunc(stringsOf(at(v, field)), sdlBlank) {
			return invalid()
		}
	}
	field := "shared_state_refs"
	if kind := stringAt(v, "interaction_class"); kind == "coordination" || kind == "interference" {
		field = "related_actions"
	}
	return require(len(array(at(v, field))) > 0)
}

package admission

import (
	"encoding/json"
	"math/big"
	"slices"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// A native fragment owner without a published definition is a closed object.
// These checks port the declared member types of such an owner. A string
// length counts Unicode code points, as the reference models do.

// nativeCheck checks one member value of a native fragment.
type nativeCheck func(any) bool

// nativeShape is a closed native object. Each required member is present,
// each present member passes its check and no other member occurs. An absent
// optional member takes its default.
type nativeShape struct {
	required map[string]nativeCheck
	optional map[string]nativeCheck
}

func (s nativeShape) holds(v any) bool {
	members := object(v)
	if members == nil {
		return false
	}
	for name, check := range s.required {
		member, present := members[name]
		if !present || !check(member) {
			return false
		}
	}
	for name, member := range members {
		if _, required := s.required[name]; required {
			continue
		}
		check, known := s.optional[name]
		if !known || !check(member) {
			return false
		}
	}
	return true
}

// textOf accepts a string of at least the minimum length.
func textOf(minimum int) nativeCheck {
	return func(v any) bool {
		s, ok := v.(string)
		return ok && utf8.RuneCountInString(s) >= minimum
	}
}

// listOf accepts a list of at least the minimum length whose items pass.
func listOf(minimum int, item nativeCheck) nativeCheck {
	return func(v any) bool {
		rows, ok := v.([]any)
		if !ok || len(rows) < minimum {
			return false
		}
		for _, row := range rows {
			if !item(row) {
				return false
			}
		}
		return true
	}
}

// uniqueListOf accepts a list of passing items with unique canonical forms.
func uniqueListOf(minimum int, item nativeCheck) nativeCheck {
	return func(v any) bool { return listOf(minimum, item)(v) && uniqueValues(v) }
}

// integerWithin accepts an integer in the closed interval. A nil bound is
// absent.
func integerWithin(minimum, maximum *big.Rat) nativeCheck {
	return func(v any) bool {
		n, ok := number(v)
		return ok && n.IsInt() && (minimum == nil || n.Cmp(minimum) >= 0) && (maximum == nil || n.Cmp(maximum) <= 0)
	}
}

func integerFrom(minimum int64) nativeCheck { return integerWithin(big.NewRat(minimum, 1), nil) }

func isBoolean(v any) bool {
	_, ok := v.(bool)
	return ok
}

func isObject(v any) bool { return object(v) != nil }

// oneOfTerms accepts one of the strings.
func oneOfTerms(terms ...string) nativeCheck {
	return func(v any) bool {
		s, ok := v.(string)
		return ok && slices.Contains(terms, s)
	}
}

// orNull also accepts JSON null.
func orNull(check nativeCheck) nativeCheck {
	return func(v any) bool { return v == nil || check(v) }
}

// anyOfChecks accepts a value that passes one of the checks.
func anyOfChecks(checks ...nativeCheck) nativeCheck {
	return func(v any) bool {
		for _, check := range checks {
			if check(v) {
				return true
			}
		}
		return false
	}
}

// prefixedDigest accepts the published prefixed digest forms.
func prefixedDigest(v any) bool {
	s, ok := v.(string)
	return ok && digest.Valid(s)
}

// definitionCheck accepts an object that the published definition admits.
func (e *Validator) definitionCheck(contract, name string) nativeCheck {
	return func(v any) bool {
		if object(v) == nil {
			return false
		}
		data, err := json.Marshal(v)
		return err == nil && e.checkModelFragment(contract, schemaDefinitionsPrefix+name, data, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) == nil
	}
}

// taggedCheck accepts an object whose tag member selects a passing check.
// The tag is required, as in a discriminated union of the reference model.
func taggedCheck(tag string, alternatives map[string]nativeCheck) nativeCheck {
	return func(v any) bool {
		kind, ok := object(v)[tag].(string)
		check, known := alternatives[kind]
		return ok && known && check(v)
	}
}

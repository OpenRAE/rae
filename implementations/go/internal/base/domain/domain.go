// Package domain owns the closed bounded scalar-domain algebra. Selection
// policy, record traversal and witness generation belong to their callers.
package domain

import (
	"encoding/json"
	"math"
	"math/big"
	"reflect"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/softwareversion"
)

// ErrInput reports an invalid domain descriptor.
var ErrInput = fault.New(fault.InvalidInput, "bounded-domain", nil)

// ErrValue reports an interval value outside the reference numeric range.
var ErrValue = fault.New(fault.InvalidInput, "bounded-domain-value", nil)

// Domain is a closed domain descriptor, validated before use.
type Domain interface {
	Validate() error
	Contains(value any) bool
	domain()
}

// In validates a descriptor and checks scalar membership.
func In(value any, descriptor Domain) (bool, error) {
	if descriptor == nil || reflect.ValueOf(descriptor).Kind() == reflect.Pointer && reflect.ValueOf(descriptor).IsNil() {
		return false, ErrInput
	}
	if err := descriptor.Validate(); err != nil {
		return false, err
	}
	switch interval := descriptor.(type) {
	case Interval:
		return interval.membership(value)
	case *Interval:
		return interval.membership(value)
	default:
		return descriptor.Contains(value), nil
	}
}

const (
	integerKind = "integer"
	numberKind  = "number"
)

type scalar struct {
	kind string
	data any
}

func scalarOf(value any) scalar {
	switch v := value.(type) {
	case bool:
		return scalar{"boolean", v}
	case string:
		return scalar{"string", v}
	case int:
		return scalar{integerKind, strconv.Itoa(v)}
	case int64:
		return scalar{integerKind, strconv.FormatInt(v, 10)}
	case *big.Int:
		if v != nil {
			return scalar{integerKind, v.String()}
		}
	case float64:
		if !math.IsNaN(v) && !math.IsInf(v, 0) {
			return scalar{numberKind, v}
		}
	case json.Number:
		return numberScalar(v)
	}
	return scalar{}
}

func numberScalar(number json.Number) scalar {
	text := string(number)
	if text == "" || strings.TrimSpace(text) != text || !json.Valid([]byte(text)) {
		return scalar{}
	}
	if strings.ContainsAny(text, ".eE") {
		parsed, err := strconv.ParseFloat(text, 64)
		if err == nil {
			return scalar{numberKind, parsed}
		}
		return scalar{}
	}
	if len(strings.TrimPrefix(text, "-")) <= 4300 {
		if integer, ok := new(big.Int).SetString(text, 10); ok {
			return scalar{integerKind, integer.String()}
		}
	}
	return scalar{}
}

// Equal compares JSON scalars by type and value: true, 1 and 1.0 differ.
func Equal(first, second any) bool {
	left, right := scalarOf(first), scalarOf(second)
	return left.kind != "" && left == right
}

// Exact is the singleton scalar domain.
type Exact struct{ Value any }

func (Exact) domain() {
	// Seal the descriptor algebra; only this package defines domain variants.
}

// Validate checks the domain invariant.
func (d Exact) Validate() error {
	if scalarOf(d.Value).kind == "" {
		return ErrInput
	}
	return nil
}

// Contains reports scalar membership.
func (d Exact) Contains(value any) bool { return Equal(value, d.Value) }

// Enumeration is a nonempty set of distinct typed JSON scalars.
type Enumeration struct{ Values []any }

func (Enumeration) domain() {
	// Seal the descriptor algebra; only this package defines domain variants.
}

// Validate checks the domain invariant.
func (d Enumeration) Validate() error {
	if len(d.Values) == 0 {
		return ErrInput
	}
	seen := map[scalar]bool{}
	for _, value := range d.Values {
		item := scalarOf(value)
		if item.kind == "" || seen[item] {
			return ErrInput
		}
		seen[item] = true
	}
	return nil
}

// Contains reports scalar membership.
func (d Enumeration) Contains(value any) bool {
	for _, item := range d.Values {
		if Equal(value, item) {
			return true
		}
	}
	return false
}

// Boolean admits both booleans, or the selected boolean when Value is set.
type Boolean struct{ Value *bool }

func (Boolean) domain() {
	// Seal the descriptor algebra; only this package defines domain variants.
}

// Validate checks the domain invariant.
func (Boolean) Validate() error { return nil }

// Contains reports scalar membership.
func (d Boolean) Contains(value any) bool {
	boolean, ok := value.(bool)
	return ok && (d.Value == nil || boolean == *d.Value)
}

// Null is the singleton JSON null domain.
type Null struct{}

func (Null) domain() {
	// Seal the descriptor algebra; only this package defines domain variants.
}

// Validate checks the domain invariant.
func (Null) Validate() error { return nil }

// Contains reports scalar membership.
func (Null) Contains(value any) bool { return value == nil }

// NumericType is the declared numeric type of an interval.
type NumericType uint8

// The closed numeric types.
const (
	Integer NumericType = 1
	Number  NumericType = 2
)

// Interval is a bounded numeric interval. Endpoints follow the reference
// float64 domain; integer values retain their own type until membership.
type Interval struct {
	Type                     NumericType
	Lower, Upper             float64
	LowerClosed, UpperClosed bool
}

func (Interval) domain() {
	// Seal the descriptor algebra; only this package defines domain variants.
}

// Validate checks the domain invariant.
func (d Interval) Validate() error {
	if d.Type != Integer && d.Type != Number || math.IsNaN(d.Lower) || math.IsNaN(d.Upper) ||
		math.IsInf(d.Lower, 0) || math.IsInf(d.Upper, 0) || d.Lower > d.Upper {
		return ErrInput
	}
	if d.Type == Integer && (math.Trunc(d.Lower) != d.Lower || math.Trunc(d.Upper) != d.Upper) {
		return ErrInput
	}
	if d.Lower == d.Upper && (!d.LowerClosed || !d.UpperClosed) {
		return ErrInput
	}
	return nil
}

// Contains reports scalar membership.
func (d Interval) Contains(value any) bool {
	member, _ := d.membership(value)
	return member
}

func (d Interval) membership(value any) (bool, error) {
	item := scalarOf(value)
	if item.kind != integerKind && item.kind != numberKind || d.Type == Integer && item.kind != integerKind {
		return false, nil
	}
	var number float64
	if item.kind == integerKind {
		text, _ := item.data.(string)
		var err error
		number, err = strconv.ParseFloat(text, 64)
		if err != nil {
			return false, ErrValue
		}
	} else {
		number, _ = item.data.(float64)
	}
	return (number > d.Lower || number == d.Lower && d.LowerClosed) &&
		(number < d.Upper || number == d.Upper && d.UpperClosed), nil
}

// References admits names in one nonempty governed set.
type References struct {
	Authority string
	Allowed   []string
}

func (References) domain() {
	// Seal the descriptor algebra; only this package defines domain variants.
}

// Validate checks the domain invariant.
func (d References) Validate() error {
	if d.Authority == "" || len(d.Allowed) == 0 {
		return ErrInput
	}
	seen := map[string]bool{}
	for _, name := range d.Allowed {
		if name == "" || seen[name] {
			return ErrInput
		}
		seen[name] = true
	}
	return nil
}

// Contains reports scalar membership.
func (d References) Contains(value any) bool {
	text, ok := value.(string)
	if !ok {
		return false
	}
	return slices.Contains(d.Allowed, text)
}

// Record describes a product; its owner resolves named fields and traversal.
// It is deliberately never a scalar member.
type Record struct {
	Fields map[string]string
	Extra  bool
}

func (Record) domain() {
	// Seal the descriptor algebra; only this package defines domain variants.
}

// Contains reports scalar membership.
func (Record) Contains(any) bool { return false }

// Validate checks the domain invariant.
func (d Record) Validate() error {
	if len(d.Fields) == 0 {
		return ErrInput
	}
	for name, target := range d.Fields {
		if name == "" || target == "" {
			return ErrInput
		}
	}
	return nil
}

// Version exposes membership of an already validated installed version domain.
type Version struct{ Domain softwareversion.Domain }

func (Version) domain() {
	// Seal the descriptor algebra; only this package defines domain variants.
}

// Validate checks the domain invariant.
func (d Version) Validate() error {
	return d.Domain.Validate()
}

// Contains reports scalar membership.
func (d Version) Contains(value any) bool {
	return d.Domain.Membership(value) == softwareversion.Conformant
}

package domain

import (
	"encoding/json"
	"errors"
	"math"
	"math/big"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/softwareversion"
)

func TestTypedScalarMembershipAndIntervalBoundaries(t *testing.T) {
	falseValue := false
	relation, err := softwareversion.Installed("numeric-triplet")
	if err != nil {
		t.Fatal(err)
	}
	lower := "1.0.0"
	version, err := softwareversion.NewDomain(relation, &lower, nil, true, true)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		domain Domain
		value  any
		want   bool
	}{
		{Exact{Value: 1}, 1, true}, {Exact{Value: 1}, true, false},
		{Exact{Value: 1}, 1.0, false}, {Exact{Value: 1.0}, json.Number("1e0"), true},
		{Exact{Value: "a"}, "a", true}, {Exact{Value: 0}, json.Number("-0"), true},
		{Exact{Value: big.NewInt(42)}, json.Number("42"), true},
		{Enumeration{Values: []any{true, 1, 1.0}}, json.Number("1"), true},
		{Enumeration{Values: []any{true, "a"}}, false, false},
		{Boolean{}, true, true}, {Boolean{}, 1, false},
		{Boolean{Value: &falseValue}, true, false}, {Boolean{Value: &falseValue}, false, true},
		{Null{}, nil, true}, {Null{}, false, false},
		{Interval{Type: Integer, Lower: 0, Upper: 2, LowerClosed: true, UpperClosed: true}, 0, true},
		{Interval{Type: Integer, Lower: 0, Upper: 2, LowerClosed: true, UpperClosed: true}, 2, true},
		{Interval{Type: Integer, Lower: 0, Upper: 2, LowerClosed: true, UpperClosed: true}, 1.0, false},
		{Interval{Type: Number, Lower: 0, Upper: 2}, 0, false},
		{Interval{Type: Number, Lower: 0, Upper: 2}, 2, false},
		{Interval{Type: Number, Lower: 0, Upper: 2}, 1.5, true},
		{Interval{Type: Number, Lower: 0, Upper: 2}, true, false},
		{References{Authority: "urn:a", Allowed: []string{"x"}}, "x", true},
		{References{Authority: "urn:a", Allowed: []string{"x"}}, "y", false},
		{References{Authority: "urn:a", Allowed: []string{"x"}}, 1, false},
		{Record{Fields: map[string]string{"a": "other"}}, map[string]any{"a": 1}, false},
		{Version{Domain: version}, "2.0.0", true}, {Version{Domain: version}, "0.0.0", false},
	} {
		got, err := In(test.value, test.domain)
		if err != nil || got != test.want {
			t.Errorf("In(%v, %T) = %t, %v, want %t", test.value, test.domain, got, err, test.want)
		}
	}
}

func TestInvalidDomainsFailBeforeMembership(t *testing.T) {
	var absent *Exact
	for _, descriptor := range []Domain{
		nil, absent, Exact{Value: struct{}{}}, Exact{Value: math.NaN()},
		Exact{Value: json.Number("1e400")}, Exact{Value: json.Number("01")},
		Enumeration{}, Enumeration{Values: []any{1, 1}},
		Enumeration{Values: []any{struct{}{}}},
		Interval{Type: 0, Lower: 0, Upper: 1},
		Interval{Type: Integer, Lower: 0.5, Upper: 1},
		Interval{Type: Integer, Lower: 0, Upper: 1.5},
		Interval{Type: Number, Lower: 2, Upper: 1},
		Interval{Type: Number, Lower: 1, Upper: 1},
		Interval{Type: Number, Lower: math.NaN(), Upper: 1},
		Interval{Type: Number, Lower: 0, Upper: math.Inf(1)},
		References{}, References{Authority: "a", Allowed: []string{""}},
		References{Authority: "a", Allowed: []string{"x", "x"}},
		Record{}, Record{Fields: map[string]string{"": "a"}}, Record{Fields: map[string]string{"a": ""}},
		Version{},
	} {
		if _, err := In(1, descriptor); err == nil {
			t.Errorf("In(invalid %T) error = nil, want a refusal", descriptor)
		}
	}
	if !errors.Is((Interval{Type: Number, Lower: math.Inf(-1)}).Validate(), ErrInput) {
		t.Error("unbounded numeric interval was accepted")
	}
	if Equal(nil, nil) || Equal(json.Number("true"), true) || Equal(json.Number(" 1"), 1) {
		t.Error("scalar equality accepted a value outside its closed scalar types")
	}
}

func TestIntervalOverflowIsARefusalRatherThanNonmembership(t *testing.T) {
	interval := Interval{Type: Number, Lower: 0, Upper: 1, LowerClosed: true, UpperClosed: true}
	huge := new(big.Int).Exp(big.NewInt(10), big.NewInt(400), nil)
	for _, descriptor := range []Domain{interval, &interval} {
		if _, err := In(huge, descriptor); !errors.Is(err, ErrValue) {
			t.Errorf("In(overflowing integer) = %v, want numeric refusal", err)
		}
		if member, err := In(1, descriptor); err != nil || !member {
			t.Errorf("In(upper boundary) = %t, %v, want a member", member, err)
		}
	}
	if interval.Contains(huge) {
		t.Error("unchecked membership accepted an overflowing integer")
	}
}

func TestScalarIntegerDigitAndSingletonIntervalBoundaries(t *testing.T) {
	text := strings.Repeat("9", 4300)
	integer, ok := new(big.Int).SetString(text, 10)
	if !ok || !Equal(json.Number(text), integer) {
		t.Error("the maximum reference integer lost scalar identity")
	}
	if _, err := In(1, Interval{Type: Number, Lower: 1, Upper: 1, LowerClosed: true, UpperClosed: true}); err != nil {
		t.Errorf("closed singleton interval was refused: %v", err)
	}
}

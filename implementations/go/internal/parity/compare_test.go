package parity

import (
	"encoding/json"
	"math/big"
	"testing"
)

func TestCompareResultsPreservesExactNumbers(t *testing.T) {
	for _, test := range []struct {
		want, got string
		equal     bool
	}{
		{`{"n":9007199254740992}`, `{"n":9007199254740993}`, false},
		{`-9007199254740992`, `-9007199254740993`, false},
		{`0.10000000000000001`, `0.1`, false},
		{`1.01e10000`, `1.02e10000`, false},
		{`1e100000000000000000000`, `1e100000000000000000001`, false},
		{`1e100`, `1.00000000000000001e100`, false},
		{`-12.3400`, `-1234e-2`, true},
		{`10`, `1e+1`, true},
		{`1.0`, `1`, true},
		{`-0e999999999999999999999`, `0.000`, true},
		{`1e999999999999999999999`, `10e999999999999999999998`, true},
		{`{"a":[true,null,1],"b":"1"}`, `{"b":"1","a":[true,null,1.0]}`, true},
		{`"1"`, `1`, false},
		{`-1`, `1`, false},
		{`1`, `2`, false},
		{`0.1`, `1`, false},
		{`0.1`, `0.01`, false},
		{`0`, `1`, false},
		{`12`, `120`, false},
		{`1E+2`, `100`, true},
		{`0.0012`, `12e-4`, true},
		{`null`, `{}`, false},
	} {
		t.Run(test.want+"/"+test.got, func(t *testing.T) {
			diff, err := compareResults(json.RawMessage(test.want), json.RawMessage(test.got))
			if err != nil {
				t.Fatalf("compareResults() error = %v", err)
			}
			if equal := diff == ""; equal != test.equal {
				t.Errorf("compareResults() equal = %t, want %t; diff: %s", equal, test.equal, diff)
			}
		})
	}
}

func TestCompareResultsRejectsInvalidJSON(t *testing.T) {
	for _, input := range []string{"", "{", "1 2", "1 garbage", "NaN", "1e", "01"} {
		for _, values := range [][2]string{{input, "1"}, {"1", input}} {
			if _, err := compareResults(json.RawMessage(values[0]), json.RawMessage(values[1])); err == nil {
				t.Errorf("compareResults(%q, %q) error = nil, want error", values[0], values[1])
			}
		}
	}
}

// Check normalization against an independent standard-library numeric parser.
// Equality-only tests can miss a transformation that shifts both operands by
// the same erroneous scale while still comparing them consistently.
func TestCanonicalNumberPreservesDecimalValue(t *testing.T) {
	for _, number := range []string{"0", "-0", "10", "1200", "-12.3400", "0.00120", "1e10", "1e-10", "9007199254740993"} {
		original, ok := new(big.Rat).SetString(number)
		if !ok {
			t.Fatalf("invalid test number %q", number)
		}
		normalized := canonicalNumber(json.Number(number))
		actual, ok := new(big.Rat).SetString(normalized)
		if !ok {
			t.Fatalf("canonicalNumber(%q) = %q, want a decimal number", number, normalized)
		}
		if actual.Cmp(original) != 0 {
			t.Errorf("canonicalNumber(%q) = %q, want the same numeric value", number, normalized)
		}
	}
}

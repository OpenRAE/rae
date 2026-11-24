package authoring

import (
	"math/big"
	"strconv"
	"strings"
	"testing"
)

func TestDurationDecimalContext(t *testing.T) {
	// Python's default Decimal context has precision 28, half-even ties,
	// Emin=-999999, Emax=999999 and Etiny=-1000026.
	cases := []struct{ name, input, want string }{
		{"even-low", "1000000000000000000000000000.5", "1000000000000000000000000000"},
		{"even-high", "1000000000000000000000000001.5", "1000000000000000000000000002"},
		{"subnormal-tie-zero", "5e-1000027", "0"},
		{"subnormal-tie-two", "15e-1000027", "2e-1000026"},
		{"maximum-exponent", "1e999999", "1e999999"},
		{"overflow", "1e1000000", ""},
		{"carry-overflow", "9.9999999999999999999999999995e999999", ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			value := contextTestValue(t, c.input)
			err := roundDurationDecimal(value)
			if c.want == "" {
				if err == nil {
					t.Fatal("context admitted overflow")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			expected := contextTestValue(t, c.want)
			if value.Cmp(expected) != 0 {
				t.Fatal("decimal context result differs")
			}
		})
	}
}

func contextTestValue(t *testing.T, text string) *big.Rat {
	t.Helper()
	if value, ok := new(big.Rat).SetString(text); ok {
		return value
	}
	coefficient, power, scientific := strings.Cut(text, "e")
	exponent, err := strconv.Atoi(power)
	numerator, ok := new(big.Int).SetString(coefficient, 10)
	if !scientific || err != nil || !ok || exponent >= 0 {
		t.Fatal("invalid decimal context test value")
	}
	denominator := new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(-exponent)), nil)
	return new(big.Rat).SetFrac(numerator, denominator)
}

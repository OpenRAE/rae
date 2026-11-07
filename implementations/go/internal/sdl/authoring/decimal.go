package authoring

import (
	"encoding/json"
	"math/big"
	"strings"
)

// Compound durations use Python's default Decimal context. The parser supplies
// only nonnegative finite decimals; source limits bound their coefficient size.
func roundDurationDecimal(value *big.Rat) error {
	if value.Sign() == 0 {
		return nil
	}
	if value.Sign() < 0 {
		return invalid()
	}
	order := durationDecimalOrder(value)
	if order > 999999 {
		return invalid()
	}
	// Etiny = Emin - precision + 1. Subnormal rounding uses this same quantum.
	step := max(order-27, -1000026)
	power := decimalPower(max(step, -step))
	numerator := new(big.Int).Set(value.Num())
	denominator := new(big.Int).Set(value.Denom())
	if step >= 0 {
		denominator.Mul(denominator, power)
	} else {
		numerator.Mul(numerator, power)
	}
	quotient, remainder := new(big.Int), new(big.Int)
	quotient.QuoRem(numerator, denominator, remainder)
	half := new(big.Int).Lsh(remainder, 1).Cmp(denominator)
	if half > 0 || half == 0 && quotient.Bit(0) != 0 {
		quotient.Add(quotient, big.NewInt(1))
	}
	if quotient.Sign() > 0 && len(quotient.String())-1+step > 999999 {
		return invalid()
	}
	if step >= 0 {
		value.SetInt(quotient.Mul(quotient, power))
	} else {
		value.SetFrac(quotient, power)
	}
	return nil
}
func durationDecimalOrder(value *big.Rat) int {
	order := len(value.Num().String()) - len(value.Denom().String())
	left, right := value.Num(), value.Denom()
	if order >= 0 {
		right = new(big.Int).Mul(right, decimalPower(order))
	} else {
		left = new(big.Int).Mul(left, decimalPower(-order))
	}
	if left.Cmp(right) < 0 {
		order--
	}
	return order
}
func decimalPower(exponent int) *big.Int {
	return new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(exponent)), nil)
}
func ceilDuration(value *big.Rat) any {
	quotient, remainder := new(big.Int), new(big.Int)
	quotient.QuoRem(value.Num(), value.Denom(), remainder)
	if remainder.Sign() != 0 {
		quotient.Add(quotient, big.NewInt(1))
	}
	return json.Number(quotient.String())
}

// The standard Rat text parser caps decimal exponents at one million. The
// source profile admits fractions beyond that bound, so construct the fraction
// directly from its bounded decimal coefficient and fractional digit count.
func parseDurationDecimal(value string) (*big.Rat, error) {
	whole, fraction, _ := strings.Cut(value, ".")
	digits := strings.TrimLeft(whole+fraction, "0")
	if digits == "" {
		return new(big.Rat), nil
	}
	coefficient, ok := new(big.Int).SetString(digits, 10)
	if !ok {
		return nil, invalid()
	}
	return new(big.Rat).SetFrac(coefficient, decimalPower(len(fraction))), nil
}

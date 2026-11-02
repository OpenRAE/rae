package parity

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"strings"

	"github.com/google/go-cmp/cmp"
)

// compareResults compares JSON values with exact decimal numeric equality.
func compareResults(want, got json.RawMessage) (string, error) {
	expected, err := decodeResult(want)
	if err != nil {
		return "", fmt.Errorf("recorded result: %w", err)
	}
	actual, err := decodeResult(got)
	if err != nil {
		return "", fmt.Errorf("runner result: %w", err)
	}
	return cmp.Diff(expected, actual, cmp.Comparer(func(a, b json.Number) bool {
		return canonicalNumber(a) == canonicalNumber(b)
	})), nil
}

func decodeResult(result json.RawMessage) (any, error) {
	decoder := json.NewDecoder(bytes.NewReader(result))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return nil, err
	}
	if _, err := decoder.Token(); !errors.Is(err, io.EOF) {
		return nil, errors.New("data follows the JSON value")
	}
	return value, nil
}

// canonicalNumber normalizes a validated JSON number without expanding its
// exponent. The coefficient has no leading or trailing zeros, unless it is zero.
func canonicalNumber(number json.Number) string {
	mantissa, exponent, _ := strings.Cut(strings.ToLower(string(number)), "e")
	var power big.Int
	if exponent != "" {
		power.SetString(exponent, 10)
	}
	if integer, fraction, ok := strings.Cut(mantissa, "."); ok {
		mantissa = integer + fraction
		power.Sub(&power, big.NewInt(int64(len(fraction))))
	}
	negative := strings.HasPrefix(mantissa, "-")
	mantissa = strings.TrimLeft(strings.TrimPrefix(mantissa, "-"), "0")
	if mantissa == "" {
		return "0"
	}
	coefficient := strings.TrimRight(mantissa, "0")
	power.Add(&power, big.NewInt(int64(len(mantissa)-len(coefficient))))
	if negative {
		coefficient = "-" + coefficient
	}
	return coefficient + "e" + power.String()
}

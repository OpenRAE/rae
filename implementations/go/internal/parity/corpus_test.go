package parity

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"maps"
	"math/big"
	"os"
	"slices"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

// TestCorpus checks each command that has a runner against the corpus. It
// skips each command without a runner, so its output reports the commands
// that the Go implementation does not cover yet.
func TestCorpus(t *testing.T) {
	cases, err := Load(os.DirFS("testdata"))
	if err != nil {
		t.Fatalf("Load(testdata) error = %v", err)
	}
	byKey := map[string][]Case{}
	for _, c := range cases {
		byKey[c.Key()] = append(byKey[c.Key()], c)
	}
	registered := runners()
	if err := checkRunners(byKey, registered, os.Getenv("RAES_PARITY_COMPLETE") == "1"); err != nil {
		t.Fatal(err)
	}
	for key := range registered {
		if len(byKey[key]) == 0 {
			t.Errorf("runner %q has no case in the corpus", key)
		}
	}
	for _, key := range slices.Sorted(maps.Keys(byKey)) {
		t.Run(key, func(t *testing.T) {
			run, ok := registered[key]
			if !ok {
				t.Skipf("no Go runner covers the %d cases yet", len(byKey[key]))
			}
			checkCases(t, run, byKey[key])
		})
	}
}

// checkCases runs each case and compares its result with the recorded result.
func checkCases(t *testing.T, run Runner, cases []Case) {
	t.Helper()
	for _, c := range cases {
		t.Run(c.Name, func(t *testing.T) {
			got, err := run(t.Context(), c)
			if err != nil {
				t.Fatalf("run(%s) error = %v", c.Name, err)
			}
			if diff := cmp.Diff(decode(t, c.Result), decode(t, got)); diff != "" {
				t.Errorf("run(%s) result mismatch (-want +got):\n%s", c.Name, diff)
			}
		})
	}
}

// decode returns the JSON value of a result, so that results compare by value.
func decode(t *testing.T, result json.RawMessage) any {
	t.Helper()
	var value any
	decoder := json.NewDecoder(bytes.NewReader(result))
	decoder.UseNumber()
	if err := decoder.Decode(&value); err != nil {
		t.Fatalf("decode(%s) error = %v", result, err)
	}
	if _, err := decoder.Token(); !errors.Is(err, io.EOF) {
		t.Fatalf("decode(%s) accepted trailing data", result)
	}
	return exactNumbers(value)
}

// checkRunners binds shipped commands independently of the runner registry.
// Complete mode is the cutover gate: no recorded command may remain unported.
func checkRunners(cases map[string][]Case, registered map[string]Runner, complete bool) error {
	for _, key := range []string{"canonical encode", "randstream vector"} {
		if registered[key] == nil || len(cases[key]) == 0 {
			return fmt.Errorf("implemented command %q is missing its runner or cases", key)
		}
	}
	if complete {
		for key := range cases {
			if registered[key] == nil {
				return fmt.Errorf("cutover has no runner for %q", key)
			}
		}
	}
	return nil
}

// exactNumbers normalizes JSON numbers without a floating-point conversion.
func exactNumbers(value any) any {
	switch v := value.(type) {
	case json.Number:
		return exactNumber(string(v))
	case []any:
		for i, item := range v {
			v[i] = exactNumbers(item)
		}
	case map[string]any:
		for key, item := range v {
			v[key] = exactNumbers(item)
		}
	}
	return value
}

// exactNumber uses a coefficient and decimal exponent, without expanding the
// exponent. Even an enormous exponent costs only space proportional to its text.
func exactNumber(text string) json.Number {
	mantissa, exponent, _ := strings.Cut(strings.ToLower(text), "e")
	power := new(big.Int)
	if exponent != "" {
		power.SetString(exponent, 10) // The decoder validated the number syntax.
	}
	sign := ""
	if strings.HasPrefix(mantissa, "-") {
		sign = "-"
		mantissa = mantissa[1:]
	}
	whole, fraction, _ := strings.Cut(mantissa, ".")
	digits := strings.TrimLeft(whole+fraction, "0")
	if digits == "" {
		return json.Number("0")
	}
	trimmed := strings.TrimRight(digits, "0")
	shift := len(digits) - len(trimmed) - len(fraction)
	adjustment := big.NewInt(int64(shift))
	power.Add(power, adjustment)
	return json.Number(sign + trimmed + "e" + power.String())
}

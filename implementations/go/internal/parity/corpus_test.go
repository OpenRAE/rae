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
	if err := checkImplemented(registered); err != nil {
		t.Error(err)
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
			expected := expectedResult(t, c)
			if diff := cmp.Diff(decode(t, expected), decode(t, got), cmp.Comparer(equalNumber)); diff != "" {
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
		t.Fatalf("json.Unmarshal(%s) error = %v", result, err)
	}
	if _, err := decoder.Token(); !errors.Is(err, io.EOF) {
		t.Fatalf("decode(%s) has trailing data, want one JSON value", result)
	}
	return value
}

// implementedCommands is an independent inventory: deleting a runner must fail.
func implementedCommands() []string {
	return []string{
		"canonical encode", "randstream vector", "primitive ingress", "primitive uri",
		"primitive ingress-exception", "primitive pointer", "primitive tokens", "primitive address", "primitive render", "primitive plan-root",
	}
}

// equalNumber compares JSON numeric values exactly, including exponent notation.
func equalNumber(a, b json.Number) bool {
	x, ok := new(big.Rat).SetString(string(a))
	y, otherOK := new(big.Rat).SetString(string(b))
	return ok && otherOK && x.Cmp(y) == 0
}

func TestExactNumbers(t *testing.T) {
	for _, pair := range [][2]string{
		{"9007199254740992", "9007199254740993"},
		{"-9007199254740992", "-9007199254740993"},
		{"1.00000000000000001", "1"}, {"1e100", "1.00000000000000001e100"},
	} {
		if cmp.Equal(decode(t, []byte(pair[0])), decode(t, []byte(pair[1])), cmp.Comparer(equalNumber)) {
			t.Errorf("compare(%s, %s) = equal, want distinct numbers", pair[0], pair[1])
		}
	}
	for _, pair := range [][2]string{{"1", "1.0"}, {"1000", "1e3"}, {"0.01", "1e-2"}, {"-0", "0"}} {
		if !equalNumber(json.Number(pair[0]), json.Number(pair[1])) {
			t.Errorf("compare(%s, %s) = distinct, want equal numeric values", pair[0], pair[1])
		}
	}
}

func checkImplemented(registered map[string]Runner) error {
	for _, key := range implementedCommands() {
		if _, ok := registered[key]; !ok {
			return fmt.Errorf("runner %q is missing", key)
		}
	}
	return nil
}

func TestImplementedRunnerCannotDisappear(t *testing.T) {
	for _, key := range implementedCommands() {
		registered := runners()
		delete(registered, key)
		if err := checkImplemented(registered); err == nil {
			t.Errorf("checkImplemented(without %q) = nil, want missing runner", key)
		}
	}
}

func expectedResult(t *testing.T, c Case) json.RawMessage {
	t.Helper()
	expected := c.Result
	if c.Command == "ingress-exception" {
		var governed struct {
			Decision  string          `json:"decision"`
			Go        json.RawMessage `json:"go"`
			Reference json.RawMessage `json:"reference"`
		}
		if err := json.Unmarshal(expected, &governed); err != nil {
			t.Fatal(err)
		}
		if governed.Decision != "maintainer-1822-2026-11-02" || len(governed.Reference) == 0 {
			t.Fatal("compatibility case has no approved decision or reference outcome")
		}
		expected = governed.Go
	}
	return expected
}

package value

import (
	"encoding/json"
	"errors"
	"math"
	"math/big"
	"strings"
	"testing"
)

type unknownCarrier struct{ called *bool }

func (u unknownCarrier) MarshalJSON() ([]byte, error) {
	*u.called = true
	panic("must not invoke an unknown snapshot callback")
}

func TestCanonicalRefusesUnknownCarriersAndKeepsNumericKinds(t *testing.T) {
	called := false
	for _, payload := range []any{unknownCarrier{called: &called}, map[string]any{"x": unknownCarrier{called: &called}}} {
		if _, err := Canonical(payload, Default()); !errors.Is(err, ErrInput) || called {
			t.Errorf("Canonical(unknown carrier) error = %v, callback = %t, want refusal before callback", err, called)
		}
	}
	for _, test := range []struct {
		value any
		want  string
	}{
		{map[string]any{"b": 1.0, "a": "é"}, "{\"a\":\"é\",\"b\":1}"},
		{1e16, "10000000000000000"}, {json.Number("1e16"), "10000000000000000"},
		{big.NewInt(42), "42"}, {int64(-42), "-42"}, {json.Number("-0"), "0"},
		{[]any{true, nil, DeclaredDocument("body")}, "[true,null,\"body\"]"},
	} {
		got, err := Canonical(test.value, Default())
		if err != nil || string(got) != test.want {
			t.Errorf("Canonical(%v) = %s, %v, want %s", test.value, got, err, test.want)
		}
	}
}

func TestValueBudgetsCoverKeysTypesDepthAndCycles(t *testing.T) {
	defaults := Default()
	for _, value := range []any{math.NaN(), math.Inf(1), "\xff", map[string]any{"\xff": 1},
		json.Number("NaN"), json.Number("1e400"), json.Number("1 2"), json.Number(strings.Repeat("9", 4301)), (*big.Int)(nil)} {
		if err := Validate(value, defaults); !errors.Is(err, ErrInput) {
			t.Errorf("Validate(%T) error = %v, want invalid input", value, err)
		}
	}
	for _, test := range []struct {
		value  any
		change func(*Limits)
	}{
		{[]any{1}, func(l *Limits) { l.MaxNodes = 1 }},
		{[]any{1}, func(l *Limits) { l.MaxOperations = 1 }},
		{[]any{[]any{1}}, func(l *Limits) { l.MaxDepth = 1 }},
		{[]any{1, 2}, func(l *Limits) { l.MaxMembers = 1 }},
		{map[string]any{"a": 1, "b": 2}, func(l *Limits) { l.MaxMembers = 1 }},
		{"é", func(l *Limits) { l.MaxScalarBytes = 1 }},
		{map[string]any{"ab": 1}, func(l *Limits) { l.MaxScalarBytes = 1 }},
		{[]any{true, false}, func(l *Limits) { l.MaxTotalScalarBytes = 8 }},
	} {
		limits := defaults
		test.change(&limits)
		if err := Validate(test.value, limits); !errors.Is(err, ErrLimit) {
			t.Errorf("Validate(budget boundary) error = %v, want limit exceeded", err)
		}
	}
	cycle := map[string]any{}
	cycle["self"] = cycle
	if err := Validate(cycle, defaults); !errors.Is(err, ErrLimit) {
		t.Errorf("Validate(cycle) error = %v, want bounded refusal", err)
	}
	text := strings.Repeat("x", 1048577)
	if err := Validate(text, Runtime()); !errors.Is(err, ErrLimit) {
		t.Errorf("Validate(ordinary large scalar) error = %v, want scalar refusal", err)
	}
	if err := Validate(DeclaredDocument(text), Runtime()); err != nil {
		t.Errorf("Validate(declared document) error = %v, want accepted body allowance", err)
	}
	if Runtime().MaxNodes != 65536 || Plan().MaxNodes != 262144 || Plan().MaxScalarBytes != Runtime().MaxScalarBytes {
		t.Error("runtime/plan aggregate budgets differ from the published defaults")
	}
}

func TestLimitDefinitionsAndDocumentAllowanceBounds(t *testing.T) {
	for _, change := range []func(*Limits){
		func(l *Limits) { l.MaxDepth = 0 }, func(l *Limits) { l.MaxDepth = 1025 },
		func(l *Limits) { l.MaxNodes = 1000001 }, func(l *Limits) { l.MaxOperations = 4000001 },
		func(l *Limits) { l.MaxMembers = 100001 }, func(l *Limits) { l.MaxIdentityChecks = 1000001 },
		func(l *Limits) { l.MaxReferenceHops = 4097 }, func(l *Limits) { l.MaxDiagnostics = 257 },
		func(l *Limits) { l.MaxScalarBytes = 8*1048576 + 1 },
		func(l *Limits) { l.MaxTotalScalarBytes = 64*1048576 + 1 },
		func(l *Limits) { l.MaxDocumentScalarBytes = 1 },
		func(l *Limits) { l.MaxDocumentScalarBytes = 8*1048576 + 1 },
	} {
		limits := Default()
		change(&limits)
		if err := Validate(nil, limits); !errors.Is(err, ErrLimits) {
			t.Errorf("Validate(invalid limit definition) error = %v, want ErrLimits", err)
		}
	}
	limits := Runtime()
	limits.MaxDocumentScalarBytes = limits.MaxScalarBytes
	if err := limits.Validate(); err != nil {
		t.Errorf("lower document ceiling boundary = %v, want valid limits", err)
	}
	limits.MaxDocumentScalarBytes = limits.MaxTotalScalarBytes
	if err := limits.Validate(); err != nil {
		t.Errorf("upper document ceiling boundary = %v, want valid limits", err)
	}
}

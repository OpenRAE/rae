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

func TestEncodeKeepsExactIntegersOutsideTheCanonicalRange(t *testing.T) {
	called := false
	if _, err := Encode(map[string]any{"x": unknownCarrier{called: &called}}, Default()); !errors.Is(err, ErrInput) || called {
		t.Errorf("Encode(unknown carrier) error = %v, callback = %t, want refusal before callback", err, called)
	}
	large := map[string]any{"n": json.Number("1000000000000000000"), "b": big.NewInt(-9007199254740993)}
	got, err := Encode(large, Default())
	if err != nil || string(got) != `{"b":-9007199254740993,"n":1000000000000000000}` {
		t.Errorf("Encode(large integers) = %s, %v", got, err)
	}
	if _, err := Canonical(large, Default()); err == nil {
		t.Error("Canonical(large integers) error = nil, want the RFC 8785 range refusal")
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

func TestPublishedLimitDefinitionBoundaries(t *testing.T) {
	for _, test := range []struct {
		name    string
		maximum int
		set     func(*Limits, int)
	}{
		{"depth", 1024, func(l *Limits, v int) { l.MaxDepth = v }},
		{"nodes", 1000000, func(l *Limits, v int) { l.MaxNodes = v }},
		{"operations", 4000000, func(l *Limits, v int) { l.MaxOperations = v }},
		{"members", 100000, func(l *Limits, v int) { l.MaxMembers = v }},
		{"identity checks", 1000000, func(l *Limits, v int) { l.MaxIdentityChecks = v }},
		{"reference hops", 4096, func(l *Limits, v int) { l.MaxReferenceHops = v }},
		{"scalar bytes", 8388608, func(l *Limits, v int) { l.MaxScalarBytes = v }},
		{"total bytes", 67108864, func(l *Limits, v int) { l.MaxTotalScalarBytes = v }},
		{"diagnostics", 256, func(l *Limits, v int) { l.MaxDiagnostics = v }},
	} {
		for _, bound := range []int{0, 1, test.maximum, test.maximum + 1} {
			limits := Default()
			test.set(&limits, bound)
			wantValid := bound == 1 || bound == test.maximum
			if err := limits.Validate(); (err == nil) != wantValid {
				t.Errorf("%s=%d validation = %v, want valid=%t", test.name, bound, err, wantValid)
			}
		}
	}
	if Plan().MaxOperations != 1048576 || Runtime().MaxDocumentScalarBytes != 4194304 {
		t.Error("published plan operations or materialization ceiling changed")
	}
}

func TestValueBudgetExactFitsAndOverflowPrecedence(t *testing.T) {
	for _, test := range []struct {
		payload any
		change  func(*Limits)
	}{
		{[]any{1, 2}, func(l *Limits) { l.MaxNodes = 3 }},
		{[]any{1, 2}, func(l *Limits) { l.MaxOperations = 3 }},
		{map[string]any{"a": 1}, func(l *Limits) { l.MaxDepth = 1 }},
		{[]any{1, 2}, func(l *Limits) { l.MaxMembers = 2 }},
		{map[string]any{"a": 1, "b": 2}, func(l *Limits) { l.MaxMembers = 2 }},
		{"é", func(l *Limits) { l.MaxScalarBytes = 2 }},
		{[]any{"ab", "cd"}, func(l *Limits) { l.MaxTotalScalarBytes = 4 }},
		{map[string]any{"ab": "cd"}, func(l *Limits) { l.MaxTotalScalarBytes = 4 }},
	} {
		limits := Default()
		test.change(&limits)
		if err := Validate(test.payload, limits); err != nil {
			t.Errorf("Validate(exact fit) = %v, want accepted", err)
		}
	}
	limits := Default()
	limits.MaxNodes = 4
	called := false
	payload := []any{0, 0, []any{unknownCarrier{called: &called}}}
	if err := Validate(payload, limits); !errors.Is(err, ErrLimit) || called {
		t.Errorf("queued nodes over budget = %v, called=%t, want refusal before visiting child", err, called)
	}
	limits = Default()
	limits.MaxDepth = 1
	if err := Validate(map[string]any{"a": map[string]any{"b": 1}}, limits); !errors.Is(err, ErrLimit) {
		t.Errorf("map depth overflow = %v, want ErrLimit", err)
	}
}

func TestIntegerByteAccountingAndPreciseFloatCanonicalization(t *testing.T) {
	for _, test := range []struct {
		integer int64
		bytes   int
	}{
		{0, 1}, {255, 1}, {-255, 1}, {256, 2}, {65535, 2}, {65536, 3},
	} {
		for _, width := range []int{test.bytes, test.bytes + 1} {
			limits := Default()
			limits.MaxScalarBytes = width
			if err := Validate(test.integer, limits); err != nil {
				t.Errorf("integer %d in %d bytes = %v, want accepted", test.integer, width, err)
			}
		}
		if test.bytes > 1 {
			limits := Default()
			limits.MaxScalarBytes = test.bytes - 1
			if err := Validate(test.integer, limits); !errors.Is(err, ErrLimit) {
				t.Errorf("integer %d below byte width = %v, want ErrLimit", test.integer, err)
			}
		}
	}
	if err := Validate(json.Number(strings.Repeat("9", 4300)), Default()); err != nil {
		t.Errorf("4,300-digit integer was refused: %v", err)
	}
	got, err := Canonical(1.2345678901234567, Default())
	if err != nil || string(got) != "1.2345678901234567" {
		t.Errorf("precise float = %s, %v, want all reference digits", got, err)
	}
}

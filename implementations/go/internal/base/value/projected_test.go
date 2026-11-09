package value

import (
	"errors"
	"testing"
)

func TestValidateProjectedStopsBeforeVisitingOverDepthDefaults(t *testing.T) {
	limits := Default()
	limits.MaxDepth = 1
	calls := 0
	project := func(input any) (any, error) {
		calls++
		number, ok := input.(int)
		if !ok {
			return nil, ErrInput
		}
		return []any{number + 1}, nil
	}
	if err := ValidateProjected(0, limits, project); !errors.Is(err, ErrLimit) || calls != 2 {
		t.Fatalf("projected depth refusal = %v, calls = %d; want limit and two visited levels", err, calls)
	}
}

func TestValidateProjectedBoundsQueuedDefaultChildren(t *testing.T) {
	limits := Default()
	limits.MaxNodes = 3
	childCalls := 0
	project := func(input any) (any, error) {
		if input == "root" {
			return []any{"child", "child", "child"}, nil
		}
		childCalls++
		return input, nil
	}
	if err := ValidateProjected("root", limits, project); !errors.Is(err, ErrLimit) || childCalls != 0 {
		t.Fatalf("queued default refusal = %v, child calls = %d", err, childCalls)
	}
}

func TestValidateProjectedRetainsCarrierRefusalAndExplicitErrors(t *testing.T) {
	called := false
	project := func(any) (any, error) { return unknownCarrier{called: &called}, nil }
	if err := ValidateProjected(nil, Default(), project); !errors.Is(err, ErrInput) || called {
		t.Fatalf("unknown projected carrier = %v, method called = %t", err, called)
	}
	failure := errors.New("projection failed")
	if err := ValidateProjected(nil, Default(), func(any) (any, error) { return nil, failure }); !errors.Is(err, failure) {
		t.Fatalf("projection failure = %v", err)
	}
	if err := ValidateProjected(nil, Default(), nil); !errors.Is(err, ErrInput) {
		t.Fatalf("nil projection = %v", err)
	}
	limits := Default()
	limits.MaxNodes = 0
	if err := ValidateProjected(nil, limits, func(any) (any, error) { t.Fatal("invalid limits invoked projection"); return false, nil }); !errors.Is(err, ErrLimits) {
		t.Fatalf("invalid projected limits = %v", err)
	}
}

func TestValidateProjectedAcceptsShallowModelDefaults(t *testing.T) {
	type frame struct{ supplied string }
	input := frame{supplied: "authored"}
	project := func(input any) (any, error) {
		if row, ok := input.(frame); ok {
			return map[string]any{"supplied": row.supplied, "default": []any{}}, nil
		}
		return input, nil
	}
	if err := ValidateProjected(input, Default(), project); err != nil || input.supplied != "authored" {
		t.Fatalf("shallow model projection = %v, input = %v", err, input)
	}
}

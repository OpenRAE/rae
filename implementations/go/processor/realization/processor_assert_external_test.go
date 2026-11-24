package realization_test

import (
	"testing"
)

//nolint:ireturn // Each use returns its requested concrete test value.
func requireType[T any](t *testing.T, input any) T {
	t.Helper()
	result, ok := input.(T)
	if !ok {
		t.Fatalf("unexpected value type %T", input)
	}
	return result
}

func requireNoError(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}

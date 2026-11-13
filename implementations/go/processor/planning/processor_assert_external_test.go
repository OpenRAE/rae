package planning_test

import (
	"encoding/json"
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
func requireJSON(t *testing.T, input any) []byte {
	t.Helper()
	raw, err := json.Marshal(input)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}
func requireNoError(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}

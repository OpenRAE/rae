package realization

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

func requireTestRequirement(t *testing.T, result Resolution, kind string) Requirement {
	t.Helper()
	for _, entry := range result.Requirements {
		if entry.Kind == kind {
			return entry
		}
	}
	t.Fatalf("missing %s requirement", kind)
	return Requirement{}
}

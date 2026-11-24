package admission

import (
	"strings"
	"testing"
)

func TestConstraintNormalizationPreservesLargeExactIntegers(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	large := "1" + strings.Repeat("0", 309)
	neighbor := "1" + strings.Repeat("0", 308) + "1"
	for _, wrapper := range []struct{ name, prefix, suffix string }{
		{name: "root"},
		{name: "record", prefix: `{"number":`, suffix: "}"},
	} {
		t.Run(wrapper.name, func(t *testing.T) {
			checkLargeIntegerNormalization(t, owner, wrapper.prefix+large+wrapper.suffix, wrapper.prefix+neighbor+wrapper.suffix)
		})
	}
}

func checkLargeIntegerNormalization(t *testing.T, owner *Validator, original, neighbor string) {
	t.Helper()
	input := constraintTestValue(t, owner, original)
	closure := RealizationClosure{Posture: "closed", Universe: "test", Profile: "test/v1"}
	built, buildErr := NormalizeRealizationLiteral(input, "test/v1", closure, RealizationNormalizationMetadata{}, DefaultConstraintLimits())
	if buildErr != nil || built.Status != "conformant" || built.Document == nil {
		t.Fatalf("normalize admitted large integer: status=%s err=%v", built.Status, buildErr)
	}
	for _, candidate := range []struct{ raw, status string }{
		{raw: original, status: "conformant"},
		{raw: neighbor, status: "nonconformant"},
	} {
		result, evaluateErr := EvaluateRealizationConstraint(built.Document, constraintTestValue(t, owner, candidate.raw), DefaultConstraintLimits())
		if evaluateErr != nil {
			t.Fatal(evaluateErr)
		}
		if actual := requireType[map[string]any](t, result.Document())["status"]; actual != candidate.status {
			t.Fatalf("exact comparison: got %v, want %s", actual, candidate.status)
		}
	}
}

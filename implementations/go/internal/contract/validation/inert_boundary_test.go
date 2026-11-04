package validation

import (
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
)

func TestInertProfileLimitsPrivacyAndRecovery(t *testing.T) {
	schema := []byte(`{"type":"object","properties":{"private":{"type":"string"}}}`)
	value := []byte(`{"private":"retained-secret"}`)
	limits := InertLimits{MaxBytes: 1048576, MaxDepth: 16, MaxNodes: 4096, MaxScalarBytes: 1048576, MaxReferences: 128, MaxEvaluations: 65536}
	for _, field := range []string{"bytes", "depth", "nodes", "scalars", "evaluations", "invalid-limits"} {
		t.Run(field, func(t *testing.T) {
			bad := limits
			switch field {
			case "bytes":
				bad.MaxBytes = len(schema) - 1
			case "depth":
				bad.MaxDepth = 1
			case "nodes":
				bad.MaxNodes = 2
			case "scalars":
				bad.MaxScalarBytes = 1
			case "evaluations":
				bad.MaxEvaluations = 6
			case "invalid-limits":
				bad.MaxReferences = -1
			}
			assertInertRefusal(t, CheckInertSchema(schema, value, inertSafeKeywords(), bad))
			if err := CheckInertSchema(schema, value, inertSafeKeywords(), limits); err != nil {
				t.Fatal("request after refusal:", err)
			}
		})
	}
	limits.MaxBytes = len(schema)
	if err := CheckInertSchema(schema, value, inertSafeKeywords(), limits); err != nil {
		t.Fatal("inclusive byte bound:", err)
	}
	ref := []byte(`{"$defs":{"s":{"type":"string"}},"$ref":"#/$defs/s"}`)
	limits.MaxReferences = 0
	assertInertRefusal(t, CheckInertSchema(ref, []byte(`"retained-secret"`), inertSafeKeywords(), limits))
	assertInertRefusal(t, CheckInertSchema(schema, value, []string{"type"}, limits))
}
func TestInertProfileRejectsMalformedInput(t *testing.T) {
	limits := InertLimits{MaxBytes: 1048576, MaxDepth: 16, MaxNodes: 4096, MaxScalarBytes: 1048576, MaxReferences: 128, MaxEvaluations: 65536}
	for _, value := range []string{`{"private":1,"private":2}`, `NaN`, `1e9999999`, `1e999`, `1 2`, `"\ud800"`, string([]byte{34, 255, 34}), `[1,]`} {
		assertInertRefusal(t, CheckInertSchema([]byte(`{}`), []byte(value), inertSafeKeywords(), limits))
	}
	assertInertRefusal(t, CheckInertSchema([]byte(`{"type":"string","type":"number"}`), []byte(`1`), inertSafeKeywords(), limits))
}
func assertInertRefusal(t *testing.T, err error) {
	t.Helper()
	category, _ := fault.CategoryOf(err)
	if err == nil || category != fault.InvalidInput {
		t.Fatalf("wanted invalid-input refusal, got %v", err)
	}
	if strings.Contains(err.Error(), "retained-secret") || strings.Contains(err.Error(), "private\"") {
		t.Fatal("profile data exposed")
	}
}

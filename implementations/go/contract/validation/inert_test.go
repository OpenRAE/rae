package validation

import (
	"encoding/json"
	"errors"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func TestInertProfileReferenceVerdicts(t *testing.T) {
	if _, err := inertMeta(); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile("testdata/inert-verdicts.json")
	if err != nil {
		t.Fatal(err)
	}
	var recording struct {
		Cases []inertCase `json:"cases"`
	}
	if err := json.Unmarshal(data, &recording); err != nil {
		t.Fatal(err)
	}
	if len(recording.Cases) != 54 {
		t.Fatalf("len(cases) = %d, want the 54 recorded reference cases", len(recording.Cases))
	}
	for _, c := range recording.Cases {
		t.Run(c.Name, func(t *testing.T) { checkInertCase(t, c) })
	}
}

type inertCase struct {
	Name      string          `json:"name"`
	Schema    json.RawMessage `json:"schema"`
	Value     json.RawMessage `json:"value"`
	Valid     bool            `json:"valid"`
	Outcome   string          `json:"outcome"`
	Minimum   int             `json:"minimum_evaluations"`
	Supported []string        `json:"supported"`
	Limits    map[string]int  `json:"limits"`
}

func inertOutcomeCode(outcome string) string {
	return map[string]string{"valid": "", "limit-exceeded": InertLimitExceeded, "unsupported-keyword": InertUnsupportedKeyword, "schema-invalid": InertSchemaInvalid, "value-invalid": InertValueInvalid}[outcome]
}

func checkInertCase(t *testing.T, c inertCase) {
	t.Helper()
	limits := InertLimits{MaxBytes: 1048576, MaxDepth: 16, MaxNodes: 4096, MaxScalarBytes: 1048576, MaxReferences: 128, MaxEvaluations: 65536}
	for name, target := range map[string]*int{"max_depth": &limits.MaxDepth, "max_nodes": &limits.MaxNodes, "max_scalar_bytes": &limits.MaxScalarBytes, "max_references": &limits.MaxReferences, "max_evaluations": &limits.MaxEvaluations} {
		if value, ok := c.Limits[name]; ok {
			*target = value
		}
	}
	supported := inertSafeKeywords()
	if c.Supported != nil {
		supported = c.Supported
	}
	err := CheckInertSchema(c.Schema, c.Value, supported, limits)
	if got := inertCode(err); got != inertOutcomeCode(c.Outcome) {
		t.Fatalf("CheckInertSchema() code = %q (%v), want reference outcome %s", got, err, c.Outcome)
	}
	if !c.Valid || c.Minimum == 0 {
		return
	}
	limits.MaxEvaluations = c.Minimum
	if err := CheckInertSchema(c.Schema, c.Value, supported, limits); err != nil {
		t.Fatalf("reference budget %d: %v", c.Minimum, err)
	}
	limits.MaxEvaluations--
	if got := inertCode(CheckInertSchema(c.Schema, c.Value, supported, limits)); got != InertLimitExceeded {
		t.Fatalf("CheckInertSchema() below reference budget code = %q, want %s", got, InertLimitExceeded)
	}
}

func inertCode(err error) string {
	if refused, ok := errors.AsType[*fault.Error](err); ok {
		return refused.Code()
	}
	if err != nil {
		return err.Error()
	}
	return ""
}

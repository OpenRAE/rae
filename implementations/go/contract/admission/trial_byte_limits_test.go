package admission

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestTrialSealingKeepsExplicitByteAllowanceAboveDefault(t *testing.T) {
	var reference struct {
		Bytes  int    `json:"limitation_bytes"`
		Digest string `json:"plan_digest"`
	}
	readFullReferenceJSON(t, "testdata/large-byte-limit-reference.json", &reference)
	raw, err := repoFixtureBytes(t, "../../../../contracts/fixtures/plans/admitted-trial-plan-v1/valid/minimal.json")
	if err != nil {
		t.Fatal(err)
	}
	var plan map[string]any
	if decodeExact(raw, &plan) != nil {
		t.Fatal("fixture")
	}
	object(plan["admission"])["limitations"] = []string{strings.Repeat("a", reference.Bytes)}
	raw, err = json.Marshal(plan)
	if err != nil {
		t.Fatal(err)
	}
	owner := boundTestOwner(t)
	if _, err = SealTrialPlan(owner, raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}); err == nil {
		t.Fatal("default byte ceiling bypassed")
	}
	admitted, err := SealTrialPlan(owner, raw, ingress.Limits{MaxBytes: len(raw) + 4096, MaxDepth: 64})
	if err != nil {
		t.Fatal("explicit larger allowance refused", err)
	}
	var projected map[string]any
	if decodeExact(admitted.JSON(), &projected) != nil || stringAt(projected, "plan_digest") != reference.Digest {
		t.Fatal("large source digest differs")
	}
	if _, err = TrialEntryOrder(owner, admitted); err != nil {
		t.Fatal("admitted larger allowance lost during ordering", err)
	}
}

package admission

import (
	"bytes"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestFullAdmissionInputFailuresLeaveNoValueAndRecover(t *testing.T) {
	e := boundTestOwner(t)
	const id = "participant-execution-service-state-v1"
	raw := controlJSON(t, fixtureObject(t, "fixtures/participant-runtime/"+id+"/valid/running-ready.json"))
	limits := ingress.Limits{MaxBytes: len(raw), MaxDepth: 64}
	for _, test := range []struct {
		name, contract string
		data           []byte
		limits         ingress.Limits
	}{
		{"byte-limit", id, raw, ingress.Limits{MaxBytes: len(raw) - 1, MaxDepth: 64}},
		{"depth-limit", id, raw, ingress.Limits{MaxBytes: len(raw), MaxDepth: 1}},
		{"unknown-contract", "unknown-contract", raw, limits},
		{"duplicate-key", id, []byte(`{"capacity":1,"capacity":2}`), limits},
		{"nonfinite", id, []byte(`{"capacity":NaN}`), limits},
		{"wrong-root", id, []byte(`[]`), limits},
		{"null-root", id, []byte(`null`), limits},
		{"trailing-document", id, []byte(`{} {}`), limits},
		{"invalid-utf8", id, []byte{'{', '"', 0xff, '"', ':', '1', '}'}, limits},
		{"private-malformed", id, []byte(`{"private-input-sentinel":`), limits},
	} {
		t.Run(test.name, func(t *testing.T) {
			value, err := e.Validate(test.contract, test.data, test.limits, nil)
			category, typed := fault.CategoryOf(err)
			if err == nil || !typed || category != fault.InvalidInput || value.ContractID() != "" || len(value.JSON()) != 0 {
				t.Fatalf("failure returned admitted data or unexpected category: %v", err)
			}
			if strings.Contains(err.Error(), "private-input-sentinel") {
				t.Fatal("input value escaped through an error")
			}
			// A refusal must not poison the reusable validator or retain its input.
			value, err = e.Validate(id, raw, limits, nil)
			if err != nil || value.ContractID() != id || !bytes.Equal(value.JSON(), raw) {
				t.Fatalf("recovery at the exact byte limit: %v", err)
			}
			returned := value.JSON()
			returned[0] = 'x'
			if !bytes.Equal(value.JSON(), raw) {
				t.Fatal("returned bytes changed admission")
			}
		})
	}
}

func TestFullAdmissionRequiresIndependentContextAndRecovers(t *testing.T) {
	e := boundTestOwner(t)
	const id = "trial-cleanup-receipt-v1"
	receipt := fixtureObject(t, "fixtures/control-plane/"+id+"/valid/success.json")
	plan := fixtureObject(t, "fixtures/plans/trial-cleanup-plan-v1/valid/fresh-range.json")
	raw := controlJSON(t, receipt)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if err := e.low.CheckSchema(id, raw, limits); err != nil {
		t.Fatal(err)
	}
	var absent *testCleanupContext
	for _, context := range []any{nil, absent, receipt, testCleanupContext{data: []byte(`{"private-owner-sentinel":`)}} {
		value, err := e.Validate(id, raw, limits, context)
		if err == nil || value.ContractID() != "" || len(value.JSON()) != 0 {
			t.Fatal("payload or absent owner granted admission")
		}
		if strings.Contains(err.Error(), "private-owner-sentinel") {
			t.Fatal("owner failure disclosed data")
		}
		value, err = e.Validate(id, raw, limits, testCleanupContext{data: controlJSON(t, plan)})
		if err != nil || value.ContractID() != id {
			t.Fatalf("valid independent owner did not recover: %v", err)
		}
	}
}

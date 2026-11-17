package stub_test

import (
	"context"
	"encoding/json"
	"os"
	"testing"
	"time"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/backend/stub"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestEvaluatorMatchesPythonReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/evaluation-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []evaluationReference
	if json.Unmarshal(raw, &cases) != nil || len(cases) != 6 {
		t.Fatal("reference")
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) { checkEvaluationReference(t, test) })
	}
}

type evaluationReference struct {
	Name    string                   `json:"name"`
	Plan    binding.EvaluationPlanV1 `json:"plan"`
	Results map[string]any           `json:"results"`
	History map[string]any           `json:"history"`
	Changed []string                 `json:"changed"`
}

func checkEvaluationReference(t *testing.T, test evaluationReference) {
	t.Helper()
	producer, err := stub.NewEvaluatorWithConfiguration(stub.Configuration{Clock: func() time.Time { return time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC) }})
	if err != nil {
		t.Fatal(err)
	}
	result, err := producer.Start(context.Background(), test.Plan, binding.RuntimeSnapshotV1{})
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]any
	if json.Unmarshal(marshalTest(t, result.Snapshot), &decoded) != nil {
		t.Fatal("snapshot")
	}
	if diff := cmp.Diff(test.Results, decoded["evaluation_results"]); diff != "" {
		t.Fatal(diff)
	}
	if diff := cmp.Diff(test.History, decoded["evaluation_history"]); diff != "" {
		t.Fatal(diff)
	}
	if diff := cmp.Diff(test.Changed, result.ChangedAddresses); diff != "" {
		t.Fatal(diff)
	}
}

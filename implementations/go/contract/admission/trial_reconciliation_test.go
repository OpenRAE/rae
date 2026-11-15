package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestTrialRunReconciliationMatchesIndependentReference(t *testing.T) {
	owner := boundTestOwner(t)
	var reference struct {
		Plan  json.RawMessage         `json:"plan"`
		Cases []trialRunReferenceCase `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/trial-run-reconciliation.json", &reference)
	plan, err := owner.Validate(trialPlanContract, reference.Plan, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatal(err)
	}
	structural := schemaOnlyTestOwner(t, owner)
	for _, ref := range reference.Cases {
		t.Run(ref.Name, func(t *testing.T) { checkTrialRunReference(t, ref, owner, structural, plan) })
	}
}

func TestTrialRunJSONUsesCompleteOwnerReconciliation(t *testing.T) {
	owner := boundTestOwner(t)
	var ref struct {
		Plan  json.RawMessage `json:"plan"`
		Cases []struct {
			Name        string            `json:"name"`
			Run         json.RawMessage   `json:"run"`
			Receipts    [][]byte          `json:"-"`
			RawReceipts []json.RawMessage `json:"receipts"`
			Valid       bool              `json:"valid"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/trial-run-reconciliation.json", &ref)
	plan, err := owner.Validate(trialPlanContract, ref.Plan, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range ref.Cases {
		t.Run(test.Name, func(t *testing.T) {
			receipts := make([][]byte, len(test.RawReceipts))
			for i, raw := range test.RawReceipts {
				receipts[i] = raw
			}
			err := ValidateTrialRunJSON(owner, plan, test.Run, receipts)
			if (err == nil) != test.Valid {
				t.Fatal("raw reconciliation mismatch", err)
			}
		})
	}
}

type trialRunReferenceCase struct {
	Name     string            `json:"name"`
	Run      json.RawMessage   `json:"run"`
	Receipts []json.RawMessage `json:"receipts"`
	Valid    bool              `json:"valid"`
}

func checkTrialRunReference(t *testing.T, ref trialRunReferenceCase, owner *Validator, structural *validation.Validator, plan validation.Value) {
	t.Helper()
	var err error

	inputs := TrialRunInputs{Plan: plan}
	// Empty registries admit schema-only handles; the boundary must recheck
	// local owner semantics and all independently supplied joins.
	inputs.Run, err = structural.Validate(termExperimentRunV1, ref.Run, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
	if err != nil {
		if ref.Valid {
			t.Fatal(err)
		}
		return
	}
	for _, raw := range ref.Receipts {
		receipt, checkErr := structural.Validate(termTrialCleanupReceiptV1, raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
		if checkErr != nil {
			t.Fatal(checkErr)
		}
		inputs.CleanupReceipts = append(inputs.CleanupReceipts, receipt)
	}
	err = ValidateTrialRun(owner, inputs)
	if (err == nil) != ref.Valid {
		t.Fatal("reconciliation admission =", err == nil, "want", ref.Valid, err)
	}
}

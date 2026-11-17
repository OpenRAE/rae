package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestFragmentBudgetChargesRepeatedHandles(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	fragment, err := AdmitFragment(owner, RealizationValue, "1234567890", ingress.Limits{MaxBytes: 128, MaxDepth: 8})
	if err != nil {
		t.Fatal(err)
	}
	if err := CheckFragmentBudget([]Fragment{fragment}, 12); err != nil {
		t.Fatal(err)
	}
	if err := CheckFragmentBudget([]Fragment{fragment, fragment}, 23); err == nil {
		t.Fatal("aggregate size bypassed")
	}
	if err := CheckFragmentBudget([]Fragment{nil}, 128); err == nil {
		t.Fatal("nil fragment accepted")
	}
}

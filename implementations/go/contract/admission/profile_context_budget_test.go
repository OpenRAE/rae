package admission

import (
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestProfileValueBudgetDoesNotAddASingleInputDepth(t *testing.T) {
	var input binding.DomainProfileBindingV1
	// The binding root is depth0; its value is depth1; the scalar is depth32.
	raw := strings.Repeat("[", 31) + `"leaf"` + strings.Repeat("]", 31)
	if err := input.Value.UnmarshalJSON([]byte(raw)); err != nil {
		t.Fatal(err)
	}
	if err := checkProfileValues(input); err != nil {
		t.Fatalf("native single input at depth32 refused: %v", err)
	}
	// A two-input relation really has the tuple root that adds one depth.
	if err := checkProfileValues(input, input); err == nil {
		t.Fatal("combined relation bypassed depth budget")
	}
}

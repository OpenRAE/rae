package admission

import "testing"

func TestFocusedContractModelBoundariesMatchIndependentPython(t *testing.T) {
	t.Parallel()
	runModelReferenceShards(t, "focused-model-boundaries", 730, 1)
}

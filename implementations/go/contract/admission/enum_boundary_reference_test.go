package admission

import "testing"

func TestContractEnumAndOptionalBoundariesMatchIndependentPython(t *testing.T) {
	t.Parallel()
	runModelReferenceShards(t, "enum-model-boundaries", 3424, 6)
}

package admission

import "testing"

func TestContractEnumAndOptionalBoundariesMatchIndependentPython(t *testing.T) {
	t.Parallel()
	runModelReferenceShards(t, "enum-model-boundaries", 3430, 6)
}

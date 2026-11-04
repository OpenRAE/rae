package admission

import "testing"

func TestActionAdmissionOptionalOwnersMatchIndependentPython(t *testing.T) {
	t.Parallel()
	checkActionOwnerRecording(t, "testdata/action-optional-verdicts.json", 42)
}

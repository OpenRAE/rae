package admission

import "testing"

func TestClockHistoryAndTemporalAssessments(t *testing.T) {
	clock := decodeRuleObject(t, `{"clock_address":"clock.c","sequence":1,"state":"running","coordinate":{"segment":0,"tick":2,"microstep":0},"history":[{"sequence":0,"kind":"initialize","previous":null,"resulting":{"segment":0,"tick":0,"microstep":0},"resulting_state":"running"},{"sequence":1,"kind":"advance","previous":{"segment":0,"tick":0,"microstep":0},"resulting":{"segment":0,"tick":2,"microstep":0},"resulting_state":"running"}]}`)
	if err := runtimeClock(clock); err != nil {
		t.Fatal(err)
	}
	object(array(at(clock, "history"))[1])["sequence"] = jsonZero
	if err := runtimeClock(clock); err == nil {
		t.Error("accepted rewritten clock sequence")
	}
	context := decodeRuleObject(t, `{"binding":{"temporal_kind":"deadline","event_point":"end"},"submitted_at":{"segment":0,"tick":1,"microstep":0},"bound_end":{"segment":0,"tick":2,"microstep":0}}`)
	proof := decodeRuleObject(t, `{"evidence_mode":"event","event_point":"end","observation_boundary_address":"boundary","coordinate":{"segment":0,"tick":2,"microstep":0}}`)
	status, _ := temporalDeadline(context, []any{proof}, "boundary", clock, "reported")
	if status != "met" {
		t.Fatal(status)
	}
	object(proof)["coordinate"] = decodeRuleObject(t, `{"segment":0,"tick":3,"microstep":0}`)
	status, _ = temporalDeadline(context, []any{proof}, "boundary", clock, "reported")
	if status != "indeterminate" {
		t.Error("accepted evidence beyond the committed clock")
	}
}

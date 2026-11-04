package admission

import "testing"

func TestTemporalBindingRule(t *testing.T) {
	for _, test := range []struct {
		raw   string
		valid bool
	}{
		{`{"temporal_kind":"deadline","evidence_mode":"event","event_point":"end","event_points":["end"],"end":{"segment":0,"tick":2,"microstep":0}}`, true},
		{`{"temporal_kind":"deadline","evidence_mode":"continuous","event_point":"end","event_points":["end"],"end":{"segment":0}}`, false},
		{`{"temporal_kind":"deadline","evidence_mode":"event","event_point":"end","event_points":["start"],"end":{"segment":0}}`, false},
		{`{"temporal_kind":"dwell","evidence_mode":"continuous","event_point":"start","event_points":["start"],"condition_precondition_id":"p","observation_boundary_address":"b","start":{"segment":0,"tick":2,"microstep":0},"end":{"segment":0,"tick":2,"microstep":1}}`, true},
		{`{"temporal_kind":"dwell","evidence_mode":"continuous","event_point":"start","event_points":["start"],"condition_precondition_id":"p","observation_boundary_address":"b","start":{"segment":0,"tick":2,"microstep":1},"end":{"segment":0,"tick":2,"microstep":1}}`, false},
		{`{"temporal_kind":"deadline","evidence_mode":"event","event_point":"end","event_points":["end"],"end":{"segment":1}}`, false},
	} {
		assertRule(t, "participant-shared-time-binding-shape", test.raw, test.valid)
	}
}

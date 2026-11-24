package processor_test

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestParticipantHistoryTransportPreservesPublishedNestedRecords(t *testing.T) {
	vectors := participantHistoryReference(t)
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"valid", "valid-shared-state", "outcome-valid", "attribution-valid", "temporal-valid"} {
		t.Run(name, func(t *testing.T) {
			test := participantTransportFixture(t, vectors, name)
			value, err := owner.Validate("participant-behavior-history-event-stream-v1", test.Input, participantTransportLimits(), nil)
			if err != nil {
				t.Fatal(err)
			}
			transport, err := value.Transport()
			if err != nil {
				t.Fatal(err)
			}
			assertReferenceJSON(t, "published event transport", requireJSON(t, transport), test.Input)
		})
	}
}
func TestParticipantHistoryPublishedShapeRefusesUnknownFields(t *testing.T) {
	vectors := participantHistoryReference(t)
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"event-member", "details-member"} {
		t.Run(name, func(t *testing.T) {
			var history []map[string]json.RawMessage
			if err := json.Unmarshal(vectors.History[0].Input, &history); err != nil {
				t.Fatal(err)
			}
			if name == "event-member" {
				history[2]["private"] = json.RawMessage(`"private-canary"`)
			} else {
				history[2]["details"] = json.RawMessage(`{"private":"private-canary"}`)
			}
			_, err := owner.Validate("participant-behavior-history-event-stream-v1", requireJSON(t, history), participantTransportLimits(), nil)
			if err == nil {
				t.Fatal("unknown closed member accepted")
			}
		})
	}
}
func participantTransportLimits() ingress.Limits {
	return ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
}

func participantTransportFixture(t *testing.T, vectors participantHistoryVectors, name string) participantHistoryCase {
	t.Helper()
	for _, test := range vectors.History {
		if test.Name == name {
			return test
		}
	}
	t.Fatal("missing named fixture")
	return participantHistoryCase{}
}

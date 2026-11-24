package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestEventFactoryDefaultsKeepSuppliedEvidence(t *testing.T) {
	e := boundTestOwner(t)
	owners := loadFullReferenceOwners(t)
	for _, test := range []struct{ id, name, key string }{
		{"participant-control-occurrence-v1", "proposal", "control-v1"},
		{"participant-control-occurrence-v2", "accepted-handoff", "control-v2"},
		{"participant-crossing-occurrence-v1", "request", "crossing"},
	} {
		t.Run(test.id, func(t *testing.T) {
			for _, field := range []string{"predecessor_event_refs", "marking_definition_refs", "markings", "granular_markings"} {
				t.Run(field, func(t *testing.T) {
					v := fixtureObject(t, "fixtures/participant-runtime/"+test.id+"/valid/"+test.name+".json")
					v[field] = []any{"evidence:changed"}
					if field == "granular_markings" {
						v[field] = map[string]any{"/actor_ref": []any{"marking:changed"}}
					}
					value, err := e.Validate(test.id, controlJSON(t, v), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, fullReferenceContext(t, e, owners, test.key))
					if err == nil || value.ContractID() != "" {
						t.Fatal("supplied evidence was erased during model comparison")
					}
				})
			}
		})
	}
}

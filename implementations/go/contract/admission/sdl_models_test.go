package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestSDLConstructorPredicates(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name, definition, data string
		valid                  bool
	}{
		{"proposition-observed-no-evidence", "Proposition", `{"description":"p","subjects":["n"],"basis":"observed_state","predicate":{"kind":"presence","property":"state","semantic_ref":"urn:test"}}`, false},
		{"proposition-declared", "Proposition", `{"description":"p","subjects":["n"],"basis":"declared_state","predicate":{"kind":"presence","property":"state","semantic_ref":"urn:test"}}`, true},
		{"proposition-threshold", "Proposition", `{"description":"p","subjects":["n"],"basis":"declared_state","quantifier":"at_least","threshold":2,"predicate":{"kind":"presence","property":"state","semantic_ref":"urn:test"}}`, false},
		{"ratio-not-reduced", "ExactRatio", `{"numerator":2,"denominator":4}`, false},
		{"ratio-reduced", "ExactRatio", `{"numerator":1,"denominator":2}`, true},
		{"behavior-blank-ref", "ParticipantBehaviorSpecification", `{"semantic_version":"1","participant_refs":[" "],"authority_scope_refs":["n"]}`, false},
		{"behavior-valid", "ParticipantBehaviorSpecification", `{"semantic_version":"1","participant_refs":["p"],"authority_scope_refs":["n"]}`, true},
		{"condition-empty", "Condition", `{}`, false},
		{"condition-command", "Condition", `{"command":"echo","interval":1}`, true},
		{"condition-two-selectors", "Condition", `{"command":"echo","interval":1,"source":{"name":"p"}}`, false},
		{"content-missing-anchors", "Content", `{"type":"file"}`, false},
		{"content-file", "Content", `{"type":"file","target":"n","path":"/x"}`, true},
		{"account-node", "Account", `{"username":"alice"}`, false},
		{"account-valid", "Account", `{"username":"alice","node":"n"}`, true},
		{"success-empty", "ObjectiveSuccess", `{}`, false},
		{"success-threshold", "ObjectiveSuccess", `{"mode":"at_least","assertions":["a"],"threshold":2}`, false},
		{"success-valid", "ObjectiveSuccess", `{"assertions":["a"]}`, true},
		{"subset-bounds", "SubsetVariationPoint", `{"target":{"owner":"n","slot":"nodes.features"},"members":{"x":{"reference":"f"}},"minimum":2}`, false},
		{"subset-valid", "SubsetVariationPoint", `{"target":{"owner":"n","slot":"nodes.features"},"members":{"x":{"reference":"f"}},"minimum":1}`, true},
		{"step-objective", "WorkflowStep", `{"type":"objective"}`, false},
		{"step-valid", "WorkflowStep", `{"type":"objective","objective":"o","on_success":"end"}`, true},
		{"clock-jump", "Clock", `{"time_domain_ref":"t","authority_kind":"runtime","authority_ref":"r","monotonicity":"may_jump","description":"clock"}`, false},
		{"clock-valid", "Clock", `{"time_domain_ref":"t","authority_kind":"runtime","authority_ref":"r","monotonicity":"may_jump","description":"clock","supports_jump":true}`, true},
		{"attestation-absent-verified", "ImageAttestation", `{"status":"absent","verification":"verified"}`, false},
		{"attestation-present", "ImageAttestation", `{"status":"present","verification":"verified"}`, true},
		{"relative-filesystem", "RuntimeFilesystemEntry", `{"path":"relative"}`, false},
		{"absolute-filesystem", "RuntimeFilesystemEntry", `{"path":"/absolute"}`, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			err := owner.CheckSDLConstruction("sdl-authoring-input-v1", "#/$defs/"+c.definition, []byte(c.data), ingress.Limits{MaxBytes: 1 << 20})
			if (err == nil) != c.valid {
				t.Fatalf("valid=%v want %v: %v", err == nil, c.valid, err)
			}
		})
	}
}

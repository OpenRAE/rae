package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestExecutionPolicyResolutionKeepsNearestCompleteRule(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	document, err := AdmitFragment(owner, OperationPolicyDocument, map[string]any{"default": map[string]any{"policy_id": "root", "response": "terminate"}, "scopes": []any{map[string]any{"scope": "/nodes/server", "policy": map[string]any{"policy_id": "local", "response": "terminate"}}}}, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	effective, err := ResolveExecutionPolicy(owner, document, "/nodes/server", nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	result := effective.Document()
	if stringAt(result, "governing_scope") != "#/nodes/server" || stringAt(result, "policy", "policy_id") != "local" {
		t.Fatalf("policy=%+v", result)
	}
	if _, ok := at(result, "policy", "retry").(map[string]any); !ok {
		t.Fatal("native retry defaults missing")
	}
	if _, ok := at(result, "policy", "retry", "compensation_refs").([]any); !ok {
		t.Fatal("native retry collection defaults missing")
	}
	gaps, err := ExecutionPolicyCapabilityGaps(effective, nil)
	if err != nil || len(gaps) != 1 || gaps[0] != "response-unsupported" {
		t.Fatalf("gaps=%v %v", gaps, err)
	}
	if _, err := ResolveExecutionPolicy(owner, replacedConstraintFragment{document}, "/nodes/server", nil, nil); err == nil {
		t.Fatal("foreign policy accepted")
	}
}

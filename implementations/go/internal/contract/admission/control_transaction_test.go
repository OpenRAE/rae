package admission

import (
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func controlModelRejectsShapeValidMutation(t *testing.T, e *Validator, id string, root any) {
	t.Helper()
	raw := controlJSON(t, root)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if err := e.low.CheckSchema(id, raw, limits); err != nil {
		t.Fatalf("mutation changed schema validity: %v", err)
	}
	if err := e.checkModels(id, raw, limits); err == nil {
		t.Fatal("accepted contradictory control transaction")
	}
}

func TestControlCompositionRejectsHiddenBlockersAndExhaustedEffects(t *testing.T) {
	e := boundTestOwner(t)
	root := fixtureObject(t, "fixtures/participant-runtime/participant-control-evaluation-v1/valid/conflict.json")
	object(root["composition"])["blockers"] = []any{}
	controlModelRejectsShapeValidMutation(t, e, "participant-control-evaluation-v1", root)
	root = fixtureObject(t, "fixtures/participant-runtime/participant-control-evaluation-v1/valid/teaching-inject.json")
	object(at(root, "request", "selection", "bounds"))["max_fanout"] = jsonZero
	controlModelRejectsShapeValidMutation(t, e, "participant-control-evaluation-v1", root)
}

func TestControlV2TransactionBindsInvocationAndCommit(t *testing.T) {
	e := boundTestOwner(t)
	root := fixtureObject(t, "fixtures/participant-runtime/participant-control-evaluation-v2/valid/dependency-chain.json")
	object(root["commit"])["decision_digest"] = "sha256:" + strings.Repeat("a", 64)
	controlModelRejectsShapeValidMutation(t, e, "participant-control-evaluation-v2", root)
	root = fixtureObject(t, "fixtures/participant-runtime/participant-control-evaluation-v2/valid/dependency-chain.json")
	calls := array(root["invocations"])
	if len(calls) == 0 {
		t.Fatal("fixture has no invocation")
	}
	object(calls[0])["context_digest"] = "sha256:" + strings.Repeat("a", 64)
	controlModelRejectsShapeValidMutation(t, e, "participant-control-evaluation-v2", root)
}

func TestControlStateWritersRequireOneExactSerialChain(t *testing.T) {
	root := fixtureObject(t, "fixtures/participant-runtime/participant-control-evaluation-v2/valid/dependency-chain.json")
	call := array(root["invocations"])[0]
	before := at(call, "state_input", "state")
	after := map[string]any{"kind": "provider-state", "ref": "state.next", "revision": "revision.2", "digest": "sha256:" + strings.Repeat("a", 64)}
	final := map[string]any{"kind": "provider-state", "ref": "state.final", "revision": "revision.3", "digest": "sha256:" + strings.Repeat("b", 64)}
	writers := []any{
		map[string]any{"invocation_id": "call.first", "scope": at(call, "state_input", "scope"), "before": before, "after": after, "commit_on": "evaluation", "predecessor_invocation_id": nil},
		map[string]any{"invocation_id": "call.second", "scope": at(call, "state_input", "scope"), "before": after, "after": final, "commit_on": "evaluation", "predecessor_invocation_id": "call.first"},
	}
	if err := controlStateProposals(writers); err != nil {
		t.Fatal(err)
	}
	object(writers[1])["predecessor_invocation_id"] = nil
	if err := controlStateProposals(writers); err == nil {
		t.Error("accepted unordered writers for one state scope")
	}
	object(writers[1])["predecessor_invocation_id"] = "call.first"
	object(writers[1])["before"] = before
	if err := controlStateProposals(writers); err == nil {
		t.Error("accepted a stale predecessor state")
	}
}

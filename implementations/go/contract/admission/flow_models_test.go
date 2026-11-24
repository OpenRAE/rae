package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestFlowModelsKeepConservativeLineageAndExactDeltas(t *testing.T) {
	e := boundTestOwner(t)
	const id = "participant-flow-control-relation-v1"
	const path = "fixtures/participant-runtime/participant-flow-control-relation-v1/valid/conservative-release-chain.json"
	v := fixtureObject(t, path)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if err := e.checkModels(id, controlJSON(t, v), limits); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"lost-obligation", "lost-influence", "unknown-release", "reused-subject", "unsorted-inputs", "changed-policy", "unknown-binding", "unsorted-evidence", "permitted-denial"} {
		t.Run(name, func(t *testing.T) {
			root := fixtureObject(t, path)
			flowModelMutation(root, name)
			raw := controlJSON(t, root)
			if err := e.low.CheckSchema(id, raw, limits); err != nil {
				t.Fatalf("mutation is not schema valid: %v", err)
			}
			if err := e.checkModels(id, raw, limits); err == nil {
				t.Fatal("accepted contradictory flow relation")
			}
		})
	}
}

func flowModelMutation(v any, name string) {
	labels := controlRows(at(v, "labels"), "label_id")
	derivation := object(array(at(v, "derivations"))[0])
	decision := object(array(at(v, "sink_decisions"))[0])
	switch name {
	case "lost-obligation":
		object(labels["label.derived.1"])["confidentiality_obligation_refs"] = []any{}
	case "lost-influence":
		object(labels["label.derived.1"])["influence_refs"] = []any{"invented"}
	case "unknown-release":
		decision["release_refs"] = []any{"unknown.release"}
	case "reused-subject":
		object(array(at(v, "releases"))[0])["result_subject"] = at(derivation, "result_subject")
	case "unsorted-inputs":
		inputs := array(derivation["inputs"])
		inputs[0], inputs[1] = inputs[1], inputs[0]
	case "changed-policy":
		object(at(derivation, "policy"))["decision_cut_revision"] = "stale"
	case "unknown-binding":
		object(at(array(at(v, "bindings"))[0], "relation_target"))["target_ref"] = "unknown.label"
	case "unsorted-evidence":
		derivation["evidence_refs"] = []any{"z", "a"}
	case "permitted-denial":
		decision["confidentiality_result"] = "deny"
	}
}

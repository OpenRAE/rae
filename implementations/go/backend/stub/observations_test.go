package stub

import (
	"encoding/json"
	"maps"
	"testing"
)

func TestRetainedObservationsRequireSelectedUnchangedApparatusBinding(t *testing.T) {
	envelope, err := packagedDocument("realization-envelopes/reference-emulation/in-process-v1.json")
	if err != nil {
		t.Fatal(err)
	}
	prior := map[string]any{"address": "provision.node.web", "field_path": "nodes.web.realization.compute-substrate", "domain": "runtime-realization", "requirement_kind": "compute-substrate", "verification_scope": "presence", "observation_strength": "daemon-observed", "observed_value": "x-openrae:in-process-emulation", "operation_id": "previous-operation", "envelope_digest": envelope["digest"], "configuration_digest": object(envelope, "configuration")["configuration_digest"], "observer_version": "test/v1", "sequence": json.Number("0"), "binding_verified": true}
	unrelated := map[string]any{"address": "provision.node.web", "field_path": "nodes.web.runtime.environment", "domain": "runtime-realization", "requirement_kind": "runtime-environment", "verification_scope": "configuration", "observation_strength": "daemon-observed"}
	operation := map[string]any{"address": "provision.node.web", "action": "unchanged"}
	selector := map[string]any{"semantic_scope": "", "data_kind": "field", "names": []any{"compute-substrate"}}
	demand := map[string]any{"scope": "", "purpose": "experimental", "mode": "selected", "collection": "require", "selectors": []any{selector}}
	plan := map[string]any{"operations": []any{operation}, "realization_constraints": []any{map[string]any{"address": "provision.node.web", "field_path": prior["field_path"], "governing_scope": "#/nodes/web", "concern": "compute-substrate"}}, "observation_demands": []any{demand}}
	for _, test := range []struct {
		name   string
		change func(map[string]any)
		reuse  bool
	}{{"bound", func(map[string]any) {}, true}, {"wrong-apparatus", func(v map[string]any) {
		v["configuration_digest"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	}, false}, {"driver-claim", func(v map[string]any) { v["observation_strength"] = "driver-reported" }, false}} {
		t.Run(test.name, func(t *testing.T) {
			disclosure := maps.Clone(prior)
			test.change(disclosure)
			result, selectionErr := retainedObservations(plan, map[string]any{"realization_observations": []any{unrelated, disclosure}}, envelope)
			if selectionErr != nil {
				t.Fatal(selectionErr)
			}
			want := map[bool]int{false: 1, true: 2}[test.reuse]
			if len(result) != want || result[0].RequirementKind != "runtime-environment" {
				t.Fatal("disclosure selection", result)
			}
		})
	}
	operation["action"] = "update"
	result, err := retainedObservations(plan, map[string]any{"realization_observations": []any{prior}}, envelope)
	if err != nil || len(result) != 0 {
		t.Fatal("update reused prior evidence", err)
	}
	operation["action"] = "unchanged"
	demand["collection"] = "disable"
	result, err = retainedObservations(plan, map[string]any{"realization_observations": []any{prior}}, envelope)
	if err != nil || len(result) != 0 {
		t.Fatal("unselected evidence retained", err)
	}
}

package planning_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

func TestPreparedSparseListenerCannotBorrowTheNativeDefaultProtocol(t *testing.T) {
	original := preparedSelectionTargetFixture(t, `name: selected-listener
realization:
 default: closed
 scopes:
 - {field_pointer: /nodes/host/runtime/service_listeners, posture: open}
nodes:
 host:
  type: compute
  runtime:
   service_listeners: [{service_listener_id: web, protocol: tcp}]
`, func(record map[string]any) {
		support := requireType[map[string]any](t, requireType[[]any](t, record["realization_support"])[0])
		for _, key := range []string{"supported_constraint_kinds", "supported_exact_requirement_kinds"} {
			support[key] = append(requireType[[]any](t, support[key]), "service-listeners")
		}
		requireType[map[string]any](t, support["observation_capabilities"])["service-listeners"] = map[string]any{"verification_scope": "configuration", "observation_strength": "guest-observed"}
	})
	admitted, violation, err := planning.CheckPreparedSelection(original, original.Provisioning())
	requireNoError(t, err)
	if admitted == nil || violation != "" {
		t.Fatalf("unchanged exact listener refused: %s", violation)
	}
	selected := changePreparedPlan(t, original.Provisioning(), func(record map[string]any) {
		operation := requireType[map[string]any](t, requireType[[]any](t, record["operations"])[0])
		payload := requireType[map[string]any](t, operation["payload"])
		node := requireType[map[string]any](t, requireType[map[string]any](t, payload["spec"])["node"])
		runtime := requireType[map[string]any](t, node["runtime"])
		runtime["service_listeners"] = []any{map[string]any{"service_listener_id": "web"}}
	})
	admitted, violation, err = planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted != nil || violation != "Backend preparation does not satisfy the recursive constraints." {
		t.Fatalf("omitted protocol received authored TCP authority: %s", violation)
	}
}

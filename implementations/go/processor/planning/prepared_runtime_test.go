package planning_test

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

func TestPreparedAdditionalNodeDeliversSupportedContainerPrivilege(t *testing.T) {
	original := preparedSelectionTargetFixture(t, portableCollectionSource, func(record map[string]any) {
		support := requireType[map[string]any](t, requireType[[]any](t, record["realization_support"])[0])
		support["supported_exact_requirement_kinds"] = append(requireType[[]any](t, support["supported_exact_requirement_kinds"]), "runtime-container-privileged")
	})
	selected := additionalPreparedNode(t, original.Provisioning(), func(operation map[string]any) {
		preparedRuntime(t, operation)["container"] = map[string]any{"privileged": true}
	})
	admitted, violation, err := planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted == nil || violation != "" {
		t.Fatalf("supported container privilege refused: %s", violation)
	}
	snapshot := preparedReturnedSnapshot(t, original, selected)
	violation, err = planning.CheckPreparedDelivery(admitted, snapshot)
	requireNoError(t, err)
	if violation != "" {
		t.Fatalf("selected container privilege delivery refused: %s", violation)
	}
	safe, err := planning.SanitizePreparedSnapshot(admitted, snapshot)
	requireNoError(t, err)
	var entry map[string]any
	requireNoError(t, json.Unmarshal(field(safe.Entries)["provision.node.extra"], &entry))
	runtime := preparedRuntime(t, map[string]any{"payload": entry["payload"]})
	if requireType[map[string]any](t, runtime["container"])["privileged"] != true {
		t.Fatal("safe projection lost selected container privilege")
	}
}

func TestPreparedOriginalNodeRefusesMalformedEngineAndRenamedDatabaseIdentity(t *testing.T) {
	original := preparedSelectionFixture(t, selectedDatabaseSource)
	baseline := changePreparedPlan(t, original.Provisioning(), func(record map[string]any) {
		preparedDatabaseEngine(t, record, "sqlite")
	})
	admitted, violation, err := planning.CheckPreparedSelection(original, baseline)
	requireNoError(t, err)
	if admitted == nil || violation != "" {
		t.Fatalf("supported original-node completion refused: %s", violation)
	}
	for _, mutation := range []struct{ field, value string }{
		{"engine", "unqualified-private-engine"},
		{"database_service_id", "renamed"},
	} {
		t.Run(mutation.field, func(t *testing.T) {
			candidate := changePreparedPlan(t, baseline, func(record map[string]any) {
				operation := requireType[map[string]any](t, requireType[[]any](t, record["operations"])[0])
				runtime := preparedRuntime(t, operation)
				requireType[map[string]any](t, requireType[[]any](t, runtime["database_services"])[0])[mutation.field] = mutation.value
			})
			selected, violation, err := planning.CheckPreparedSelection(original, candidate)
			if selected != nil || (err == nil && violation == "") {
				t.Fatalf("malformed %s completion accepted: %s", mutation.field, violation)
			}
		})
	}
}

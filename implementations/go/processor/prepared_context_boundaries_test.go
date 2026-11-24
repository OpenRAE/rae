package processor

import "testing"

func TestPreparedMountGrantsRequireCanonicalTargetsAndKeepSourceFields(t *testing.T) {
	valid := map[string]any{"node": "host", "target": "/mnt/data", "delivery_mode": "mount", "target_address": "provision.node.host"}
	rows, err := preparedMountConsumers([]any{valid})
	if err != nil || len(rows) != 1 {
		t.Fatalf("valid mount grant refused: %v", err)
	}
	projected, ok := rows[0].(map[string]any)
	if !ok || projected["node"] != "host" || projected["target"] != "/mnt/data" || projected["delivery_mode"] != nil || projected["target_address"] != nil {
		t.Fatalf("invalid native mount projection: %v", projected)
	}
	if valid["delivery_mode"] != "mount" || valid["target_address"] != "provision.node.host" {
		t.Fatal("grant projection mutated caller fields")
	}
	for _, input := range []any{"not-a-list", []any{"not-a-record"}, []any{map[string]any{"node": "host", "delivery_mode": "environment"}}, []any{map[string]any{"node": "host", "target_address": "provision.node.other"}}} {
		if _, err := preparedMountConsumers(input); err == nil {
			t.Fatalf("invalid mount grant accepted: %v", input)
		}
	}
	if rows, err := preparedMountConsumers(nil); err != nil || len(rows) != 0 {
		t.Fatal("absent mount grants were not empty")
	}
}

func TestPreparedResourceSpecificationsRefuseMismatchedNativeIdentity(t *testing.T) {
	context := preparedContext{value: map[string]any{"persistent_volumes": map[string]any{}}}
	valid := map[string]any{"resource_type": "persistent-volume", "payload": map[string]any{"name": "data", "spec": map[string]any{"consumers": []any{map[string]any{"node": "host", "delivery_mode": "mount", "target_address": "provision.node.host"}}}}}
	if err := context.resource("provision.persistent-volume.data", valid); err != nil {
		t.Fatal(err)
	}
	volumes, ok := context.value["persistent_volumes"].(map[string]any)
	if !ok || len(volumes) != 1 {
		t.Fatal("valid native volume specification was lost")
	}
	for _, input := range []any{nil, map[string]any{}, map[string]any{"resource_type": "persistent-volume", "payload": "bad"}, map[string]any{"resource_type": "persistent-volume", "payload": map[string]any{"name": "data"}}, map[string]any{"resource_type": "persistent-volume", "payload": map[string]any{"name": "other", "spec": map[string]any{}}}} {
		if context.resource("provision.persistent-volume.data", input) == nil {
			t.Fatalf("invalid resource specification accepted: %v", input)
		}
	}
	if context.resource("provision.node.host", map[string]any{"resource_type": "node", "payload": map[string]any{}}) != nil {
		t.Fatal("unrelated resource kind was treated as a volume")
	}
	if _, err := preparedProjectionRows("bad"); err == nil {
		t.Fatal("non-list grant projection accepted")
	}
}

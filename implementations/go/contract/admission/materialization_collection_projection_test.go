package admission

import "testing"

func TestMaterializationDifferencesKeepNestedNativeInventoryIdentity(t *testing.T) {
	before := decodeRuleObject(t, `{"nodes":{"host":{"runtime":{"database_services":[{"database_service_id":"db","databases":[{"database_id":"first","name":"a"},{"database_id":"second","name":"b"}]}]}}}}`)
	after := decodeRuleObject(t, `{"nodes":{"host":{"runtime":{"database_services":[{"database_service_id":"db","databases":[{"database_id":"second","name":"b"},{"database_id":"first","name":"a"}]}]}}}}`)
	difference := materializationDiff{identities: map[string][]string{"/nodes/host/runtime/database_services": {"database_service_id"}}, remaining: 100000}
	if err := difference.walk(materializationOperand{value: before, present: true}, materializationOperand{value: after, present: true}); err != nil {
		t.Fatal(err)
	}
	if len(difference.origins) != 0 {
		t.Fatalf("reordering native database identities invented %d differences", len(difference.origins))
	}
}

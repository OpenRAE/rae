package sdlrules

import "testing"

func TestServiceContentProjectionRefusesMalformedTypedFields(t *testing.T) {
	for _, raw := range []string{
		`{"content":{"a":{"service_materialization":3}}}`,
		`{"nodes":{"n":{"services":[{"name":{}}]}}}`,
		`{"content":{"a":{"service_materialization":{"target_service_ref":"nodes.n.services.s","shared_service_relationship_ref":"r"}}},"relationships":{"r":{"type":"uses_shared_service","target":"nodes.n.services.s","shared_service":1}}}`,
	} {
		if findings, err := ServiceMaterialization([]byte(raw), nil); err == nil || len(findings) != 0 {
			t.Errorf("malformed projection produced findings %v, error %v", findings, err)
		}
	}
}

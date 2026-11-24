package parity

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestProcessorDiagnosticProjectionKeepsPayloadMembers(t *testing.T) {
	document := map[string]any{
		"diagnostics": []any{map[string]any{"code": "example", "domain": "provisioning", "address": "host", "severity": "error", "message": "reported-diagnostic-message"}},
		"provisioning": map[string]any{
			"diagnostics": []any{},
			"operations": []any{map[string]any{"payload": map[string]any{
				"diagnostics": []any{map[string]any{"code": "user-data", "message": "retained-payload-value"}},
			}}},
		},
	}
	raw, err := json.Marshal(processorDiagnosticProjection(document))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), "retained-payload-value") {
		t.Fatalf("payload changed during diagnostic projection: %s", raw)
	}
	if strings.Contains(string(raw), "reported-diagnostic-message") {
		t.Fatal("known diagnostic location was not normalized")
	}
}

func TestProcessorPlanProjectionOmitsCredentialMaterialValues(t *testing.T) {
	source := []byte(`name: example
nodes:
  server: {type: compute}
accounts:
  operator:
    node: server
    username: operator
    credential_bindings:
      - credential_id: login
        purpose: primary_authentication
        auth_method: password
        material: {classification: secret_fixture, value: fixture-password}
`)
	result, err := processorPlanRunner()(t.Context(), Case{Args: []string{"processor", "plan", "scenario.yaml", "--format", "json"}, Files: map[string][]byte{"scenario.yaml": source}})
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(result), "fixture-password") {
		t.Fatal("plan inspection exposed credential material")
	}
	if !strings.Contains(string(result), `"value_present":true`) {
		t.Fatalf("presence projection missing: %s", result)
	}
}

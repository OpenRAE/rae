package admission

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestAccountProjectionDisclosesOnlyCredentialMaterialPresence(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	input := map[string]any{"name": "operator", "spec": map[string]any{"username": "operator", "credential_bindings": []any{
		map[string]any{"credential_id": "fixture", "purpose": "login", "auth_method": "password", "material": map[string]any{"classification": "secret_fixture", "value": "fixture-password", "extra": "discard"}},
		map[string]any{"credential_id": "operator", "purpose": "login", "auth_method": "key", "material": map[string]any{"classification": "operator_secret", "reference_id": "sensitive-reference"}},
	}}}
	fragment, err := AdmitFragment(owner, RealizationValue, input, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	result, err := ValueFreeAccountPlacement(fragment)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(result.Document())
	if err != nil {
		t.Fatal(err)
	}
	for _, secret := range []string{"fixture-password", "sensitive-reference", "extra"} {
		if strings.Contains(string(raw), secret) {
			t.Fatalf("material leaked: %s", raw)
		}
	}
	bindings := requireType[[]any](t, object(at(result.Document(), "spec"))["credential_bindings"])
	if at(bindings[0], "material", "value_present") != true || at(bindings[1], "material", "reference_present") != true {
		t.Fatalf("presence lost: %s", raw)
	}
	original := array(at(fragment.Document(), "spec", "credential_bindings"))
	if stringAt(original[0], "material", "value") != "fixture-password" {
		t.Fatal("projection changed its native input")
	}

	if _, err := ValueFreeAccountPlacement(replacedConstraintFragment{fragment}); err == nil {
		t.Fatal("foreign fragment accepted")
	}
}

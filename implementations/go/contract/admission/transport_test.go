package admission_test

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type foreignTransport struct{ binding.BackendManifestV2 }

func (foreignTransport) MarshalJSON() ([]byte, error) { panic("foreign transport called") }

func TestTransportBoundsBeforeSerialization(t *testing.T) {
	var document binding.BackendManifestV2
	raw := []byte(`{"constraints":{"value":"<&"},"supported_contract_versions":["one"],"configuration_registry":{"enabled":false}}`)
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: len(encoded), MaxDepth: 16}
	if err := admission.CheckTransport(document, limits); err != nil {
		t.Fatal(err)
	}
	limits.MaxBytes--
	if admission.CheckTransport(document, limits) == nil {
		t.Fatal("encoded byte overflow was accepted")
	}
	limits.MaxBytes = 1 << 20
	constraints, _ := document.Constraints.Value()
	constraints["value"] = string([]byte{0xff})
	if admission.CheckTransport(document, limits) == nil {
		t.Fatal("invalid Unicode was accepted")
	}
	constraints["value"] = "safe"
	message, _ := document.ConfigurationRegistry.Value()
	copy(message, []byte(`{"enabled":NaN }`))
	if admission.CheckTransport(document, limits) == nil {
		t.Fatal("invalid raw JSON was accepted")
	}
	if admission.CheckTransport(foreignTransport{}, limits) == nil {
		t.Fatal("foreign transport was accepted")
	}
}

func TestTransportRetainsRawEscapesAndDepthBounds(t *testing.T) {
	for _, payload := range []string{`{"value":"\u0061<&"}`, `{"value":"line\nend"}`, `123456789012345678901234567890`, `false`, `null`} {
		var document binding.BackendManifestV2
		if err := json.Unmarshal([]byte(`{"configuration_registry":`+payload+`}`), &document); err != nil {
			t.Fatal(err)
		}
		encoded, err := json.Marshal(document)
		if err != nil {
			t.Fatal(err)
		}
		if err := admission.CheckTransport(document, ingress.Limits{MaxBytes: len(encoded), MaxDepth: 16}); err != nil {
			t.Fatalf("valid exact byte boundary refused for %s: %v", payload, err)
		}
		if admission.CheckTransport(document, ingress.Limits{MaxBytes: len(encoded) - 1, MaxDepth: 16}) == nil {
			t.Fatal("raw escape bytes did not consume the budget")
		}
	}
	var document binding.BackendManifestV2
	if err := json.Unmarshal([]byte(`{"configuration_registry":{"nested":{"value":true}}}`), &document); err != nil {
		t.Fatal(err)
	}
	if admission.CheckTransport(document, ingress.Limits{MaxBytes: 4096, MaxDepth: 1}) == nil {
		t.Fatal("nested raw transport bypassed the depth bound")
	}
}

type foreignText string

func (foreignText) MarshalJSON() ([]byte, error) { panic("foreign text called") }
func TestTransportTreeBoundsKnownRecordsWithoutForeignMethods(t *testing.T) {
	var record binding.RuntimeSnapshotV1
	if json.Unmarshal([]byte(`{"schema_version":"runtime-snapshot/v1","entries":{}}`), &record) != nil {
		t.Fatal("fixture")
	}
	tree := map[string]any{"record": record, "count": 3, "ratio": 0.5, "null": nil, "raw": json.RawMessage(`{"valid":true}`)}
	raw, err := json.Marshal(tree)
	if err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: len(raw), MaxDepth: 64}
	if err = admission.CheckTransportTree(tree, limits); err != nil {
		t.Fatal(err)
	}
	limits.MaxBytes--
	if admission.CheckTransportTree(tree, limits) == nil {
		t.Fatal("aggregate overflow accepted")
	}
	for _, v := range []any{foreignTransport{}, foreignText("text")} {
		if admission.CheckTransportTree(map[string]any{"foreign": v}, ingress.Limits{MaxBytes: 1024, MaxDepth: 64}) == nil {
			t.Fatal("foreign carrier accepted")
		}
	}
	cycle := map[string]any{}
	cycle["self"] = cycle
	if admission.CheckTransportTree(cycle, ingress.Limits{MaxBytes: 1024, MaxDepth: 64}) == nil {
		t.Fatal("cycle accepted")
	}
}

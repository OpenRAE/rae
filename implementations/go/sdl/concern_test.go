package sdl_test

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type foreignFragment struct{ admission.Fragment }

func (foreignFragment) Document() any { panic("foreign fragment called") }

func TestPublicConcernUsesNativeDefaultsAndScalarRules(t *testing.T) {
	validator, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}
	fragment := func(profile admission.FragmentProfile, value any) admission.Fragment {
		t.Helper()
		result, checkErr := admission.AdmitFragment(validator, profile, value, limits)
		if checkErr != nil {
			t.Fatal(checkErr)
		}
		return result
	}
	descriptor := fragment(admission.RealizationConcern, map[string]any{"section": "nodes", "authored_path": []any{"runtime", "environment"}, "concern_kind": "runtime-environment", "payload_path": []any{"spec", "node", "runtime", "environment"}, "non_stateful_mounts_only": false, "explicitness_excluded_fields": []any{}, "collection_identity_fields": []any{"name"}})
	input := fragment(admission.RealizationValue, []any{map[string]any{"name": "PUBLIC", "value": "example", "value_classification": "PLAIN", "provenance": "IMAGE"}})
	result, err := sdl.NormalizeConcernValue(descriptor, input)
	if err != nil {
		t.Fatal(err)
	}
	values := requireType[[]any](t, result.Document())
	entry := requireType[map[string]any](t, values[0])
	if entry["value_classification"] != "plain" || entry["provenance"] != "image" || entry["source"] != "" || entry["description"] != "" {
		t.Fatalf("constructor rules were lost: %#v", entry)
	}
	for _, value := range []admission.Fragment{nil, foreignFragment{input}} {
		if _, err := sdl.NormalizeConcernValue(descriptor, value); err == nil {
			t.Fatal("foreign value was accepted")
		}
	}
	if _, err := sdl.NormalizeConcernValue(foreignFragment{descriptor}, input); err == nil {
		t.Fatal("foreign descriptor was accepted")
	}
	invalid := fragment(admission.RealizationValue, []any{map[string]any{"name": "PUBLIC", "extra": true}})
	if _, err := sdl.NormalizeConcernValue(descriptor, invalid); err == nil {
		t.Fatal("unknown native field was accepted")
	}
}

func TestCapabilityNormalizationUsesSDLScalarRules(t *testing.T) {
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	for _, item := range []struct {
		concern         string
		input, expected any
		invalid         bool
	}{
		{"nodes.architecture", "amd64", "x86_64", false},
		{"infrastructure.count", "5000000000", nil, false},
		{"infrastructure.count", true, nil, true},
		{"infrastructure.count", "0", nil, true},
		{"nodes.os", "LINUX", "linux", false},
		{"nodes.unrecognized", "linux", nil, true},
	} {
		fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, item.input, ingress.Limits{MaxBytes: 1024, MaxDepth: 8})
		if err != nil {
			t.Fatal(err)
		}
		result, err := sdl.NormalizeCapabilityValue(item.concern, fragment)
		if item.invalid {
			if err == nil {
				t.Fatalf("accepted %s=%v", item.concern, item.input)
			}
			continue
		}
		if err != nil {
			t.Fatalf("%s: %v", item.concern, err)
		}
		if item.expected != nil && result.Document() != item.expected {
			t.Fatalf("%s=%v", item.concern, result.Document())
		}
	}
	if _, err := sdl.NormalizeCapabilityValue("nodes.os", foreignFragment{}); err == nil {
		t.Fatal("foreign value accepted")
	}
}

func TestInstantiatedModelRetainsDefaultListenerProtocol(t *testing.T) {
	scenario, err := sdl.Parse([]byte("name: example\nnodes:\n  server:\n    type: compute\n    runtime:\n      service_listeners: [{service_listener_id: telemetry}]\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := sdl.ModelBytes(instance)
	if err != nil {
		t.Fatal(err)
	}
	var model struct {
		Nodes map[string]struct {
			Runtime struct {
				Listeners []struct {
					Protocol string `json:"protocol"`
				} `json:"service_listeners"`
			} `json:"runtime"`
		} `json:"nodes"`
	}
	if err := json.Unmarshal(raw, &model); err != nil {
		t.Fatal(err)
	}
	if model.Nodes["server"].Runtime.Listeners[0].Protocol != "tcp" {
		t.Fatalf("listener default omitted: %s", raw)
	}
}

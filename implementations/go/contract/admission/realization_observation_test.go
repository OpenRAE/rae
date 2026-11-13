package admission

import (
	"encoding/json"
	"maps"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func observedBindingFixture() map[string]any {
	return map[string]any{"address": "provision.node.server", "field_path": "nodes.server.realization.compute-substrate", "domain": "runtime-realization", "requirement_kind": "compute-substrate", "verification_scope": "presence", "observation_strength": "daemon-observed", "observed_value": "virtual-machine", "operation_id": "operation:test", "envelope_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "configuration_digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "observer_version": "test/v1", "sequence": json.Number("0"), "binding_verified": true}
}
func checkObservationModel(t *testing.T, owner *Validator, document map[string]any) error {
	t.Helper()
	raw, err := json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	return owner.CheckModelFragment("runtime-snapshot-v1", "#/$defs/RealizationObservationDisclosureModel", raw, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
}
func TestRealizationObservationRequiresCompleteIndependentBinding(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	valid := observedBindingFixture()
	if err := checkObservationModel(t, owner, valid); err != nil {
		t.Fatal(err)
	}
	for _, field := range []string{"observed_value", "operation_id", "envelope_digest", "configuration_digest", "observer_version", "sequence", "binding_verified"} {
		t.Run(field, func(t *testing.T) {
			changed := maps.Clone(valid)
			delete(changed, field)
			if err := checkObservationModel(t, owner, changed); err == nil {
				t.Fatalf("missing %s admitted", field)
			}
		})
	}
	for _, value := range []any{"Virtual-machine", "unknown-substrate"} {
		changed := maps.Clone(valid)
		changed["observed_value"] = value
		if err := checkObservationModel(t, owner, changed); err == nil {
			t.Fatal("ungoverned substrate admitted")
		}
	}
}
func TestRealizationObservationSeparatesOSAndValueFreeConcerns(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	operating := observedBindingFixture()
	operating["requirement_kind"] = "operating-system"
	operating["observed_value"] = nil
	operating["operating_system"] = map[string]any{"family": "linux", "distribution": "ubuntu", "version": "24.04"}
	operating["observation_strength"] = "guest-observed"
	if err := checkObservationModel(t, owner, operating); err != nil {
		t.Fatal(err)
	}
	changed := maps.Clone(operating)
	changed["observation_strength"] = "daemon-observed"
	if err := checkObservationModel(t, owner, changed); err == nil {
		t.Fatal("daemon claim substituted for guest identity")
	}
	operating["operating_system"] = map[string]any{"family": "windows", "distribution": "ubuntu", "version": "24.04"}
	if err := checkObservationModel(t, owner, operating); err == nil {
		t.Fatal("cross-family OS identity admitted")
	}
	valueFree := map[string]any{"address": "provision.node.server", "field_path": "nodes.server.runtime.environment", "domain": "runtime-realization", "requirement_kind": "runtime-environment", "verification_scope": "configuration", "observation_strength": "daemon-observed"}
	if err := checkObservationModel(t, owner, valueFree); err != nil {
		t.Fatal(err)
	}
	valueFree["sequence"] = json.Number("0")
	if err := checkObservationModel(t, owner, valueFree); err == nil {
		t.Fatal("ordinary concern acquired value-bearing binding")
	}
}

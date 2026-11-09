package admission

import (
	"encoding/json"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestRuntimeProcessLimitReference(t *testing.T) {
	var reference struct {
		Cases []struct {
			Name, Digest                  string
			Value, Projection, Capability json.RawMessage
			Soft, Hard                    json.RawMessage
			Admitted                      bool
		}
	}
	readFullReferenceJSON(t, "testdata/runtime-process-limits.json", &reference)
	for _, row := range reference.Cases {
		t.Run(row.Name, func(t *testing.T) {
			value := decodeRuleObject(t, string(row.Value))
			projection := sdlProcessLimitProjection(value)
			if diff := cmp.Diff(decodeRuleObject(t, string(row.Projection)), projection); diff != "" {
				t.Errorf("projection differs (-reference +actual):\n%s", diff)
			}
			identity, err := sdlProcessLimitIdentity(value)
			if err != nil || identity != row.Digest {
				t.Errorf("identity = %q, %v; want %q", identity, err, row.Digest)
			}
			claim := decodeRuleObject(t, string(row.Capability))
			soft := array(decodeRuleObject(t, string(row.Soft)))
			hard := array(decodeRuleObject(t, string(row.Hard)))
			if actual := sdlProcessLimitCapabilityAdmits(claim, value, soft, hard); actual != row.Admitted {
				t.Errorf("capability admits = %v; want %v", actual, row.Admitted)
			}
		})
	}
}

func TestRuntimeProcessLimitIdentityBounds(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	for _, row := range []struct {
		name, value string
		accepted    bool
	}{
		{"largest-exact-selector", `{"process_limits":[{"resource":"open_file_descriptors","soft":1,"hard":2,"subject":{"pid":9007199254740991}}]}`, true},
		{"nonrepresentable-selector", `{"process_limits":[{"resource":"open_file_descriptors","soft":1,"hard":2,"subject":{"pid":9007199254740992}}]}`, false},
		{"duplicate-identity-different-bounds", `{"process_limits":[{"resource":"open_file_descriptors","soft":1,"hard":2,"subject":{"name":"worker"}},{"resource":"open_file_descriptors","soft":3,"hard":4,"subject":{"name":"worker"},"description":"different"}]}`, false},
	} {
		t.Run(row.name, func(t *testing.T) {
			err := owner.CheckSDLConstruction("sdl-authoring-input-v1", "#/$defs/RuntimeResourceLimits", []byte(row.value), ingress.Limits{MaxBytes: len(row.value)})
			if (err == nil) != row.accepted {
				t.Errorf("accepted = %v, %v; want %v", err == nil, err, row.accepted)
			}
		})
	}
}

func TestRuntimeProcessLimitProjectionCopiesSelector(t *testing.T) {
	value := decodeRuleObject(t, `{"resource":"open_file_descriptors","soft":1,"hard":2,"subject":{"name":"worker","command":["run","--flag"]}}`)
	projection := sdlProcessLimitProjection(value)
	subject := object(projection["subject"])
	subject["name"] = "changed"
	array(subject["command"])[0] = "changed"
	if stringAt(value, "subject", "name") != "worker" || text(array(at(value, "subject", "command"))[0]) != "run" {
		t.Fatal("projection changed caller-owned selector")
	}
}

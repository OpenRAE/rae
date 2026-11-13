package sdl_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestForwardingProtocolAgreementKeepsPrivateIdentityExact(t *testing.T) {
	for _, test := range []struct {
		name, protocol string
		valid          bool
	}{
		{"same-private-identity", "x-owner:wire", true},
		{"different-private-identity", "x-owner:other", false},
		{"core-is-not-private-identity", "syslog", false},
		{"unknown-edge-defers-agreement", "unknown", true},
	} {
		t.Run(test.name, func(t *testing.T) {
			source := "name: private-protocol\nnodes: {source: {type: switch}, sink: {type: switch}}\nforwarding_agents:\n- forwarding_agent_id: shipper\n  ship_targets: [{target_id: target, protocol: 'x-owner:wire'}]\nrelationships:\n  shipping:\n    type: connects_to\n    source: source\n    target: sink\n    forwarding_edge: {forwarder_ref: shipper, protocol: '" + test.protocol + "'}\n"
			_, err := sdl.Parse([]byte(source), sdl.DefaultParseOptions())
			if (err == nil) != test.valid {
				t.Fatalf("valid=%v,error=%v", test.valid, err)
			}
		})
	}
}

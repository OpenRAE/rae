package admission

import "testing"

func TestStatefulResourceLocalRules(t *testing.T) {
	for _, test := range []struct {
		rule, raw string
		valid     bool
	}{
		{"stateful-generated-artifact-semantics", `{"generated_artifacts":{"key":{"generator":"ssh_key_bundle","outputs":[{"name":"public","path":"key.pub","sensitivity":"public"}],"consumers":[{"node":"host","mount_destination":"/keys","access_mode":"read_only","selected_outputs":["public"]}]}}}`, true},
		{"stateful-generated-artifact-semantics", `{"generated_artifacts":{"key":{"generator":"ssh_key_bundle","outputs":[{"name":"private","path":"key","disposition":"producer_private"}],"consumers":[{"node":"host","mount_destination":"/keys","access_mode":"read_only","selected_outputs":["private"]}]}}}`, false},
		{"stateful-generated-artifact-semantics", `{"generated_artifacts":{"value":{"generator":"random_value","regeneration_scope":"trial","random_value":{"alphabet":"hex_lower","length":32},"outputs":[{"name":"value","path":"value","sensitivity":"secret"}]}}}`, true},
		{"stateful-generated-artifact-semantics", `{"generated_artifacts":{"value":{"generator":"random_value","regeneration_scope":"trial","random_value":{"alphabet":"hex_lower","length":31},"outputs":[{"name":"value","path":"value","sensitivity":"secret"}]}}}`, false},
		{"stateful-persistent-volume-semantics", `{"persistent_volumes":{"volume":{"access_mode":"read_write_once","consumers":[{"node":"one","mount_destination":"/data","access_mode":"read_write"},{"node":"two","mount_destination":"/data","access_mode":"read_write"}]}}}`, false},
		{"stateful-cross-resource-semantics", `{"nodes":{"host":{"os":"linux"}},"persistent_volumes":{"one":{"consumers":[{"node":"host","mount_destination":"/data"}]},"two":{"consumers":[{"node":"nodes.host","mount_destination":"/data"}]}}}`, false},
	} {
		assertRule(t, test.rule, test.raw, test.valid)
	}
}

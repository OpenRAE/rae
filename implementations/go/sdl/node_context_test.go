package sdl_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

//nolint:ireturn // The test requires the native opaque fragment admission boundary.
func nodeContextFragment(t *testing.T, input any) admission.Fragment {
	t.Helper()
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	result, err := admission.AdmitFragment(owner, admission.RealizationValue, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	return result
}
func TestNodeRealizationContextUsesNativeRuntimeReferenceChecks(t *testing.T) {
	for _, test := range []struct {
		name, service string
		invalid       bool
	}{{"existing-service", "database", false}, {"missing-service", "absent", true}} {
		t.Run(test.name, func(t *testing.T) {
			input := nodeContextFragment(t, map[string]any{"name": "prepared-node-context", "nodes": map[string]any{"host": map[string]any{"type": "compute", "services": []any{map[string]any{"name": "database", "port": 5432}}, "runtime": map[string]any{"database_services": []any{map[string]any{"database_service_id": "db", "engine": "sqlite", "service": test.service}}}}}})
			findings, err := sdl.ValidateNodeRealizationContext(input)
			if err != nil {
				t.Fatal(err)
			}
			if (len(findings) > 0) != test.invalid {
				t.Fatalf("native reference findings=%v", findings)
			}
		})
	}
}
func TestNodeRealizationContextRefusesForeignAndGlobalAuthority(t *testing.T) {
	input := nodeContextFragment(t, map[string]any{"name": "prepared-node-context", "nodes": map[string]any{}})
	if _, err := sdl.ValidateNodeRealizationContext(foreignFragment{input}); err == nil {
		t.Fatal("foreign handle accepted")
	}
	extra := nodeContextFragment(t, map[string]any{"name": "prepared-node-context", "nodes": map[string]any{}, "features": map[string]any{}})
	if _, err := sdl.ValidateNodeRealizationContext(extra); err == nil {
		t.Fatal("selected node context accepted global source authority")
	}
}

func TestNodeRealizationContextRetainsSelectedInputRefusals(t *testing.T) {
	cases := []struct {
		name                 string
		node, infrastructure map[string]any
	}{
		{"cpu-variable", map[string]any{"type": "compute", "resources": map[string]any{"ram": 1024, "cpu": "${unresolved_cpu}"}}, nil},
		{"missing-artifact", map[string]any{"type": "compute", "runtime": map[string]any{"environment": []any{map[string]any{"name": "MODE", "value_classification": "plain", "provenance": "runtime", "value_from": map[string]any{"generated_artifact": "generated_artifacts.absent", "output": "mode"}}}}}, nil},
		{"missing-acl-network", map[string]any{"type": "compute"}, map[string]any{"acls": []any{map[string]any{"from_net": "absent-network", "to_net": "absent-network"}}}},
		{"distribution-without-family", map[string]any{"type": "compute", "os_distribution": "ubuntu"}, nil},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			context := map[string]any{"name": "prepared-node-context", "nodes": map[string]any{"host": test.node}}
			if test.infrastructure != nil {
				context["infrastructure"] = map[string]any{"host": test.infrastructure}
			}
			findings, err := sdl.ValidateNodeRealizationContext(nodeContextFragment(t, context))
			if err == nil && len(findings) == 0 {
				t.Fatal("selected context bypassed native semantic refusal")
			}
		})
	}
}

package realization

import (
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestComputeSubstrateRetainsNeutralExactFiniteAndMigratedAuthority(t *testing.T) {
	for _, test := range []struct {
		name, source, posture, provenance string
		domain                            any
		migrate                           bool
	}{
		{"neutral", "name: neutral\nnodes: {endpoint: {type: compute, os: linux}}", "open", "author-declared", nil, false},
		{"exact", "name: exact\nrealization: {constraints: [{field_pointer: /nodes/endpoint, concern: compute-substrate, posture: exact, domain: {kind: exact, value: virtual-machine}}]}\nnodes: {endpoint: {type: compute}}", "exact", "author-declared", map[string]any{"kind": "exact", "value": "virtual-machine"}, false},
		{"finite", "name: finite\nrealization: {constraints: [{field_pointer: /nodes/endpoint, concern: compute-substrate, posture: constrained, domain: {kind: enum, values: [operating-system-container, physical-device]}}]}\nnodes: {endpoint: {type: compute}}", "constrained", "author-declared", map[string]any{"kind": "enum", "values": []any{"operating-system-container", "physical-device"}}, false},
		{"legacy-vm", "name: legacy\nnodes: {endpoint: {type: vm}}", "exact", "author-declared", map[string]any{"kind": "exact", "value": "virtual-machine"}, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			options := sdl.DefaultParseOptions()
			if test.migrate {
				options.MigrationPolicy = sdl.AcceptMigration
			}
			scenario, err := sdl.Parse([]byte(test.source), options)
			requireNoError(t, err)
			concrete, err := sdl.Instantiate(scenario, nil)
			requireNoError(t, err)
			compiled, err := Compile(concrete)
			requireNoError(t, err)
			requirement := requireTestRequirement(t, compiled, "compute-substrate")
			if requirement.Posture == nil || *requirement.Posture != test.posture || requirement.Provenance != test.provenance || requirement.GoverningScope != "#/nodes/endpoint" {
				t.Fatalf("compute authority=%+v", requirement)
			}
			if diff := cmp.Diff(test.domain, fragmentDocument(requirement.ValueDomain)); diff != "" {
				t.Fatalf("compute domain differs (-expected +actual):\n%s", diff)
			}
			if test.migrate && requirement.ConstraintProvenance != "legacy-node-type-vm" {
				t.Fatalf("migration constraint lost its processor-owned origin: %s", requirement.ConstraintProvenance)
			}
		})
	}
}

func TestComputeSubstrateSourceRefusesForgedAndCollidingAuthority(t *testing.T) {
	for _, test := range []struct {
		name, node, constraint string
		migrate                bool
	}{
		{"legacy-requires-migration", "vm", "", false},
		{"switch-cannot-select-substrate", "switch", "{field_pointer: /nodes/endpoint, concern: compute-substrate, posture: exact, domain: {kind: exact, value: virtual-machine}}", false},
		{"forged-provenance", "compute", "{field_pointer: /nodes/endpoint, concern: compute-substrate, posture: exact, domain: {kind: exact, value: virtual-machine}, provenance: legacy-node-type-vm}", false},
		{"legacy-collision", "vm", "{field_pointer: /nodes/endpoint, concern: compute-substrate, posture: exact, domain: {kind: exact, value: virtual-machine}}", true},
		{"ungoverned-domain", "compute", "{field_pointer: /nodes/endpoint, concern: compute-substrate, posture: exact, domain: {kind: exact, value: unknown-substrate}}", false},
		{"unrecognized-product", "compute", "{field_pointer: /nodes/endpoint, concern: compute-substrate, posture: constrained, domain: {kind: exact, value: docker}}", false},
		{"ungoverned-finite-member", "compute", "{field_pointer: /nodes/endpoint, concern: compute-substrate, posture: constrained, domain: {kind: enum, values: [virtual-machine, unknown-substrate]}}", false},
		{"non-substrate-domain", "compute", "{field_pointer: /nodes/endpoint, concern: compute-substrate, posture: constrained, domain: {kind: numeric-interval, numeric_type: integer, lower: 1, upper: 2}}", false},
	} {
		t.Run(test.name, func(t *testing.T) {
			source := "name: refused\nnodes: {endpoint: {type: " + test.node + "}}\n"
			if test.constraint != "" {
				source += "realization: {constraints: [" + test.constraint + "]}\n"
			}
			options := sdl.DefaultParseOptions()
			if test.migrate {
				options.MigrationPolicy = sdl.AcceptMigration
			}
			if _, err := sdl.Parse([]byte(source), options); err == nil {
				t.Fatal("forged or conflicting substrate authority accepted")
			}
		})
	}
}

func TestImportedComputeSubstrateRetainsNamespacedAuthority(t *testing.T) {
	sources := map[string][]byte{
		"space/root.yaml":   []byte("name: imported-compute\nimports:\n- source: local:module.yaml\n  namespace: shared\n  version: 1.0.0\n"),
		"space/module.yaml": []byte("name: compute-module\nversion: 1.0.0\nmodule: {id: raes/compute-module, version: 1.0.0, exports: {nodes: [endpoint]}}\nrealization: {constraints: [{field_pointer: /nodes/endpoint, concern: compute-substrate, posture: exact, domain: {kind: exact, value: virtual-machine}}]}\nnodes: {endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}}\n"),
	}
	scenario, err := sdl.ParseContext(sdl.SourceContext{Sources: sources, Root: "space/root.yaml"}, sdl.DefaultParseOptions())
	requireNoError(t, err)
	concrete, err := sdl.Instantiate(scenario, nil)
	requireNoError(t, err)
	compiled, err := Compile(concrete)
	requireNoError(t, err)
	requirement := requireTestRequirement(t, compiled, "compute-substrate")
	if requirement.Address != "provision.node.shared.endpoint" || requirement.GoverningScope != "#/nodes/shared.endpoint" {
		t.Fatalf("imported authority lost its namespace: %+v", requirement)
	}
	if diff := cmp.Diff(map[string]any{"kind": "exact", "value": "virtual-machine"}, fragmentDocument(requirement.ValueDomain)); diff != "" {
		t.Fatalf("imported exact substrate domain differs (-expected +actual):\n%s", diff)
	}
}

func TestPublishedPlanRefusesUnproducibleExactComputeDomains(t *testing.T) {
	owner, err := realizationOwner()
	requireNoError(t, err)
	for _, test := range []struct {
		name   string
		domain any
		valid  bool
	}{
		{"singleton", map[string]any{"kind": "exact", "value": "virtual-machine"}, true},
		{"numeric", map[string]any{"kind": "numeric-interval", "numeric_type": "integer", "lower": 1, "upper": 2}, false},
		{"non-singleton-exact", map[string]any{"kind": "enum", "values": []any{"virtual-machine", "operating-system-container"}}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			document := map[string]any{
				"operations":            []any{map[string]any{"action": "create", "address": "provision.node.endpoint", "resource_type": "node", "payload": map[string]any{"spec": map[string]any{"node": map[string]any{"type": "compute"}}}}},
				"realization_authority": []any{}, "diagnostics": []any{},
				"realization_constraints": []any{map[string]any{"address": "provision.node.endpoint", "field_path": "nodes.endpoint.realization.compute-substrate", "concern": "compute-substrate", "posture": "exact", "value_domain": test.domain, "governing_scope": "#/nodes/endpoint", "provenance": "author-declared"}},
			}
			checkErr := owner.CheckPortable("provisioning-plan-v1", requireJSON(t, document), ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
			if (checkErr == nil) != test.valid {
				t.Fatalf("valid=%v,error=%v", test.valid, checkErr)
			}
		})
	}
}

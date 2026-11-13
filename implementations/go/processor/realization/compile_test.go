package realization

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func compileRealizationFixture(t *testing.T, raw string) Resolution {
	t.Helper()
	scenario, err := sdl.Parse([]byte(raw), sdl.DefaultParseOptions())
	if err != nil {
		if detail, ok := errors.AsType[diagnostic.Error](err); ok {
			t.Fatalf("%v: %+v", err, detail.Diagnostics())
		}
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	result, err := Compile(instance)
	if err != nil {
		t.Fatal(err)
	}
	return result
}
func TestRealizationCompileRetainsAuthorityAndSafeLeafConstraints(t *testing.T) {
	result := compileRealizationFixture(t, `name: example
nodes:
  server:
    type: compute
    os: linux
    runtime:
      environment:
        - {name: TOKEN, value: example, value_classification: plain}
        - {name: PUBLIC, value: '', value_classification: redacted}
`)
	if len(result.Authority) != 68 {
		t.Fatalf("authority count=%d", len(result.Authority))
	}
	var environment *Requirement
	for i := range result.Requirements {
		entry := &result.Requirements[i]
		if entry.Kind == "runtime-environment" {
			environment = entry
		}
		if entry.Kind == "os-family" && (entry.Posture == nil || *entry.Posture != "exact") {
			t.Fatal("lost exact OS authority")
		}
	}
	if environment == nil || environment.Constraint == nil || environment.ConstraintBinding == "" || environment.ObservationScope != "configuration" || environment.StructureError {
		t.Fatalf("environment=%+v", environment)
	}
	if err := admission.CheckFragment(environment.Constraint, admission.RealizationConstraint); err != nil {
		t.Fatal(err)
	}
	projection := environment.source.value
	observed, err := ProjectConcern("runtime-environment", projection, false, true)
	if err != nil {
		t.Fatal(err)
	}
	checked, err := admission.EvaluateRealizationConstraint(environment.Constraint, observed, admission.DefaultConstraintLimits())
	if err != nil || requireType[map[string]any](t, checked.Document())["status"] != "conformant" {
		t.Fatalf("compiled constraint=%v %v", checked, err)
	}
}

func TestRealizationCompileKeepsDefaultOmissionClosed(t *testing.T) {
	result := compileRealizationFixture(t, "name: example\nnodes:\n  server: {type: compute}\n")
	for _, entry := range result.Requirements {
		if entry.Kind == "runtime-environment" {
			t.Fatal("omitted closed concern acquired a requirement")
		}
	}
	for _, entry := range result.Authority {
		if entry.Concern == "runtime-environment" && (entry.Posture != "closed" || entry.Source != "legacy-default") {
			t.Fatalf("omitted authority=%+v", entry)
		}
	}
}

func TestRealizationCompileRetainsNestedClosureAndSubstrateDomain(t *testing.T) {
	result := compileRealizationFixture(t, `name: example
realization:
  default: closed
  scopes:
    - {field_pointer: /nodes/server/runtime/environment, posture: open}
  constraints:
    - field_pointer: /nodes/server
      concern: compute-substrate
      posture: constrained
      domain: {kind: enum, values: [virtual-machine, physical-device]}
nodes:
  server:
    type: compute
    runtime:
      environment: [{name: TOKEN, value: example, value_classification: plain}]
`)
	var environment, substrate *Requirement
	for i := range result.Requirements {
		entry := &result.Requirements[i]
		switch entry.Kind {
		case "runtime-environment":
			environment = entry
		case "compute-substrate":
			substrate = entry
		}
	}
	if substrate == nil || substrate.Posture == nil || *substrate.Posture != "constrained" || substrate.ValueDomain == nil {
		t.Fatalf("substrate=%+v", substrate)
	}
	if environment == nil || environment.Posture == nil || *environment.Posture != "open" || environment.Constraint == nil || environment.StructureError {
		t.Fatalf("environment=%+v", environment)
	}
	document := requireType[map[string]any](t, environment.Constraint.Document())
	if requireType[map[string]any](t, document["default_closure"])["posture"] != "open" {
		t.Fatal("local open closure lost")
	}
}

func TestRealizationCompileRetainsProcessIdentityAndExactBounds(t *testing.T) {
	result := compileRealizationFixture(t, `name: example
nodes:
  server:
    type: compute
    runtime:
      processes: [{name: worker}]
      operational_policy:
        resource_limits:
          process_limits:
            - resource: open_file_descriptors
              subject: {name: worker}
              scope: process
              soft: 5000000000
              hard: unlimited
`)
	for _, entry := range result.Requirements {
		if entry.Kind != "process-resource-limits" {
			continue
		}
		if len(entry.ProcessResourceLimits) != 1 {
			t.Fatalf("limits=%+v", entry)
		}
		limit := entry.ProcessResourceLimits[0]
		if limit.IdentityDigest == "" || requireType[json.Number](t, limit.Soft.Document()) != "5000000000" || limit.Hard.Document() != "unlimited" || entry.ObservationStrength != "guest-observed" {
			t.Fatalf("limit=%+v", limit)
		}
		return
	}
	t.Fatal("missing process requirement")
}

func TestRealizationCompileBindsFiniteCollectionIdentityChoices(t *testing.T) {
	result := compileRealizationFixture(t, `name: example
variables:
  key: {type: string, default: CAP_NET_ADMIN, allowed_values: [CAP_NET_ADMIN, CAP_CHOWN]}
nodes:
  server:
    type: compute
    runtime:
      linux_capabilities: {required: ['${key}']}
`)
	for _, requirement := range result.Requirements {
		if requirement.Kind != "linux-capabilities" {
			continue
		}
		if requirement.StructureError || requirement.Constraint == nil {
			t.Fatalf("finite identity lost: %+v", requirement)
		}
		source := requireType[map[string]any](t, requirement.source.value.Document())
		source["required"] = []any{"CAP_CHOWN"}
		fragment, err := requirement.source.input.valueFragment(source)
		if err != nil {
			t.Fatal(err)
		}
		observed, err := ProjectConcern(requirement.Kind, fragment, false, true)
		if err != nil {
			t.Fatal(err)
		}
		checked, err := admission.EvaluateRealizationConstraint(requirement.Constraint, observed, admission.DefaultConstraintLimits())
		if err != nil || requireType[map[string]any](t, checked.Document())["status"] != "conformant" {
			t.Fatalf("finite choice not admitted: %v %v", checked, err)
		}
		return
	}
	t.Fatal("missing finite identity requirement")
}

func TestRealizationCompileRefusesUnpublishableClassifiedBounds(t *testing.T) {
	result := compileRealizationFixture(t, `name: example
variables:
  key: {type: string, default: A, allowed_values: [A, B]}
nodes:
  server:
    type: compute
    runtime:
      environment: [{name: '${key}', value: example, value_classification: plain}]
`)
	for _, entry := range result.Requirements {
		if entry.Kind == "runtime-environment" {
			if !entry.StructureError || entry.Constraint != nil {
				t.Fatal("classified alternatives acquired publication authority")
			}
			return
		}
	}
	t.Fatal("missing classified requirement")
}

func TestRealizationCompileKeepsReferenceScopeOrderInBinding(t *testing.T) {
	// Captured from the reference compiler's complete requirement projection.
	result := compileRealizationFixture(t, `name: example
nodes:
  server:
    type: compute
    os: linux
    runtime:
      environment:
        - {name: TOKEN, value: example, value_classification: plain}
        - {name: PUBLIC, value: '', value_classification: redacted}
      linux_capabilities: {required: [CAP_NET_ADMIN], drop: [CAP_CHOWN]}
`)
	for _, entry := range result.Requirements {
		if entry.Kind == "linux-capabilities" {
			if entry.ConstraintBinding != "sha256:e9b446cb2b60b7f7e10bca2fbddfd64713b49fa76be4bced1e61c7c4a178d9b6" {
				t.Fatalf("reference binding changed: %s", entry.ConstraintBinding)
			}
			return
		}
	}
	t.Fatal("missing capability requirement")
}

func TestRealizationSoftwareJoinRetainsImpliedPackageCoordinates(t *testing.T) {
	result := compileRealizationFixture(t, `name: example
nodes:
  server:
    type: compute
    runtime:
      packages: [{manager: apt, name: example, version: '1'}]
      software_components:
        - component_id: app
          name: Example
          package_ref: {manager: apt, name: example}
`)
	for _, requirement := range result.Requirements {
		if requirement.Kind != "runtime-software-components" {
			continue
		}
		if requirement.StructureError || requirement.Constraint == nil {
			t.Fatalf("software join lost: %+v", requirement)
		}
		root := requireType[map[string]any](t, requireType[map[string]any](t, requirement.Constraint.Document())["root"])
		fields := requireType[map[string]any](t, requireType[map[string]any](t, requireType[map[string]any](t, requireType[[]any](t, root["members"])[0])["constraint"])["fields"])
		for key, want := range map[string]string{"package_manager": "apt", "package_name": "example", "package_version": "1"} {
			field := requireType[map[string]any](t, fields[key])
			if field["value"] != want || field["origin"] != "processor" || field["presence"] != "required" {
				t.Fatalf("implied %s=%v", key, field)
			}
		}
		return
	}
	t.Fatal("missing software requirement")
}

func TestDomainAuthorityAccountReceivesTopologyRequirement(t *testing.T) {
	result := compileRealizationFixture(t, `name: example
nodes:
  dc: {type: compute}
accounts:
  admin: {node: dc, username: administrator}
identity_domains:
  corp:
    profile: active-directory
    dns_name: corp.example
    netbios_name: CORP
    authority_account_ref: admin
relationships:
  controller: {type: domain_controller_for, source: dc, target: corp, domain_controller: {}}
`)
	found := false
	for _, requirement := range result.Requirements {
		if requirement.Address == "provision.account.admin" && requirement.Kind == "domain-topology" {
			found = true
		}
	}
	if !found {
		t.Fatal("domain authority account has no topology requirement")
	}
}

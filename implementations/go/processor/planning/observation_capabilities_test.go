package planning_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

func TestPlannerKeepsOperationalReadbackSeparateFromObservationDemands(t *testing.T) {
	target := changeManifest(t, func(record map[string]any) {
		support := requireType[map[string]any](t, requireType[[]any](t, record["realization_support"])[0])
		support["supported_exact_requirement_kinds"] = append(requireType[[]any](t, support["supported_exact_requirement_kinds"]), "forwarding-agents")
		support["observation_capabilities"] = map[string]any{"forwarding-agents": map[string]any{"verification_scope": "presence", "observation_strength": "daemon-observed"}}
	})
	for _, configured := range []bool{false, true} {
		t.Run(map[bool]string{false: "inventory-presence", true: "operational-settings"}[configured], func(t *testing.T) {
			settings := ""
			if configured {
				settings = "\n      settings: [{setting_id: endpoint, name: endpoint, value: 'https://collector.invalid', classification: plain, provenance: configuration_file}]"
			}
			model := compile(t, "name: example\nnodes:\n host:\n  type: compute\n  runtime:\n   forwarding_agents:\n    - forwarding_agent_id: telemetry"+settings+"\n")
			if len(model.Model().View().ObservationDemands) != 0 {
				t.Fatal("operational declaration invented observation demand")
			}
			result, err := planning.PlanWithManifest(model, target, planning.Options{})
			requireNoError(t, err)
			underObserved := false
			for _, finding := range result.Diagnostics {
				underObserved = underObserved || finding.Code == "realization.under-observed-exact-requirement"
			}
			if underObserved != configured {
				t.Fatalf("configured=%v observation diagnostics=%+v", configured, result.Diagnostics)
			}
		})
	}
}

func TestPlannerKeepsExactPhysicalSubstrateAuthority(t *testing.T) {
	model := compile(t, "name: physical-required\nrealization: {constraints: [{field_pointer: /nodes/endpoint, concern: compute-substrate, posture: exact, domain: {kind: exact, value: physical-device}}]}\nnodes: {endpoint: {type: compute, resources: {ram: 1 gib, cpu: 1}}}\n")
	missing, err := planning.PlanWithManifest(model, manifest(t), planning.Options{})
	requireNoError(t, err)
	if !hasPlanDiagnostic(missing, "realization.compute-substrate-envelope-required") || missing.Plan.Valid() {
		t.Errorf("exact physical substrate lost missing-envelope refusal: %+v", missing.Diagnostics)
	}
	var projection map[string]any
	requireNoError(t, json.Unmarshal(requireJSON(t, missing.Plan.Provisioning()), &projection))
	constraint := requireType[map[string]any](t, requireType[[]any](t, projection["realization_constraints"])[0])
	if constraint["posture"] != "exact" || requireType[map[string]any](t, constraint["value_domain"])["value"] != "physical-device" {
		t.Fatal("physical substrate source constraint changed")
	}
	raw, err := os.ReadFile("../../../../contracts/fixtures/realization-envelope/realization-envelope-v1/valid/generic.json")
	requireNoError(t, err)
	var envelope binding.RealizationEnvelopeV1
	requireNoError(t, json.Unmarshal(raw, &envelope))
	target := changeManifest(t, func(record map[string]any) {
		record["supported_contract_versions"] = append(requireType[[]any](t, record["supported_contract_versions"]), "realization-envelope-v1")
		record["realization_envelope"] = map[string]string{"envelope_id": field(envelope.Id), "digest": field(envelope.Digest), "configuration_digest": field(field(envelope.Configuration).ConfigurationDigest)}
	})
	selected, err := planning.PlanWithManifest(model, target, planning.Options{RealizationEnvelope: &envelope})
	requireNoError(t, err)
	if !hasPlanDiagnostic(selected, "realization.compute-substrate-not-admitted") || selected.Plan.Valid() {
		t.Errorf("VM target accepted physical substrate: %+v", selected.Diagnostics)
	}
}

func TestPlannerDefersOnlyNegotiatedOpenOperatingSystemChoice(t *testing.T) {
	envelope := preparedConfiguredEnvelope(t, map[string]any{
		"domains":  map[string]any{"family": map[string]any{"kind": "exact", "value": "linux"}},
		"bindings": []any{map[string]any{"path": "nodes.host.os", "scope": "field", "posture": "exact", "domain": "family", "overrideable": false}},
	})
	source := "name: example\nrealization: {default: closed, scopes: [{field_pointer: /nodes/host/os, posture: open}]}\nnodes: {host: {type: compute}}\n"
	for _, preparation := range []bool{false, true} {
		t.Run(map[bool]string{false: "ordinary-open-demand", true: "negotiated-choice"}[preparation], func(t *testing.T) {
			result := preparedSelectionEnvelopeResult(t, source, envelope, func(record map[string]any) {
				provisioner := requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])
				provisioner["operating_systems"] = []any{map[string]any{"family": "linux", "distribution": "ubuntu", "versions": []string{"22.04"}}}
				if !preparation {
					omitPreparationVersion(t, record)
				}
			})
			if hasPlanDiagnostic(result, "realization-envelope.subsumption.requested-unconstrained") == preparation || result.Plan.Valid() != preparation {
				t.Fatalf("negotiated=%v diagnostics=%+v", preparation, result.Diagnostics)
			}
		})
	}
}

func omitPreparationVersion(t *testing.T, record map[string]any) {
	t.Helper()
	versions := []any{}
	for _, version := range requireType[[]any](t, record["supported_contract_versions"]) {
		if version != "backend-realization-preparation-v1" {
			versions = append(versions, version)
		}
	}
	record["supported_contract_versions"] = versions
}

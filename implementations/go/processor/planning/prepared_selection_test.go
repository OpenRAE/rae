package planning_test

import (
	"encoding/json"
	"maps"
	"os"
	"strconv"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

//nolint:ireturn // This fixture returns the actual planner-issued handle.
func preparedSelectionFixture(t *testing.T, source string) planning.ExecutionPlan {
	t.Helper()
	return preparedSelectionTargetFixture(t, source, nil)
}

//nolint:ireturn // This fixture returns the actual planner-issued handle.
func preparedSelectionTargetFixture(t *testing.T, source string, configure func(map[string]any)) planning.ExecutionPlan {
	t.Helper()
	raw, err := os.ReadFile("../../../../contracts/fixtures/realization-envelope/realization-envelope-v1/valid/generic.json")
	requireNoError(t, err)
	var envelope binding.RealizationEnvelopeV1
	requireNoError(t, json.Unmarshal(raw, &envelope))
	return preparedSelectionEnvelopeFixture(t, source, envelope, configure)
}

//nolint:ireturn // This fixture returns the actual planner-issued handle.
func preparedSelectionEnvelopeFixture(t *testing.T, source string, envelope binding.RealizationEnvelopeV1, configure func(map[string]any)) planning.ExecutionPlan {
	t.Helper()
	result := preparedSelectionEnvelopeResult(t, source, envelope, configure)
	if !result.Plan.Valid() {
		t.Fatalf("invalid preparation fixture: %+v", result.Diagnostics)
	}
	return result.Plan
}

func preparedSelectionEnvelopeResult(t *testing.T, source string, envelope binding.RealizationEnvelopeV1, configure func(map[string]any)) planning.Result {
	t.Helper()
	target := changeManifest(t, func(record map[string]any) {
		record["supported_contract_versions"] = append(requireType[[]any](t, record["supported_contract_versions"]), "backend-realization-preparation-v1", "realization-envelope-v1")
		support := requireType[map[string]any](t, requireType[[]any](t, record["realization_support"])[0])
		support["support_mode"] = "open-realization"
		support["supported_constraint_kinds"] = append(requireType[[]any](t, support["supported_constraint_kinds"]), "runtime-database-services", "runtime-environment")
		support["supported_exact_requirement_kinds"] = append(requireType[[]any](t, support["supported_exact_requirement_kinds"]), "runtime-database-services", "runtime-environment")
		support["observation_capabilities"] = map[string]any{"runtime-database-services": map[string]any{"verification_scope": "configuration", "observation_strength": "guest-observed"}, "runtime-environment": map[string]any{"verification_scope": "configuration", "observation_strength": "guest-observed"}}
		record["realization_envelope"] = map[string]string{"envelope_id": field(envelope.Id), "digest": field(envelope.Digest), "configuration_digest": field(field(envelope.Configuration).ConfigurationDigest)}
		if configure != nil {
			configure(record)
		}
	})
	result, err := planning.PlanWithManifest(compile(t, source), target, planning.Options{RealizationEnvelope: &envelope})
	requireNoError(t, err)
	return result
}

func TestPreparedOfferUsesNativeRuntimePresence(t *testing.T) {
	raw, err := os.ReadFile("../../contract/admission/testdata/processor/closed-prepared-envelope.json")
	requireNoError(t, err)
	var record map[string]any
	requireNoError(t, json.Unmarshal(raw, &record))
	expression := requireType[map[string]any](t, record["expression"])
	domains := requireType[map[string]any](t, expression["domains"])
	domains["identity"] = map[string]any{"kind": "exact", "value": "db"}
	requireType[map[string]any](t, requireType[map[string]any](t, domains["service"])["fields"])["database_service_id"] = "identity"
	delete(record, "digest")
	canonical, err := canonjson.Sorted(requireJSON(t, record), true)
	requireNoError(t, err)
	record["digest"] = digest.SHA256(canonical)
	var envelope binding.RealizationEnvelopeV1
	requireNoError(t, json.Unmarshal(requireJSON(t, record), &envelope))
	original := preparedSelectionEnvelopeFixture(t, "name: example\nrealization: {default: closed, scopes: [{field_pointer: /nodes/host/runtime/database_services, posture: open}]}\nnodes: {host: {type: compute, runtime: {database_services: [{database_service_id: db, engine: sqlite}]}}}\n", envelope, nil)
	admitted, violation, err := planning.CheckPreparedSelection(original, original.Provisioning())
	requireNoError(t, err)
	if admitted == nil || violation != "" {
		t.Fatalf("constructor defaults counted as extra runtime fields: %s", violation)
	}
}
func changePreparedPlan(t *testing.T, source binding.ProvisioningPlanV1, change func(map[string]any)) binding.ProvisioningPlanV1 {
	t.Helper()
	var record map[string]any
	requireNoError(t, json.Unmarshal(requireJSON(t, source), &record))
	change(record)
	var result binding.ProvisioningPlanV1
	requireNoError(t, json.Unmarshal(requireJSON(t, record), &result))
	return result
}
func TestPreparedSelectionOwnsTheOriginalPlanAndChosenProjection(t *testing.T) {
	original := preparedSelectionFixture(t, "name: example\nnodes: {host: {type: compute}}\n")
	selected, violation, err := planning.CheckPreparedSelection(original, original.Provisioning())
	requireNoError(t, err)
	if violation != "" || selected == nil {
		t.Fatalf("unchanged selection refused: %s", violation)
	}
	projection := selected.Provisioning()
	field(field(projection.Operations)[0].Payload)["changed"] = json.RawMessage(`true`)
	if _, changed := field(field(selected.Provisioning().Operations)[0].Payload)["changed"]; changed {
		t.Fatal("caller changed admitted selection")
	}
	if _, _, err := planning.CheckPreparedSelection(replacedPlan{original}, original.Provisioning()); err == nil {
		t.Fatal("foreign original accepted")
	}
}
func TestPreparedSelectionRefusesChangedOperationAuthority(t *testing.T) {
	original := preparedSelectionFixture(t, "name: example\nnodes: {host: {type: compute}}\n")
	selected := changePreparedPlan(t, original.Provisioning(), func(record map[string]any) {
		operation := requireType[map[string]any](t, requireType[[]any](t, record["operations"])[0])
		operation["ordering_dependencies"] = []string{"provision.node.other"}
	})
	admitted, violation, err := planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted != nil || violation != "Backend preparation changed submitted operation authority." {
		t.Fatalf("changed authority admitted: %s", violation)
	}
}
func TestPreparedSelectionRefusesChangedResidualPayload(t *testing.T) {
	original := preparedSelectionFixture(t, "name: example\nnodes: {host: {type: compute}}\n")
	selected := changePreparedPlan(t, original.Provisioning(), func(record map[string]any) {
		operation := requireType[map[string]any](t, requireType[[]any](t, record["operations"])[0])
		payload := requireType[map[string]any](t, operation["payload"])
		spec := requireType[map[string]any](t, payload["spec"])
		requireType[map[string]any](t, spec["node"])["description"] = "changed"
	})
	admitted, violation, err := planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted != nil || violation != "Backend preparation changed a value outside realization authority." {
		t.Fatalf("changed residual admitted: %s", violation)
	}
}

func TestPreparedCollectionRejectsAnExtraNonportableResource(t *testing.T) {
	original := preparedSelectionFixture(t, "name: example\nrealization: {default: closed, scopes: [{field_pointer: /nodes, posture: open}, {field_pointer: /nodes/host, posture: closed}]}\nnodes: {host: {type: compute}}\n")
	selected := changePreparedPlan(t, original.Provisioning(), func(record map[string]any) {
		operations := requireType[[]any](t, record["operations"])
		record["operations"] = append(operations, map[string]any{"action": "create", "address": "provision.feature-binding.host.extra", "resource_type": "feature-binding", "payload": map[string]any{}, "ordering_dependencies": []string{}, "refresh_dependencies": []string{}})
	})
	admitted, violation, err := planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted != nil || violation != "Backend preparation exceeded its portable node collection universe." {
		t.Fatalf("extra nonportable resource admitted: %s", violation)
	}
}

const selectedDatabaseSource = `name: example
realization:
 default: closed
 scopes:
 - {field_pointer: /nodes/host/runtime/database_services/0/engine, posture: open}
nodes:
 host:
  type: compute
  runtime:
   database_services: [{database_service_id: db}]
`

func TestPreparedDeliveryRequiresTheAdmittedCompletion(t *testing.T) {
	original := preparedSelectionFixture(t, selectedDatabaseSource)
	selected := changePreparedPlan(t, original.Provisioning(), func(record map[string]any) { preparedDatabaseEngine(t, record, "sqlite") })
	admitted, violation, err := planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted == nil || violation != "" {
		t.Fatalf("supported selected database engine refused: %s", violation)
	}
	snapshot, err := planning.AssumedSnapshot(original)
	requireNoError(t, err)
	for _, value := range []string{"sqlite", "postgresql"} {
		t.Run(value, func(t *testing.T) {
			var entry map[string]any
			requireNoError(t, json.Unmarshal(field(snapshot.Entries)["provision.node.host"], &entry))
			preparedPayloadDatabaseEngine(t, requireType[map[string]any](t, entry["payload"]), value)
			field(snapshot.Entries)["provision.node.host"] = requireJSON(t, entry)
			violation, err := planning.CheckPreparedDelivery(admitted, snapshot)
			requireNoError(t, err)
			if (violation == "") != (value == "sqlite") {
				t.Fatalf("delivered %s violation=%s", value, violation)
			}
		})
	}
}
func preparedDatabaseEngine(t *testing.T, plan map[string]any, value string) {
	t.Helper()
	operation := requireType[map[string]any](t, requireType[[]any](t, plan["operations"])[0])
	preparedPayloadDatabaseEngine(t, requireType[map[string]any](t, operation["payload"]), value)
}
func preparedPayloadDatabaseEngine(t *testing.T, payload map[string]any, value string) {
	t.Helper()
	spec := requireType[map[string]any](t, payload["spec"])
	node := requireType[map[string]any](t, spec["node"])
	runtime := requireType[map[string]any](t, node["runtime"])
	requireType[map[string]any](t, requireType[[]any](t, runtime["database_services"])[0])["engine"] = value
}

func TestPreparedOpenCollectionAdmitsACompletePortableNode(t *testing.T) {
	original := preparedSelectionFixture(t, "name: example\nrealization: {default: closed, scopes: [{field_pointer: /nodes, posture: open}, {field_pointer: /nodes/host, posture: closed}]}\nnodes: {host: {type: compute}}\n")
	selected := additionalPreparedNode(t, original.Provisioning(), nil)
	admitted, violation, err := planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted == nil || violation != "" {
		t.Fatalf("portable completion refused: %s", violation)
	}
}
func additionalPreparedNode(t *testing.T, original binding.ProvisioningPlanV1, change func(map[string]any)) binding.ProvisioningPlanV1 {
	t.Helper()
	return changePreparedPlan(t, original, func(record map[string]any) {
		operations := requireType[[]any](t, record["operations"])
		var host any
		for _, item := range operations {
			if requireType[map[string]any](t, item)["address"] == "provision.node.host" {
				host = item
			}
		}
		if host == nil {
			t.Fatal("host operation missing")
		}
		var extra map[string]any
		requireNoError(t, json.Unmarshal(requireJSON(t, host), &extra))
		extra["address"] = "provision.node.extra"
		payload := requireType[map[string]any](t, extra["payload"])
		payload["name"] = "extra"
		payload["node_name"] = "extra"
		if change != nil {
			change(extra)
		}
		record["operations"] = append(operations, extra)
	})
}

func TestPreparedAdditionalNodeDeliveryUsesTheSameSafeProjection(t *testing.T) {
	original := preparedSelectionFixture(t, "name: example\nrealization: {default: closed, scopes: [{field_pointer: /nodes, posture: open}, {field_pointer: /nodes/host, posture: closed}]}\nnodes: {host: {type: compute}}\n")
	selected := additionalPreparedNode(t, original.Provisioning(), func(operation map[string]any) {
		payload := requireType[map[string]any](t, operation["payload"])
		spec := requireType[map[string]any](t, payload["spec"])
		requireType[map[string]any](t, spec["node"])["runtime"] = map[string]any{"database_services": []any{map[string]any{"database_service_id": "db", "engine": "sqlite"}}}
	})
	admitted, violation, err := planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted == nil || violation != "" {
		t.Fatalf("additional database node refused: %s", violation)
	}
	snapshot := preparedReturnedSnapshot(t, original, selected)
	violation, err = planning.CheckPreparedDelivery(admitted, snapshot)
	requireNoError(t, err)
	if violation != "" {
		t.Fatalf("identical delivered portable node refused: %s", violation)
	}
	for _, mutation := range []string{"changed-engine", "missing-entry"} {
		returned := preparedReturnedSnapshot(t, original, selected)
		if mutation == "missing-entry" {
			delete(field(returned.Entries), "provision.node.extra")
		} else {
			var entry map[string]any
			requireNoError(t, json.Unmarshal(field(returned.Entries)["provision.node.extra"], &entry))
			preparedPayloadDatabaseEngine(t, requireType[map[string]any](t, entry["payload"]), "postgresql")
			field(returned.Entries)["provision.node.extra"] = requireJSON(t, entry)
		}
		violation, err := planning.CheckPreparedDelivery(admitted, returned)
		requireNoError(t, err)
		if violation != "Backend did not deliver its admitted portable node completion." {
			t.Fatalf("%s completion admitted: %s", mutation, violation)
		}
	}
}
func preparedReturnedSnapshot(t *testing.T, original planning.ExecutionPlan, selected binding.ProvisioningPlanV1) binding.RuntimeSnapshotV1 {
	t.Helper()
	snapshot, err := planning.AssumedSnapshot(original)
	requireNoError(t, err)
	for _, operation := range field(selected.Operations) {
		entry := map[string]any{"address": field(operation.Address), "domain": "provisioning", "resource_type": field(operation.ResourceType), "payload": field(operation.Payload), "ordering_dependencies": field(operation.OrderingDependencies), "refresh_dependencies": field(operation.RefreshDependencies), "profile_bindings": []any{}, "status": "ready"}
		field(snapshot.Entries)[field(operation.Address)] = requireJSON(t, entry)
	}
	return snapshot
}
func TestPreparedAdditionalNodeAcceptsProtectedPresenceWithoutRawBytes(t *testing.T) {
	original := preparedSelectionFixture(t, "name: example\nrealization: {default: closed, scopes: [{field_pointer: /nodes, posture: open}, {field_pointer: /nodes/host, posture: closed}]}\nnodes: {host: {type: compute}}\n")
	selected := additionalPreparedNode(t, original.Provisioning(), func(operation map[string]any) {
		payload := requireType[map[string]any](t, operation["payload"])
		spec := requireType[map[string]any](t, payload["spec"])
		requireType[map[string]any](t, spec["node"])["runtime"] = map[string]any{"environment": []any{map[string]any{"name": "TOKEN", "value_classification": "redacted", "provenance": "unknown", "source": "", "value_present": true}}}
	})
	admitted, violation, err := planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted == nil || violation != "" {
		t.Fatalf("protected presence refused: %s", violation)
	}
	safe, err := planning.SanitizePreparedSnapshot(admitted, preparedReturnedSnapshot(t, original, selected))
	requireNoError(t, err)
	var entry map[string]any
	requireNoError(t, json.Unmarshal(field(safe.Entries)["provision.node.extra"], &entry))
	payload := requireType[map[string]any](t, entry["payload"])
	spec := requireType[map[string]any](t, payload["spec"])
	runtime := requireType[map[string]any](t, requireType[map[string]any](t, spec["node"])["runtime"])
	value := requireType[map[string]any](t, requireType[[]any](t, runtime["environment"])[0])
	if value["value_present"] != true {
		t.Fatal("protected presence lost")
	}
	if _, raw := value["value"]; raw {
		t.Fatal("safe output retained a raw protected value field")
	}
}

func TestPreparedAdditionalNodeCannotCombineOperatingSystemRows(t *testing.T) {
	original := preparedSelectionTargetFixture(t, "name: example\nrealization: {default: closed, scopes: [{field_pointer: /nodes, posture: open}, {field_pointer: /nodes/host, posture: closed}]}\nnodes: {host: {type: compute}}\n", func(record map[string]any) {
		provisioner := requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])
		provisioner["operating_systems"] = []any{map[string]any{"family": "linux", "distribution": "ubuntu", "versions": []string{"22.04"}}, map[string]any{"family": "linux", "distribution": "debian", "versions": []string{"24.04"}}}
	})
	selected := additionalPreparedNode(t, original.Provisioning(), func(operation map[string]any) {
		payload := requireType[map[string]any](t, operation["payload"])
		node := requireType[map[string]any](t, requireType[map[string]any](t, payload["spec"])["node"])
		payload["os_family"] = "linux"
		payload["os_distribution"] = "ubuntu"
		payload["os_version"] = "24.04"
		node["os"] = "linux"
		node["os_distribution"] = "ubuntu"
		node["os_version"] = "24.04"
	})
	admitted, violation, err := planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted != nil || violation != "Backend preparation selected an inadmissible portable node completion." {
		t.Fatalf("cross-combined OS row admitted: %s", violation)
	}
}

func TestPreparedOriginalNodeRechecksNativeReferences(t *testing.T) {
	original := preparedSelectionFixture(t, "name: example\nvariables: {service_name: {type: string, default: database, allowed_values: [database, missing]}}\nnodes: {host: {type: compute, services: [{name: database, port: 5432}], runtime: {database_services: [{database_service_id: db, engine: sqlite, service: '${service_name}'}]}}}\n")
	for _, service := range []string{"database", "missing"} {
		t.Run(service, func(t *testing.T) {
			selected := changePreparedPlan(t, original.Provisioning(), func(record map[string]any) {
				operation := requireType[map[string]any](t, requireType[[]any](t, record["operations"])[0])
				runtime := preparedRuntime(t, operation)
				requireType[map[string]any](t, requireType[[]any](t, runtime["database_services"])[0])["service"] = service
			})
			admitted, violation, err := planning.CheckPreparedSelection(original, selected)
			requireNoError(t, err)
			if (admitted != nil && violation == "") != (service == "database") {
				t.Fatalf("service %s admitted=%v violation=%s", service, admitted != nil, violation)
			}
			if service == "missing" && violation != "Backend preparation selected an inadmissible portable node completion." {
				t.Fatalf("native reference check did not own refusal: %s", violation)
			}
		})
	}
}

func preparedRuntime(t *testing.T, operation map[string]any) map[string]any {
	t.Helper()
	payload := requireType[map[string]any](t, operation["payload"])
	node := requireType[map[string]any](t, requireType[map[string]any](t, payload["spec"])["node"])
	runtime, _ := node["runtime"].(map[string]any)
	if runtime == nil {
		runtime = map[string]any{}
		node["runtime"] = runtime
	}
	return runtime
}

const portableCollectionSource = "name: example\nrealization: {default: closed, scopes: [{field_pointer: /nodes, posture: open}, {field_pointer: /nodes/host, posture: closed}]}\nnodes: {host: {type: compute}}\n"

func TestPreparedAdditionalNodeRefusesCapabilityIdentityAndReferenceDefects(t *testing.T) {
	original := preparedSelectionFixture(t, portableCollectionSource)
	cases := map[string]func(map[string]any){
		"unsupported-runtime": func(operation map[string]any) {
			preparedRuntime(t, operation)["container"] = map[string]any{"privileged": true}
		},
		"unknown-count": func(operation map[string]any) {
			payload := requireType[map[string]any](t, operation["payload"])
			payload["count"] = "${unresolved_count}"
			requireType[map[string]any](t, requireType[map[string]any](t, payload["spec"])["infrastructure"])["count"] = "${unresolved_count}"
		},
		"self-dependency": func(operation map[string]any) {
			operation["ordering_dependencies"] = []string{"provision.node.extra"}
			operation["refresh_dependencies"] = []string{"provision.node.extra"}
		},
		"missing-namespace-binding": func(operation map[string]any) {
			preparedRuntime(t, operation)["container"] = map[string]any{"namespaces": map[string]any{"network": map[string]any{"target_node_ref": "nodes.host"}}}
		},
		"wrong-node-name": func(operation map[string]any) {
			requireType[map[string]any](t, operation["payload"])["node_name"] = "host"
		},
		"missing-service": func(operation map[string]any) {
			preparedRuntime(t, operation)["database_services"] = []any{map[string]any{"database_service_id": "db", "engine": "sqlite", "service": "missing"}}
		},
		"missing-artifact": func(operation map[string]any) {
			preparedRuntime(t, operation)["environment"] = []any{map[string]any{"name": "MODE", "value_classification": "plain", "provenance": "runtime", "value_from": map[string]any{"generated_artifact": "generated_artifacts.absent", "output": "mode"}}}
		},
		"cpu-variable": func(operation map[string]any) {
			payload := requireType[map[string]any](t, operation["payload"])
			requireType[map[string]any](t, requireType[map[string]any](t, payload["spec"])["node"])["resources"] = map[string]any{"ram": 1024, "cpu": "${unresolved_cpu}"}
		},
		"missing-acl-network": func(operation map[string]any) {
			payload := requireType[map[string]any](t, operation["payload"])
			requireType[map[string]any](t, requireType[map[string]any](t, payload["spec"])["infrastructure"])["acls"] = []any{map[string]any{"from_net": "absent", "to_net": "absent"}}
		},
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			admitted, violation, err := planning.CheckPreparedSelection(original, additionalPreparedNode(t, original.Provisioning(), mutate))
			requireNoError(t, err)
			if admitted != nil || violation == "" {
				t.Fatalf("invalid node admitted: %s", violation)
			}
		})
	}
	admitted, violation, err := planning.CheckPreparedSelection(original, additionalPreparedNode(t, original.Provisioning(), nil))
	requireNoError(t, err)
	if admitted == nil || violation != "" {
		t.Fatalf("valid completion after refusals failed: %s", violation)
	}
}

func TestPreparedRetainedAdditionRechecksChangedCapacity(t *testing.T) {
	original := preparedSelectionFixture(t, portableCollectionSource)
	selected := additionalPreparedNode(t, original.Provisioning(), nil)
	admitted, violation, err := planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted == nil || violation != "" {
		t.Fatalf("baseline addition refused: %s", violation)
	}
	snapshot := preparedReturnedSnapshot(t, original, selected)
	var record map[string]any
	requireNoError(t, json.Unmarshal(requireJSON(t, original.Manifest()), &record))
	requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])["max_total_nodes"] = 1
	var target binding.BackendManifestV2
	requireNoError(t, json.Unmarshal(requireJSON(t, record), &target))
	context := original.Context()
	next, err := planning.PlanWithManifest(compile(t, portableCollectionSource), target, planning.Options{Snapshot: &snapshot, RealizationEnvelope: context.RealizationEnvelope})
	requireNoError(t, err)
	if !next.Plan.Valid() {
		t.Fatalf("authored single-node plan refused before retained completion check: %+v", next.Diagnostics)
	}
	admitted, violation, err = planning.CheckPreparedSelection(next.Plan, next.Plan.Provisioning())
	requireNoError(t, err)
	if admitted != nil || violation != "Backend preparation selected an inadmissible portable node completion." {
		t.Fatalf("retained excess node admitted: %s", violation)
	}
}

type foreignPreparedSelection struct{ planning.PreparedSelection }

func (foreignPreparedSelection) Provisioning() binding.ProvisioningPlanV1 {
	panic("foreign projection must never be called")
}

func TestPreparedDeliveryAndSanitizationRefuseForeignHandlesBeforeMethods(t *testing.T) {
	foreign := foreignPreparedSelection{}
	if _, err := planning.CheckPreparedDelivery(foreign, binding.RuntimeSnapshotV1{}); err == nil {
		t.Fatal("foreign delivery handle accepted")
	}
	if _, err := planning.SanitizePreparedSnapshot(foreign, binding.RuntimeSnapshotV1{}); err == nil {
		t.Fatal("foreign sanitizer handle accepted")
	}
}

func TestPreparedPlanKeepsStaticMissingOfferOutsideDeclaredAuthority(t *testing.T) {
	envelope := preparedConfiguredEnvelope(t, map[string]any{
		"domains":  map[string]any{"description": map[string]any{"kind": "exact", "value": ""}},
		"bindings": []any{map[string]any{"path": "nodes.extra.description", "scope": "field", "posture": "exact", "domain": "description", "overrideable": false}},
	})
	result := preparedSelectionEnvelopeResult(t, portableCollectionSource, envelope, nil)
	if result.Plan.Valid() || !hasPlanDiagnostic(result, "realization-envelope.membership.path-absent") {
		t.Fatalf("missing static offer hidden by collection preparation: %+v", result.Diagnostics)
	}
}

func preparedConfiguredEnvelope(t *testing.T, replace map[string]any) binding.RealizationEnvelopeV1 {
	t.Helper()
	raw, err := os.ReadFile("../../contract/admission/testdata/processor/closed-prepared-envelope.json")
	requireNoError(t, err)
	var record map[string]any
	requireNoError(t, json.Unmarshal(raw, &record))
	expression := requireType[map[string]any](t, record["expression"])
	maps.Copy(expression, replace)
	delete(record, "digest")
	canonical, err := canonjson.Sorted(requireJSON(t, record), true)
	requireNoError(t, err)
	record["digest"] = digest.SHA256(canonical)
	var envelope binding.RealizationEnvelopeV1
	requireNoError(t, json.Unmarshal(requireJSON(t, record), &envelope))
	return envelope
}

func TestPreparedNodeCannotInventGeneratedArtifactEnvironmentDelivery(t *testing.T) {
	source := `name: example
realization: {default: closed, scopes: [{field_pointer: /nodes, posture: open}, {field_pointer: /nodes/host, posture: closed}]}
nodes:
 host:
  type: compute
  runtime:
   environment:
   - {name: MODE, value_classification: plain, provenance: runtime, value_from: {generated_artifact: generated_artifacts.token, output: value}}
generated_artifacts:
 token:
  generator: random_value
  lifecycle: reuse_valid
  provenance: test
  regeneration_scope: once
  random_value: {alphabet: hex_lower, length: 32}
  outputs: [{name: value, path: token, sensitivity: public}]
`
	original := preparedSelectionTargetFixture(t, source, func(record map[string]any) {
		provisioner := requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])
		provisioner["supported_generated_artifact_kinds"] = []string{"random_value"}
		provisioner["supported_regeneration_scopes"] = []string{"once"}
		provisioner["supported_generated_artifact_delivery_modes"] = []string{"environment"}
	})
	baseline, violation, err := planning.CheckPreparedSelection(original, original.Provisioning())
	requireNoError(t, err)
	if baseline == nil || violation != "" {
		t.Fatalf("existing generated-artifact delivery refused: %s", violation)
	}
	admitted, violation, err := planning.CheckPreparedSelection(original, additionalPreparedNode(t, original.Provisioning(), nil))
	requireNoError(t, err)
	if admitted != nil || violation != "Backend preparation selected an inadmissible portable node completion." {
		t.Fatalf("new node invented environment delivery grant: %s", violation)
	}
}

func TestPreparedNodeNormalizesAliasesThroughTheNativeOwner(t *testing.T) {
	original := preparedSelectionFixture(t, portableCollectionSource)
	selected := additionalPreparedNode(t, original.Provisioning(), func(operation map[string]any) {
		payload := requireType[map[string]any](t, operation["payload"])
		payload["architecture"] = "x86_64"
		requireType[map[string]any](t, requireType[map[string]any](t, payload["spec"])["node"])["architecture"] = "amd64"
	})
	admitted, violation, err := planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted == nil || violation != "" {
		t.Fatalf("native architecture alias refused: %s", violation)
	}
}

func TestPreparedNodeCannotSupplyItsOwnNormalizedMetadata(t *testing.T) {
	original := preparedSelectionFixture(t, portableCollectionSource)
	selected := additionalPreparedNode(t, original.Provisioning(), func(operation map[string]any) {
		requireType[map[string]any](t, operation["payload"])["normalized_node"] = map[string]any{"type": "compute", "architecture": "x86_64"}
	})
	admitted, violation, err := planning.CheckPreparedSelection(original, selected)
	requireNoError(t, err)
	if admitted != nil || violation != "Backend preparation selected an inadmissible portable node completion." {
		t.Fatalf("candidate supplied independent phase metadata: %s", violation)
	}
}

func TestPreparedDeliveryAndSanitizationBoundTheReturnedSnapshot(t *testing.T) {
	original := preparedSelectionFixture(t, "name: example\nnodes: {host: {type: compute}}\n")
	selected, violation, err := planning.CheckPreparedSelection(original, original.Provisioning())
	requireNoError(t, err)
	if selected == nil || violation != "" {
		t.Fatalf("baseline selection refused: %s", violation)
	}
	snapshot := preparedReturnedSnapshot(t, original, original.Provisioning())
	metadata := map[string]any{}
	for i := range 200 {
		metadata[strconv.Itoa(i)] = make([]any, 400)
	}
	requireNoError(t, snapshot.Metadata.UnmarshalJSON(requireJSON(t, metadata)))
	if _, err := planning.CheckPreparedDelivery(selected, snapshot); err == nil {
		t.Fatal("delivery copied an oversized runtime aggregate")
	}
	if _, err := planning.SanitizePreparedSnapshot(selected, snapshot); err == nil {
		t.Fatal("sanitizer copied an oversized runtime aggregate")
	}
}

func TestPreparedDeliveryPreservesAnAdmittedSequenceOrder(t *testing.T) {
	source := "name: example\nvariables:\n first: {type: string, default: '1.1.1.1', allowed_values: ['1.1.1.1', '8.8.8.8']}\n second: {type: string, default: '8.8.8.8', allowed_values: ['1.1.1.1', '8.8.8.8']}\nnodes: {host: {type: compute, runtime: {container: {dns: ['${first}', '${second}']}}}}\n"
	original := preparedSelectionTargetFixture(t, source, func(record map[string]any) {
		support := requireType[map[string]any](t, requireType[[]any](t, record["realization_support"])[0])
		support["supported_exact_requirement_kinds"] = append(requireType[[]any](t, support["supported_exact_requirement_kinds"]), "runtime-container-dns")
		support["supported_constraint_kinds"] = append(requireType[[]any](t, support["supported_constraint_kinds"]), "runtime-container-dns")
		requireType[map[string]any](t, support["observation_capabilities"])["runtime-container-dns"] = map[string]any{"verification_scope": "configuration", "observation_strength": "guest-observed"}
	})
	selected, violation, err := planning.CheckPreparedSelection(original, original.Provisioning())
	requireNoError(t, err)
	if selected == nil || violation != "" {
		t.Fatalf("admitted sequence refused: %s", violation)
	}
	for _, reverse := range []bool{false, true} {
		snapshot := preparedReturnedSnapshot(t, original, original.Provisioning())
		var entry map[string]any
		requireNoError(t, json.Unmarshal(field(snapshot.Entries)["provision.node.host"], &entry))
		if reverse {
			container := requireType[map[string]any](t, preparedRuntime(t, entry)["container"])
			container["dns"] = []string{"8.8.8.8", "1.1.1.1"}
		}
		field(snapshot.Entries)["provision.node.host"] = requireJSON(t, entry)
		violation, err := planning.CheckPreparedDelivery(selected, snapshot)
		requireNoError(t, err)
		if (violation == "") == reverse {
			t.Fatalf("reverse=%v delivered sequence violation=%s", reverse, violation)
		}
	}
}

func TestPreparedSanitizerChecksUnexpectedRuntimeConcernsOnAddedNodes(t *testing.T) {
	original := preparedSelectionFixture(t, portableCollectionSource)
	chosen := additionalPreparedNode(t, original.Provisioning(), nil)
	selected, violation, err := planning.CheckPreparedSelection(original, chosen)
	requireNoError(t, err)
	if selected == nil || violation != "" {
		t.Fatalf("baseline node refused: %s", violation)
	}
	snapshot := preparedReturnedSnapshot(t, original, chosen)
	var entry map[string]any
	requireNoError(t, json.Unmarshal(field(snapshot.Entries)["provision.node.extra"], &entry))
	preparedRuntime(t, entry)["environment"] = []any{map[string]any{"name": "TOKEN", "value_classification": "secret_fixture", "value": "unsafe-returned-fixture-value"}}
	field(snapshot.Entries)["provision.node.extra"] = requireJSON(t, entry)
	if _, err := planning.SanitizePreparedSnapshot(selected, snapshot); err == nil {
		t.Fatal("unexpected runtime concern bypassed the closed observation sanitizer")
	}
}

func TestPreparedOpaqueRuntimeFieldRemainsDataAndFailsClosedDelivery(t *testing.T) {
	original := preparedSelectionFixture(t, portableCollectionSource)
	chosen := additionalPreparedNode(t, original.Provisioning(), nil)
	selected, violation, err := planning.CheckPreparedSelection(original, chosen)
	requireNoError(t, err)
	if selected == nil || violation != "" {
		t.Fatalf("baseline node refused: %s", violation)
	}
	snapshot := preparedReturnedSnapshot(t, original, chosen)
	var entry map[string]any
	requireNoError(t, json.Unmarshal(field(snapshot.Entries)["provision.node.extra"], &entry))
	preparedRuntime(t, entry)["private_canary"] = "opaque-untyped-field"
	field(snapshot.Entries)["provision.node.extra"] = requireJSON(t, entry)
	safe, err := planning.SanitizePreparedSnapshot(selected, snapshot)
	requireNoError(t, err)
	requireNoError(t, json.Unmarshal(field(safe.Entries)["provision.node.extra"], &entry))
	if preparedRuntime(t, entry)["private_canary"] != "opaque-untyped-field" {
		t.Fatal("opaque unknown data was reinterpreted as an admitted concern")
	}
	violation, err = planning.CheckPreparedDelivery(selected, snapshot)
	requireNoError(t, err)
	if violation != "Backend did not deliver its admitted portable node completion." {
		t.Fatalf("unknown opaque data widened selected node: %s", violation)
	}
}

func TestPreparedAdditionalNodeDeliveryPreservesSelectedDNSOrder(t *testing.T) {
	original := preparedSelectionTargetFixture(t, portableCollectionSource, func(record map[string]any) {
		support := requireType[map[string]any](t, requireType[[]any](t, record["realization_support"])[0])
		support["supported_exact_requirement_kinds"] = append(requireType[[]any](t, support["supported_exact_requirement_kinds"]), "runtime-container-dns")
		requireType[map[string]any](t, support["observation_capabilities"])["runtime-container-dns"] = map[string]any{"verification_scope": "configuration", "observation_strength": "guest-observed"}
	})
	chosen := additionalPreparedNode(t, original.Provisioning(), func(operation map[string]any) {
		preparedRuntime(t, operation)["container"] = map[string]any{"dns": []string{"1.1.1.1", "8.8.8.8"}}
	})
	selected, violation, err := planning.CheckPreparedSelection(original, chosen)
	requireNoError(t, err)
	if selected == nil || violation != "" {
		t.Fatalf("chosen DNS node refused: %s", violation)
	}
	snapshot := preparedReturnedSnapshot(t, original, chosen)
	var entry map[string]any
	requireNoError(t, json.Unmarshal(field(snapshot.Entries)["provision.node.extra"], &entry))
	requireType[map[string]any](t, preparedRuntime(t, entry)["container"])["dns"] = []string{"8.8.8.8", "1.1.1.1"}
	field(snapshot.Entries)["provision.node.extra"] = requireJSON(t, entry)
	violation, err = planning.CheckPreparedDelivery(selected, snapshot)
	requireNoError(t, err)
	if violation != "Backend did not deliver its admitted portable node completion." {
		t.Fatalf("reordered additional DNS node admitted: %s", violation)
	}
}

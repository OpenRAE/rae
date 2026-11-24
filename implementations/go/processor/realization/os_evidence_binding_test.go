package realization

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type boundOSTestFixture struct {
	plan     map[string]any
	snapshot map[string]any
	options  EvaluationOptions
}

func boundOSFixture(t *testing.T) boundOSTestFixture {
	t.Helper()
	library := portableReferenceLibrary(t)
	for _, test := range library.Cases {
		if test.Relation == "planned-evaluate" && strings.Contains(test.Name, "test_in_bound_constrained_selection_passes_pre_mutation_and_runtime_gates") {
			return makeBoundOSFixture(t, library, test)
		}
	}
	t.Fatal("missing independently recorded portable OS fixture")
	return boundOSTestFixture{}
}
func makeBoundOSFixture(t *testing.T, library portableRelationLibrary, test relationCase) boundOSTestFixture {
	t.Helper()
	manifest := library.Manifests[test.Manifest]
	manifestDocument := osTestDocument(t, manifest)
	for _, input := range requireType[[]any](t, manifestDocument["realization_support"]) {
		row := requireType[map[string]any](t, input)
		row["supported_constraint_kinds"] = append(requireType[[]any](t, row["supported_constraint_kinds"]), termOsDistribution, termOsVersion)
	}
	requireNoError(t, json.Unmarshal(requireJSON(t, manifestDocument), &manifest))
	result := boundOSTestFixture{plan: osTestDocument(t, library.Plans[test.Plan]), snapshot: osTestDocument(t, library.Snapshots[test.Snapshot]), options: EvaluationOptions{Manifest: &manifest, Envelope: library.Envelopes[test.Envelope]}}
	for _, authority := range osTestAuthorities(t, result.plan) {
		setExactOSTestAuthority(t, authority)
	}
	bindOSTestFixture(t, result)
	return result
}
func setExactOSTestAuthority(t *testing.T, authority map[string]any) {
	t.Helper()
	if observationKind(requireType[string](t, authority["requirement_kind"])) != termOperatingSystem {
		return
	}
	authority["mode"], authority["source"], authority["provenance"] = "exact", "authored-leaf", "author-declared"
	authority["bounds"] = []any{}
	authority["verification_scope"], authority["required_observation_strength"] = "presence", "guest-observed"
	delete(authority, "structure")
	delete(authority, "constraint_document")
	delete(authority, "constraint_binding")
}
func bindOSTestFixture(t *testing.T, fixture boundOSTestFixture) {
	t.Helper()
	fixture.plan["operation_id"] = "os-operation-current"
	operation := osTestOperation(t, fixture)
	payload := requireType[map[string]any](t, operation["payload"])
	payload["os_family"], payload["os_distribution"], payload["os_version"] = "linux", "ubuntu", "22.04"
	entries := requireType[map[string]any](t, fixture.snapshot["entries"])
	entry := requireType[map[string]any](t, entries[requireType[string](t, operation["address"])])
	entry["payload"] = osTestDocument(t, payload)
	observation := osTestObservation(t, fixture.snapshot)
	observation["operating_system"] = map[string]any{"family": "linux", "distribution": "ubuntu", "version": "22.04"}
	observation["operation_id"] = fixture.plan["operation_id"]
	observation["envelope_digest"] = sourceValue(fixture.options.Envelope.Digest)
	observation["configuration_digest"] = sourceValue(sourceValue(fixture.options.Envelope.Configuration).ConfigurationDigest)
}
func osTestOperation(t *testing.T, fixture boundOSTestFixture) map[string]any {
	t.Helper()
	return requireType[map[string]any](t, requireType[[]any](t, fixture.plan["operations"])[0])
}

func osTestDocument(t *testing.T, input any) map[string]any {
	t.Helper()
	document, err := nativeValue(requireJSON(t, input))
	requireNoError(t, err)
	return requireType[map[string]any](t, document)
}
func osTestAuthorities(t *testing.T, plan map[string]any) []map[string]any {
	t.Helper()
	rows := requireType[[]any](t, plan["realization_authority"])
	result := make([]map[string]any, len(rows))
	for index, row := range rows {
		result[index] = requireType[map[string]any](t, row)
	}
	return result
}
func osTestObservation(t *testing.T, snapshot map[string]any) map[string]any {
	t.Helper()
	for _, input := range requireType[[]any](t, snapshot["realization_observations"]) {
		row := requireType[map[string]any](t, input)
		if row["requirement_kind"] == termOperatingSystem {
			return row
		}
	}
	t.Fatal("missing dedicated OS disclosure")
	return nil
}
func (fixture boundOSTestFixture) transports(t *testing.T) (binding.ProvisioningPlanV1, binding.RuntimeSnapshotV1) {
	t.Helper()
	var plan binding.ProvisioningPlanV1
	var snapshot binding.RuntimeSnapshotV1
	requireNoError(t, json.Unmarshal(requireJSON(t, fixture.plan), &plan))
	requireNoError(t, json.Unmarshal(requireJSON(t, fixture.snapshot), &snapshot))
	return plan, snapshot
}
func osTestEvaluate(t *testing.T, fixture boundOSTestFixture, route string) Evaluation {
	t.Helper()
	plan, snapshot := fixture.transports(t)
	if route == "portable" {
		result, err := EvaluatePlanned(plan, snapshot, fixture.options)
		requireNoError(t, err)
		return result
	}
	requirements := osNativeRequirements(t, plan)
	result, err := Evaluate(requirements, plan, snapshot, fixture.options)
	requireNoError(t, err)
	return result
}
func osNativeRequirements(t *testing.T, plan binding.ProvisioningPlanV1) []Requirement {
	t.Helper()
	views, err := PlannedRequirements(plan)
	requireNoError(t, err)
	var wire evaluatedPlan
	requireNoError(t, json.Unmarshal(requireJSON(t, plan), &wire))
	requirements := []Requirement{}
	for _, view := range views {
		if observationKind(view.Kind) != termOperatingSystem {
			continue
		}
		for _, authority := range wire.Authority {
			if authority.Kind == view.Kind && len(authority.Bounds) == 1 {
				// The direct compiler view carries the same authored scalar domain that
				// the portable relation retains in its addressed bound metadata.
				view.ValueDomain = relationFragment(t, authority.Bounds[0].Domain, admission.RealizationValue)
			}
		}
		requirements = append(requirements, view)
	}
	return requirements
}

func assertOSReadback(t *testing.T, result Evaluation, accepted bool) {
	t.Helper()
	count := 0
	for _, entry := range result.Provenance {
		if observationKind(entry.Kind) == termOperatingSystem {
			count++
		}
	}
	if accepted {
		if len(result.Diagnostics) != 0 || count != 3 {
			t.Fatalf("valid bound OS readback refused: findings=%v,OS provenance=%d", result.Diagnostics, count)
		}
		return
	}
	if len(result.Diagnostics) < 3 || count != 0 {
		t.Fatalf("unbound OS evidence accepted: findings=%v,OS provenance=%d", result.Diagnostics, count)
	}
}

func TestOSEvidenceMatchesTheCurrentOperationAndApparatus(t *testing.T) {
	for _, route := range []string{"native", "portable"} {
		for _, mutation := range []string{"valid", "operation", "envelope", "configuration", "replayed-unchanged", "missing-operation", "plan-envelope", "optional-floor-replay"} {
			t.Run(route+"/"+mutation, func(t *testing.T) {
				fixture := boundOSFixture(t)
				mutateOSTestBinding(t, fixture, mutation)
				result := osTestEvaluate(t, fixture, route)
				assertOSReadback(t, result, mutation == "valid")
			})
		}
	}
}
func mutateOSTestBinding(t *testing.T, fixture boundOSTestFixture, mutation string) {
	t.Helper()
	observation := osTestObservation(t, fixture.snapshot)
	switch mutation {
	case "operation", "replayed-unchanged", "optional-floor-replay":
		observation["operation_id"] = "os-operation-previous"
	case "envelope":
		observation["envelope_digest"] = "sha256:" + strings.Repeat("c", 64)
	case "configuration":
		observation["configuration_digest"] = "sha256:" + strings.Repeat("c", 64)
	case "missing-operation":
		delete(fixture.plan, "operation_id")
	case "plan-envelope":
		requireType[map[string]any](t, fixture.plan["realization_envelope"])["digest"] = "sha256:" + strings.Repeat("c", 64)
	}
	if mutation == "replayed-unchanged" {
		requireType[map[string]any](t, requireType[[]any](t, fixture.plan["operations"])[0])["action"] = "unchanged"
	}
	if mutation == "optional-floor-replay" {
		for _, authority := range osTestAuthorities(t, fixture.plan) {
			if observationKind(requireType[string](t, authority["requirement_kind"])) == termOperatingSystem {
				delete(authority, "verification_scope")
				delete(authority, "required_observation_strength")
			}
		}
	}
}

func TestPortableOSBoundsCheckTheDedicatedObservedValue(t *testing.T) {
	for _, route := range []string{"native", "portable"} {
		for _, kind := range []string{termOsFamily, termOsDistribution, termOsVersion} {
			for _, mutation := range []string{"observation-outside", "inventory-outside", "inventory-missing-observation-outside", "inventory-missing-observation-inside", "observation-missing"} {
				t.Run(route+"/"+kind+"/"+mutation, func(t *testing.T) {
					fixture := boundOSFixture(t)
					configureOSTestBound(t, fixture, kind, mutation)
					result := osTestEvaluate(t, fixture, route)
					assertOSBoundResult(t, result, kind, strings.Contains(mutation, "observation-outside") || mutation == "observation-missing")
				})
			}
		}
	}
}
func configureOSTestBound(t *testing.T, fixture boundOSTestFixture, kind, mutation string) {
	t.Helper()
	inside := map[string]string{termOsFamily: "linux", termOsDistribution: "ubuntu", termOsVersion: "22.04"}[kind]
	for _, authority := range osTestAuthorities(t, fixture.plan) {
		selected := requireType[string](t, authority["requirement_kind"])
		if observationKind(selected) != termOperatingSystem {
			continue
		}
		authority["mode"] = "open"
		if selected == kind {
			authority["mode"] = "constrained"
			authority["bounds"] = []any{map[string]any{"value_pointer": "", "domain": map[string]any{"kind": "enum", "values": []any{inside}}}}
			if mutation == "observation-missing" {
				delete(authority, "verification_scope")
				delete(authority, "required_observation_strength")
			}
		}
	}
	mutateOSTestBoundValue(t, fixture, kind, mutation)
}
func mutateOSTestBoundValue(t *testing.T, fixture boundOSTestFixture, kind, mutation string) {
	t.Helper()
	if mutation == "observation-missing" {
		fixture.snapshot["realization_observations"] = []any{}
		return
	}
	outside := map[string]string{termOsFamily: "windows", termOsDistribution: "debian", termOsVersion: "24.04"}[kind]
	entries := requireType[map[string]any](t, fixture.snapshot["entries"])
	entry := requireType[map[string]any](t, entries[requireType[string](t, osTestOperation(t, fixture)["address"])])
	payload := requireType[map[string]any](t, entry["payload"])
	field := map[string]string{termOsFamily: "os_family", termOsDistribution: "os_distribution", termOsVersion: "os_version"}[kind]
	if strings.Contains(mutation, "inventory-missing") {
		delete(payload, field)
	}
	if mutation == "inventory-outside" {
		payload[field] = outside
	}
	if !strings.Contains(mutation, "observation-outside") {
		return
	}
	identity := requireType[map[string]any](t, osTestObservation(t, fixture.snapshot)["operating_system"])
	switch kind {
	case termOsFamily:
		identity["family"], identity["distribution"], identity["version"] = "windows", "windows-server", "2022"
	case termOsDistribution:
		identity["distribution"], identity["version"] = "debian", "12"
	case termOsVersion:
		identity["version"] = "24.04"
	}
}
func assertOSBoundResult(t *testing.T, result Evaluation, kind string, rejected bool) {
	t.Helper()
	finding := false
	for _, diagnostic := range result.Diagnostics {
		if diagnostic.Code == "runtime.backend-contract-invalid" && strings.Contains(diagnostic.Message, "'"+kind+"'") {
			finding = true
		}
	}
	if finding != rejected {
		t.Fatalf("OS bound used inventory instead of dedicated observation: findings=%v", result.Diagnostics)
	}
	for _, entry := range result.Provenance {
		if rejected && entry.Kind == kind {
			t.Fatal("out-of-domain dedicated OS value gained provenance")
		}
	}
}

func TestOSEvidenceStillRequiresCompatibleObservationPosture(t *testing.T) {
	for _, route := range []string{"native", "portable"} {
		t.Run(route, func(t *testing.T) {
			fixture := boundOSFixture(t)
			configureOSTestIncompatiblePosture(t, fixture)
			result := osTestEvaluate(t, fixture, route)
			if len(result.Diagnostics) == 0 {
				t.Fatal("a valid binding replaced independent posture support")
			}
			for _, entry := range result.Provenance {
				if observationKind(entry.Kind) == termOperatingSystem {
					t.Fatal("unsupported observation posture gained OS provenance")
				}
			}
		})
	}
}

func configureOSTestIncompatiblePosture(t *testing.T, fixture boundOSTestFixture) {
	t.Helper()
	manifest := osTestDocument(t, *fixture.options.Manifest)
	for _, input := range requireType[[]any](t, manifest["realization_support"]) {
		requireType[map[string]any](t, input)["support_mode"] = "constrained"
	}
	requireNoError(t, json.Unmarshal(requireJSON(t, manifest), fixture.options.Manifest))
	for _, authority := range osTestAuthorities(t, fixture.plan) {
		if observationKind(requireType[string](t, authority["requirement_kind"])) == termOperatingSystem {
			authority["mode"] = "open"
		}
	}
}

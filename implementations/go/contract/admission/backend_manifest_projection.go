package admission

import (
	"cmp"
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/pyrepr"
)

// NormalizeBackendManifest returns the complete portable manifest projection.
// Set-valued capability claims have their published stable order; ordered
// evidence, bindings, and user constraint values keep their admitted order.
// The check invokes no methods on foreign values and grants no execution authority.
func NormalizeBackendManifest(v *Validator, manifest binding.BackendManifestV2) (binding.BackendManifestV2, error) {
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
	if v == nil || CheckTransport(manifest, limits) != nil {
		return binding.BackendManifestV2{}, invalid()
	}
	raw, err := json.Marshal(manifest)
	if err != nil || v.CheckPortable(contractBackend, raw, limits) != nil {
		return binding.BackendManifestV2{}, invalid()
	}
	document, err := v.low.DefaultedObjectFragment(contractBackend, "#", raw, limits)
	if err != nil {
		return binding.BackendManifestV2{}, err
	}
	manifestFactoryDefaults(document)
	normalizeManifestClaims(document)
	encoded, err := json.Marshal(document)
	if err != nil {
		return binding.BackendManifestV2{}, invalid()
	}
	var result binding.BackendManifestV2
	if json.Unmarshal(encoded, &result) != nil {
		return binding.BackendManifestV2{}, invalid()
	}
	return result, nil
}

func normalizeManifestClaims(document map[string]any) {
	declared := set(document["supported_contract_versions"])
	versions := []any{}
	for _, version := range supportedManifestContracts(componentBackend) {
		if declared[version] {
			versions = append(versions, version)
		}
	}
	document["supported_contract_versions"] = versions
	sortManifestFields(object(document["compatibility"]), []string{"processors"})
	for _, declaration := range array(document["realization_support"]) {
		record := object(declaration)
		sortManifestFields(record, []string{termSupportedConstraintKinds, "supported_exact_requirement_kinds", "disclosure_kinds"})
		for _, limits := range array(record["process_resource_limits"]) {
			sortManifestFields(object(limits), []string{termScopes})
		}
	}
	capabilities := object(document["capabilities"])
	for _, name := range []string{"provisioner", "orchestrator", "evaluator", "participant_runtime", termObservation, termCleanup, termTime, "recovery_observation"} {
		sortManifestSupportedFields(object(capabilities[name]))
	}
	normalizeProvisionerClaims(object(capabilities["provisioner"]))
	normalizeResourceBudgetClaims(object(at(capabilities, "participant_runtime", "resource_budgets")))
	for _, offer := range array(at(capabilities, termObservation, "capture_offers")) {
		sortManifestFields(object(offer), []string{"artifact_roles", "media_types", "source_classes", termSourceRefs, termScopes, termScopeRefs, "channel_kinds", termChannelRefs, "window_kinds", "integrity_modes", "retention_policy_refs"})
	}
}

func sortManifestSupportedFields(record map[string]any) {
	for name := range record {
		if strings.HasPrefix(name, "supported_") {
			sortManifestField(record, name)
		}
	}
}
func sortManifestFields(record map[string]any, names []string) {
	for _, name := range names {
		sortManifestField(record, name)
	}
}
func sortManifestField(record map[string]any, name string) {
	values, ok := record[name].([]any)
	if !ok {
		return
	}
	slices.SortStableFunc(values, func(a, b any) int { return strings.Compare(manifestClaimSortKey(a), manifestClaimSortKey(b)) })
	record[name] = slices.CompactFunc(values, equal)
}
func manifestClaimSortKey(input any) string {
	if literal, ok := input.(string); ok {
		return literal
	}
	coordinate := object(input)
	var key strings.Builder
	for index, name := range []string{termNamespace, termAuthority, termProfileID, termRevision, "definition_digest"} {
		if index > 0 {
			key.WriteByte(' ')
		}
		key.WriteString(name)
		key.WriteByte('=')
		key.WriteString(pyrepr.Quote(text(coordinate[name])))
	}
	return key.String()
}
func normalizeProvisionerClaims(record map[string]any) {
	rows := array(record["operating_systems"])
	slices.SortStableFunc(rows, func(a, b any) int {
		if order := cmp.Compare(stringAt(a, "family"), stringAt(b, "family")); order != 0 {
			return order
		}
		return cmp.Compare(stringAt(a, "distribution"), stringAt(b, "distribution"))
	})
	for _, row := range rows {
		sortManifestFields(object(row), []string{"versions"})
	}
	if boolean(record["supports_generated_artifacts"]) && len(array(record["supported_generated_artifact_delivery_modes"])) == 0 {
		record["supported_generated_artifact_delivery_modes"] = []any{"mount"}
	}
}
func normalizeResourceBudgetClaims(record map[string]any) {
	if record == nil {
		return
	}
	sortManifestSupportedFields(record)
	sortManifestFields(record, []string{"realization_contract_ids", termCrossRangePoolRefs})
}

// JSON Schema defaults do not describe constructor factories. These are the
// finite empty collection factories of the existing manifest models; supplied
// collections remain unchanged, including their ordered evidence members.
func manifestFactoryDefaults(document map[string]any) {
	factoryFields(document, nil, []string{termConstraints})
	delete(document, "configuration_registry")
	omitManifestNulls(document, []string{"execution_policy", "domain_profile_context_digest"})
	capabilities := object(document["capabilities"])
	omitManifestNulls(capabilities, []string{termOperationSupervision, "recovery_observation"})
	factoryFields(object(capabilities["provisioner"]), []string{"operating_systems", "supported_account_features", "supported_content_types", "supported_domain_profiles", "supported_generated_artifact_delivery_modes", "supported_generated_artifact_kinds", "supported_node_architectures", "supported_regeneration_scopes", "supported_service_materialization_profiles"}, []string{termConstraints})
	factoryFields(object(capabilities["evaluator"]), []string{"supported_evidence_channels", "supported_predicate_families", "supported_quantifiers", "supported_time_domains", "supported_truth_outcomes"}, []string{termConstraints})
	factoryFields(object(capabilities["orchestrator"]), []string{"supported_workflow_features", "supported_workflow_state_predicates"}, []string{termConstraints})
	participant := object(capabilities["participant_runtime"])
	omitManifestNulls(participant, []string{"tool_profiles", "invocation_tool_actions"})
	factoryFields(participant, []string{termExecutionBindings, "feature_support", termSupportedAutonomousActionContracts, "supported_autonomous_activity_features", termSupportedAutonomousObservationBoundaries, termSupportedAutonomousPolicyProfiles, "supported_autonomous_random_stream_profiles", termSupportedAutonomousSelectionStrategies, termSupportedAutonomousTargetAddresses, "supported_execution_control_actions"}, []string{termConstraints})
	for _, binding := range array(participant[termExecutionBindings]) {
		if len(array(at(binding, "temporal_contract_digests"))) == 0 {
			delete(object(binding), "temporal_contract_digests")
		}
	}
	for _, feature := range array(participant["feature_support"]) {
		factoryFields(object(feature), []string{"constraint_refs", "disclosure_refs", fieldEvidenceRefs, termLimitationRefs}, nil)
	}
	factoryFields(object(participant["resource_budgets"]), []string{termCrossRangePoolRefs}, nil)
	observation := object(capabilities[termObservation])
	factoryFields(observation, []string{"capture_offers"}, []string{termConstraints})
	for _, offer := range array(observation["capture_offers"]) {
		factoryFields(object(offer), []string{"channel_kinds", termChannelRefs, "retention_policy_refs", termScopeRefs, termSourceRefs}, nil)
	}
	factoryFields(object(capabilities[termTime]), []string{termSupportedConstraintKinds, termSupportedMappingKinds}, []string{termConstraints})
	for _, support := range array(document["realization_support"]) {
		factoryFields(object(support), []string{"artifact_mechanisms", "process_resource_limits", termSupportedConstraintKinds, "supported_exact_requirement_kinds"}, []string{termConstraints, "observation_capabilities"})
	}
}
func factoryFields(record map[string]any, arrays, mappings []string) {
	if record == nil {
		return
	}
	for _, name := range arrays {
		if _, present := record[name]; !present {
			record[name] = []any{}
		}
	}
	for _, name := range mappings {
		if _, present := record[name]; !present {
			record[name] = map[string]any{}
		}
	}
}

func omitManifestNulls(record map[string]any, names []string) {
	for _, name := range names {
		if record[name] == nil {
			delete(record, name)
		}
	}
}

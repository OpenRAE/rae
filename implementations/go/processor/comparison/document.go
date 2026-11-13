package comparison

import (
	"encoding/json"
	"slices"
	"strings"
)

type documentOwner struct{ kind, model, id, version string }

func documentOwnerFor(id string) (documentOwner, bool) {
	switch id {
	case "experiment-task-v1":
		return documentOwner{kindTask, "ExperimentTaskModel", "task_id", "task_version"}, true
	case "experiment-run-v1":
		return documentOwner{kindRun, "ExperimentRunModel", "run_id", "run_version"}, true
	case "experiment-capture-spec-v1":
		return documentOwner{kindCapture, "ExperimentCaptureSpecModel", "capture_spec_id", "spec_version"}, true
	case "experiment-study-v1":
		return documentOwner{kindStudy, "ExperimentStudyModel", "study_id", "study_version"}, true
	case "external-concept-bindings-v1":
		return documentOwner{kindExternal, "ExternalConceptBindingDocumentModel", "binding_set_id", "binding_set_version"}, true
	case "resolved-import-provenance":
		return documentOwner{kindModule, "ResolvedImportProvenance", "module_id", "module_version"}, true
	default:
		return documentOwner{}, false
	}
}
func documentArtifact(id string, raw []byte) (*artifact, error) {
	info, ok := documentOwnerFor(id)
	if !ok {
		return nil, invalid()
	}
	normalized, err := normalizedDocument(id, info, raw)
	if err != nil {
		return nil, err
	}
	digest, err := hash(normalized)
	if err != nil {
		return nil, err
	}
	result := &artifact{kind: info.kind, name: text(normalized[info.id]), version: text(normalized[info.version]), schema: text(normalized["schema_version"]), digest: digest, projections: map[string]ownerProjection{}}
	// Source presence belongs only to the task protocol's authored field set.
	protocolFields, err := protocolPresence(raw)
	if err != nil {
		return nil, err
	}
	revisions := []string{"1"}
	if info.kind == kindTask || info.kind == kindRun || info.kind == kindStudy {
		revisions = append(revisions, "2")
	}
	for _, revision := range revisions {
		projection, err := documentProjection(result, normalized, protocolFields, revision)
		if err != nil {
			return nil, err
		}
		result.projections[revision] = projection
	}
	return result, nil
}
func normalizedDocument(id string, info documentOwner, raw []byte) (map[string]any, error) {
	owner, err := owners()
	if err != nil {
		return nil, err
	}
	var document any
	if info.kind == kindModule {
		document, err = owner.low.DefaultedObjectFragment("instantiated-scenario-v1", "#/$defs/ResolvedImportProvenance", raw, inputLimits())
	} else {
		if owner.admitted.CheckPortable(id, raw, inputLimits()) != nil {
			return nil, invalid()
		}
		document, err = owner.low.Defaulted(id, raw, inputLimits())
	}
	if err != nil {
		return nil, invalid()
	}
	return normalizeOwner(info.model, document)
}
func protocolPresence(raw []byte) ([]string, error) {
	var original map[string]json.RawMessage
	if decode(raw, &original) != nil {
		return nil, invalid()
	}
	protocolFields := []string{}
	if original["evaluation_protocol"] != nil {
		var fields map[string]json.RawMessage
		if decode(original["evaluation_protocol"], &fields) != nil {
			return nil, invalid()
		}
		for key := range fields {
			protocolFields = append(protocolFields, key)
		}
		slices.Sort(protocolFields)
	}

	return protocolFields, nil
}
func documentProjection(owner *artifact, document map[string]any, protocol []string, revision string) (ownerProjection, error) {
	structural, err := hash(documentStructure(owner.kind, document, protocol, revision))
	if err != nil {
		return ownerProjection{}, err
	}
	semantic, err := hash(documentSemantics(owner.kind, document, revision))
	if err != nil {
		return ownerProjection{}, err
	}
	identity := owner.kind + ":" + owner.name
	if owner.kind == kindCapture {
		identity = "capture-spec:" + owner.name
	}
	result := ownerProjection{identity: identity, subjects: []subject{{identity: identity, structural: structural, semantic: semantic}}, dependencies: []dependency{}}
	if owner.kind == kindStudy || owner.kind == kindExternal {
		children, childErr := documentSubjects(owner.kind, document)
		if childErr != nil {
			return ownerProjection{}, childErr
		}
		result.subjects = append(result.subjects, children...)
	}
	result.dependencies, err = documentDependencies(owner.kind, identity, document)
	if err != nil {
		return ownerProjection{}, err
	}
	slices.SortFunc(result.subjects, func(a, b subject) int { return compareStrings(a.identity, b.identity) })
	return result, nil
}
func text(input any) string           { result, _ := input.(string); return result }
func object(input any) map[string]any { result, _ := input.(map[string]any); return result }
func array(input any) []any           { result, _ := input.([]any); return result }
func field(input any, keys ...string) any {
	for _, key := range keys {
		input = object(input)[key]
	}
	return input
}
func pick(input map[string]any, names ...string) map[string]any {
	result := map[string]any{}
	for _, name := range names {
		if v, ok := input[name]; ok {
			result[name] = v
		}
	}
	return result
}
func keys(input any) []string {
	result := []string{}
	for name := range object(input) {
		result = append(result, name)
	}
	slices.Sort(result)
	return result
}
func referenceKinds(input any) []string {
	result := []string{}
	for _, ref := range array(input) {
		result = append(result, text(field(ref, "ref_kind")))
	}
	slices.Sort(result)
	return result
}
func sortedRelations(input any) []any {
	result := append([]any{}, array(input)...)
	slices.SortFunc(result, func(a, b any) int {
		return compareStrings(text(field(a, "relation_id")), text(field(b, "relation_id")))
	})
	return result
}
func documentSemantics(kind string, v map[string]any, revision string) map[string]any {
	var result map[string]any
	switch kind {
	case kindModule:
		result = pick(v, "module_id", "module_version", "export_hash", "bindings")
	case kindTask:
		result = pick(v, "schema_version", "task_id", "task_version", "scenario_ref", "evaluation_protocol", "intended_use", "non_use", "population_or_construct", "split_and_leakage_controls", "apparatus_constraints", "validity_notes", "artifact_refs", "validation_basis_disclosures")
		if revision == "2" {
			result["observation_demands"] = v["observation_demands"]
		}
	case kindRun:
		result = pick(v, "schema_version", "run_id", "run_version", "task_ref", "scenario_snapshot_ref", "trial_provenance", "difficulty_provenance", "apparatus_context", "participant_implementation_provenance", "parameter_set", "realized_bindings", "stochastic_controls", "stochastic_draws", "started_at", "ended_at", "clock_context", "realized_time_model", "run_status", "outcome_status", "traceability", "realized_form_disclosures", "augmentation_disclosures", "evidence_artifacts", "result_summaries", "deviations", "invalidation", "used_refs", "generated_refs", "derived_from_refs", "validation_basis_disclosures")
	case kindCapture:
		result = pick(v, "schema_version", "capture_spec_id", "spec_version", "scope_refs", "capture_windows", "capture_requirements", "validity_notes", "artifact_refs")
	case kindStudy:
		result = pick(v, "schema_version", "study_id", "study_version", "study_kind", "purpose", "research_questions", "behavioral_claims", "inclusion_criteria", "factors", "run_allocation", "analysis_plan", "validity_notes", "report_artifacts", "export_artifacts", "validation_basis_disclosures")
		membership := map[string]any{}
		for key, member := range object(v["membership"]) {
			membership[key] = pick(object(member), "target_ref", "role", "grouping")
		}
		result["membership"] = membership
	case kindExternal:
		result = pick(v, "bindings")
	}
	if revision == "2" && (kind == kindTask || kind == kindRun || kind == kindStudy) {
		result["evidence_requirement_relations"] = sortedRelations(v["evidence_requirement_relations"])
	}
	return result
}
func documentStructure(kind string, v map[string]any, protocol []string, revision string) map[string]any {
	result := map[string]any{}
	switch kind {
	case kindModule:
		result = structureModule(v, protocol)
	case kindTask:
		result = structureTask(v, protocol)
	case kindRun:
		result = structureRun(v, protocol)
	case kindCapture:
		result = structureCapture(v, protocol)
	case kindStudy:
		result = structureStudy(v, protocol)
	case kindExternal:
		result = structureExternal(v, protocol)
	}

	if revision == "2" && (kind == kindTask || kind == kindRun || kind == kindStudy) {
		relations := []any{}
		for _, relation := range sortedRelations(v["evidence_requirement_relations"]) {
			relations = append(relations, pick(object(relation), "relation_id", "relation_kind", "scope", "refinement_dimensions"))
		}
		result["evidence_requirement_relations"] = relations
	}
	return result
}
func structureModule(v map[string]any, _ []string) map[string]any {
	result := map[string]any{}
	result["namespace_depth"] = len(array(v["namespace"]))
	parameters := []string{}
	for _, binding := range array(v["bindings"]) {
		parts := []string{}
		for _, part := range array(field(binding, "parameter")) {
			parts = append(parts, text(part))
		}
		parameters = append(parameters, strings.Join(parts, "."))
	}
	slices.Sort(parameters)
	result["binding_parameters"] = parameters
	result["has_export_surface"] = text(v["export_hash"]) != ""

	return result
}
func structureTask(v map[string]any, protocol []string) map[string]any {
	result := map[string]any{}
	result["scenario_reference_kind"] = field(v, "scenario_ref", "ref_kind")
	result["evaluation_protocol_fields"] = protocol
	result["non_use_count"] = len(array(v["non_use"]))
	result["artifact_ref_count"] = len(array(v["artifact_refs"]))
	result["validation_basis_count"] = len(array(v["validation_basis_disclosures"]))

	return result
}
func structureRun(v map[string]any, _ []string) map[string]any {
	result := map[string]any{}
	result["task_reference_kind"] = field(v, "task_ref", "ref_kind")
	result["scenario_reference_kind"] = field(v, "scenario_snapshot_ref", "ref_kind")
	result["result_summary_ids"] = keys(v["result_summaries"])
	result["evidence_artifact_count"] = len(array(v["evidence_artifacts"]))
	result["used_ref_kinds"] = referenceKinds(v["used_refs"])
	result["generated_ref_kinds"] = referenceKinds(v["generated_refs"])
	result["derived_ref_kinds"] = referenceKinds(v["derived_from_refs"])

	return result
}
func structureCapture(v map[string]any, _ []string) map[string]any {
	result := map[string]any{}
	result["scope_ref_kinds"] = referenceKinds(v["scope_refs"])
	windows := []string{}
	for _, window := range array(v["capture_windows"]) {
		windows = append(windows, text(field(window, "window_id")))
	}
	slices.Sort(windows)
	result["window_ids"] = windows
	result["requirement_ids"] = keys(v["capture_requirements"])
	result["artifact_ref_count"] = len(array(v["artifact_refs"]))

	return result
}
func structureStudy(v map[string]any, _ []string) map[string]any {
	result := map[string]any{}
	membership := map[string]any{}
	for key, member := range object(v["membership"]) {
		membership[key] = map[string]any{"role": field(member, "role"), "target_kind": field(member, "target_ref", "ref_kind")}
	}
	result["membership"] = membership
	result["factor_ids"] = keys(v["factors"])
	result["has_run_allocation"] = v["run_allocation"] != nil
	result["has_analysis_plan"] = v["analysis_plan"] != nil

	return result
}
func structureExternal(v map[string]any, _ []string) map[string]any {
	result := map[string]any{}
	bindings := map[string]any{}
	for key, binding := range object(v["bindings"]) {
		bindings[key] = bindingStructure(binding)
	}
	result["bindings"] = bindings
	return result
}
func bindingStructure(binding any) map[string]any {
	return map[string]any{"relationship_kind": field(binding, "assertion", "relationship_kind"), "subject_kind": field(binding, "subject", "subject_kind"), "lifecycle_phase": field(binding, "subject", "lifecycle_phase")}
}
func documentSubjects(kind string, v map[string]any) ([]subject, error) {
	result := []subject{}
	family, prefix := "membership", "study-member:"
	if kind == kindExternal {
		family, prefix = "bindings", "external-binding:"
	}
	for key, member := range object(v[family]) {
		var shape, semantics any
		if kind == kindStudy {
			shape = map[string]any{"role": field(member, "role"), "target_kind": field(member, "target_ref", "ref_kind"), "has_grouping": field(member, "grouping") != nil}
			semantics = pick(object(member), "target_ref", "role", "grouping")
		} else {
			shape = bindingStructure(member)
			semantics = member
		}
		structural, err := hash(shape)
		if err != nil {
			return nil, err
		}
		semantic, err := hash(semantics)
		if err != nil {
			return nil, err
		}
		result = append(result, subject{identity: prefix + key, structural: structural, semantic: semantic})
	}
	return result, nil
}

type dependencyInput struct {
	target, rule string
	evidence     any
}

func documentDependencies(kind, dependent string, v map[string]any) ([]dependency, error) {
	result := []dependency{}
	for _, input := range dependencyInputs(kind, v) {
		provenance, err := hash(input.evidence)
		if err != nil {
			return nil, err
		}
		result = append(result, dependency{dependent: dependent, target: input.target, rule: input.rule, provenance: provenance})
	}
	slices.SortFunc(result, func(a, b dependency) int {
		return compareTuple([]string{a.dependent, a.rule, a.target, a.provenance}, []string{b.dependent, b.rule, b.target, b.provenance})
	})
	return result, nil
}
func dependencyInputs(kind string, v map[string]any) []dependencyInput {
	result := []dependencyInput{}
	switch kind {
	case kindTask:
		result = append(result, dependencyInput{"scenario:" + text(field(v, "scenario_ref", "ref_id")), "experiment-task-scenario-reference", v["scenario_ref"]})
	case kindRun:
		result = append(result, dependencyInput{"task:" + text(field(v, "task_ref", "ref_id")), "experiment-run-task-reference", v["task_ref"]}, dependencyInput{"scenario:" + text(field(v, "scenario_snapshot_ref", "ref_id")), "experiment-run-scenario-snapshot-reference", v["scenario_snapshot_ref"]})
	case kindCapture:
		for _, ref := range array(v["scope_refs"]) {
			result = append(result, dependencyInput{referenceIdentity(ref), "experiment-capture-scope-reference", ref})
		}
	case kindStudy:
		for _, member := range object(v["membership"]) {
			result = append(result, dependencyInput{referenceIdentity(field(member, "target_ref")), "experiment-study-membership", member})
		}
	case kindExternal:
		for _, binding := range object(v["bindings"]) {
			result = append(result, dependencyInput{text(field(binding, "subject", "canonical_ref")), "external-concept-subject", field(binding, "subject")})
		}
	}
	return result
}
func referenceIdentity(ref any) string {
	kind := text(field(ref, "ref_kind"))
	if kind == "scenario-snapshot" {
		kind = kindScenario
	}
	return kind + ":" + text(field(ref, "ref_id"))
}
func compareTuple(a, b []string) int { return slices.Compare(a, b) }

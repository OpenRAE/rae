package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func (e *Validator) runProvenanceRules() map[string]definition {
	return map[string]definition{
		"experiment-run-admitted-trial-provenance":      {check: runTrialProvenance},
		"run-materialization-carriers-archived":         {check: runMaterializations},
		"adaptive-difficulty-run-provenance-valid":      {check: runDifficulty},
		"adaptive-difficulty-authoring-admission-valid": {check: e.difficultyAuthoring, contextual: true},
		"realized-time-model-bound-to-run":              {check: e.runTimeModel},
	}
}
func runTrialProvenance(i validation.Invocation) error {
	run := i.Instance
	p := at(run, "trial_provenance")
	if p == nil {
		return nil
	}
	if !equal(at(run, termRunID), at(p, "admitted_run_id")) || !equal(at(run, "scenario_snapshot_ref", "ref_digest"), at(p, "instantiated_scenario_digest")) {
		return invalid()
	}
	refs := array(at(p, "processor_plan_refs"))
	if len(refs) != 3 || len(rowSet(refs, "plan_kind")) != 3 {
		return invalid()
	}
	for _, ref := range refs {
		if err := processorPlanReference(ref); err != nil {
			return err
		}
	}
	attempts := array(at(p, "execution_attempts"))
	ids := rowSet(attempts, "execution_attempt_id")
	if len(ids) != len(attempts) || len(rowSet(attempts, "cleanup_receipt_ref")) != len(attempts) || !ids[stringAt(p, "terminal_attempt_id")] || ids[stringAt(p, "admitted_run_id")] {
		return invalid()
	}
	for _, attempt := range attempts {
		if !fieldsUnique(attempt, "operation_refs") {
			return invalid()
		}
	}
	return nil
}

// processorPlanReference requires a digest-bound reference to the published
// contract of the plan kind.
func processorPlanReference(ref any) error {
	contract := map[string]string{termProvisioning: termProvisioningPlanV1, termOrchestration: termOrchestrationPlanV1, termEvaluation: termEvaluationPlanV1}[stringAt(ref, "plan_kind")]
	artifact := at(ref, "artifact_ref")
	return require(contract != "" && stringAt(artifact, fieldRefKind) == termOther && stringAt(artifact, fieldRefVersion) == contract && at(artifact, "ref_digest") != nil && at(artifact, "ref_path") == nil)
}

func archiveRecordLocal(v any) error {
	artifact, ref := at(v, "artifact"), at(v, "reference")
	if at(v, "inventory") != nil && !equal(at(v, "inventory", termRunID), at(v, termRunID)) {
		return invalid()
	}
	if stringAt(artifact, "role") != kindMaterializationAttestation || !equal(at(ref, fieldRefID), at(artifact, termArtifactID)) || stringAt(artifact, "uri") != "urn:sha256:"+stringAt(artifact, "checksum", "value") || stringAt(artifact, "checksum", "algorithm") != "sha256" || stringAt(artifact, "media_type") != "application/vnd.raes.sdl+yaml" {
		return invalid()
	}
	sensitivity := stringAt(artifact, "sensitivity")
	return require((sensitivity == "restricted" || sensitivity == "redacted") && !numericGreater(at(artifact, "size_bytes"), json.Number("4194304")))
}
func runMaterializations(i validation.Invocation) error {
	v := i.Instance
	records := array(at(v, "materialization_attestations"))
	if len(records) == 0 {
		return materializationCarriers(v, nil)
	}
	if err := value.Validate(records, value.Runtime()); err != nil {
		return invalid()
	}
	archived := map[string]bool{}
	ids := map[string]bool{}
	for _, record := range records {
		if !equal(at(record, termRunID), at(v, termRunID)) {
			return invalid()
		}
		id := stringAt(record, "reference", fieldRefID)
		if ids[id] {
			return invalid()
		}
		ids[id] = true
		if err := archiveRecordLocal(record); err != nil {
			return err
		}
		archived[referenceKey(at(record, "reference"))] = true
	}
	return materializationCarriers(v, archived)
}

func experimentSpecProjection(v any) any {
	root := object(v)
	if root["factorial_design"] == nil {
		delete(root, "factorial_design")
	}
	runPlan := object(at(root, "run_plan"))
	for _, field := range []string{"replacement_policy", "allocation_policy"} {
		if runPlan[field] == nil {
			delete(runPlan, field)
		}
	}
	for _, assignment := range object(at(runPlan, "allocation", "condition_assignments")) {
		omitEmptyBindings(assignment)
	}
	return root
}
func omitEmptyBindings(v any) {
	for _, field := range []string{termRequiredBindings, termRequiredSelections} {
		if len(array(at(v, field))) == 0 {
			delete(object(v), field)
		}
	}
}
func (e *Validator) difficultyAuthoring(i validation.Invocation) error {
	context, ok := i.Context.(ExperimentDifficultyContext)
	if !ok {
		if at(i.Instance, "difficulty_provenance") == nil {
			return nil
		}
		return contextRequired()
	}
	spec, err := e.contextDocument(termExperimentAuthoringInputV1, context.ExperimentDesign())
	if err != nil {
		return err
	}
	spec, err = e.defaulted(termExperimentAuthoringInputV1, spec)
	if err != nil {
		return err
	}
	spec = experimentSpecProjection(spec)
	assignment := at(spec, "run_plan", "allocation", "condition_assignments", context.ConditionID())
	if assignment == nil {
		return invalid()
	}
	run := i.Instance
	if !matchingFields(at(run, "task_ref"), at(spec, "task_ref"), fieldRefID, fieldRefVersion) {
		return invalid()
	}
	provenance := at(run, "difficulty_provenance")
	condition := text(defaultMember(assignment, "difficulty_condition", conditionFixed))
	if provenance == nil {
		return require(condition == conditionFixed)
	}
	if stringAt(provenance, termPolicy, "condition") != condition {
		return invalid()
	}
	registry := at(spec, "run_plan", "difficulty_policy_registry")
	policyID := stringAt(assignment, "difficulty_policy_id")
	if policyID == "" {
		policyID = stringAt(registry, "default_policy_id")
	}
	if registry == nil || at(registry, "policies", policyID) == nil || !equal(at(provenance, termPolicy), at(registry, "policies", policyID)) {
		return invalid()
	}
	digest, err := jsonDigest(spec)
	if err != nil {
		return err
	}
	return require(equal(at(provenance, "design_ref", fieldRefID), at(spec, "spec_id")) && equal(at(provenance, "design_ref", fieldRefVersion), at(spec, "spec_version")) && stringAt(provenance, "design_ref", "ref_digest") == digest)
}

func materializationCarriers(v any, archived map[string]bool) error {
	for _, disclosure := range array(at(v, "augmentation_disclosures")) {
		for _, ref := range array(at(disclosure, "carrier_refs")) {
			if stringAt(ref, fieldRefKind) == kindMaterializationAttestation && !archived[referenceKey(ref)] {
				return invalid()
			}
		}
	}
	return nil
}

package trial

import (
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

// RealizeEntry projects one sealed entry through the existing SDL compiler and planner.
func RealizeEntry(inputs RealizationInputs, entryID string, options RealizationOptions) (Realization, error) {
	request, document, entry, err := realizationRequest(inputs, entryID)
	if err != nil {
		return Realization{}, err
	}
	input, err := prepareInputs(request)
	if err != nil {
		return Realization{}, err
	}
	if err = authoringSelections(request, input, document); err != nil {
		return Realization{}, err
	}
	backend, present := input.backends[inputs.BackendKey]
	if !present {
		return Realization{}, trialInvalid()
	}
	processorManifest, err := realizationProcessor(input)
	if err != nil {
		return Realization{}, err
	}
	instantiated, err := InstantiateEntry(inputs.Plan, entryID, inputs.Family)
	if err != nil {
		return Realization{}, err
	}
	capture, err := captureInputs(request, input)
	if err != nil {
		return Realization{}, err
	}
	compiled, err := processor.CompileWithOptions(instantiated, processor.CompileOptions{Capture: capture})
	if err != nil {
		return Realization{}, err
	}
	result, err := planning.PlanWithManifest(compiled, backend, planning.Options{ProcessorManifest: processorManifest, RealizationEnvelope: &input.envelope, Scope: &planning.Scope{TargetName: options.TargetName, RunID: &entry.RunID, InstantiationID: &entry.ID}, ArtifactAvailability: options.ArtifactAvailability})
	if err != nil {
		return Realization{}, err
	}
	if result.Plan == nil || !result.Plan.Valid() {
		return Realization{}, trialInvalid()
	}
	digest, err := sdl.CanonicalDigest(instantiated)
	if err != nil {
		return Realization{}, err
	}
	realization := Realization{Instantiated: instantiated, SnapshotDigest: digest, ExecutionPlan: result.Plan, ProvisioningPlan: result.Plan.Provisioning(), OrchestrationPlan: result.Plan.Orchestration(), EvaluationPlan: result.Plan.Evaluation(), ParticipantConfigurations: []binding.ParticipantConfigurationResultV1{}, ProcessorPlanRefs: []admission.Fragment{}}
	if err = realizationArtifacts(input.owner, entry, &realization); err != nil {
		return Realization{}, err
	}
	return realization, nil
}
func realizationArtifacts(owner *admission.Validator, entry trialEntry, realization *Realization) error {
	for _, item := range []struct {
		kind, contract string
		value          any
	}{{"provisioning", "provisioning-plan-v1", realization.ProvisioningPlan}, {"orchestration", "orchestration-plan-v1", realization.OrchestrationPlan}, {"evaluation", "evaluation-plan-v1", realization.EvaluationPlan}} {
		ref, err := processorReference(owner, entry.RunID, item.kind, item.contract, item.value)
		if err != nil {
			return err
		}
		realization.ProcessorPlanRefs = append(realization.ProcessorPlanRefs, ref)
	}
	for _, raw := range entry.Configurations {
		var configuration binding.ParticipantConfigurationResultV1
		if decode(raw, &configuration) != nil {
			return trialInvalid()
		}
		realization.ParticipantConfigurations = append(realization.ParticipantConfigurations, configuration)
	}
	return nil
}
func realizationRequest(inputs RealizationInputs, entryID string) (Request, trialPlan, trialEntry, error) {
	var document trialPlan
	admitted, err := admitPlan(inputs.Plan)
	if err != nil {
		return Request{}, document, trialEntry{}, err
	}
	owner, err := trialOwner()
	if err != nil {
		return Request{}, document, trialEntry{}, err
	}
	raw, err := admission.TrialPlanProjection(owner, admitted, trialIngress())
	if err != nil {
		return Request{}, document, trialEntry{}, err
	}
	if decode(raw, &document) != nil {
		return Request{}, document, trialEntry{}, trialInvalid()
	}
	entry, present := document.Entries[entryID]
	if !present {
		return Request{}, document, entry, fault.New(fault.NotFound, "trial-entry-not-found", nil)
	}
	var apparatus struct {
		Kind string `json:"realization_kind"`
	}
	if decode(entry.Apparatus, &apparatus) != nil || apparatus.Kind == "mixed-composition" {
		return Request{}, document, entry, trialInvalid()
	}
	var cleanup cleanupTemplate
	if decode(document.Cleanup[entry.Controls.CleanupRef], &cleanup) != nil {
		return Request{}, document, entry, trialInvalid()
	}
	cleanupRaw, err := encoded(cleanup)
	if err != nil {
		return Request{}, document, entry, err
	}
	authority, err := encoded(executionAuthority{entry.Controls.Timeout, entry.Controls.OnTimeout, entry.Controls.OnCancellation, cleanupRaw})
	if err != nil {
		return Request{}, document, entry, err
	}
	request := Request{Family: inputs.Family, Experiment: inputs.Experiment, Task: inputs.Task, RealizationEnvelope: inputs.RealizationEnvelope, CaptureSpecs: inputs.CaptureSpecs, ParticipantManifests: inputs.ParticipantManifests, ApparatusManifests: inputs.ApparatusManifests, Limits: DefaultLimits(), MixedCompositionLimits: DefaultMixedCompositionLimits()}
	for _, item := range []struct {
		raw     json.RawMessage
		profile admission.FragmentProfile
		target  *admission.Fragment
	}{{document.Refs, admission.TrialInputRefs, &request.InputRefs}, {entry.Apparatus, admission.TrialApparatus, &request.Apparatus}, {authority, admission.TrialExecutionAuthority, &request.ExecutionAuthority}} {
		var value any
		if decode(item.raw, &value) != nil {
			return Request{}, document, entry, trialInvalid()
		}
		*item.target, err = admission.AdmitFragment(owner, item.profile, value, trialIngress())
		if err != nil {
			return Request{}, document, entry, err
		}
	}
	return request, document, entry, nil
}
func realizationProcessor(input compilationInputs) (*binding.ProcessorManifestV2, error) {
	var apparatus apparatusBinding
	if decode(input.apparatusJSON, &apparatus) != nil {
		return nil, trialInvalid()
	}
	var selected *binding.ProcessorManifestV2
	for _, ref := range apparatus.Manifests {
		if ref.Subject == nil || ref.Subject.Kind != componentProcessor {
			continue
		}
		key := ApparatusManifestKey{ComponentKind: ref.Subject.Kind, ComponentName: ref.Subject.ID, ComponentVersion: text(ref.Subject.Version), ManifestVersion: text(ref.Version)}
		if selected != nil {
			return nil, trialInvalid()
		}
		selected = input.manifests[key].Processor
	}
	if selected == nil {
		return nil, trialInvalid()
	}
	return selected, nil
}
func captureInputs(request Request, input compilationInputs) (processor.CaptureInputs, error) {
	capture := processor.CaptureInputs{RelationScenario: request.Family}
	for _, id := range slices.Sorted(maps.Keys(request.CaptureSpecs)) {
		capture.CaptureSpecs = append(capture.CaptureSpecs, request.CaptureSpecs[id])
	}
	raw, err := encoded(request.Task)
	if err != nil {
		return capture, err
	}
	var task struct {
		Relations []json.RawMessage `json:"evidence_requirement_relations"`
	}
	if decode(raw, &task) != nil {
		return capture, trialInvalid()
	}
	relations := append(slices.Clone(task.Relations), input.spec.RunPlan.EvidenceRelations...)
	for _, raw := range relations {
		var value any
		if decode(raw, &value) != nil {
			return capture, trialInvalid()
		}
		fragment, err := admission.AdmitFragment(input.owner, admission.ExperimentEvidenceRequirementRelation, value, trialIngress())
		if err != nil {
			return capture, err
		}
		capture.EvidenceRelations = append(capture.EvidenceRelations, fragment)
	}
	return capture, nil
}
func processorReference(owner *admission.Validator, runID, kind, contract string, plan any) (admission.Fragment, error) { //nolint:ireturn // The contract owner mints this admitted reference.
	d, err := hash(plan)
	if err != nil {
		return nil, err
	}
	ref := struct {
		Kind     string `json:"plan_kind"`
		Artifact struct {
			Kind    string  `json:"ref_kind"`
			ID      string  `json:"ref_id"`
			Version string  `json:"ref_version"`
			Digest  string  `json:"ref_digest"`
			Path    *string `json:"ref_path"`
		} `json:"artifact_ref"`
	}{Kind: kind}
	ref.Artifact.Kind = "other"
	ref.Artifact.ID = runID + ":" + kind
	ref.Artifact.Version = contract
	ref.Artifact.Digest = d
	raw, err := encoded(ref)
	if err != nil {
		return nil, err
	}
	var value any
	if decode(raw, &value) != nil {
		return nil, trialInvalid()
	}
	return admission.AdmitFragment(owner, admission.TrialProcessorPlanReference, value, trialIngress())
}

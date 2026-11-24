package planning

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

type plannedResource struct {
	facts    processor.Resource
	payload  json.RawMessage
	profiles []binding.DomainProfileBindingV1
}
type snapshotEntry struct {
	Address  string                           `json:"address"`
	Domain   string                           `json:"domain"`
	Kind     string                           `json:"resource_type"`
	Payload  json.RawMessage                  `json:"payload"`
	Ordering []string                         `json:"ordering_dependencies"`
	Refresh  []string                         `json:"refresh_dependencies"`
	Profiles []binding.DomainProfileBindingV1 `json:"profile_bindings"`
	Status   string                           `json:"status"`
}
type planOperation struct {
	ExecutionPolicy       json.RawMessage                  `json:"execution_policy,omitempty"`
	ExecutionPolicyScopes []json.RawMessage                `json:"execution_policy_scopes,omitempty"`
	Action                string                           `json:"action"`
	Address               string                           `json:"address"`
	Kind                  string                           `json:"resource_type"`
	Payload               json.RawMessage                  `json:"payload"`
	Ordering              []string                         `json:"ordering_dependencies"`
	Refresh               []string                         `json:"refresh_dependencies"`
	Profiles              []binding.DomainProfileBindingV1 `json:"profile_bindings,omitempty"`
}

// Plan builds execution phases from an admitted compilation and backend manifest.
func Plan(compilation processor.Compilation, manifest validation.Value, options Options) (Result, error) {
	if manifest.ContractID() != "backend-manifest-v2" {
		return Result{}, invalidPlan()
	}
	transport, err := manifest.Transport()
	if err != nil {
		return Result{}, err
	}
	typed, ok := transport.(binding.BackendManifestV2)
	if !ok {
		return Result{}, invalidPlan()
	}
	return PlanWithManifest(compilation, typed, options)
}

// PlanWithManifest builds execution phases from a generated backend manifest carrier.
func PlanWithManifest(compilation processor.Compilation, manifest binding.BackendManifestV2, options Options) (Result, error) {
	compiled, err := processor.AdmitCompilation(compilation)
	if err != nil {
		return Result{}, err
	}
	if checkErr := checkTransport("backend-manifest-v2", manifest); checkErr != nil {
		return Result{}, checkErr
	}
	manifest = copyTransport(manifest)
	original := compiled.Model()
	context, err := prepareOptions(original, options)
	if err != nil {
		return Result{}, err
	}
	model, resolved, err := resolvePlanningModel(original, manifest, options, &context)
	if err != nil {
		return Result{}, err
	}
	view := model.View()
	resources := compiledPlanningResources(view)
	entries := map[string]snapshotEntry{}
	for address, raw := range fieldValue(context.Snapshot.Entries) {
		var entry snapshotEntry
		if json.Unmarshal(raw, &entry) != nil {
			return Result{}, invalidPlan()
		}
		entries[address] = entry
	}
	profileAuthority, profileDiagnostics, err := prepareProfiles(view, manifest, context.ProfileContext, resources, entries)
	if err != nil {
		return Result{}, err
	}
	regenerationDiagnostics, err := bindRegenerationScopes(view.Resources, resources, context.Scope)
	if err != nil {
		return Result{}, err
	}
	actions, deleted, err := reconcileResources(resources, entries, resolved.Requirements)
	if err != nil {
		return Result{}, err
	}
	if options.RefreshEvaluation {
		refreshEvaluationActions(resources, actions)
	}
	plan := &executionPlan{model: model, observations: view.ObservationDemands, manifest: manifest, context: context, resources: resources, profileAuthority: profileAuthority, operations: map[string][]planOperation{}}
	plan.diagnostics, err = plan.admissionDiagnostics(view, resolved, profileDiagnostics, regenerationDiagnostics)
	if err != nil {
		return Result{}, err
	}
	counts, err := plan.buildOperations(resources, actions, deleted)
	if err != nil {
		return Result{}, err
	}
	if err := plan.finalizePlanning(view, entries); err != nil {
		return Result{}, err
	}
	if err := plan.project(resolved); err != nil {
		return Result{}, err
	}
	return Result{Plan: plan, Resources: counts, Diagnostics: copyDiagnostics(plan.diagnostics)}, nil
}

//nolint:ireturn // Resolution preserves the exact native compiled handle.
func resolvePlanningModel(original processor.RuntimeModel, manifest binding.BackendManifestV2, options Options, context *PlanningContext) (processor.RuntimeModel, realization.Resolution, error) {
	decisions := []realization.Decision{}
	for _, requirement := range original.View().RealizationRequirements {
		if !requirement.Delegated && !requirement.RecursivePending {
			continue
		}
		closure := ClosedWorld
		if options.ApparatusDefault != nil {
			fragment, checkErr := realization.AdmitRequirement(requirement)
			if checkErr != nil {
				return nil, realization.Resolution{}, checkErr
			}
			closure, checkErr = options.ApparatusDefault.Resolve(fragment, copyTransport(manifest))
			if checkErr != nil {
				return nil, realization.Resolution{}, checkErr
			}
		}
		if closure != ClosedWorld && closure != OpenWorld {
			return nil, realization.Resolution{}, invalidPlan()
		}
		context.ApparatusDecisions[RequirementKey{requirement.Address, requirement.FieldPath, requirement.Kind}] = closure
		decisions = append(decisions, realization.Decision{Address: requirement.Address, FieldPath: requirement.FieldPath, Kind: requirement.Kind, Closure: string(closure)})
	}
	return processor.ResolveRealization(original, realization.ResolveOptions{Manifest: manifest, Envelope: options.RealizationEnvelope, Decisions: decisions})
}
func refreshEvaluationActions(resources map[string]plannedResource, actions map[string]string) {
	for address, resource := range resources {
		if resource.facts.Domain == termEvaluation && actions[address] == termUnchanged {
			actions[address] = termUpdate
		}
	}
}
func (plan *executionPlan) admissionDiagnostics(view processor.CompiledScenario, resolved realization.Resolution, profileDiagnostics, regenerationDiagnostics []diagnostic.Diagnostic) ([]diagnostic.Diagnostic, error) {
	manifest := plan.manifest
	model := plan.model
	context := plan.context
	resources := plan.resources
	capabilityDiagnostics, err := manifestDiagnostics(view, manifest)
	if err != nil {
		return nil, err
	}
	participantSupport, err := processor.ParticipantSupport(model, manifest, context.ProcessorManifest)
	if err != nil {
		return nil, err
	}
	diagnostics := []diagnostic.Diagnostic{}
	for _, finding := range profileDiagnostics {
		if finding.Code == "realization.profile-unsupported" {
			diagnostics = append(diagnostics, finding)
		}
	}
	diagnostics = append(diagnostics, regenerationDiagnostics...)
	diagnostics = append(diagnostics, participantSupport.Tools...)
	for _, finding := range profileDiagnostics {
		if finding.Code == "realization.descriptor-profile-unsupported" {
			diagnostics = append(diagnostics, finding)
		}
	}
	diagnostics = append(diagnostics, view.Diagnostics...)
	diagnostics = append(diagnostics, capabilityDiagnostics...)
	timeDiagnostics, err := timeDiagnostics(view, fieldValue(fieldValue(manifest.Capabilities).Time))
	if err != nil {
		return nil, err
	}
	diagnostics = append(diagnostics, timeDiagnostics...)
	diagnostics = append(diagnostics, participantSupport.Execution...)
	if context.MixedControlAdmission == nil {
		diagnostics = append(diagnostics, participantSupport.MixedControl...)
	}
	captureDiagnostics, err := captureAdmission(view, fieldValue(fieldValue(manifest.Capabilities).Observation))
	if err != nil {
		return nil, err
	}
	diagnostics = append(diagnostics, captureDiagnostics...)
	diagnostics = append(diagnostics, resolved.Diagnostics...)
	artifactDiagnostics, err := realization.ArtifactSupport(resolved.Requirements, manifest, context.ArtifactAvailability)
	if err != nil {
		return nil, err
	}
	diagnostics = append(diagnostics, artifactDiagnostics...)
	memberDiagnostics, err := plannedEnvelopeMemberDiagnostics(view, resolved.Requirements, manifest, context.RealizationEnvelope)
	if err != nil {
		return nil, err
	}
	diagnostics = append(diagnostics, memberDiagnostics...)
	diagnostics = append(diagnostics, orderingDiagnostics(resources)...)
	return diagnostics, nil
}
func (plan *executionPlan) buildOperations(resources map[string]plannedResource, actions map[string]string, deleted map[string]snapshotEntry) (map[string]int, error) {
	counts := map[string]int{termProvisioning: 0, termOrchestration: 0, termEvaluation: 0}
	for _, domain := range []string{termProvisioning, termOrchestration, termEvaluation} {
		ops, checkErr := domainOperations(domain, resources, actions, deleted)
		if checkErr != nil {
			return nil, checkErr
		}
		plan.operations[domain] = ops
		for _, resource := range resources {
			if resource.facts.Domain == domain {
				counts[domain]++
			}
		}
	}
	return counts, nil
}
func (plan *executionPlan) finalizePlanning(view processor.CompiledScenario, entries map[string]snapshotEntry) error {
	manifest := plan.manifest
	context := plan.context
	preparationDiagnostics, err := plan.attachPreparation(view, entries)
	if err != nil {
		return err
	}
	descendantDiagnostics, err := plan.retainReportedDescendants(view, entries)
	if err != nil {
		return err
	}
	plan.provisioningDiagnostics = append(plan.provisioningDiagnostics, preparationDiagnostics...)
	plan.provisioningDiagnostics = append(plan.provisioningDiagnostics, descendantDiagnostics...)
	serviceDiagnostics, err := plan.serviceMaterializationDiagnostics()
	if err != nil {
		return err
	}
	plan.provisioningDiagnostics = append(plan.provisioningDiagnostics, serviceDiagnostics...)
	if checkErr := plan.attachExecutionPolicies(view.ExecutionPolicies); checkErr != nil {
		return checkErr
	}
	plan.materializationSource, plan.materializationDiagnostics, err = plannedMaterializationSource(view, manifest, context.Scope)
	if err != nil {
		return err
	}
	plan.augmentationScopeRequired = view.AugmentationScopeRequired
	if view.Descriptive {
		plan.purpose = "inspection"
	}
	return nil
}

func planDiagnostic(code, domain, address, message string) diagnostic.Diagnostic {
	return diagnostic.Diagnostic{Code: code, Domain: domain, Address: address, Message: message, Severity: "error"}
}

func compiledPlanningResources(view processor.CompiledScenario) map[string]plannedResource {
	resources := map[string]plannedResource{}
	for _, resource := range view.Resources {
		resources[resource.Address] = plannedResource{facts: resource, payload: resource.Payload.JSON(), profiles: []binding.DomainProfileBindingV1{}}
	}
	return resources
}

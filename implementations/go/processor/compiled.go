// Package processor compiles admitted scenarios into native immutable models.
package processor

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type runtimeModel struct {
	view         CompiledScenario
	document     []byte
	participants compiledParticipants
}

// Keep participant semantics behind the same native compiled owner. Later
// capability and preparation checks use these records, never payload JSON.
type compiledParticipants struct {
	actions        map[string]participantAction
	outcomes       map[string]participantOutcomeRule
	boundaries     map[string]participantBoundary
	behaviors      map[string]participantBehavior
	specifications map[string]participantSpecification
	tools          map[string]participantTool
	deliveries     map[string]participantDelivery
}
type compilation struct{ model *runtimeModel }

func (*runtimeModel) compiledModel() {
	// This unexported marker seals the handle to its native owner.
}
func (*compilation) compiledScenario() {
	// This unexported marker seals the handle to its native owner.
}

// JSON returns a copy of the published operation payload.
func (payload ResourcePayload) JSON() []byte         { return slices.Clone(payload.data) }
func (model *runtimeModel) View() CompiledScenario   { return copyCompiledScenario(model.view) }
func (model *runtimeModel) Document() map[string]any { return decodeProjection(model.document) }

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func (result *compilation) Model() RuntimeModel      { return result.model }
func (result *compilation) Document() map[string]any { return result.model.Document() }
func (result *compilation) Diagnostics() []diagnostic.Diagnostic {
	return copyDiagnostics(result.model.view.Diagnostics)
}
func (result *compilation) Nodes() int    { return result.count(termNode) }
func (result *compilation) Networks() int { return result.count(termNetwork) }
func (result *compilation) count(kind string) int {
	count := 0
	for _, resource := range result.model.view.Resources {
		if resource.Domain == termProvisioning && resource.Kind == kind {
			count++
		}
	}
	return count
}

// AdmitCompilation checks the exact issuing owner without invoking foreign methods.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func AdmitCompilation(input Compilation) (Compilation, error) {
	result, err := nativeCompilation(input)
	if err != nil {
		return nil, err
	}
	return result, nil
}

func nativeCompilation(input Compilation) (*compilation, error) {
	result, ok := input.(*compilation)
	if !ok || result == nil || result.model == nil {
		return nil, invalidCompiled()
	}
	return result, nil
}

// AdmitRuntimeModel checks the exact issuing owner without invoking foreign methods.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func AdmitRuntimeModel(input RuntimeModel) (RuntimeModel, error) {
	model, err := nativeRuntimeModel(input)
	if err != nil {
		return nil, err
	}
	return model, nil
}

func nativeRuntimeModel(input RuntimeModel) (*runtimeModel, error) {
	model, ok := input.(*runtimeModel)
	if !ok || model == nil {
		return nil, invalidCompiled()
	}
	return model, nil
}
func invalidCompiled() error { return fault.New(fault.InvalidInput, "processor-compiled-input", nil) }
func decodeProjection(raw []byte) map[string]any {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var output map[string]any
	if err := decoder.Decode(&output); err != nil {
		panic("processor: invalid owned projection")
	}
	return output
}
func copyDiagnostics(input []diagnostic.Diagnostic) []diagnostic.Diagnostic {
	output := slices.Clone(input)
	for i := range output {
		if output[i].Range != nil {
			v := *output[i].Range
			output[i].Range = &v
		}
	}
	return output
}
func copyResource(input Resource) Resource {
	result := input
	result.SelectedProfiles = copyTransport(input.SelectedProfiles)
	result.OrderingDependencies = slices.Clone(input.OrderingDependencies)
	result.RefreshDependencies = slices.Clone(input.RefreshDependencies)
	result.RequiredFeatures = slices.Clone(input.RequiredFeatures)
	result.AccountFeatures = slices.Clone(input.AccountFeatures)
	result.WorkflowStatePredicateFeatures = slices.Clone(input.WorkflowStatePredicateFeatures)
	if input.Topology != nil {
		topology := *input.Topology
		topology.ControllerAddresses = slices.Clone(input.Topology.ControllerAddresses)
		topology.ProfileBinding = copyTransport(input.Topology.ProfileBinding)
		result.Topology = &topology
	}
	if input.Artifact != nil {
		artifact := *input.Artifact
		artifact.DeliveryModes = slices.Clone(input.Artifact.DeliveryModes)
		artifact.OutputNames = slices.Clone(input.Artifact.OutputNames)
		artifact.Consumers = slices.Clone(input.Artifact.Consumers)
		artifact.GeneratorBinding = copyTransport(input.Artifact.GeneratorBinding)
		result.Artifact = &artifact
	}
	if input.ServiceMaterialization != nil {
		service := *input.ServiceMaterialization
		service.ReadbackAssertionAddresses = slices.Clone(service.ReadbackAssertionAddresses)
		service.EvidenceRequirementRefs = slices.Clone(service.EvidenceRequirementRefs)
		service.ObservationBoundaryAddresses = slices.Clone(service.ObservationBoundaryAddresses)
		service.FieldSemantics = maps.Clone(service.FieldSemantics)
		service.ProfileBinding = copyTransport(service.ProfileBinding)
		result.ServiceMaterialization = &service
	}
	if input.Node != nil {
		node := *input.Node
		if node.Count != nil {
			count := *node.Count
			node.Count = &count
		}
		result.Node = &node
	}
	if input.Evaluation != nil {
		evaluation := *input.Evaluation
		evaluation.EvidenceChannels = slices.Clone(evaluation.EvidenceChannels)
		evaluation.UnresolvedEvidenceChannelRefs = slices.Clone(evaluation.UnresolvedEvidenceChannelRefs)
		result.Evaluation = &evaluation
	}
	return result
}
func copyCompiledScenario(input CompiledScenario) CompiledScenario {
	result := input
	result.Resources = slices.Clone(input.Resources)
	for i := range result.Resources {
		result.Resources[i] = copyResource(input.Resources[i])
	}
	result.Definitions = slices.Clone(input.Definitions)
	result.ParticipantResources = slices.Clone(input.ParticipantResources)
	for i := range result.ParticipantResources {
		result.ParticipantResources[i] = copyResource(input.ParticipantResources[i])
	}
	result.Diagnostics = copyDiagnostics(input.Diagnostics)
	result.TimeModel = copyTimeModel(input.TimeModel)
	result.CapabilityConstraints = slices.Clone(input.CapabilityConstraints)
	for i := range result.CapabilityConstraints {
		result.CapabilityConstraints[i].Parameter = slices.Clone(input.CapabilityConstraints[i].Parameter)
		result.CapabilityConstraints[i].AllowedValues = slices.Clone(input.CapabilityConstraints[i].AllowedValues)
	}
	result.RealizationRequirements = slices.Clone(input.RealizationRequirements)
	for i := range result.RealizationRequirements {
		requirement := &result.RealizationRequirements[i]
		if requirement.Posture != nil {
			posture := *requirement.Posture
			requirement.Posture = &posture
		}
		requirement.ValueConstraints = slices.Clone(requirement.ValueConstraints)
		for j := range requirement.ValueConstraints {
			requirement.ValueConstraints[j].Parameter = slices.Clone(requirement.ValueConstraints[j].Parameter)
		}
		requirement.ProcessResourceLimits = slices.Clone(requirement.ProcessResourceLimits)
		if requirement.ArtifactRequirement != nil {
			requirement.ArtifactRequirement = copyTransport(requirement.ArtifactRequirement)
		}
	}
	result.RealizationAuthority = slices.Clone(input.RealizationAuthority)
	for i := range result.RealizationAuthority {
		result.RealizationAuthority[i].PayloadPath = slices.Clone(input.RealizationAuthority[i].PayloadPath)
	}
	result.DescriptorProfiles = copyTransport(input.DescriptorProfiles)
	result.ProfileAuthority = copyTransport(input.ProfileAuthority)
	result.ObservationDemands = slices.Clone(input.ObservationDemands)
	result.CaptureDemands = slices.Clone(input.CaptureDemands)
	for i := range result.CaptureDemands {
		demand := &result.CaptureDemands[i]
		demand.FieldSelectors = slices.Clone(demand.FieldSelectors)
		demand.ArtifactRoles = slices.Clone(demand.ArtifactRoles)
		demand.MediaTypes = slices.Clone(demand.MediaTypes)
		demand.SourceClasses = slices.Clone(demand.SourceClasses)
		demand.SourceRefs = slices.Clone(demand.SourceRefs)
		demand.Scopes = slices.Clone(demand.Scopes)
		demand.ScopeRefs = slices.Clone(demand.ScopeRefs)
		demand.ChannelKinds = slices.Clone(demand.ChannelKinds)
		demand.ChannelRefs = slices.Clone(demand.ChannelRefs)
		demand.WindowKinds = slices.Clone(demand.WindowKinds)
		demand.IntegrityModes = slices.Clone(demand.IntegrityModes)
		demand.RetentionPolicyRefs = slices.Clone(demand.RetentionPolicyRefs)
		if demand.RedactionPolicy != nil {
			value := *demand.RedactionPolicy
			demand.RedactionPolicy = &value
		}
	}
	result.ExecutionPolicies = slices.Clone(input.ExecutionPolicies)
	return result
}

// copyTransport only receives already admitted, owner-held transport values.
//
//nolint:ireturn // Each generated instantiation returns its concrete transport type without a runtime interface.
func copyTransport[T any](input T) T {
	raw, err := json.Marshal(input)
	if err != nil {
		panic("processor: invalid owned transport")
	}
	var result T
	if err := json.Unmarshal(raw, &result); err != nil {
		panic("processor: invalid owned transport projection")
	}
	return result
}
func copyTimeModel(input CompiledTimeModel) CompiledTimeModel {
	result := input
	result.Domains = slices.Clone(input.Domains)
	result.Clocks = slices.Clone(input.Clocks)
	result.Mappings = slices.Clone(input.Mappings)
	result.ProgressionPolicies = slices.Clone(input.ProgressionPolicies)
	copyNumber := func(input *json.Number) *json.Number {
		if input == nil {
			return nil
		}
		result := *input
		return &result
	}
	for i := range result.ProgressionPolicies {
		p := &result.ProgressionPolicies[i]
		p.StepTicks = copyNumber(p.StepTicks)
		p.DriftBoundTicks = copyNumber(p.DriftBoundTicks)
	}
	result.Constraints = slices.Clone(input.Constraints)
	for i := range result.Constraints {
		c := &result.Constraints[i]
		c.SubjectAddresses = slices.Clone(c.SubjectAddresses)
		c.StartTick = copyNumber(c.StartTick)
		c.StartMicrostep = copyNumber(c.StartMicrostep)
		c.EndTick = copyNumber(c.EndTick)
		c.EndMicrostep = copyNumber(c.EndMicrostep)
		c.DurationTicks = copyNumber(c.DurationTicks)
		c.CadenceTicks = copyNumber(c.CadenceTicks)
	}
	return result
}

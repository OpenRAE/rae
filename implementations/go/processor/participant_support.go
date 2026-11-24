package processor

import (
	"encoding/json"
	"math/big"
	"slices"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

// ParticipantSupportDiagnostics separates tool, execution, and mixed-control support gaps.
type ParticipantSupportDiagnostics struct{ Tools, Execution, MixedControl []diagnostic.Diagnostic }
type participantToolFeatureSupport struct {
	Feature      string `json:"feature"`
	SupportLevel string `json:"support_level"`
}
type participantToolProfiles struct {
	SemanticVersions []string                        `json:"semantic_versions"`
	MaxBindings      *json.Number                    `json:"max_bindings_per_profile"`
	MaxParticipants  *json.Number                    `json:"max_participants_per_binding"`
	FeatureSupport   []participantToolFeatureSupport `json:"feature_support"`
}
type participantRuntimeCapability struct {
	autonomousCapabilities

	Roles              []string                 `json:"supported_participant_roles"`
	ToolProfiles       *participantToolProfiles `json:"tool_profiles"`
	SupportsAutonomous bool                     `json:"supports_autonomous_execution"`
}

var processorAdmissionOwner = sync.OnceValues(admission.New) //nolint:gochecknoglobals // Immutable contract validator.

func checkSupportTransport(owner *admission.Validator, id string, transport any) error {
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
	if err := admission.CheckTransport(transport, limits); err != nil {
		return err
	}
	raw, err := json.Marshal(transport)
	if err != nil {
		return invalidCompiled()
	}
	return owner.CheckPortable(id, raw, limits)
}

// ParticipantSupport reads only retained typed facts from an exact native model.
// Its diagnostics describe declared support and grant no execution authority.
func ParticipantSupport(input RuntimeModel, manifest binding.BackendManifestV2, processorManifest *binding.ProcessorManifestV2) (ParticipantSupportDiagnostics, error) {
	model, owner, capability, err := participantSupportInputs(input, manifest, processorManifest)
	if err != nil {
		return ParticipantSupportDiagnostics{}, err
	}
	result := ParticipantSupportDiagnostics{Tools: []diagnostic.Diagnostic{}, Execution: []diagnostic.Diagnostic{}, MixedControl: []diagnostic.Diagnostic{}}
	if len(model.participants.tools) > 0 {
		result.Tools, err = participantToolDiagnostics(model, manifest, processorManifest, capability, owner)
		if err != nil {
			return ParticipantSupportDiagnostics{}, err
		}
	}
	policies, mixed := model.participantPolicies()
	execution, err := autonomousSupportDiagnostics(model, manifest, capability, policies)
	if err != nil {
		return ParticipantSupportDiagnostics{}, err
	}
	result.Execution = append(result.Execution, execution...)
	features, err := model.participantFeatureDiagnostics(manifest, owner)
	if err != nil {
		return ParticipantSupportDiagnostics{}, err
	}
	result.Execution = append(result.Execution, features...)
	slices.Sort(mixed)
	mixed = slices.Compact(mixed)
	for _, address := range mixed {
		result.MixedControl = append(result.MixedControl, compileDiagnostic("participant.mixed-control-semantics-unsupported", termParticipant, address, "Reusable mixed-control planning requires an explicit matching installed-owner admission."))
	}
	return result, nil
}

func participantSupportInputs(input RuntimeModel, manifest binding.BackendManifestV2, processorManifest *binding.ProcessorManifestV2) (*runtimeModel, *admission.Validator, *participantRuntimeCapability, error) {
	model, err := nativeRuntimeModel(input)
	if err != nil {
		return nil, nil, nil, err
	}
	owner, err := processorAdmissionOwner()
	if err != nil {
		return nil, nil, nil, err
	}
	if checkErr := checkSupportTransport(owner, "backend-manifest-v2", manifest); checkErr != nil {
		return nil, nil, nil, checkErr
	}
	if processorManifest != nil {
		if checkErr := checkSupportTransport(owner, "processor-manifest-v2", processorManifest); checkErr != nil {
			return nil, nil, nil, checkErr
		}
	}
	component := fieldValue(fieldValue(manifest.Capabilities).ParticipantRuntime)
	var capability *participantRuntimeCapability
	if len(component) > 0 && json.Unmarshal(component, &capability) != nil {
		return nil, nil, nil, invalidCompiled()
	}
	return model, owner, capability, nil
}

func (model *runtimeModel) participantPolicies() ([]*participantAutonomous, []string) {
	policies := []*participantAutonomous{}
	mixed := []string{}
	for _, resource := range model.view.ParticipantResources {
		if specification, exists := model.participants.specifications[resource.Address]; exists {
			if specification.AutonomousExecution != nil {
				policies = append(policies, specification.AutonomousExecution)
			}
			if specification.MixedControlSemantics == "mixed-control-policy-occurrence/rev1" {
				mixed = append(mixed, resource.Address)
			}
		}
		if delivery, exists := model.participants.deliveries[resource.Address]; exists && delivery.Control != nil && delivery.Control.Semantics == "mixed-control-policy-occurrence/rev1" {
			mixed = append(mixed, resource.Address)
		}
	}
	return policies, mixed
}

func autonomousSupportDiagnostics(model *runtimeModel, manifest binding.BackendManifestV2, capability *participantRuntimeCapability, policies []*participantAutonomous) ([]diagnostic.Diagnostic, error) {
	result := []diagnostic.Diagnostic{}
	if len(policies) == 0 {
		return result, nil
	}
	gaps, err := autonomousCapabilityGaps(model, manifest, capability, policies)
	if err != nil {
		return nil, err
	}
	for _, gap := range gaps {
		result = append(result, compileDiagnostic("participant.autonomous-execution-unsupported", termParticipant, "participant.autonomous-execution", gap))
	}
	return result, nil
}

func (model *runtimeModel) participantFeatureDiagnostics(manifest binding.BackendManifestV2, owner *admission.Validator) ([]diagnostic.Diagnostic, error) {
	result := []diagnostic.Diagnostic{}
	for _, resource := range model.view.ParticipantResources {
		if specification, exists := model.participants.specifications[resource.Address]; exists {
			gaps, err := admission.ParticipantFeatureSupportGaps(owner, manifest, specification.BackendFeatureSupportRefs, termExact)
			if err != nil {
				return nil, err
			}
			for _, gap := range gaps {
				result = append(result, compileDiagnostic("participant.feature-support-insufficient", termParticipant, resource.Address, gap))
			}
		}
	}
	return result, nil
}

func participantToolCapacity(model *runtimeModel, profiles *participantToolProfiles) bool {
	if profiles == nil {
		return false
	}
	counts := map[string]int{}
	for _, tool := range model.participants.tools {
		counts[tool.BehaviorSpecificationAddress]++
		if exceedsCount(len(tool.ParticipantAddresses), profiles.MaxParticipants) {
			return false
		}
	}
	for _, count := range counts {
		if exceedsCount(count, profiles.MaxBindings) {
			return false
		}
	}
	return true
}
func exceedsCount(count int, maximum *json.Number) bool {
	if maximum == nil {
		return false
	}
	return big.NewInt(int64(count)).Cmp(exactInteger(*maximum)) > 0
}

type participantToolDemand struct{ tools, features, roles []string }

func participantToolDiagnostics(model *runtimeModel, manifest binding.BackendManifestV2, processorManifest *binding.ProcessorManifestV2, capability *participantRuntimeCapability, owner *admission.Validator) ([]diagnostic.Diagnostic, error) {
	demand := model.participantToolDemand()
	result := []diagnostic.Diagnostic{}
	processorSupported, err := model.processorToolSupport(processorManifest, demand.tools)
	if err != nil {
		return nil, err
	}
	if !processorSupported {
		result = append(result, compileDiagnostic("processor.tool-support-insufficient", termParticipant, "participant.tool-profiles", "Selected processor lacks required tool-profile semantics, strength, or capacity."))
	}
	backendSupported, err := model.backendToolSupport(manifest, capability, owner, demand)
	if err != nil {
		return nil, err
	}
	if !backendSupported {
		result = append(result, compileDiagnostic("participant.tool-support-insufficient", termParticipant, "participant.tool-profiles", "Selected backend lacks required tool-profile semantics, strength, contracts, or capacity."))
	}
	return result, nil
}

func (model *runtimeModel) participantToolDemand() participantToolDemand {
	demand := participantToolDemand{tools: []string{termToolAffordances}, features: []string{termActionContracts, termObservationBoundaries}}
	for _, resource := range model.view.ParticipantResources {
		tool, exists := model.participants.tools[resource.Address]
		if !exists {
			continue
		}
		if len(tool.ParticipantRefs) > 0 || len(tool.ParticipantRoleRefs) > 0 {
			demand.tools = append(demand.tools, "scoped_tool_affordances")
		}
		demand.roles = append(demand.roles, model.participantToolRoles(tool)...)
		for _, address := range tool.ActionContractAddresses {
			demand.features = append(demand.features, participantToolActionFeatures(model.participants.actions[address])...)
		}
	}
	return demand
}

func (model *runtimeModel) participantToolRoles(tool participantTool) []string {
	roles := []string{}
	for _, address := range tool.ParticipantAddresses {
		if role := model.participants.behaviors[address].Role; role != "" {
			roles = append(roles, role)
		}
	}
	return roles
}

func participantToolActionFeatures(action participantAction) []string {
	features := []string{}
	for _, field := range []struct {
		feature string
		used    bool
	}{
		{"preconditions", len(action.PreconditionClasses) > 0},
		{"effects", len(action.EffectClasses) > 0},
		{"failure_classes", len(action.FailureClasses) > 0},
		{"temporal_contracts", len(action.TemporalContractIDs) > 0},
	} {
		if field.used {
			features = append(features, field.feature)
		}
	}
	return append(features, action.InteractionClasses...)
}

func (model *runtimeModel) processorToolSupport(processorManifest *binding.ProcessorManifestV2, tools []string) (bool, error) {
	var selected binding.ProcessorManifestV2
	if processorManifest == nil {
		var err error
		selected, err = Manifest("native", nil)
		if err != nil {
			return false, err
		}
	} else {
		selected = *processorManifest
	}
	caps := fieldValue(selected.Capabilities)
	var profiles *participantToolProfiles
	raw := fieldValue(caps.ParticipantTools)
	if len(raw) > 0 && json.Unmarshal(raw, &profiles) != nil {
		return false, invalidCompiled()
	}
	supported := profiles != nil && participantToolCapacity(model, profiles) && slices.Contains(profiles.SemanticVersions, "participant-tool-profile/v1") && slices.Contains(fieldValue(caps.SupportedSdlVersions), "sdl-authoring-input-v1")
	compilation, planning := false, false
	for _, feature := range fieldValue(caps.SupportedFeatures) {
		compilation = compilation || string(feature) == "compilation"
		planning = planning || string(feature) == "planning"
	}
	return supported && compilation && planning && processorToolFeaturesSupported(profiles, tools), nil
}

func processorToolFeaturesSupported(profiles *participantToolProfiles, tools []string) bool {
	for _, feature := range tools {
		supported := slices.ContainsFunc(profiles.FeatureSupport, func(entry participantToolFeatureSupport) bool {
			return entry.Feature == feature && (entry.SupportLevel == "bounded" || entry.SupportLevel == termExact)
		})
		if !supported {
			return false
		}
	}
	return true
}

func (model *runtimeModel) backendToolSupport(manifest binding.BackendManifestV2, capability *participantRuntimeCapability, owner *admission.Validator, demand participantToolDemand) (bool, error) {
	if capability == nil || capability.ToolProfiles == nil {
		return false, nil
	}
	supported := participantToolCapacity(model, capability.ToolProfiles) && slices.Contains(capability.ToolProfiles.SemanticVersions, "participant-tool-profile/v1")
	for _, role := range demand.roles {
		if !slices.Contains(capability.Roles, role) {
			supported = false
		}
	}
	toolGaps, err := admission.ParticipantFeatureSupportGaps(owner, manifest, demand.tools, "bounded")
	if err != nil {
		return false, err
	}
	featureGaps, err := admission.ParticipantFeatureSupportGaps(owner, manifest, demand.features, termExact)
	if err != nil {
		return false, err
	}
	return supported && len(toolGaps) == 0 && len(featureGaps) == 0, nil
}

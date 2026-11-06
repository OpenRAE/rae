package admission

import (
	"bytes"
	"encoding/json"
	"maps"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// Fragment is an admitted native submodel, not a published document Value.
// Profile identifies the exact existing owner model; Document returns a copy.
type Fragment interface {
	Profile() FragmentProfile
	Document() any
	admittedFragment()
}

// FragmentProfile names the existing owner model of a native fragment.
type FragmentProfile string

// The closed fragment profiles. The owner model of each profile is recorded
// in the concept and profile design for issue #1781.
const (
	TrialInputRefs                     FragmentProfile = "trial-input-refs"
	TrialApparatus                     FragmentProfile = "trial-apparatus"
	TrialExecutionAuthority            FragmentProfile = "trial-execution-authority"
	AdmittedMixedCompositionBinding    FragmentProfile = "admitted-mixed-composition-binding"
	RealizationRequirement             FragmentProfile = "realization-requirement"
	RealizationDesignation             FragmentProfile = "realization-designation"
	RealizationConcern                 FragmentProfile = "realization-concern"
	RealizationValue                   FragmentProfile = "realization-value"
	RealizationSupport                 FragmentProfile = "realization-support"
	RealizationConstraint              FragmentProfile = "realization-constraint"
	RealizationConstraintEvaluation    FragmentProfile = "realization-constraint-evaluation"
	RealizationStructure               FragmentProfile = "realization-structure"
	ValidatedActionSelection           FragmentProfile = "validated-action-selection"
	ParticipantImplementationSelection FragmentProfile = "participant-implementation-selection"
	ParticipantActionResult            FragmentProfile = "participant-action-result"
	ParticipantTemporalContext         FragmentProfile = "participant-temporal-context"
	ParticipantResourceMeasurement     FragmentProfile = "participant-resource-measurement"
	ParticipantTemporalEvidence        FragmentProfile = "participant-temporal-evidence"
	ParticipantExecutionState          FragmentProfile = "participant-execution-state"
	OperationExecutionPolicy           FragmentProfile = "operation-execution-policy"
	OperationPolicyScope               FragmentProfile = "operation-policy-scope"
	StochasticControl                  FragmentProfile = "stochastic-control"
	ParticipantControlRequest          FragmentProfile = "participant-control-request"
	ParticipantControlResult           FragmentProfile = "participant-control-result"
	ParticipantControlInvocation       FragmentProfile = "participant-control-invocation"
	ParticipantControlStageResult      FragmentProfile = "participant-control-stage-result"
	ParticipantControlSupport          FragmentProfile = "participant-control-support"
	ControlArtifactReference           FragmentProfile = "control-artifact-reference"
	ParticipantControlPolicy           FragmentProfile = "participant-control-policy"
	ParticipantControlIntent           FragmentProfile = "participant-control-intent"
	ParticipantControlDeclaration      FragmentProfile = "participant-control-declaration"
	ParticipantInjectDelivery          FragmentProfile = "participant-inject-delivery"
	ParticipantInjectContent           FragmentProfile = "participant-inject-content"
	ParticipantCrossingEvidence        FragmentProfile = "participant-crossing-evidence"
	CompiledRealizationRequirement     FragmentProfile = "compiled-realization-requirement"
	CrossingSubject                    FragmentProfile = "crossing-subject"
	CrossingPolicy                     FragmentProfile = "crossing-policy"
	OpacityEnforcement                 FragmentProfile = "opacity-enforcement"
	OpacitySupport                     FragmentProfile = "opacity-support"
	ControlRealizationBinding          FragmentProfile = "control-realization-binding"
	TrialProcessorPlanReference        FragmentProfile = "trial-processor-plan-reference"
	CleanupObligationResult            FragmentProfile = "cleanup-obligation-result"
	TrialExecutionControls             FragmentProfile = "trial-execution-controls"
)

// fragment keeps the canonical bytes of an admitted native document.
type fragment struct {
	profile FragmentProfile
	data    []byte
}

func (f fragment) Profile() FragmentProfile { return f.profile }

// Document returns a fresh copy with exact JSON numbers.
func (f fragment) Document() any {
	decoder := json.NewDecoder(bytes.NewReader(f.data))
	decoder.UseNumber()
	var document any
	if decoder.Decode(&document) != nil {
		panic("admission: an admitted fragment holds invalid JSON")
	}
	return document
}

func (fragment) admittedFragment() {}

func fragmentInvalid() error { return fault.New(fault.InvalidInput, "fragment-invalid", nil) }

// AdmitFragment copies and bounds a native document, checks the native shape
// and local rules of the profile and returns an opaque fragment. A fragment
// grants no execution authority. An unknown profile, an unsupported carrier,
// a value outside the limits or a failed owner rule is an InvalidInput fault.
func AdmitFragment(v *Validator, profile FragmentProfile, document any, limits ingress.Limits) (Fragment, error) { //nolint:ireturn // The planned interface keeps each admitted fragment opaque and sealed.
	check, known := fragmentChecks()[profile]
	if v == nil || !known {
		return nil, fragmentInvalid()
	}
	data, err := value.Encode(document, value.Runtime())
	if err != nil {
		return nil, fragmentInvalid()
	}
	if err := boundedDocument(profile, data, limits); err != nil {
		return nil, fragmentInvalid()
	}
	if err := check(v, data, limits); err != nil {
		return nil, fragmentInvalid()
	}
	return fragment{profile: profile, data: data}, nil
}

// boundedDocument applies the caller's byte and depth limits. Only a
// realization value may have a root other than an object.
func boundedDocument(profile FragmentProfile, data []byte, limits ingress.Limits) error {
	if profile != RealizationValue {
		_, err := ingress.Parse(data, limits, ingress.Object)
		return err
	}
	return boundedRoot(data, limits)
}

// boundedRoot applies the byte and depth limits to a document of any JSON
// root, by wrapping it in an array.
func boundedRoot(data []byte, limits ingress.Limits) error {
	wrapped := limits
	wrapped.MaxBytes += 2
	if wrapped.MaxDepth > 0 {
		wrapped.MaxDepth++
	}
	if len(data) > limits.MaxBytes {
		return fragmentInvalid()
	}
	_, err := ingress.Parse(append(append([]byte{'['}, data...), ']'), wrapped, ingress.Array)
	return err
}

type fragmentCheck func(v *Validator, data []byte, limits ingress.Limits) error

// publishedModel checks the document against one or more published definitions.
// The document must satisfy at least one of them.
func publishedModel(locations ...[2]string) fragmentCheck {
	return func(v *Validator, data []byte, limits ingress.Limits) error {
		for _, location := range locations {
			if v.checkModelFragment(location[0], location[1], data, limits) == nil {
				return nil
			}
		}
		return fragmentInvalid()
	}
}

// checkModelFragment applies a published definition, its local invariants
// and the admission model rules at each of its instances.
func (e *Validator) checkModelFragment(contract, pointer string, data []byte, limits ingress.Limits) error {
	var normalized any
	return e.low.CheckLocalFragment(contract, pointer, data, limits, func(instance validation.SchemaInstance) error {
		if instance.Discriminator != "" {
			if _, present := object(instance.Value)[instance.Discriminator]; !present && !legacyServiceProfileDefault(instance) {
				return invalid()
			}
		}
		instance, err := e.fragmentDefaultInstance(instance, pointer, data, limits, &normalized)
		if err != nil {
			return err
		}
		return e.instanceModel(instance)
	})
}

// fragmentDefaultInstance gives the control and flow model rules the
// defaulted view of their instance, as the contract-level walk does. The
// view is relative to the fragment root.
func (e *Validator) fragmentDefaultInstance(instance validation.SchemaInstance, pointer string, data []byte, limits ingress.Limits, normalized *any) (validation.SchemaInstance, error) {
	name := strings.TrimPrefix(instance.SchemaPointer, schemaDefinitionsPrefix)
	if !controlNeedsDefaults(name) && !flowNeedsDefaults(instance) {
		return instance, nil
	}
	if *normalized == nil {
		defaulted, err := e.low.DefaultedObjectFragment(instance.ContractID, pointer, data, limits)
		if err != nil {
			return instance, err
		}
		*normalized = defaulted
	}
	value, present := pointerAt(*normalized, instance.Path)
	if !present {
		return instance, invalid()
	}
	instance.Value = value
	return instance, nil
}

func def(contract, name string) [2]string {
	return [2]string{contract, schemaDefinitionsPrefix + name}
}

// fragmentChecks returns the check of each profile.
func fragmentChecks() map[FragmentProfile]fragmentCheck {
	const (
		trialPlan  = "admitted-trial-plan-v1"
		history    = "participant-behavior-history-event-stream-v1"
		controlV1  = "participant-control-evaluation-v1"
		controlV2  = "participant-control-evaluation-v2"
		crossing   = "participant-crossing-occurrence-v1"
		plan       = "provisioning-plan-v1"
		experiment = "experiment-run-v1"
	)
	checks := map[FragmentProfile]fragmentCheck{
		TrialInputRefs:                     publishedModel(def(trialPlan, "AdmittedTrialPlanInputRefsModel")),
		TrialApparatus:                     publishedModel(def(trialPlan, "AdmittedApparatusBindingModel")),
		AdmittedMixedCompositionBinding:    publishedModel(def(trialPlan, "AdmittedMixedCompositionBindingModel")),
		TrialExecutionControls:             publishedModel(def(trialPlan, "AdmittedExecutionControlModel")),
		RealizationRequirement:             publishedModel(def(plan, "ResolvedRealizationAuthorityModel")),
		RealizationSupport:                 publishedModel(def(termBackendManifestV2, "RealizationSupportDeclarationModel")),
		RealizationConstraint:              publishedModel(def("plan-realization-profiles-v1", "RealizationConstraintDocument")),
		ParticipantImplementationSelection: publishedModel(def(experiment, "ParticipantImplementationSelectionModel")),
		ParticipantActionResult:            publishedModel(def(history, "ParticipantActionResultModel")),
		ParticipantTemporalContext:         publishedModel(def(history, "ParticipantTemporalRuntimeContextModel")),
		ParticipantTemporalEvidence:        publishedModel(def(history, "ParticipantTemporalEvidenceModel")),
		ParticipantExecutionState:          publishedModel(def(termRuntimeSnapshotV1, "ParticipantAutonomousExecutionStateModel")),
		OperationExecutionPolicy:           publishedModel(def(plan, "EffectiveExecutionPolicy")),
		OperationPolicyScope:               publishedModel(def(plan, "EffectiveExecutionPolicy")),
		StochasticControl:                  publishedModel(def("experiment-apparatus-context-v1", "ExperimentStochasticControlModel")),
		ParticipantControlRequest:          publishedModel(def(controlV1, "ParticipantControlRequestModel"), def(controlV2, "ParticipantControlRequestV2Model")),
		ParticipantControlResult:           publishedModel(def(controlV1, "ControlMechanismResultModel")),
		ParticipantControlInvocation:       publishedModel(def(controlV2, "ControlInvocationV2Model")),
		ParticipantControlStageResult:      publishedModel(def(controlV2, "ControlMechanismResultV2Model")),
		ParticipantControlSupport:          publishedModel(def(controlV1, "ControlEffectiveSupportModel"), def(controlV2, "ControlSupportAssessmentV2Model")),
		ControlArtifactReference:           publishedModel(def(controlV1, "ControlArtifactReferenceModel")),
		ParticipantInjectContent:           publishedModel(def("participant-inject-delivery-receipt-v1", "ParticipantInjectContentModel")),
		CrossingSubject:                    publishedModel(def(crossing, "ParticipantCrossingSubjectReferenceModel")),
		CrossingPolicy:                     publishedModel(def(crossing, "ParticipantCrossingPolicyReferenceModel")),
		OpacityEnforcement:                 publishedModel(def(crossing, "ParticipantOpacityRuntimeEnforcementBindingModel")),
		ControlRealizationBinding:          publishedModel(def(controlV1, "ControlRealizationBindingModel")),
		TrialProcessorPlanReference:        publishedModel(def(experiment, "TrialProcessorPlanReferenceModel")),
		CleanupObligationResult:            publishedModel(def("trial-cleanup-receipt-v1", "CleanupObligationResultModel")),
	}
	maps.Copy(checks, portChecks())
	return checks
}

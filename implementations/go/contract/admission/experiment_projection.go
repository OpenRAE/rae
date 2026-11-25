package admission

import (
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// ExperimentProjection applies native model defaults and serializer omissions.
// Its bytes grant no new contextual, scientific, or execution authority.
func ExperimentProjection(v *Validator, document validation.Value) ([]byte, error) {
	id := document.ContractID()
	if v == nil || !strings.HasPrefix(id, "experiment-") || experimentRootModel(id) == "" {
		return nil, invalid()
	}
	return v.experimentProjection(id, document.JSON())
}

func (e *Validator) experimentProjection(id string, data []byte) ([]byte, error) {
	limits := ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}
	projection, data, err := e.experimentConstructed(id, data, limits)
	if err != nil {
		return nil, err
	}
	if checkErr := e.low.CheckLocal(id, data, limits); checkErr != nil {
		return nil, checkErr
	}
	if checkErr := e.checkModels(id, data, limits); checkErr != nil {
		return nil, checkErr
	}
	if checkErr := e.experimentModelWalk(id, data, projection, limits, func(model string, root map[string]any) error { experimentConstructorOmissions(model, root); return nil }); checkErr != nil {
		return nil, checkErr
	}
	raw, err := json.Marshal(projection)
	if err != nil || len(raw) > limits.MaxBytes {
		return nil, invalid()
	}
	return raw, nil
}

func (e *Validator) experimentConstructed(id string, data []byte, limits ingress.Limits) (any, []byte, error) {
	initial, err := ingress.Parse(data, limits, ingress.Object)
	if err != nil {
		return nil, nil, err
	}
	addExperimentFactories(experimentRootModel(id), object(initial))
	data, err = json.Marshal(initial)
	if err != nil || len(data) > limits.MaxBytes {
		return nil, nil, invalid()
	}
	projection, err := e.low.Defaulted(id, data, limits)
	if err != nil {
		return nil, nil, err
	}
	if checkErr := e.experimentConstructorDefaults(id, data, projection, limits); checkErr != nil {
		return nil, nil, checkErr
	}
	data, err = json.Marshal(projection)
	if err != nil {
		return nil, nil, invalid()
	}
	data, err = e.prepare(id, data, limits)
	if err != nil {
		return nil, nil, err
	}
	projection, err = e.low.Defaulted(id, data, limits)
	if err != nil {
		return nil, nil, err
	}
	if checkErr := e.experimentConstructorDefaults(id, data, projection, limits); checkErr != nil {
		return nil, nil, checkErr
	}
	data, err = json.Marshal(projection)
	if err != nil || len(data) > limits.MaxBytes {
		return nil, nil, invalid()
	}
	return projection, data, nil
}

func (e *Validator) experimentConstructorDefaults(id string, data []byte, projection any, limits ingress.Limits) error {
	return e.experimentModelWalk(id, data, projection, limits, func(model string, root map[string]any) error {
		for field, initial := range experimentFactoryValues(model) {
			if _, present := root[field]; !present {
				root[field] = initial
			}
		}
		return nil
	})
}

func (e *Validator) experimentModelWalk(id string, data []byte, projection any, limits ingress.Limits, apply func(string, map[string]any) error) error {
	return e.low.CheckInstances(id, data, limits, func(instance validation.SchemaInstance) error {
		model := strings.TrimPrefix(instance.SchemaPointer, schemaDefinitionsPrefix)
		if instance.SchemaPointer == "#" {
			model = experimentRootModel(id)
		}
		selected, present := pointerAt(projection, instance.Path)
		if !present {
			return nil
		}
		root := object(selected)
		if root == nil {
			return nil
		}
		return apply(model, root)
	})
}

func experimentConstructorOmissions(model string, document map[string]any) {
	switch model {
	case termBackendManifestV2Model:
		omitExperimentNull(document, "configuration_registry", "execution_policy", "domain_profile_context_digest")
	case termProcessorManifestV2Model, termParticipantImplementationManifestModel:
		omitExperimentNull(document, "configuration_registry")
	case "ProcessorCapabilitiesV2Model":
		omitExperimentNull(document, "participant_tools")
	case "BackendCapabilitiesV2Model":
		omitExperimentNull(document, "operation_supervision", "recovery_observation")
	case termParticipantRuntimeCapabilitiesModel:
		omitExperimentNull(document, "tool_profiles", "invocation_tool_actions")
	case "ParticipantExecutionBindingModel":
		omitExperimentEmpty(document, "temporal_contract_digests")

	case modelExperimentSpec:
		omitExperimentNull(document, "factorial_design")
	case modelExperimentRunPlan:
		omitExperimentNull(document, "replacement_policy", "allocation_policy")
	case termExperimentConditionAssignmentModel:
		omitExperimentEmpty(document, "required_bindings", "required_selections")
	case termConfigurationTargetDeclarationModel:
		omitExperimentNull(document, "default", "control_context")
	case "RealizedConfigurationValueModel":
		omitExperimentNull(document, "control_context_selection")
	case modelExperimentRun:
		if stringAt(document, "record_state") == experimentTermArchival {
			delete(document, "record_state")
		}
		omitExperimentNull(document, "execution_accounting")
		omitExperimentEmpty(document, "realized_selections")
	case modelExperimentStudy:
		omitExperimentNull(document, "definition_ref")
	case modelAdmittedTrialEntry, modelTrialInputRefs, "AdmittedTrialPlanProfilesModel", modelTrialApparatus, modelTrialMixedApparatus, "AdmittedSelectionRecordModel", modelAdmittedTrialPlan:
		trialModelProjection(document)
	}
}

func omitExperimentNull(document map[string]any, fields ...string) {
	for _, field := range fields {
		if document[field] == nil {
			delete(document, field)
		}
	}
}

func omitExperimentEmpty(document map[string]any, fields ...string) {
	for _, field := range fields {
		if len(array(document[field])) == 0 {
			delete(document, field)
		}
	}
}

// ExperimentModelProjection checks local model rules and applies constructor defaults.
// The returned bytes grant no task, evidence, or execution authority.
func ExperimentModelProjection(v *Validator, contractID string, data []byte) ([]byte, error) {
	if v == nil || experimentRootModel(contractID) == "" || !experimentLocalModelID(contractID) {
		return nil, invalid()
	}
	return v.experimentProjection(contractID, data)
}

func experimentLocalModelID(id string) bool {
	return strings.HasPrefix(id, "experiment-") || id == termParticipantConfigurationResultV1 || id == "trial-cleanup-plan-v1" || id == termTrialCleanupReceiptV1 || id == contractWorkflowStepDispatch
}

// ManifestModelProjection reconstructs local manifest defaults without reordering claims.
// It grants no contextual or execution authority.
func ManifestModelProjection(v *Validator, contractID string, data []byte) ([]byte, error) {
	if v == nil {
		return nil, invalid()
	}
	switch contractID {
	case "backend-manifest-v2", "processor-manifest-v2", "participant-implementation-manifest-v1":
		return v.experimentProjection(contractID, data)
	default:
		return nil, invalid()
	}
}

// WorkflowStepDispatchDigest returns the commitment of one admitted workflow
// step dispatch: the digest of its complete model with constructor defaults.
func WorkflowStepDispatchDigest(v *Validator, data []byte) (string, error) {
	if v == nil {
		return "", invalid()
	}
	projected, err := v.experimentProjection(contractWorkflowStepDispatch, data)
	if err != nil {
		return "", err
	}
	var document any
	if err = decodeExact(projected, &document); err != nil {
		return "", invalid()
	}
	return jsonDigest(document)
}

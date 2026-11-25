package admission

import (
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) trialFragmentProjection(profile FragmentProfile, data []byte, limits ingress.Limits) ([]byte, error) {
	if profile == TrialExecutionAuthority {
		return e.trialAuthorityProjection(data, limits)
	}
	contractID := trialPlanContract
	if profile == TrialProcessorPlanReference {
		contractID = termExperimentRunV1
	}
	if profile == CleanupObligationResult {
		contractID = termTrialCleanupReceiptV1
	}
	model, selected := map[FragmentProfile]string{CleanupObligationResult: termCleanupObligationResultModel, TrialProcessorPlanReference: "TrialProcessorPlanReferenceModel", TrialExecutionControls: "AdmittedExecutionControlModel", TrialInputRefs: modelTrialInputRefs, TrialApparatus: modelTrialApparatus, AdmittedMixedCompositionBinding: modelTrialMixedApparatus}[profile]
	if !selected {
		return data, nil
	}
	pointer := schemaDefinitionsPrefix + model
	root, err := e.low.DefaultedObjectFragment(contractID, pointer, data, limits)
	if err != nil {
		return nil, err
	}
	err = e.low.CheckLocalFragment(contractID, pointer, data, limits, func(instance validation.SchemaInstance) error {
		selected, present := pointerAt(root, instance.Path)
		if present {
			addExperimentFactories(strings.TrimPrefix(instance.SchemaPointer, schemaDefinitionsPrefix), object(selected))
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	trialProjection(root)
	result, err := json.Marshal(root)
	if err != nil || len(result) > limits.MaxBytes {
		return nil, invalid()
	}
	return result, nil
}

func addExperimentFactories(model string, document map[string]any) {
	if document == nil {
		return
	}
	for key, value := range experimentFactoryValues(model) {
		if _, present := document[key]; !present {
			document[key] = value
		}
	}
}

func (e *Validator) trialAuthorityProjection(data []byte, limits ingress.Limits) ([]byte, error) {
	var root map[string]any
	if decodeExact(data, &root) != nil {
		return nil, invalid()
	}
	cleanup := object(root["cleanup"])
	cleanup[fieldPlanID], cleanup[fieldPlanEntryID], cleanup["run_id"] = termCleanupTemplate, "entry-template", "run-template"
	raw, err := json.Marshal(cleanup)
	if err != nil {
		return nil, invalid()
	}
	constructed, _, err := e.experimentConstructed(termTrialCleanupPlanV1, raw, limits)
	if err != nil {
		return nil, err
	}
	cleanup = object(constructed)
	for _, key := range []string{fieldPlanID, fieldPlanEntryID, "run_id", termSchemaVersion} {
		delete(cleanup, key)
	}
	root["cleanup"] = cleanup
	return json.Marshal(root)
}

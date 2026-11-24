package trial

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func prepareInputs(request Request) (compilationInputs, error) {
	var input compilationInputs
	if request.Limits.Validate() != nil || request.MixedCompositionLimits.Validate() != nil {
		return input, trialInvalid()
	}
	owner, err := trialOwner()
	if err != nil {
		return input, err
	}
	input.owner = owner
	experiment, err := input.authoredInputs(request)
	if err != nil {
		return input, err
	}
	if err = input.authorityFragments(request); err != nil {
		return input, err
	}
	if err = validateInputPins(request, input, experiment); err != nil {
		return input, err
	}
	if err = input.realizationEnvelope(request); err != nil {
		return input, err
	}
	err = input.selectedAuthorities(request)
	return input, err
}
func (input *compilationInputs) authoredInputs(request Request) ([]byte, error) {
	if request.Experiment.ContractID() != "experiment-authoring-input-v1" || request.RealizationEnvelope.ContractID() != "realization-envelope-v1" {
		return nil, trialInvalid()
	}
	family, err := sdl.DocumentBytes(request.Family)
	if err != nil {
		return nil, err
	}
	if decode(family, &input.family) != nil {
		return nil, trialInvalid()
	}
	raw, err := admission.ExperimentProjection(input.owner, request.Experiment)
	if err != nil {
		return nil, err
	}
	if decode(raw, &input.spec) != nil {
		return nil, trialInvalid()
	}
	var spec binding.ExperimentAuthoringInputV1
	if decode(raw, &spec) != nil {
		return nil, trialInvalid()
	}
	if _, err = sdl.ValidateExperimentSelectionAgainstFamily(spec, request.Family); err != nil {
		return nil, refuse("selection-intent-rejected", "/run_plan/selection_policies", "selection policy intent failed scenario-family admission")
	}
	return raw, nil
}
func (input *compilationInputs) authorityFragments(request Request) error {
	for _, item := range []struct {
		fragment admission.Fragment
		profile  admission.FragmentProfile
		target   *json.RawMessage
	}{{request.InputRefs, admission.TrialInputRefs, &input.refsJSON}, {request.ExecutionAuthority, admission.TrialExecutionAuthority, &input.authorityJSON}, {request.Apparatus, admission.TrialApparatus, &input.apparatusJSON}} {
		if admission.CheckFragment(item.fragment, item.profile) != nil {
			return trialInvalid()
		}
		value, err := admission.AdmitFragment(input.owner, item.profile, item.fragment.Document(), trialIngress())
		if err != nil {
			return err
		}
		*item.target, err = encoded(value.Document())
		if err != nil {
			return err
		}
	}
	if decode(input.refsJSON, &input.refs) != nil || decode(input.authorityJSON, &input.authority) != nil {
		return trialInvalid()
	}
	return nil
}
func (input *compilationInputs) realizationEnvelope(request Request) error {
	if err := admission.CheckTransport(request.Task, trialIngress()); err != nil {
		return err
	}
	transport, err := request.RealizationEnvelope.Transport()
	if err != nil {
		return err
	}
	carrier, ok := transport.(binding.RealizationEnvelopeV1)
	if !ok {
		return trialInvalid()
	}
	input.envelope = carrier
	_, err = input.owner.Validate("realization-envelope-v1", request.RealizationEnvelope.JSON(), trialIngress(), nil)
	return err
}
func (input *compilationInputs) selectedAuthorities(request Request) error {
	var err error
	input.mixedProfiles, err = validateMixedPins(request, *input)
	if err != nil {
		return err
	}
	input.participants, err = participantAuthorities(request, *input)
	if err != nil {
		return err
	}
	if len(request.RealizationAssignments) > 0 || len(input.mixedProfiles) > 0 || len(input.refs.Mixed) > 0 {
		return nil
	}
	selected, err := selectedApparatus(request, *input)
	if err != nil {
		return err
	}
	input.backends = selected.backends
	input.manifests = selected.manifests
	input.descriptors, err = admittedDescriptors(request, *input)
	return err
}

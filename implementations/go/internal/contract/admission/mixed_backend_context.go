package admission

import "github.com/OpenRAE/rae/implementations/go/internal/contract/validation"

// MixedBackendBindingsContext supplies the complete independently installed
// binding set for one admitted composition profile and its resolved authorities.
type MixedBackendBindingsContext interface {
	MixedCompositionContext
	MixedProfile() []byte
	MixedBindings() [][]byte
}

func (e *Validator) mixedBackendContextRules() map[string]definition {
	return map[string]definition{
		"mixed-backend-binding-profile-join": {check: e.mixedBackendBindings, contextual: true, requiresContext: true},
		"mixed-backend-contextual-admission": {check: e.mixedBackendAdmission, contextual: true, requiresContext: true},
	}
}

func (e *Validator) mixedBackendBindings(i validation.Invocation) (err error) {
	defer func() {
		if recover() != nil {
			err = invalid()
		}
	}()
	context, ok := i.Context.(MixedBackendBindingsContext)
	if !ok {
		return contextRequired()
	}
	r, err := e.mixedResolution(context)
	if err != nil {
		return err
	}
	profile, err := e.contextDocument(termMixedParticipantCompositionProfileV1, context.MixedProfile())
	if err != nil {
		return err
	}
	profile, err = e.defaulted(termMixedParticipantCompositionProfileV1, profile)
	if err != nil {
		return err
	}
	if err = r.visit(profile); err != nil {
		return err
	}
	raw := context.MixedBindings()
	if len(raw) > 2048 {
		return invalid()
	}
	bindings, err := e.experimentDocuments(termMixedBackendExecutionBindingV1, raw)
	if err != nil {
		return err
	}
	if len(rowSet(bindings, "binding_id")) != len(bindings) {
		return invalid()
	}
	candidate, err := e.defaulted(termMixedBackendExecutionBindingV1, i.Instance)
	if err != nil {
		return err
	}
	return r.owner.mixedInstalledBindings(r, profile, candidate, bindings)
}

func (e *Validator) mixedBackendAdmission(i validation.Invocation) (err error) {
	defer func() {
		if recover() != nil {
			err = invalid()
		}
	}()
	context, ok := i.Context.(BackendAdmissionContext)
	if !ok {
		return contextRequired()
	}
	binding, err := e.defaulted(termMixedBackendExecutionBindingV1, i.Instance)
	if err != nil {
		return err
	}
	request, err := e.backendDocument(termBackendOperationRequestV1, context.OperationRequest())
	if err != nil {
		return err
	}
	capabilities, err := e.backendDocument(termBackendOperationCapabilitiesV1, context.InstalledCapabilities())
	if err != nil {
		return err
	}
	response, err := e.backendDocument(termBackendOperationResponseV1, context.AdmissionResponse())
	if err != nil {
		return err
	}
	if err = mixedBackendRequest(binding, request); err != nil {
		return err
	}
	if err = backendResponseJoin(request, response, nil); err != nil {
		return err
	}
	return backendAdmissionJoin(request, capabilities, response)
}

func mixedBackendRequest(binding, request any) error {
	digest, err := jsonDigest(binding)
	if err != nil {
		return err
	}
	reference := map[string]any{termContractID: termMixedBackendExecutionBindingV1, termArtifactID: at(binding, "binding_id"), termDigest: digest}
	subject := at(binding, "subject")
	service := at(subject, "bridge")
	if stringAt(subject, "kind") == termHandoff {
		service = at(subject, "transfer")
	}
	return require(equal(at(request, "command"), reference) && equal(at(request, "binding", "context", "operation_kind"), at(subject, "operation_kind")) && equal(at(request, "binding", "backend_id"), at(service, "service_ref")))
}

func (e *Validator) mixedInstalledBindings(r *mixedResolution, profile, candidate any, bindings []any) error {
	found := false
	edges, handoffs := map[string]any{}, map[string]any{}
	for _, binding := range bindings {
		normalized, err := e.defaulted(termMixedBackendExecutionBindingV1, binding)
		if err != nil {
			return err
		}
		found = found || equal(normalized, candidate)
		if err = mixedInstalledBinding(normalized, profile, edges, handoffs); err != nil {
			return err
		}
	}
	if !found {
		return invalid()
	}
	return r.backendBindings(profile, edges, handoffs)
}
func mixedInstalledBinding(binding, profile any, edges, handoffs map[string]any) error {
	if !matchingFields(binding, profile, termProfileID, "profile_revision", "profile_digest") {
		return invalid()
	}
	subject := at(binding, "subject")
	index, key := edges, stringAt(subject, "edge_id")
	if stringAt(subject, "kind") == termHandoff {
		index, key = handoffs, stringAt(subject, "transition_id")
	}
	if index[key] != nil {
		return invalid()
	}
	index[key] = subject
	return nil
}

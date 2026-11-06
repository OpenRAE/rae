package admission

import "github.com/OpenRAE/rae/implementations/go/contract/validation"

func (e *Validator) backendDocument(id string, raw []byte) (any, error) {
	v, err := e.contextDocument(id, raw)
	if err != nil {
		return nil, err
	}
	return e.backendNormalized(id, v)
}

func (e *Validator) backendNormalized(id string, value any) (any, error) {
	v, err := e.defaulted(id, value)
	if err != nil {
		return nil, err
	}
	if binding := object(at(v, "binding")); binding != nil && binding["effect_scope"] == nil {
		binding["effect_scope"] = map[string]any{termKind: "target-run", "addresses": []any{}, "independence": nil}
	}
	if id == termBackendOperationCapabilitiesV1 && at(v, "execution_policy") == nil {
		delete(object(v), "execution_policy")
	}
	return v, nil
}

func (e *Validator) backendResponse(i validation.Invocation) error {
	context, ok := i.Context.(BackendResponseContext)
	if !ok {
		return contextRequired()
	}
	request, err := e.backendDocument(termBackendOperationRequestV1, context.OperationRequest())
	if err != nil {
		return err
	}
	response, err := e.backendNormalized(termBackendOperationResponseV1, i.Instance)
	if err != nil {
		return err
	}
	var control any
	kind := stringAt(response, "message", termKind)
	if kind == messageControl || kind == messageReconciliation {
		control, err = e.backendDocument(termBackendOperationControlV1, context.OperationControl())
		if err != nil {
			return err
		}
	}
	return backendResponseJoin(request, response, control)
}

func backendResponseJoin(request, response, control any) error {
	commitment, err := jsonDigest(request)
	if err != nil {
		return err
	}
	if !equal(at(request, "binding"), at(response, "binding")) || stringAt(response, "request_digest") != commitment {
		return invalid()
	}
	message := at(response, "message")
	kind := stringAt(message, termKind)
	if kind == messageControl || kind == messageReconciliation {
		if err := backendControlJoin(request, response, control); err != nil {
			return err
		}
	}
	if (kind == messageOutcome || kind == messageReconciliation) && stringAt(request, "binding", "effect_scope", termKind) == scopeResources {
		return require(subset(stringsOf(at(message, termEffects, "residual_scope")), set(at(request, "binding", "effect_scope", "addresses"))))
	}
	return nil
}

func (e *Validator) backendAdmission(i validation.Invocation) error {
	context, ok := i.Context.(BackendAdmissionContext)
	if !ok {
		return contextRequired()
	}
	request, err := e.backendDocument(termBackendOperationRequestV1, context.OperationRequest())
	if err != nil {
		return err
	}
	response, err := e.backendDocument(termBackendOperationResponseV1, context.AdmissionResponse())
	if err != nil {
		return err
	}
	installed, err := e.backendDocument(termBackendOperationCapabilitiesV1, context.InstalledCapabilities())
	if err != nil {
		return err
	}
	capabilities, err := e.backendNormalized(termBackendOperationCapabilitiesV1, i.Instance)
	if err != nil {
		return err
	}
	if !equal(capabilities, installed) {
		return invalid()
	}
	if err := backendResponseJoin(request, response, nil); err != nil {
		return err
	}
	return backendAdmissionJoin(request, capabilities, response)
}

func backendAdmissionJoin(request, capabilities, response any) error {
	message := at(response, "message")
	if stringAt(message, termKind) != termAdmission || stringAt(message, "disposition") != "willing" || !equal(at(capabilities, "backend_id"), at(request, "binding", "backend_id")) {
		return invalid()
	}
	if !set(at(capabilities, "supported_operation_kinds"))[stringAt(request, "binding", "context", "operation_kind")] || !subset(stringsOf(at(request, "required_guarantees")), set(at(capabilities, "guarantees"))) {
		return invalid()
	}
	commitment, err := jsonDigest(capabilities)
	if err != nil {
		return err
	}
	return require(stringAt(message, "capability_digest") == commitment)
}

func backendControlJoin(request, response, control any) error {
	message := at(response, "message")
	kind := stringAt(message, termKind)
	if control == nil || !equal(at(control, "binding"), at(request, "binding")) || !equal(at(control, "request_digest"), at(response, "request_digest")) || !equal(at(control, "control_id"), at(message, "control_id")) {
		return invalid()
	}
	controlDigest, err := jsonDigest(control)
	if err != nil {
		return err
	}
	if stringAt(message, "control_digest") != controlDigest {
		return invalid()
	}
	if kind == messageReconciliation && stringAt(control, "action") != "observe" && stringAt(control, "action") != termReconcile {
		return invalid()
	}
	return nil
}

package admission

import "encoding/json"

func (r *controlResolution) validateV1(v any) error {
	gate, present, err := r.optionalReference(r.snapshot.IncumbentGateEvidence)
	if err != nil {
		return err
	}
	if !present || !equal(at(v, "composition", "incumbent_gate_evidence"), gate) || stringAt(v, "composition", "incumbent_gate_disposition") != r.snapshot.IncumbentGateDisposition {
		return invalid()
	}
	bindings := controlRows(at(v, "request", "selection", termBindings), "instance_id")
	for _, support := range array(at(v, "support")) {
		id := stringAt(support, "instance_id")
		binding := bindings[id]
		if stringAt(support, "effective_level") != statusUnsupported && !equal(r.indexes[termBindings][id], binding) || !equal(r.indexes[termEffective][id], support) {
			return invalid()
		}
		bindingRaw, supportRaw := controlRaw(binding), controlRaw(support)
		declared, declarationErr := r.context.ControlDeclaredSupport(bindingRaw, supportRaw)
		if declarationErr != nil || declared != stringAt(support, "declared_level") || declared == "" {
			return invalid()
		}
	}
	if err = r.resultsV1(v); err != nil {
		return err
	}
	for _, receipt := range array(at(v, "realizations")) {
		if !equal(r.indexes["receipts"][stringAt(receipt, "receipt", "ref")], receipt) {
			return invalid()
		}
	}
	return nil
}

func controlRaw(v any) json.RawMessage {
	raw, err := json.Marshal(v)
	if err != nil {
		return nil
	}
	return raw
}

func (r *controlResolution) resultsV1(v any) error {
	cut := at(v, "request", "context")
	for _, result := range array(at(v, "results")) {
		if stringAt(result, "status") == termResolved && !equal(r.indexes["results"][stringAt(result, "result_id")], result) {
			return invalid()
		}
		payload := at(result, "payload")
		switch stringAt(payload, termKind) {
		case termEffectRequest:
			if err := r.effectAuthority(payload, cut); err != nil {
				return err
			}
		case termIfcFact:
			if !controlIsSecurityFact(payload) {
				continue
			}
			if err := r.securityFact(payload, cut); err != nil {
				return err
			}
		}
	}
	return nil
}

func (r *controlResolution) effectAuthority(effect, cut any) error {
	digest, err := controlDigest(effect)
	if err != nil || !equal(r.indexes[termEffects][digest], cut) {
		return invalid()
	}
	if stringAt(effect, "target", termKind) == termInject {
		return r.inject(at(effect, "target"), cut)
	}
	return nil
}

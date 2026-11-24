package admission

import (
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) flowRules() map[string]definition {
	return map[string]definition{"participant-flow-control-resolved-context": {check: e.flowResolvedContext, contextual: true, requiresContext: true}}
}

func (e *Validator) flowResolvedContext(i validation.Invocation) (err error) {
	defer func() {
		if recover() != nil {
			err = invalid()
		}
	}()
	context, ok := i.Context.(FlowControlContext)
	if !ok {
		return contextRequired()
	}
	v, err := e.defaulted(termParticipantFlowControlRelationV1, i.Instance)
	if err != nil {
		return err
	}
	f := flowControl{owner: e, context: context, snapshot: context.FlowControlSnapshot()}
	if err = f.load(v); err != nil {
		return err
	}
	if err = f.profileCoordinates(v); err != nil {
		return err
	}
	if err = f.trustedCoordinates(v); err != nil {
		return err
	}
	if err = f.incumbents(); err != nil {
		return err
	}
	if err = f.bindings(v); err != nil {
		return err
	}
	if err = f.ownerCoordinates(v); err != nil {
		return err
	}
	return f.sinks(v)
}

func (e *Validator) flowAdmittedDocument(id string, admitted validation.Value) (any, error) {
	if admitted.ContractID() != id {
		return nil, invalid()
	}
	v, err := ingress.Parse(admitted.JSON(), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return nil, err
	}
	return e.defaulted(id, v)
}

func (f *flowControl) load(v any) error {
	s := f.snapshot
	for _, count := range []int{len(s.SourceLabels), len(s.PolicyCuts), len(s.ReleaseAuthorities), len(s.KnownSinks), len(s.RuntimeFactPlanes), len(s.ActionSelections), len(s.ActionAdmissions), len(s.ActionResolutions), len(s.CapabilityResolutions), len(s.HistoryResolutions), len(s.OwnerReleaseAuthorities), len(s.OwnerSinks)} {
		if count > 4096 {
			return invalid()
		}
	}
	profileID := stringAt(v, "profile", termProfileID)
	profile, err := f.owner.contextDocument(profileID, s.Profile)
	if err != nil {
		return err
	}
	f.profile, err = f.owner.defaulted(profileID, profile)
	if err != nil {
		return err
	}
	if !matchingFields(f.profile, at(v, "profile"), termProfileID, "profile_revision", "authority_revision") {
		return invalid()
	}
	digest, err := jsonDigest(f.profile)
	if err != nil || digest != stringAt(v, "profile", "profile_digest") {
		return invalid()
	}
	f.labels, err = f.fragments("ParticipantEffectiveFlowLabelModel", s.SourceLabels)
	if err != nil {
		return err
	}
	f.cuts, err = f.fragments("ParticipantFlowPolicyCutReferenceModel", s.PolicyCuts)
	if err != nil {
		return err
	}
	f.planes = map[string]any{}
	remaining := 64 * 1048576
	for key, plane := range s.RuntimeFactPlanes {
		raw := plane.JSON()
		if len(raw) > remaining {
			return invalid()
		}
		remaining -= len(raw)
		f.planes[key], err = f.owner.flowAdmittedDocument("runtime-fact-binding-plane-v1", plane)
		if err != nil {
			return err
		}
	}
	return f.loadActions()
}

func (f *flowControl) fragments(name string, raw map[string][]byte) (map[string]any, error) {
	result := make(map[string]any, len(raw))
	remaining := 64 * 1048576
	for key, data := range raw {
		if len(data) > remaining {
			return nil, invalid()
		}
		remaining -= len(data)
		v, err := f.owner.flowOwnerFragment(termParticipantFlowControlRelationV1, name, data)
		if err != nil {
			return nil, err
		}
		result[key] = v
	}
	return result, nil
}

func (f *flowControl) loadActions() error {
	f.selections, f.admissions = map[string]any{}, map[string]any{}
	remaining := 64 * 1048576
	for key, selection := range f.snapshot.ActionSelections {
		v, err := flowSelectionDocument(selection)
		if err != nil {
			return err
		}
		raw := controlRaw(v)
		if len(raw) > remaining {
			return invalid()
		}
		remaining -= len(raw)
		f.selections[join(key[0], key[1])] = v
	}
	for key, request := range f.snapshot.ActionAdmissions {
		v, err := f.owner.flowAction(request)
		if err != nil {
			return err
		}
		raw := controlRaw(v)
		if len(raw) > remaining {
			return invalid()
		}
		remaining -= len(raw)
		f.admissions[key] = v
	}
	return f.resolutionShapes()
}

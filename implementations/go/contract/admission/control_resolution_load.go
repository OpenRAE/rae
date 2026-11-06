package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (r *controlResolution) fragment(name string, raw []byte) (any, error) {
	v, err := r.owner.low.DefaultedObjectFragment(r.id, schemaDefinitionsPrefix+name, raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
	if err != nil {
		return nil, err
	}
	if _, err = r.owner.controlModel(name, v); err != nil {
		return nil, err
	}
	return v, nil
}

func (r *controlResolution) load() error {
	s := r.snapshot
	requestModel, bindingModel, resultModel := termParticipantControlRequestModel, "ControlMechanismBindingModel", "ControlMechanismResultModel"
	if r.v2 {
		requestModel, bindingModel, resultModel = termParticipantControlRequestV2Model, "ControlMechanismBindingV2Model", "ControlMechanismResultV2Model"
	}
	var err error
	r.request, err = r.fragment(requestModel, s.AdmittedRequest)
	if err != nil {
		return err
	}
	if len(s.SafeReferences) > 100000 || len(s.ResolvedSupport) > 4096 || len(s.CommittedIntents) > 4096 || len(s.FlowRelations) > 4096 || len(s.InjectOwners) > 4096 {
		return invalid()
	}
	r.safe = map[string]bool{}
	remaining := 64 * 1048576
	for _, raw := range s.SafeReferences {
		if len(raw) > remaining {
			return invalid()
		}
		remaining -= len(raw)
		ref, refErr := r.fragment("ControlArtifactReferenceModel", raw)
		if refErr != nil {
			return refErr
		}
		digest, digestErr := jsonDigest(ref)
		if digestErr != nil {
			return digestErr
		}
		r.safe[digest] = true
	}
	indexes := []struct {
		name, model string
		values      map[string][]byte
	}{
		{termBindings, bindingModel, s.InstalledBindings}, {"effective", "ControlEffectiveSupportModel", s.EffectiveSupport},
		{"results", resultModel, s.ResolvedResults}, {termEffects, termParticipantControlContextModel, s.AuthorizedEffects},
		{"receipts", "ControlRealizationBindingModel", s.RealizationReceipts},
	}
	if r.v2 {
		indexes = append(indexes, struct {
			name, model string
			values      map[string][]byte
		}{"coverage", "ControlObligationCoverageV2Model", s.ResolvedCoverage}, struct {
			name, model string
			values      map[string][]byte
		}{"proposals", "ControlStateProposalV2Model", s.AuthorizedStateProposals})
	}
	for _, index := range indexes {
		if r.indexes[index.name], err = r.loadIndex(index.model, index.values); err != nil {
			return err
		}
	}
	return nil
}

func (r *controlResolution) loadIndex(model string, raw map[string][]byte) (map[string]any, error) {
	if len(raw) > 4096 {
		return nil, invalid()
	}
	remaining := 64 * 1048576
	result := make(map[string]any, len(raw))
	for key, data := range raw {
		if key == "" || len(data) > remaining {
			return nil, invalid()
		}
		remaining -= len(data)
		value, err := r.fragment(model, data)
		if err != nil {
			return nil, err
		}
		result[key] = value
	}
	return result, nil
}

func (r *controlResolution) references(v any) error {
	raw, err := json.Marshal(v)
	if err != nil {
		return invalid()
	}
	return r.owner.low.CheckInstances(r.id, raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, func(i validation.SchemaInstance) error {
		if i.SchemaPointer != "#/$defs/ControlArtifactReferenceModel" {
			return nil
		}
		digest, err := jsonDigest(i.Value)
		if err != nil || !r.safe[digest] {
			return invalid()
		}
		return nil
	})
}

func (r *controlResolution) optionalReference(raw []byte) (any, bool, error) {
	if len(raw) == 0 {
		return nil, false, nil
	}
	v, err := r.fragment("ControlArtifactReferenceModel", raw)
	return v, true, err
}

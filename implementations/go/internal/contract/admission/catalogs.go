package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

func (e *Validator) checkCatalogs() error {
	source, err := corpus.Open()
	if err != nil {
		return fault.New(fault.Operational, codeContractCatalogInvalid, nil)
	}
	for id, path := range map[string]string{
		"uco-alignment-v1":                        "concept-authority/uco-alignment-v1.json",
		"reference-models-v1":                     "concept-authority/reference-models-v1.json",
		"concept-families-v1":                     "concept-authority/concept-families-v1.json",
		"controlled-vocabularies-v1":              "concept-authority/controlled-vocabularies-v1.json",
		"validation-profile-catalog-v1":           "profiles/validation/validation-profile-catalog-v1.json",
		"participant-control-teaching-profile-v1": "profiles/participant-control/teaching-influence-rev1.json",
		"participant-boundary-flow-policy-v1":     "profiles/participant-boundary-flow-policy/participant-boundary-flow-policy-v1.json",
		"participant-owner-flow-policy-v1":        "profiles/participant-boundary-flow-policy/participant-owner-flow-policy-v1.json",
	} {
		v, readErr := readCatalog(source, path)
		if readErr != nil {
			return readErr
		}
		if err = e.checkCatalog(id, v); err != nil {
			return err
		}
	}
	if err = e.checkCatalog("participant-information-reconstruction-profile-v1", e.informationProfile); err != nil {
		return err
	}
	for _, profile := range e.streams {
		if err = e.checkCatalog("random-stream-profile-v1", profile); err != nil {
			return err
		}
	}
	return e.checkBehaviorCatalogs()
}

func (e *Validator) checkCatalog(id string, v any) error {
	raw, err := json.Marshal(v)
	if err != nil {
		return fault.New(fault.Operational, codeContractCatalogInvalid, nil)
	}
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if err = e.low.CheckLocal(id, raw, limits); err != nil {
		return fault.New(fault.Operational, codeContractCatalogInvalid, nil)
	}
	if err = e.checkModels(id, raw, limits); err != nil {
		return fault.New(fault.Operational, codeContractCatalogInvalid, nil)
	}
	return nil
}

func (e *Validator) checkBehaviorCatalogs() error {
	for _, catalog := range e.relationCatalogs {
		if err := e.checkCatalog("behavioral-relations-v1", catalog); err != nil {
			return err
		}
	}
	for _, profile := range e.relationProfiles {
		if err := e.checkCatalog("behavioral-relation-profile-v1", profile); err != nil {
			return err
		}
	}
	return nil
}

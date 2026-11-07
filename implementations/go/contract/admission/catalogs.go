package admission

import (
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/concept"
)

// checkCatalogs admits every packaged schema-bound document of the owners
// with the complete family rules.
func (e *Validator) checkCatalogs() error { return e.checkDocuments(e.documents) }

func (e *Validator) checkDocuments(documents []concept.Document) error {
	for _, document := range documents {
		if err := e.checkCatalog(document.ContractID, document.JSON); err != nil {
			return err
		}
	}
	return nil
}

func (e *Validator) checkCatalog(id string, raw []byte) error {
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if err := e.low.CheckLocal(id, raw, limits); err != nil {
		return fault.New(fault.Operational, codeContractCatalogInvalid, nil)
	}
	if err := e.checkModels(id, raw, limits); err != nil {
		return fault.New(fault.Operational, codeContractCatalogInvalid, nil)
	}
	return nil
}

// Package concept owns the concept-authority catalogs of the published
// corpus: the controlled vocabularies, the concept families, the
// behavioral-relation taxonomy revisions and the pinned external source
// snapshots. It also resolves external concept-binding assertions against
// caller-supplied subjects and scheme snapshots, without discovery or network
// access.
//
// Load reads the packaged documents once. Each document passes strict
// ingress and its published schema before the owner decodes it. Full family
// admission of the documents is the work of contract/admission, which reads
// them through Documents.
package concept

import (
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

// Document is one packaged authority document and its published contract.
type Document struct {
	ContractID, Path string
	JSON             []byte
}

// Authority is the immutable set of packaged concept-authority catalogs.
// Its methods are safe for concurrent use.
type Authority struct {
	schemas      *validation.Validator
	documents    []Document
	vocabularies map[string]vocabulary
	scopes       map[string]string
	families     map[string]Family
	relations    map[string]RelationCatalog
	current      string
	snapshots    []SchemeSnapshot
}

// Load reads and checks the packaged catalogs with the compiled published
// schemas. Keep the result for reuse.
func Load(schemas *validation.Validator) (*Authority, error) {
	if schemas == nil {
		return nil, fault.New(fault.InvalidInput, "concept-validator-required", nil)
	}
	source, err := corpus.Open()
	if err != nil {
		return nil, damaged()
	}
	return load(source, schemas)
}

// Documents returns copies of the packaged documents in path order.
func (a *Authority) Documents() []Document {
	documents := slices.Clone(a.documents)
	for i := range documents {
		documents[i].JSON = slices.Clone(documents[i].JSON)
	}
	return documents
}

// damaged reports a packaged document that fails its checks. Only a damaged
// build or installation can cause it.
func damaged() error { return fault.New(fault.Operational, "concept-authority-invalid", nil) }

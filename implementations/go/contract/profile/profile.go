// Package profile owns the published profiles of the packaged corpus: the
// behavioral-relation profiles, the validation-profile catalog, the
// scientific-completeness taxonomy and assessments, the semantic-comparison
// profiles and the other packaged profiles. It also resolves and admits
// domain-profile bindings offline, with the bounded inert schema engine.
//
// Load reads the packaged profiles once. Each profile passes strict ingress
// and its published schema, or the reference model rules where no published
// schema exists, before the owner decodes it. Full family admission of the
// schema-bound profiles is the work of contract/admission, which reads them
// through Documents.
package profile

import (
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/concept"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

// Profiles is the immutable set of packaged profiles. Its methods are safe
// for concurrent use.
type Profiles struct {
	schemas     *validation.Validator
	documents   []concept.Document
	relations   map[[2]string]RelationProfile
	validation  ValidationCatalog
	taxonomy    CompletenessTaxonomy
	assessments map[string]CompletenessAssessment
	comparisons map[string]ComparisonProfile
}

// Load reads and checks the packaged profiles with the compiled published
// schemas. Keep the result for reuse.
func Load(schemas *validation.Validator) (*Profiles, error) {
	if schemas == nil {
		return nil, invalid("profile-validator-required")
	}
	source, err := corpus.Open()
	if err != nil {
		return nil, damaged()
	}
	return load(source, schemas)
}

// Documents returns copies of the packaged schema-bound profiles in path
// order. ContractID names the published contract of each document.
func (p *Profiles) Documents() []concept.Document {
	documents := slices.Clone(p.documents)
	for i := range documents {
		documents[i].JSON = slices.Clone(documents[i].JSON)
	}
	return documents
}

// damaged reports a packaged profile that fails its checks. Only a damaged
// build or installation can cause it.
func damaged() error { return fault.New(fault.Operational, "profile-authority-invalid", nil) }

func notFound(code string) error { return fault.New(fault.NotFound, code, nil) }

func invalid(code string) error { return fault.New(fault.InvalidInput, code, nil) }

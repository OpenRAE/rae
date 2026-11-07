package concept

import (
	"maps"
	"regexp"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// Vocabulary is one governed term set of controlled-vocabularies-v1.
// ExtensionPattern is empty when the vocabulary has no extension pattern.
type Vocabulary struct {
	ID, Title, Description, Kind, ExtensionPolicy, ExtensionPattern string
	GovernedScopes, Terms                                           []string
}

type vocabulary struct {
	record    Vocabulary
	terms     map[string]bool
	extension *regexp.Regexp
}

const closedPolicy = "closed"

type vocabularyWire struct {
	Vocabularies map[string]struct {
		Title            string         `json:"title"`
		Description      string         `json:"description"`
		Kind             string         `json:"kind"`
		ExtensionPolicy  string         `json:"extension_policy"`
		ExtensionPattern *string        `json:"extension_pattern"`
		GovernedScopes   []string       `json:"governed_scopes"`
		Terms            map[string]any `json:"terms"`
	} `json:"vocabularies"`
}

func (a *Authority) decodeVocabularies(documents map[string][]byte) error {
	var wire vocabularyWire
	if err := decode(documents[pathVocabularies], &wire); err != nil {
		return err
	}
	a.vocabularies, a.scopes = map[string]vocabulary{}, map[string]string{}
	for id, row := range wire.Vocabularies {
		v := vocabulary{record: Vocabulary{ID: id, Title: row.Title, Description: row.Description, Kind: row.Kind, ExtensionPolicy: row.ExtensionPolicy, GovernedScopes: slices.Clone(row.GovernedScopes), Terms: slices.Sorted(maps.Keys(row.Terms))}, terms: map[string]bool{}}
		for term := range row.Terms {
			v.terms[term] = true
		}
		if row.ExtensionPattern != nil {
			compiled, err := regexp.Compile(`\A(?:` + *row.ExtensionPattern + `)\z`)
			if err != nil {
				return damaged()
			}
			v.record.ExtensionPattern, v.extension = *row.ExtensionPattern, compiled
		}
		for _, scope := range row.GovernedScopes {
			if _, taken := a.scopes[scope]; taken {
				return damaged()
			}
			a.scopes[scope] = id
		}
		a.vocabularies[id] = v
	}
	return nil
}

// Vocabulary returns the vocabulary with the catalog ID.
func (a *Authority) Vocabulary(id string) (Vocabulary, bool) {
	v, ok := a.vocabularies[id]
	return v.copy(), ok
}

// ScopeVocabulary returns the vocabulary that governs the scope.
func (a *Authority) ScopeVocabulary(scope string) (Vocabulary, bool) {
	id, ok := a.scopes[scope]
	return a.vocabularies[id].copy(), ok
}

// Permits reports whether the vocabulary admits the term: a catalog term, or
// a term that matches the extension pattern of a vocabulary that is not
// closed. An unknown vocabulary admits no term.
func (a *Authority) Permits(vocabularyID, term string) bool {
	v, ok := a.vocabularies[vocabularyID]
	if !ok || v.terms[term] {
		return ok
	}
	return v.record.ExtensionPolicy != closedPolicy && v.extension != nil && v.extension.MatchString(term)
}

// CheckScope checks each value against the vocabulary that governs the
// scope. It refuses a scope that no vocabulary governs and a value that the
// vocabulary does not admit, with an InvalidInput fault.
func (a *Authority) CheckScope(scope string, values ...string) error {
	id, ok := a.scopes[scope]
	if !ok {
		return fault.New(fault.InvalidInput, "vocabulary-scope-ungoverned", nil)
	}
	for _, value := range values {
		if !a.Permits(id, value) {
			return fault.New(fault.InvalidInput, "vocabulary-term-unpermitted", nil)
		}
	}
	return nil
}

func (v vocabulary) copy() Vocabulary {
	record := v.record
	record.GovernedScopes, record.Terms = slices.Clone(record.GovernedScopes), slices.Clone(record.Terms)
	return record
}

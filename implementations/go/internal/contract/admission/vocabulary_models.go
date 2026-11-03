package admission

import "regexp"

var vocabularyTermIdentity = regexp.MustCompile(`^[a-z0-9]+(?:[-_][a-z0-9]+)*$`)

func (e *Validator) governedVocabularyScope(scope string) bool {
	if backendConceptScope(scope) {
		return true
	}
	for _, definition := range e.vocabularies {
		if set(at(definition, "governed_scopes"))[scope] {
			return true
		}
	}
	return false
}

func (e *Validator) vocabularyDefinition(v any) error {
	for term := range object(at(v, "terms")) {
		if !vocabularyTermIdentity.MatchString(term) {
			return invalid()
		}
	}
	if !fieldsUnique(v, "governed_scopes") {
		return invalid()
	}
	for _, scope := range stringsOf(at(v, "governed_scopes")) {
		if !e.governedVocabularyScope(scope) {
			return invalid()
		}
	}
	closed := stringAt(v, "extension_policy") == termClosed
	if stringAt(v, "kind") == "enumeration" && !closed {
		return invalid()
	}
	if closed {
		return require(at(v, "extension_pattern") == nil)
	}
	return require(len(array(at(v, "governed_scopes"))) > 0 && at(v, "extension_pattern") != nil && pythonPatternValid(stringAt(v, "extension_pattern")))
}

func vocabularyCatalog(v any) error {
	owners := map[string]string{}
	for id, definition := range object(at(v, "vocabularies")) {
		for _, scope := range stringsOf(at(definition, "governed_scopes")) {
			if owner, present := owners[scope]; present && owner != id {
				return invalid()
			}
			owners[scope] = id
		}
	}
	return nil
}

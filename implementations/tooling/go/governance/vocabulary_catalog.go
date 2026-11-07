package governance

import (
	"slices"
)

func vocabularyCatalog(profile vocabularyProfile, source, catalog *mapping) []string {
	if profile.id == "" {
		return nil
	}
	vocabulary := object(object(catalog.get("vocabularies")).get(profile.id))
	if vocabulary == nil {
		return []string{vocabularyCatalogPath + ": missing vocabulary " + pythonRepr(profile.id)}
	}
	findings := vocabularyCatalogSource(profile, vocabulary)
	if scopes, _ := vocabulary.get("governed_scopes").([]any); len(scopes) > 0 {
		findings = append(findings, vocabularyCatalogPath+": "+profile.id+".governed_scopes is "+pythonRepr(scopes)+"; expected []")
	}
	if vocabulary.get("extension_policy") != "closed" {
		findings = append(findings, vocabularyCatalogPath+": "+profile.id+" must remain a closed optional source catalog")
	}
	return append(findings, vocabularyTerms(profile, source, object(vocabulary.get("terms")))...)
}

func vocabularyCatalogSource(profile vocabularyProfile, vocabulary *mapping) []string {
	source := object(vocabulary.get("source"))
	provenance, authority := "adopted", profile.value(sourceAuthorityField)
	if profile.label == attackVocabulary {
		authority = "MITRE ATT&CK Enterprise"
	}
	if profile.label == nistVocabulary {
		provenance = "adapted"
	}
	if source == nil {
		return []string{vocabularyCatalogPath + ": " + profile.id + " must declare " + provenance + " " + profile.label + " source metadata"}
	}
	fields := []vocabularyField{
		{provenanceField, provenance}, {authorityField, authority},
		{"authority_version", profile.value(sourceVersionField)},
		{"source_artifact_ref", profile.path},
		{sourceURLField, profile.value(sourceURLField)},
		{sourceDigestField, profile.value(sourceDigestField)},
		{licenseURLField, profile.value(licenseURLField)},
		{licenseNoticeField, profile.value(licenseNoticeField)},
	}
	findings := vocabularyFields(vocabularyCatalogPath+": "+profile.id+".source.", source, fields)
	return append(findings, vocabularyCitations(profile, source, true)...)
}

func vocabularyTerms(profile vocabularyProfile, source, terms *mapping) []string {
	field, key := "tactics", shortnameField
	if profile.label == nistVocabulary {
		field, key = "categories", "term_id"
	}
	expected := rowStrings(source, field, key)
	actual := make([]string, len(terms.keys))
	for i, key := range terms.keys {
		actual[i], _ = key.(string)
	}
	findings := []string{}
	if !slices.Equal(actual, expected) {
		message := vocabularyCatalogPath + ": " + profile.id + " term order/content differs from NIST source"
		if profile.label != nistVocabulary {
			message = vocabularyCatalogPath + ": " + profile.id + " term order/content differs from pinned " + profile.label + " matrix order; actual=" + pythonRepr(actual) + " expected=" + pythonRepr(expected)
		}
		findings = append(findings, message)
	}
	rows, _ := source.get(field).([]any)
	for _, row := range rows {
		item := object(row)
		name, _ := item.get(key).(string)
		term := object(terms.get(name))
		if term == nil {
			if profile.label != nistVocabulary {
				findings = append(findings, vocabularyCatalogPath+": missing "+profile.label+" tactic "+pythonRepr(name))
			}
			continue
		}
		findings = append(findings, vocabularyTerm(profile, name, item, term)...)
	}
	return findings
}

func vocabularyTerm(profile vocabularyProfile, name string, source, term *mapping) []string {
	prefix := vocabularyCatalogPath + ": " + name
	findings := []string{}
	if profile.label == nistVocabulary {
		if term.get(titleField) != source.get(titleField) || term.get("source_id") != source.get("category_id") {
			findings = append(findings, prefix+" title or source_id differs from NIST source")
		}
		if term.get(sourceURLField) != "https://doi.org/10.6028/NIST.CSWP.29" {
			findings = append(findings, prefix+".source_url must cite NIST CSWP 29")
		}
		return findings
	}
	for _, field := range []struct{ actual, expected string }{{titleField, nameField}, {descriptionField, descriptionField}, {"source_id", tacticIDField}, {sourceURLField, urlField}} {
		if term.get(field.actual) == source.get(field.expected) {
			continue
		}
		message := prefix + "." + field.actual + " is " + pythonRepr(term.get(field.actual)) + "; expected " + pythonRepr(source.get(field.expected))
		if field.actual == descriptionField {
			message = prefix + ".description differs from pinned " + profile.label + " text"
		}
		findings = append(findings, message)
	}
	return findings
}

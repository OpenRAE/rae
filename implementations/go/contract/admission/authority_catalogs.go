package admission

import (
	"strings"
	"unicode"
)

func (e *Validator) ucoCatalog(v any) error {
	expected := map[string]string{}
	for id, family := range e.conceptFamilies {
		provenance := stringAt(family, "provenance")
		if stringAt(family, termAuthority) == "UCO" && (provenance == "adopted" || provenance == "adapted") {
			expected[id] = provenance
		}
	}
	rows := object(at(v, "alignments"))
	if len(rows) != len(expected) {
		return invalid()
	}
	for id, row := range rows {
		if strings.TrimSpace(id) == "" || stringAt(row, "concept_family") != id || expected[id] == "" || stringAt(row, "provenance") != expected[id] {
			return invalid()
		}
		if err := ucoAlignment(row); err != nil {
			return err
		}
	}
	return nil
}
func ucoAlignment(v any) error {
	provenance := stringAt(v, "provenance")
	divergences := len(array(at(v, "divergences")))
	if provenance == "native" || provenance == "adapted" && divergences == 0 || provenance == "adopted" && divergences != 0 {
		return invalid()
	}
	rows := array(at(v, "uco_types"))
	if len(rowSet(rows, "uco_class")) != len(rows) {
		return invalid()
	}
	for _, row := range rows {
		prefix, local, present := strings.Cut(stringAt(row, "uco_class"), ":")
		if !present || stringAt(row, "iri") != "https://ontology.unifiedcyberontology.org/uco/"+prefix+"/"+local {
			return invalid()
		}
	}
	return nil
}

func conceptFamilyKeys(v any) error {
	for key := range object(at(v, "families")) {
		if strings.TrimFunc(key, func(r rune) bool {
			return unicode.IsSpace(r) || r >= 0x1c && r <= 0x1f
		}) == "" {
			return invalid()
		}
	}
	return nil
}

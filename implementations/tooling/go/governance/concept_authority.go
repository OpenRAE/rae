package governance

import (
	"encoding/json"
	"io/fs"
	"math"
	"regexp"
	"slices"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

const conceptFamiliesPath = "contracts/concept-authority/concept-families-v1.json"

// Keep the legacy model's null/absent representation and blank-identifier
// profile before strict admission. Nonblank identifiers remain unchanged;
// the existing published schema rejects any normalized empty property name.
func normalizeConceptCatalog(id string, data []byte) ([]byte, error) {
	if id != "concept-families-v1" {
		return data, nil
	}
	value, err := ingress.Parse(data, ingress.Limits{MaxBytes: math.MaxInt, MaxDepth: 65000}, ingress.Object)
	if err != nil {
		return nil, err
	}
	root, _ := value.(map[string]any)
	families, _ := root["families"].(map[string]any)
	for key, family := range families {
		if key != "" && strings.TrimFunc(key, pythonWhitespace) == "" {
			families[""] = family
			delete(families, key)
		}
		definition, _ := family.(map[string]any)
		if definition[provenanceField] != "native" {
			continue
		}
		for _, field := range []string{authorityField, "authority_reference"} {
			if definition[field] == nil {
				delete(definition, field)
			}
		}
	}
	return json.Marshal(value)
}

func (c *checker) conceptAuthority(r *repository) (Report, error) {
	catalog, findings, err := c.conceptCatalog(r, conceptFamiliesPath, "families", "concept-family")
	if err != nil {
		return Report{}, err
	}
	if catalog == nil {
		return c.finish(r, findings)
	}
	families := object(catalog.get("families"))
	familyIDs := sortedMappingKeys(families)
	findings = append(findings, conceptADRLinkage(r, familyIDs)...)
	vocabularies, invalid, err := c.conceptCatalog(r, vocabularyCatalogPath, "vocabularies", "controlled-vocabulary")
	findings = append(findings, invalid...)
	if err != nil {
		return Report{}, err
	}
	if vocabularies != nil {
		known := append(slices.Clone(familyIDs), sortedMappingKeys(object(vocabularies.get("vocabularies")))...)
		findings = append(findings, conceptReferences(families, familyIDs, known)...)
	}
	return c.finish(r, findings)
}

func (c *checker) conceptCatalog(r *repository, name, kind, label string) (*mapping, []Finding, error) {
	rule := "concept-authority-" + kind + "-catalog-"
	if !r.file(name) {
		return nil, []Finding{finding(rule+"missing", label+" catalog not found: "+name, name)}, nil
	}
	catalog, err := c.vocabularyModel(r, name)
	if err == nil {
		return catalog, nil, nil
	}
	if category, expected := fault.CategoryOf(err); !expected || category != fault.InvalidInput {
		return nil, nil, err
	}
	return nil, []Finding{finding(rule+"invalid", name+": "+err.Error(), name)}, nil
}

func conceptADRLinkage(r *repository, families []string) []Finding {
	directory, err := r.resolve(adrDirectory)
	if err == nil {
		info, statErr := r.root.Stat(directory)
		if statErr == nil && info.IsDir() {
			return conceptADRMentions(r, directory, families)
		}
	}
	return []Finding{finding("concept-authority-adr-dir-missing", "ADR directory not found: "+adrDirectory, adrDirectory)}
}

func conceptADRMentions(r *repository, directory string, families []string) []Finding {
	names, _ := fs.Glob(r.root.FS(), directory+"/adr-*.md")
	texts := make([]string, 0, len(names))
	for _, name := range names {
		if text, readErr := r.text(name); readErr == nil && text != "" {
			texts = append(texts, text)
		}
	}
	text := strings.Join(texts, "\n")
	findings := []Finding{}
	for _, family := range families {
		if !conceptMention(text, family) {
			findings = append(findings, finding("concept-authority-family-adr-missing", "concept family '"+family+"' is not mentioned as a whole token in any ADR under "+adrDirectory+"; add ADR linkage (specs, docs, and tests do not satisfy it)", conceptFamiliesPath))
		}
	}
	return findings
}

func conceptMention(text, token string) bool {
	for offset := 0; offset < len(text); {
		index := strings.Index(text[offset:], token)
		if index < 0 {
			return false
		}
		start := offset + index
		end := start + len(token)
		before, _ := utf8.DecodeLastRuneInString(text[:start])
		after, _ := utf8.DecodeRuneInString(text[end:])
		if !pythonWord(before) && before != '-' && !pythonWord(after) && after != '-' {
			return true
		}
		offset = start + 1
	}
	return false
}

func conceptReferences(families *mapping, familyIDs, known []string) []Finding {
	inline := regexp.MustCompile("`([^`\n]+)`")
	id := regexp.MustCompile(`^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`)
	findings := []Finding{}
	for _, family := range familyIDs {
		seen := map[string]bool{}
		rules, _ := stringList(object(families.get(family)).get("relation_rules"), false)
		for _, rule := range rules {
			for _, match := range inline.FindAllStringSubmatch(rule, -1) {
				token := match[1]
				if id.MatchString(token) && !seen[token] && !slices.Contains(known, token) {
					seen[token] = true
					findings = append(findings, finding("concept-authority-dangling-reference", "concept family '"+family+"' relation_rules reference '"+token+"', which is not a known concept family or controlled vocabulary", conceptFamiliesPath))
				}
			}
		}
	}
	return findings
}

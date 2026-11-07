package governance

import (
	"regexp"
	"strings"
	"unicode/utf8"
)

var activityNamePattern = regexp.MustCompile(`data-link-type="dfn">([A-Za-z]+)</a>`)

func extractTacticSnapshot(label string, data []byte) ([]any, error) {
	var payload any
	var err error
	if label == atlasVocabulary {
		payload, err = yamlValue(data, false)
	} else {
		payload, err = decodeJSON(data, 0, false)
	}
	if err != nil {
		return nil, policyInputError("upstream tactic snapshot could not be decoded")
	}
	if object(payload) == nil {
		return nil, policyInputError("upstream tactic snapshot must be an object")
	}
	if label == atlasVocabulary {
		return extractAtlasTactics(object(payload))
	}
	return extractEnterpriseTactics(object(payload))
}

func extractEnterpriseTactics(payload *mapping) ([]any, error) {
	matrix, tactics, err := enterpriseTacticIndex(payload)
	if err != nil {
		return nil, err
	}
	refs := matrix.get("tactic_refs")
	if !matrix.has("tactic_refs") {
		refs = []any{}
	}
	values, ok := refs.([]any)
	if !ok {
		return nil, policyInputError("STIX tactic_refs must be an array")
	}
	rows := []any{}
	for _, ref := range values {
		if !yamlHashable(ref) || tactics[yamlKey(ref)] == nil {
			return nil, policyInputError("matrix references missing active tactic " + pythonRepr(ref))
		}
		row, err := enterpriseTacticRow(tactics[yamlKey(ref)])
		if err != nil {
			return nil, err
		}
		rows = append(rows, row)
	}
	return rows, nil
}

func enterpriseTacticIndex(payload *mapping) (*mapping, map[any]*mapping, error) {
	raw := payload.get("objects")
	if !payload.has("objects") {
		raw = []any{}
	}
	entries, ok := raw.([]any)
	if !ok {
		return nil, nil, policyInputError("STIX objects must be an array")
	}
	tactics := map[any]*mapping{}
	var matrix *mapping
	for _, value := range entries {
		item := object(value)
		if item == nil {
			return nil, nil, policyInputError("STIX object must be a mapping")
		}
		if activeEnterpriseTactic(item) {
			if !item.has("id") || !yamlHashable(item.get("id")) {
				return nil, nil, policyInputError("active STIX tactic has no hashable id")
			}
			tactics[yamlKey(item.get("id"))] = item
		}
		if matrix == nil && item.get("type") == "x-mitre-matrix" && item.get(nameField) == "Enterprise ATT&CK" {
			matrix = item
		}
	}
	if matrix == nil {
		return nil, nil, policyInputError("STIX payload is missing matrix 'Enterprise ATT&CK'")
	}
	return matrix, tactics, nil
}

func enterpriseTacticRow(tactic *mapping) (*mapping, error) {
	refs, ok := tactic.get("external_references").([]any)
	if !tactic.has("external_references") {
		refs = []any{}
		ok = true
	}
	if !ok {
		return nil, policyInputError("STIX external_references must be an array")
	}
	var reference *mapping
	for _, value := range refs {
		item := object(value)
		if item == nil {
			return nil, policyInputError("STIX external reference must be a mapping")
		}
		if item.get("source_name") == "mitre-attack" {
			reference = item
			break
		}
	}
	if reference == nil {
		return nil, policyInputError("STIX object " + pythonStr(tactic.get("id")) + " is missing a mitre-attack external reference")
	}
	fields := []struct {
		out, in string
		source  *mapping
	}{
		{tacticIDField, "external_id", reference}, {shortnameField, "x_mitre_shortname", tactic}, {nameField, nameField, tactic}, {descriptionField, descriptionField, tactic}, {urlField, urlField, reference}, {"stix_id", "id", tactic},
	}
	row := newMapping()
	for _, field := range fields {
		if !field.source.has(field.in) {
			return nil, policyInputError("STIX tactic is missing a required field")
		}
		row.set(field.out, pythonStr(field.source.get(field.in)))
	}
	return row, nil
}

func extractActivityNames(data []byte) ([]string, error) {
	if !utf8.Valid(data) {
		return nil, errNotUTF8
	}
	text := string(data)
	start := strings.Index(text, `<section id="activity-types"`)
	if start < 0 {
		return nil, policyInputError("ActivityStreams snapshot is missing the activity-types section")
	}
	text = text[start:]
	start = strings.Index(text, "<ul>")
	if start < 0 {
		return nil, policyInputError("ActivityStreams snapshot is missing the activity type list")
	}
	text = text[start:]
	end := strings.Index(text, "</ul>")
	if end < 0 {
		return nil, policyInputError("ActivityStreams snapshot has no activity type list ending")
	}
	names := []string{}
	for _, match := range activityNamePattern.FindAllStringSubmatch(text[:end], -1) {
		names = append(names, match[1])
	}
	return names, nil
}

func activeEnterpriseTactic(item *mapping) bool {
	return item.get("type") == "x-mitre-tactic" && !truth(item.get("revoked")) && !truth(item.get("x_mitre_deprecated"))
}

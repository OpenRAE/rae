package validation

import (
	"bytes"
	_ "embed" // Required by go:embed for the packaged compatibility records.
	"encoding/json"
	"io"
	"maps"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

const (
	keywordMaxLength        = "maxLength"
	keywordMinLength        = "minLength"
	sdlMaterializedContract = "materialized-scenario-v1"
)

//go:embed sdl-field-patterns.json
var sdlPatternJSON []byte

type sdlFieldPattern struct {
	Path         []string `json:"path"`
	Pattern      string   `json:"pattern"`
	MinLength    *int     `json:"min_length,omitempty"`
	MaxLength    *int     `json:"max_length,omitempty"`
	SchemaSHA256 string   `json:"schema_sha256,omitempty"`
}
type sdlPatternFields map[string]map[string][]sdlFieldPattern
type sdlPatternRecord struct {
	Reference string                      `json:"reference"`
	Contracts map[string]sdlPatternFields `json:"contracts"`
}

func readSDLPatterns() (sdlPatternRecord, error) {
	return decodeSDLPatterns(sdlPatternJSON)
}

func sdlPatternInvalid() error {
	return failure(fault.Operational, "sdl-construction-field-pattern-invalid")
}

func decodeSDLPatterns(raw []byte) (sdlPatternRecord, error) {
	var record sdlPatternRecord
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&record); err != nil || len(record.Reference) != 40 || len(record.Contracts) != 2 {
		return record, sdlPatternInvalid()
	}
	var extra any
	if decoder.Decode(&extra) != io.EOF {
		return record, sdlPatternInvalid()
	}
	for _, id := range []string{"sdl-authoring-input-v1", sdlMaterializedContract} {
		if len(record.Contracts[id]) == 0 {
			return record, sdlPatternInvalid()
		}
	}
	return record, nil
}

func applySDLFieldPatterns(id string, root map[string]any) (map[string]any, error) {
	record, err := readSDLPatterns()
	if err != nil {
		return nil, err
	}
	defs := maps.Clone(sdlSchemaObject(root["$defs"]))
	for name, fields := range record.Contracts[id] {
		model := maps.Clone(sdlSchemaObject(defs[name]))
		properties := maps.Clone(sdlSchemaObject(model["properties"]))
		if name == "" || len(fields) == 0 || properties == nil {
			return nil, sdlPatternInvalid()
		}
		for field, facts := range fields {
			property, err := applySDLPatternFacts(root, sdlSchemaObject(properties[field]), facts)
			if field == "" || err != nil {
				return nil, sdlPatternInvalid()
			}
			properties[field] = property
		}
		model["properties"] = properties
		defs[name] = model
	}
	copyRoot := maps.Clone(root)
	copyRoot["$defs"] = defs
	return copyRoot, nil
}

func applySDLPatternFacts(root, schema map[string]any, facts []sdlFieldPattern) (map[string]any, error) {
	if schema == nil || len(facts) == 0 {
		return nil, sdlPatternInvalid()
	}
	for _, fact := range facts {
		if !validSDLPatternFact(fact) {
			return nil, sdlPatternInvalid()
		}
		updated, err := applySDLPatternFact(root, schema, fact)
		if err != nil {
			return nil, err
		}
		schema = updated
	}
	return schema, nil
}

func applySDLPatternFact(root, schema map[string]any, fact sdlFieldPattern) (map[string]any, error) {
	if fact.SchemaSHA256 != "" {
		if len(fact.Path) != 0 || !stageDigestMatches(schema, fact.SchemaSHA256) {
			return nil, sdlPatternInvalid()
		}
		return sdlStringPattern(map[string]any{"type": "string"}, fact)
	}
	updated, found, err := rewriteSDLPattern(root, schema, fact, 0)
	if err != nil || !found {
		return nil, sdlPatternInvalid()
	}
	return updated, nil
}

func validSDLPatternFact(fact sdlFieldPattern) bool {
	if fact.Pattern == "" || len(fact.Path) > 16 {
		return false
	}
	for _, step := range fact.Path {
		if step != "items" {
			return false
		}
	}
	return true
}

func sdlSchemaObject(value any) map[string]any {
	object, _ := value.(map[string]any)
	return object
}

func rewriteSDLPattern(root, schema map[string]any, fact sdlFieldPattern, depth int) (map[string]any, bool, error) {
	if depth >= 32 || schema == nil {
		return nil, false, sdlPatternInvalid()
	}
	if reference, ok := schema["$ref"].(string); ok {
		var target any = root
		for _, token := range jsonpointer.Tokens(strings.TrimPrefix(reference, "#")) {
			target = sdlSchemaObject(target)[token]
		}
		resolved := maps.Clone(sdlSchemaObject(target))
		if resolved == nil {
			return nil, false, sdlPatternInvalid()
		}
		for key, value := range schema {
			if key != "$ref" {
				resolved[key] = value
			}
		}
		return rewriteSDLPattern(root, resolved, fact, depth+1)
	}
	if len(fact.Path) == 0 && schema["pattern"] == fact.Pattern {
		copySchema, err := sdlStringPattern(schema, fact)
		return copySchema, err == nil, err
	}
	return rewriteSDLPatternChildren(root, schema, fact, depth)
}

func rewriteSDLPatternChildren(root, schema map[string]any, fact sdlFieldPattern, depth int) (map[string]any, bool, error) {
	result, changed := schema, false
	if len(fact.Path) > 0 && schema["items"] != nil {
		child := fact
		child.Path = fact.Path[1:]
		updated, found, err := rewriteSDLPattern(root, sdlSchemaObject(schema["items"]), child, depth+1)
		if err != nil {
			return nil, false, err
		}
		if found {
			result, changed = maps.Clone(schema), true
			result["items"] = updated
		}
	}
	return rewriteSDLPatternAlternatives(root, result, fact, depth, changed)
}

func sdlStringPattern(schema map[string]any, fact sdlFieldPattern) (map[string]any, error) {
	pattern, err := rustSDLPattern(fact.Pattern)
	if err != nil {
		return nil, err
	}
	copySchema := maps.Clone(schema)
	copySchema["pattern"] = pattern
	for keyword, bound := range map[string]*int{keywordMinLength: fact.MinLength, keywordMaxLength: fact.MaxLength} {
		if bound != nil {
			if *bound < 0 {
				return nil, sdlPatternInvalid()
			}
			copySchema[keyword] = json.Number(strconv.Itoa(*bound))
		}
	}
	return copySchema, nil
}

func rewriteSDLPatternAlternatives(root, schema map[string]any, fact sdlFieldPattern, depth int, changed bool) (map[string]any, bool, error) {
	result := schema
	for _, keyword := range []string{"anyOf", "oneOf", "allOf"} {
		branches, _ := schema[keyword].([]any)
		copies, err := rewriteSDLPatternBranches(root, branches, fact, depth)
		if err != nil {
			return nil, false, err
		}
		if copies != nil {
			if !changed {
				result = maps.Clone(schema)
			}
			changed = true
			result[keyword] = copies
		}
	}
	return result, changed, nil
}

func rewriteSDLPatternBranches(root map[string]any, branches []any, fact sdlFieldPattern, depth int) ([]any, error) {
	var copies []any
	for index, branch := range branches {
		updated, found, err := rewriteSDLPattern(root, sdlSchemaObject(branch), fact, depth+1)
		if err != nil {
			return nil, err
		}
		if found {
			if copies == nil {
				copies = append([]any(nil), branches...)
			}
			copies[index] = updated
		}
	}
	return copies, nil
}

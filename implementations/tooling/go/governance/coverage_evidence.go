package governance

import (
	"errors"
	"io/fs"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"unicode/utf8"
)

const schemaDialectField = "$schema"

func boundedJSONObject(r *repository, name string, limit int) (*mapping, error) {
	if !r.file(name) {
		return nil, policyInputError("missing or unsafe repository artifact")
	}
	data, err := r.readLimit(name, int64(limit))
	if err != nil {
		if _, pathError := errors.AsType[*fs.PathError](err); pathError {
			return nil, err
		}
		return nil, policyInputError("repository artifact exceeds byte limit")
	}
	value, err := decodeJSON(data, limit, true)
	if err != nil {
		return nil, policyInputError("repository artifact is not a bounded JSON object")
	}
	if err := checkSchemaJSON(value); err != nil {
		return nil, err
	}
	return object(value), nil
}

func coverageDocument(r *repository, name, label string, limit int) (*mapping, string, error) {
	value, err := boundedJSONObject(r, name, limit)
	if _, input := errors.AsType[policyInputError](err); input {
		return nil, label + " source is not a readable bounded JSON object: " + name, nil
	}
	return value, "", err
}

func coverageFixture(r *repository, name, id, schema string) (string, error) {
	if !strings.HasPrefix(name, "contracts/") || !strings.HasSuffix(name, ".json") {
		return "fixture source must be a JSON artifact under contracts/: " + name, nil
	}
	payload, reason, err := coverageDocument(r, name, "fixture", 1000000)
	if err != nil || reason != "" {
		return reason, err
	}
	version, _ := payload.get("schema_version").(string)
	forms := []string{id}
	if match := regexp.MustCompile(`^(.+)-(v\p{Nd}+)$`).FindStringSubmatch(id); match != nil {
		forms = append(forms, match[1]+"/"+match[2])
	}
	if !slices.Contains(forms, version) {
		return "fixture source does not carry a payload of this contract: " + name, nil
	}
	return coverageValidated(r, payload, schema, nil, name)
}

func coverageEmbedded(r *repository, name, schema string, rawPointer, schemaPointer any) (string, error) {
	if !strings.HasPrefix(name, "contracts/") || !strings.HasSuffix(name, ".json") {
		return "embedded source must be a JSON artifact under contracts/: " + name, nil
	}
	pointer, ok := rawPointer.(string)
	if !ok || !strings.HasPrefix(pointer, "/") || utf8.RuneCountInString(pointer) > 256 {
		return "embedded source needs an RFC 6901 pointer into the carrier: " + name, nil
	}
	if schemaPointer != nil {
		value, valid := schemaPointer.(string)
		if !valid || !strings.HasPrefix(value, "#/$defs/") || utf8.RuneCountInString(value) > 256 {
			return "embedded schema pointer must name a published definition: " + name, nil
		}
	}
	carrier, reason, err := coverageDocument(r, name, "embedded", 4000000)
	if err != nil || reason != "" {
		return reason, err
	}
	node, found := coveragePointer(carrier, pointer)
	if !found {
		return "embedded pointer " + pointer + " resolves to nothing in " + name, nil
	}
	return coverageValidated(r, node, schema, schemaPointer, name)
}

func coveragePointer(node any, pointer string) (any, bool) {
	for _, raw := range strings.Split(pointer, "/")[1:] {
		token := strings.ReplaceAll(strings.ReplaceAll(raw, "~1", "/"), "~0", "~")
		switch value := node.(type) {
		case *mapping:
			if !value.has(token) {
				return nil, false
			}
			node = value.get(token)
		case []any:
			index, valid := coverageArrayIndex(token, len(value))
			if !valid {
				return nil, false
			}
			node = value[index]
		default:
			return nil, false
		}
	}
	return node, true
}

func coverageValidated(r *repository, payload any, schemaPath string, pointer any, name string) (string, error) {
	schema, reason, err := coverageDocument(r, schemaPath, "published schema", 4000000)
	if err != nil {
		return "", err
	}
	if reason != "" {
		return "published schema is not a readable bounded JSON object: " + schemaPath, nil
	}
	if pointer != nil {
		definition, _ := pointer.(string)
		defs := object(schema.get("$defs"))
		if !defs.has(strings.TrimPrefix(definition, "#/$defs/")) {
			return "schema pointer names no published definition: " + definition, nil
		}
		wrapper := newMapping()
		dialect := schema.get(schemaDialectField)
		if !schema.has(schemaDialectField) {
			dialect = defaultMetaschema
		}
		wrapper.set(schemaDialectField, dialect)
		wrapper.set("$defs", defs)
		wrapper.set("$ref", definition)
		schema = wrapper
	}
	compiled, err := compileCandidate(schema, true, false)
	if errors.Is(err, errSchemaPattern) {
		return "", err
	}
	if err != nil {
		return "published schema is not a valid JSON Schema: " + schemaPath, nil //nolint:nilerr // The reference reports a malformed schema as an evidence reason.
	}
	if err := compiled.Validate(schemaTransport(payload)); err != nil {
		location := schemaErrorLocation(err, payload)
		return "source does not conform to the published schema at " + location + ": " + name, nil
	}
	return "", nil
}

func coverageArrayIndex(token string, length int) (int, bool) {
	if token == "" || len(token) > 1 && token[0] == '0' {
		return 0, false
	}
	for _, digit := range token {
		if digit < '0' || digit > '9' {
			return 0, false
		}
	}
	index, err := strconv.Atoi(token)
	return index, err == nil && index < length
}

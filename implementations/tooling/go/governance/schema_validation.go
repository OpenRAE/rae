package governance

import (
	"errors"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

const defaultMetaschema = "https://json-schema.org/draft/2020-12/schema"

// candidateSchema compiles actual candidate bytes; it never substitutes an
// embedded published schema. The reference coverage surface asserts no formats.
func candidateSchema(data []byte) (*jsonschema.Schema, error) {
	value, err := decodeJSON(data, 0, false)
	if err != nil {
		return nil, err
	}
	return compileCandidate(value, true, false)
}

func schemaCompiler(formats bool, profileError *error) *jsonschema.Compiler {
	compiler := jsonschema.NewCompiler()
	compiler.DefaultDraft(jsonschema.Draft2020)
	compiler.UseLoader(offlineSchemas{})
	frozenSchemaFormats(compiler)
	compiler.RegisterVocabulary(schemaNumericProfile())
	compiler.AssertVocabs()
	compiler.UseRegexpEngine(func(source string) (jsonschema.Regexp, error) {
		pattern, err := compileSchemaPattern(source)
		if errors.Is(err, errSchemaPattern) {
			*profileError = err
		}
		return pattern, err
	})
	if formats {
		compiler.AssertFormat()
	}
	return compiler
}

func compileCandidate(value any, coverage, formats bool) (*jsonschema.Schema, error) {
	if err := checkCandidateMeta(value, coverage); err != nil {
		return nil, err
	}
	if err := checkSchemaJSON(value); err != nil {
		return nil, err
	}
	if !coverage && object(value) == nil {
		return nil, policyInputError("schema file must be a JSON object")
	}
	var profileError error
	compiler := schemaCompiler(formats, &profileError)
	const id = "https://governance.invalid/candidate"
	transport := schemaTransport(value)
	if root, ok := transport.(map[string]any); ok {
		root["$schema"] = candidateDialect(value, coverage)
	}
	if err := compiler.AddResource(id, transport); err != nil {
		return nil, err
	}
	compiled, err := compiler.Compile(id)
	if profileError != nil {
		return nil, profileError
	}
	return compiled, err
}

func schemaTransport(value any) any {
	switch v := value.(type) {
	case float64:
		return exactSchemaFloat(v)
	case *mapping:
		result := make(map[string]any, len(v.keys))
		for _, key := range v.keys {
			name, _ := key.(string)
			result[name] = schemaTransport(v.get(key))
		}
		return result
	case []any:
		result := make([]any, len(v))
		for i, item := range v {
			result[i] = schemaTransport(item)
		}
		return result
	default:
		return value
	}
}

// Metaschema checking does not follow candidate $ref values or compile their
// targets. This preserves the reference's distinct schema-syntax surface.
func checkCandidateMeta(value any, coverage bool) error {
	if err := checkSchemaJSON(value); err != nil {
		return err
	}
	id := candidateDialect(value, coverage)
	var profileError error
	compiler := schemaCompiler(true, &profileError)
	meta, err := compiler.Compile(id)
	if err != nil {
		return err
	}
	err = meta.Validate(schemaTransport(value))
	if profileError != nil {
		return profileError
	}
	return err
}

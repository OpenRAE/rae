package governance

import (
	"errors"
	"slices"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

const artifactLockPath = "implementations/tooling/artifacts.lock.json"
const artifactProfilesPath = "implementations/tooling/profiles/development-profiles.json"
const artifactAdmissionPath = "implementations/tooling/admission-policy.json"
const toolingAuthorityLimit = 2 * 1024 * 1024

type artifactPolicyError string

func (e artifactPolicyError) Error() string          { return string(e) }
func (artifactPolicyError) Category() fault.Category { return fault.Operational }

const errArtifactSelection = artifactPolicyError("development artifact policy failed before acquisition: selection rejected")

func toolingAuthority(r *repository, name string) (*mapping, error) {
	if !regularRepoFile(r, name) {
		return nil, errArtifactSelection
	}
	value, err := boundedJSONObject(r, name, toolingAuthorityLimit)
	if err != nil {
		return nil, errArtifactSelection
	}
	return value, nil
}

func toolingRecord(r *repository, value *mapping, authority, definition string) error {
	schemaName := map[string]string{
		artifactLockPath: "artifact-lock.schema.json", artifactProfilesPath: "profiles.schema.json", artifactAdmissionPath: "admission-policy.schema.json",
	}[authority]
	if schemaName == "" {
		return errArtifactSelection
	}
	schema, err := toolingAuthority(r, "implementations/tooling/schemas/"+schemaName)
	if err != nil {
		return err
	}
	if definition != "" {
		wrapper := newMapping()
		wrapper.set("$defs", schema.get("$defs"))
		wrapper.set("$ref", "#/$defs/"+definition)
		schema = wrapper
	}
	if nonlocalToolingReference(schema) {
		return errArtifactSelection
	}
	var profileError error
	compiler := schemaCompiler(true, &profileError)
	compiler.UseRegexpEngine(func(source string) (jsonschema.Regexp, error) {
		pattern, patternErr := compileToolingPattern(source)
		if errors.Is(patternErr, errSchemaPattern) {
			profileError = patternErr
		}
		return pattern, patternErr
	})
	meta, err := compiler.Compile(defaultMetaschema)
	if err != nil {
		return errArtifactSelection
	}
	err = meta.Validate(schemaTransport(schema))
	if profileError != nil {
		return profileError
	}
	if err != nil {
		return errArtifactSelection
	}
	transport, ok := schemaTransport(schema).(map[string]any)
	if !ok {
		return errArtifactSelection
	}
	transport["$schema"] = defaultMetaschema
	const location = "urn:raes:private:tooling-record"
	if compiler.AddResource(location, transport) != nil {
		return errArtifactSelection
	}
	compiled, err := compiler.Compile(location)
	if profileError != nil {
		return profileError
	}
	if err != nil || compiled.Validate(schemaTransport(value)) != nil {
		return errArtifactSelection
	}
	return nil
}

func nonlocalToolingReference(value any) bool {
	pending := []any{value}
	for len(pending) > 0 {
		value := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		switch value := value.(type) {
		case *mapping:
			for _, key := range value.keys {
				child := value.get(key)
				if key == "$ref" && !localToolingReference(child) {
					return true
				}
				pending = append(pending, child)
			}
		case []any:
			pending = append(pending, value...)
		}
	}
	return false
}

func mappingCopy(value *mapping) *mapping {
	result := newMapping()
	for _, key := range value.keys {
		result.set(key, value.get(key))
	}
	return result
}
func stringSet(value any) []string {
	entries, _ := value.([]any)
	seen := map[string]bool{}
	result := []string{}
	for _, entry := range entries {
		if text, ok := entry.(string); ok && !seen[text] {
			seen[text] = true
			result = append(result, text)
		}
	}
	slices.Sort(result)
	return result
}

func stringsAsValues(values []string) []any {
	result := make([]any, len(values))
	for i, value := range values {
		result[i] = value
	}
	return result
}
func mappingItems(value any) []*mapping {
	entries, _ := value.([]any)
	result := []*mapping{}
	for _, entry := range entries {
		if item := object(entry); item != nil {
			result = append(result, item)
		}
	}
	return result
}

func localToolingReference(value any) bool {
	ref, ok := value.(string)
	return ok && strings.HasPrefix(ref, "#")
}

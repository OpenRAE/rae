// Package domainprofile holds the reference model rules of the domain-profile
// contracts that no published schema keyword expresses. contract/admission
// applies them at each matching schema instance; contract/profile applies
// them to the inputs of its domain-profile operations.
package domainprofile

import (
	"bytes"
	"encoding/json"
	"errors"
	"maps"
	"math/big"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/base/urisafety"
)

// Dialect is the only admitted profile schema dialect.
const Dialect = "https://json-schema.org/draft/2020-12/schema"

// The schema versions of the domain-profile contracts.
const (
	definitionVersion = "domain-profile-definition/v1"
	defaultMaxCount   = 256
	maxLimitValue     = 16777216
)

// ErrModel reports an instance that breaks a domain-profile model rule.
var ErrModel = errors.New("domain-profile model rule failed")

// CheckModel applies the model rule of the named contract or schema
// definition to one schema-checked instance. It reports false for a name
// that is not a domain-profile model.
func CheckModel(name string, value any) (bool, error) {
	check, known := modelRules()[name]
	if !known {
		return false, nil
	}
	if !check(value) {
		return true, ErrModel
	}
	return true, nil
}

// modelRules returns the rule of each domain-profile contract and schema
// definition.
func modelRules() map[string]func(any) bool {
	return map[string]func(any) bool{
		"DomainProfileCoordinateModel":           authorityInert,
		"DomainProfileSemanticContractModel":     authorityInert,
		"DomainProfileNamespaceAdmissionModel":   authorityInert,
		"DomainProfileSchemaModel":               schemaIdentity,
		"domain-profile-definition-v1":           definitionDigestMatches,
		"DomainProfileDefinitionModel":           definitionDigestMatches,
		"DomainProfileDefinitionProvenanceModel": func(v any) bool { return inert(text(field(v, "source_locator"))) },
		"AdmittedDomainProfileDefinitionModel":   admittedSourceDigest,
		"domain-profile-support-declaration-v1":  supportSets,
		"DomainProfileSupportDeclarationModel":   supportSets,
		"domain-profile-resolution-context-v1":   contextCounts,
		"DomainProfileResolutionContextModel":    contextCounts,
		"domain-profile-admission-policy-v1":     func(v any) bool { return sortedUnique(v, "required_operations") },
		"DomainProfileAdmissionPolicyModel":      func(v any) bool { return sortedUnique(v, "required_operations") },
		"DomainProfileBindingProvenanceModel":    evidenceBasis,
		"domain-profile-binding-v1":              childIDsUnique,
		"DomainProfileBindingModel":              childIDsUnique,
	}
}

// Inert reports whether a URI is absolute, carries no credential or secret
// query field, has no fragment and does not use the file or data scheme.
func Inert(uri string) bool { return inert(uri) }

func inert(uri string) bool {
	return urisafety.Check(uri, urisafety.Options{ForbiddenSchemes: []string{"data", "file"}, ForbidFragment: true}) == nil
}

func authorityInert(v any) bool { return inert(text(field(v, "authority"))) }

// schemaIdentity checks the pinned schema: an inert ID that the document
// repeats, the selected dialect, the RFC 8785 document digest and the
// required vocabularies that the document declares.
func schemaIdentity(v any) bool {
	document := object(field(v, "schema_document"))
	dialect := text(member(v, "dialect", Dialect))
	if !inert(text(field(v, "schema_id"))) || text(document["$schema"]) != dialect || text(document["$id"]) != text(field(v, "schema_id")) || !sortedUnique(v, "required_vocabularies") {
		return false
	}
	documentDigest, err := Digest(document)
	if err != nil || documentDigest != text(field(v, "schema_digest")) {
		return false
	}
	declared, present := document["$vocabulary"]
	if present && object(declared) == nil {
		return false
	}
	required := map[string]bool{}
	for uri, flag := range object(declared) {
		value, ok := flag.(bool)
		if !ok {
			return false
		}
		if value {
			required[uri] = true
		}
	}
	listed := texts(field(v, "required_vocabularies"))
	for _, uri := range listed {
		if !inert(uri) {
			return false
		}
	}
	return maps.Equal(required, setOf(listed))
}

func definitionDigestMatches(v any) bool {
	if !sortedUnique(v, "allowed_contexts") {
		return false
	}
	expected, err := DefinitionDigest(v)
	return err == nil && text(field(field(v, "coordinate"), "definition_digest")) == expected
}

// DefinitionDigest returns the RFC 8785 digest of the self-free projection of
// a definition: its identity without the digest, the schema with its
// published defaults, the semantic contract and the allowed contexts.
func DefinitionDigest(definition any) (string, error) {
	identity := maps.Clone(object(field(definition, "coordinate")))
	delete(identity, "definition_digest")
	schema := maps.Clone(object(field(definition, "profile_schema")))
	if _, present := schema["dialect"]; !present {
		schema["dialect"] = Dialect
	}
	if _, present := schema["required_vocabularies"]; !present {
		schema["required_vocabularies"] = []any{}
	}
	return Digest(map[string]any{
		"schema_version":    definitionVersion,
		"identity":          identity,
		"profile_schema":    schema,
		"semantic_contract": field(definition, "semantic_contract"),
		"allowed_contexts":  field(definition, "allowed_contexts"),
	})
}

// Digest returns the rendered SHA-256 digest of the RFC 8785 form of a JSON
// value.
func Digest(value any) (string, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return "", ErrModel
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return "", ErrModel
	}
	return digest.SHA256(canonical), nil
}

func admittedSourceDigest(v any) bool {
	return text(field(field(v, "provenance"), "source_digest")) == text(field(field(field(v, "definition"), "coordinate"), "definition_digest"))
}

func supportSets(v any) bool {
	for _, name := range []string{"operations", "supported_schema_dialects", "supported_vocabularies", "supported_schema_keywords"} {
		if !sortedUnique(v, name) {
			return false
		}
	}
	for _, name := range []string{"supported_schema_dialects", "supported_vocabularies"} {
		for _, uri := range texts(field(v, name)) {
			if !inert(uri) {
				return false
			}
		}
	}
	structural := slices.Contains(texts(field(v, "operations")), "structural-validation")
	return !structural || len(texts(field(v, "supported_schema_dialects"))) > 0 && len(texts(field(v, "supported_schema_keywords"))) > 0
}

func contextCounts(v any) bool {
	limit := Limit(field(v, "limits"), "max_definitions", defaultMaxCount)
	for _, name := range []string{"definitions", "namespace_admissions", "support_declarations"} {
		if len(array(field(v, name))) > limit {
			return false
		}
	}
	return true
}

// Limit returns the integer limit member, its default when absent, or zero
// for a member that is not an integer from 0 to 16,777,216.
func Limit(limits any, name string, fallback int) int {
	value, present := object(limits)[name]
	if !present {
		return fallback
	}
	number, ok := value.(json.Number)
	if !ok {
		return 0
	}
	parsed, exact := new(big.Rat).SetString(number.String())
	if !exact || !parsed.IsInt() || !parsed.Num().IsInt64() || parsed.Sign() < 0 || parsed.Num().Int64() > maxLimitValue {
		return 0
	}
	return int(parsed.Num().Int64())
}

func evidenceBasis(v any) bool {
	observed := text(field(v, "basis")) == "observed"
	return sortedUnique(v, "evidence_refs") && observed == (len(array(field(v, "evidence_refs"))) > 0)
}

func childIDsUnique(v any) bool {
	ids := map[string]bool{}
	for _, child := range array(field(v, "children")) {
		ids[text(field(child, "binding_id"))] = true
	}
	return len(ids) == len(array(field(v, "children")))
}

func sortedUnique(v any, name string) bool {
	values := texts(field(v, name))
	return slices.IsSorted(values) && len(slices.Compact(slices.Clone(values))) == len(values)
}

func object(v any) map[string]any  { m, _ := v.(map[string]any); return m }
func array(v any) []any            { a, _ := v.([]any); return a }
func text(v any) string            { s, _ := v.(string); return s }
func field(v any, name string) any { return object(v)[name] }

func member(v any, name string, fallback any) any {
	if value, present := object(v)[name]; present {
		return value
	}
	return fallback
}

func texts(v any) []string {
	result := make([]string, 0, len(array(v)))
	for _, value := range array(v) {
		result = append(result, text(value))
	}
	return result
}

func setOf(values []string) map[string]bool {
	result := make(map[string]bool, len(values))
	for _, value := range values {
		result[value] = true
	}
	return result
}

// Decode reads JSON with exact numbers into the value form that the schema
// instances use.
func Decode(data []byte) (any, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	var value any
	if decoder.Decode(&value) != nil {
		return nil, ErrModel
	}
	return value, nil
}

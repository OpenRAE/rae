package admission

import (
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/internal/base/urisafety"
)

const domainProfileDialect = "https://json-schema.org/draft/2020-12/schema"

func inertProfileURI(uri string) bool {
	return urisafety.Check(uri, urisafety.Options{ForbiddenSchemes: []string{"data", "file"}, ForbidFragment: true}) == nil
}

func sortedProfileFields(v any, fields ...string) bool {
	for _, field := range fields {
		values := stringsOf(at(v, field))
		if !slices.IsSorted(values) || !unique(values) {
			return false
		}
	}
	return true
}

func profileSchemaDefaults(v any) map[string]any {
	result := maps.Clone(object(v))
	if _, present := result["dialect"]; !present {
		result["dialect"] = domainProfileDialect
	}
	if _, present := result["required_vocabularies"]; !present {
		result["required_vocabularies"] = []any{}
	}
	return result
}

func profileSchemaIdentity(v any) error {
	if !inertProfileURI(stringAt(v, "schema_id")) || stringAt(v, "schema_document", "$schema") != text(defaultMember(v, "dialect", domainProfileDialect)) || !equal(at(v, "schema_document", "$id"), at(v, "schema_id")) || !sortedProfileFields(v, "required_vocabularies") {
		return invalid()
	}
	expected, err := jsonDigest(at(v, "schema_document"))
	if err != nil || expected != stringAt(v, "schema_digest") {
		return invalid()
	}
	required := map[string]bool{}
	declared, present := object(at(v, "schema_document"))["$vocabulary"]
	if present && object(declared) == nil {
		return invalid()
	}
	for uri, requiredValue := range object(declared) {
		flag, ok := requiredValue.(bool)
		if !ok {
			return invalid()
		}
		if flag {
			required[uri] = true
		}
	}
	for _, uri := range stringsOf(at(v, "required_vocabularies")) {
		if !inertProfileURI(uri) {
			return invalid()
		}
	}
	return require(equalSet(required, set(at(v, "required_vocabularies"))))
}

func profileDefinition(v any) error {
	if !sortedProfileFields(v, "allowed_contexts") {
		return invalid()
	}
	identity := maps.Clone(object(at(v, "coordinate")))
	delete(identity, "definition_digest")
	projection := map[string]any{termSchemaVersion: "domain-profile-definition/v1", termIdentity: identity, "profile_schema": profileSchemaDefaults(at(v, "profile_schema")), "semantic_contract": at(v, "semantic_contract"), "allowed_contexts": at(v, "allowed_contexts")}
	expected, err := jsonDigest(projection)
	return require(err == nil && stringAt(v, "coordinate", "definition_digest") == expected)
}

func profileSupport(v any) error {
	if !sortedProfileFields(v, "operations", "supported_schema_dialects", "supported_vocabularies", "supported_schema_keywords") {
		return invalid()
	}
	for _, field := range []string{"supported_schema_dialects", "supported_vocabularies"} {
		for _, uri := range stringsOf(at(v, field)) {
			if !inertProfileURI(uri) {
				return invalid()
			}
		}
	}
	return require(!set(at(v, "operations"))["structural-validation"] || len(array(at(v, "supported_schema_dialects"))) > 0 && len(array(at(v, "supported_schema_keywords"))) > 0)
}

func profileContext(v any) error {
	limit := profileLimit(at(v, "limits"), "max_definitions", 256)
	return require(len(array(at(v, "definitions"))) <= limit && len(array(at(v, "namespace_admissions"))) <= limit && len(array(at(v, "support_declarations"))) <= limit)
}

func profileLimit(v any, field string, fallback int) int {
	if at(v, field) == nil {
		return fallback
	}
	n, ok := number(at(v, field))
	if !ok || !n.IsInt() || !n.Num().IsInt64() || n.Sign() < 0 || n.Num().Int64() > 16777216 {
		return 0
	}
	return int(n.Num().Int64())
}

func (e *Validator) domainProfileModel(name string, v any) (bool, error) {
	switch name {
	case "DomainProfileCoordinateModel", "DomainProfileSemanticContractModel", "DomainProfileNamespaceAdmissionModel":
		return true, require(inertProfileURI(stringAt(v, termAuthority)))
	case "DomainProfileSchemaModel":
		return true, profileSchemaIdentity(v)
	case "domain-profile-definition-v1", "DomainProfileDefinitionModel":
		return true, profileDefinition(v)
	case "DomainProfileDefinitionProvenanceModel":
		return true, require(inertProfileURI(stringAt(v, "source_locator")))
	case "AdmittedDomainProfileDefinitionModel":
		return true, require(equal(at(v, "provenance", "source_digest"), at(v, "definition", "coordinate", "definition_digest")))
	case "domain-profile-support-declaration-v1", "DomainProfileSupportDeclarationModel":
		return true, profileSupport(v)
	case "domain-profile-resolution-context-v1", "DomainProfileResolutionContextModel":
		return true, profileContext(v)
	case "domain-profile-admission-policy-v1", "DomainProfileAdmissionPolicyModel":
		return true, require(sortedProfileFields(v, "required_operations"))
	case "DomainProfileBindingProvenanceModel":
		return true, require(sortedProfileFields(v, "evidence_refs") && (stringAt(v, "basis") == "observed") == (len(array(at(v, "evidence_refs"))) > 0))
	case "domain-profile-binding-v1", "DomainProfileBindingModel":
		return true, require(len(rowSet(at(v, "children"), "binding_id")) == len(array(at(v, "children"))))
	default:
		return false, nil
	}
}

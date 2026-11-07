package domainprofile

import (
	"errors"
	"strings"
	"testing"
)

func value(t *testing.T, text string) any {
	t.Helper()
	v, err := Decode([]byte(text))
	if err != nil {
		t.Fatalf("Decode(%s) error = %v", text, err)
	}
	return v
}

const schemaDocument = `{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:example:schema:repository","type":"object"}`

// schemaDigest is the reference RFC 8785 digest of schemaDocument.
func schemaDigest(t *testing.T) string {
	t.Helper()
	d, err := Digest(value(t, schemaDocument))
	if err != nil {
		t.Fatalf("Digest() error = %v", err)
	}
	return d
}

func schemaModel(t *testing.T, document string, extra string) string {
	t.Helper()
	d, err := Digest(value(t, document))
	if err != nil {
		t.Fatalf("Digest() error = %v", err)
	}
	return `{"schema_id":"urn:example:schema:repository","revision":"1.0.0","schema_digest":"` + d + `","schema_document":` + document + extra + `}`
}

func TestCheckModelRules(t *testing.T) {
	vocabulary := "https://example.test/vocab/required"
	withVocabulary := `{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:example:schema:repository","$vocabulary":{"` + vocabulary + `":true,"https://example.test/optional":false}}`
	cases := []struct {
		name, model, instance string
		valid                 bool
	}{
		{"coordinate authority", "DomainProfileCoordinateModel", `{"authority":"urn:example:authority"}`, true},
		{"coordinate credential authority", "DomainProfileCoordinateModel", `{"authority":"https://user:pass@example.test/a"}`, false},
		{"semantic file authority", "DomainProfileSemanticContractModel", `{"authority":"file:///etc/passwd"}`, false},
		{"namespace data authority", "DomainProfileNamespaceAdmissionModel", `{"authority":"data:text/plain,a"}`, false},
		{"namespace fragment authority", "DomainProfileNamespaceAdmissionModel", `{"authority":"urn:example:a#b"}`, false},
		{"schema", "DomainProfileSchemaModel", schemaModel(t, schemaDocument, ""), true},
		{"schema explicit dialect", "DomainProfileSchemaModel", schemaModel(t, schemaDocument, `,"dialect":"https://json-schema.org/draft/2020-12/schema"`), true},
		{"schema other dialect", "DomainProfileSchemaModel", schemaModel(t, schemaDocument, `,"dialect":"https://json-schema.org/draft/2019-09/schema"`), false},
		{"schema digest", "DomainProfileSchemaModel", strings.Replace(schemaModel(t, schemaDocument, ""), `"schema_digest":"sha256:`, `"schema_digest":"sha256:0`, 1), false},
		{"schema id mismatch", "DomainProfileSchemaModel", schemaModel(t, strings.Replace(schemaDocument, "repository", "other", 1), ""), false},
		{"schema id credential", "DomainProfileSchemaModel", strings.Replace(schemaModel(t, strings.Replace(schemaDocument, "urn:example:schema:repository", "https://u:p@example.test/s", 1), ""), "urn:example:schema:repository", "https://u:p@example.test/s", 1), false},
		{"schema missing dialect", "DomainProfileSchemaModel", schemaModel(t, `{"$id":"urn:example:schema:repository"}`, ""), false},
		{"schema vocabularies", "DomainProfileSchemaModel", schemaModel(t, withVocabulary, `,"required_vocabularies":["`+vocabulary+`"]`), true},
		{"schema vocabulary omitted", "DomainProfileSchemaModel", schemaModel(t, withVocabulary, ""), false},
		{"schema vocabulary extra", "DomainProfileSchemaModel", schemaModel(t, schemaDocument, `,"required_vocabularies":["`+vocabulary+`"]`), false},
		{"schema vocabulary unsorted", "DomainProfileSchemaModel", schemaModel(t, schemaDocument, `,"required_vocabularies":["b","a"]`), false},
		{"schema vocabulary not object", "DomainProfileSchemaModel", schemaModel(t, `{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:example:schema:repository","$vocabulary":[]}`, ""), false},
		{"schema vocabulary not boolean", "DomainProfileSchemaModel", schemaModel(t, `{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:example:schema:repository","$vocabulary":{"urn:x":1}}`, ""), false},
		{"schema vocabulary not inert", "DomainProfileSchemaModel", schemaModel(t, `{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:example:schema:repository","$vocabulary":{"file:///v":true}}`, `,"required_vocabularies":["file:///v"]`), false},
		{"provenance", "DomainProfileDefinitionProvenanceModel", `{"source_locator":"urn:example:admitted-profile"}`, true},
		{"provenance relative", "DomainProfileDefinitionProvenanceModel", `{"source_locator":"relative/profile.json"}`, false},
		{"admitted digest", "AdmittedDomainProfileDefinitionModel", `{"provenance":{"source_digest":"sha256:a"},"definition":{"coordinate":{"definition_digest":"sha256:a"}}}`, true},
		{"admitted digest mismatch", "AdmittedDomainProfileDefinitionModel", `{"provenance":{"source_digest":"sha256:a"},"definition":{"coordinate":{"definition_digest":"sha256:b"}}}`, false},
		{"support", "DomainProfileSupportDeclarationModel", `{"operations":["semantic-validation","structural-validation"],"supported_schema_dialects":["https://json-schema.org/draft/2020-12/schema"],"supported_schema_keywords":["type"]}`, true},
		{"support without structural", "domain-profile-support-declaration-v1", `{"operations":["execution"]}`, true},
		{"support structural without dialects", "DomainProfileSupportDeclarationModel", `{"operations":["structural-validation"],"supported_schema_keywords":["type"]}`, false},
		{"support structural without keywords", "DomainProfileSupportDeclarationModel", `{"operations":["structural-validation"],"supported_schema_dialects":["urn:d"]}`, false},
		{"support unsorted operations", "DomainProfileSupportDeclarationModel", `{"operations":["typed-report","execution"]}`, false},
		{"support repeated keywords", "DomainProfileSupportDeclarationModel", `{"operations":["execution"],"supported_schema_keywords":["type","type"]}`, false},
		{"support dialect not inert", "DomainProfileSupportDeclarationModel", `{"operations":["execution"],"supported_schema_dialects":["file:///d"]}`, false},
		{"support vocabulary not inert", "DomainProfileSupportDeclarationModel", `{"operations":["execution"],"supported_vocabularies":["data:x"]}`, false},
		{"context default limit", "domain-profile-resolution-context-v1", `{"definitions":[],"namespace_admissions":[]}`, true},
		{"context limit", "DomainProfileResolutionContextModel", `{"definitions":[1,2],"limits":{"max_definitions":1}}`, false},
		{"context admission limit", "DomainProfileResolutionContextModel", `{"namespace_admissions":[1,2],"limits":{"max_definitions":1}}`, false},
		{"context support limit", "DomainProfileResolutionContextModel", `{"support_declarations":[1,2],"limits":{"max_definitions":2}}`, true},
		{"context support over limit", "DomainProfileResolutionContextModel", `{"support_declarations":[1,2,3],"limits":{"max_definitions":2.0}}`, false},
		{"policy", "domain-profile-admission-policy-v1", `{"required_operations":["execution","typed-report"]}`, true},
		{"policy unsorted", "DomainProfileAdmissionPolicyModel", `{"required_operations":["typed-report","execution"]}`, false},
		{"policy repeated", "DomainProfileAdmissionPolicyModel", `{"required_operations":["execution","execution"]}`, false},
		{"observed with evidence", "DomainProfileBindingProvenanceModel", `{"basis":"observed","evidence_refs":["a","b"]}`, true},
		{"observed without evidence", "DomainProfileBindingProvenanceModel", `{"basis":"observed"}`, false},
		{"authored with evidence", "DomainProfileBindingProvenanceModel", `{"basis":"author-supplied","evidence_refs":["a"]}`, false},
		{"evidence unsorted", "DomainProfileBindingProvenanceModel", `{"basis":"observed","evidence_refs":["b","a"]}`, false},
		{"children unique", "domain-profile-binding-v1", `{"children":[{"binding_id":"a"},{"binding_id":"b"}]}`, true},
		{"children repeated", "DomainProfileBindingModel", `{"children":[{"binding_id":"a"},{"binding_id":"a"}]}`, false},
	}
	for _, tc := range cases {
		known, err := CheckModel(tc.model, value(t, tc.instance))
		if !known || (err == nil) != tc.valid || err != nil && !errors.Is(err, ErrModel) {
			t.Errorf("%s: CheckModel() = %t, %v; want known and valid=%t", tc.name, known, err, tc.valid)
		}
	}
	if known, err := CheckModel("OtherModel", nil); known || err != nil {
		t.Errorf("CheckModel(OtherModel) = %t, %v; want unknown", known, err)
	}
}

func TestDefinitionDigestUsesTheSelfFreeProjection(t *testing.T) {
	document := value(t, schemaDocument)
	definition := map[string]any{
		"coordinate":        map[string]any{"namespace": "com.example.private", "authority": "urn:example:profile-authority", "profile_id": "repository", "revision": "1.0.0", "definition_digest": "sha256:unused"},
		"profile_schema":    map[string]any{"schema_id": "urn:example:schema:repository", "revision": "1.0.0", "schema_digest": schemaDigest(t), "schema_document": document},
		"semantic_contract": map[string]any{"authority": "urn:example:profile-authority", "contract_id": "repository-semantics", "revision": "1.0.0", "digest": "sha256:" + strings.Repeat("1", 64)},
		"allowed_contexts":  []any{"artifact-acquisition"},
	}
	first, err := DefinitionDigest(definition)
	if err != nil {
		t.Fatalf("DefinitionDigest() error = %v", err)
	}
	coordinate, _ := definition["coordinate"].(map[string]any)
	coordinate["definition_digest"] = "sha256:other"
	schema, _ := definition["profile_schema"].(map[string]any)
	schema["dialect"], schema["required_vocabularies"] = Dialect, []any{}
	second, err := DefinitionDigest(definition)
	if err != nil || second != first {
		t.Errorf("DefinitionDigest(explicit defaults) = %s, %v; want %s", second, err, first)
	}
	definition["allowed_contexts"] = []any{"other"}
	if third, _ := DefinitionDigest(definition); third == first {
		t.Errorf("DefinitionDigest() ignores the allowed contexts")
	}
	sealed := definition
	sealed["allowed_contexts"] = []any{"artifact-acquisition"}
	coordinate["definition_digest"] = first
	if known, err := CheckModel("DomainProfileDefinitionModel", sealed); !known || err != nil {
		t.Errorf("CheckModel(sealed definition) = %t, %v; want valid", known, err)
	}
	sealed["allowed_contexts"] = []any{"b", "a"}
	if _, err := CheckModel("domain-profile-definition-v1", sealed); err == nil {
		t.Errorf("CheckModel(unsorted contexts) error = nil, want refusal")
	}
	if _, err := Digest(func() {}); !errors.Is(err, ErrModel) {
		t.Errorf("Digest(func) error = %v, want ErrModel", err)
	}
}

func TestLimitDefaultsAndBounds(t *testing.T) {
	limits := value(t, `{"a":5,"b":5.0,"c":-1,"d":16777217,"e":"5","f":1.5,"g":16777216,"h":0}`)
	for name, want := range map[string]int{"a": 5, "b": 5, "c": 0, "d": 0, "e": 0, "f": 0, "g": 16777216, "h": 0, "absent": 7} {
		if got := Limit(limits, name, 7); got != want {
			t.Errorf("Limit(%q) = %d, want %d", name, got, want)
		}
	}
}

func TestInertAndDecode(t *testing.T) {
	if !Inert("urn:example:a") || Inert("relative") || Inert("https://example.test/a?token=x") {
		t.Errorf("Inert() does not apply the URI safety rules")
	}
	if _, err := Decode([]byte("{")); !errors.Is(err, ErrModel) {
		t.Errorf("Decode(malformed) error = %v, want ErrModel", err)
	}
}

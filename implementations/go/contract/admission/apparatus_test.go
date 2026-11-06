package admission

import "testing"

func TestApparatusManifestRules(t *testing.T) {
	root := fixtureObject(t, "fixtures/experiment-core/experiment-apparatus-context-v1/valid/reference.json")
	assertObjectRule(t, "canonical-apparatus-manifest-selected", root, true)
	root["selected_manifests"] = []any{}
	assertObjectRule(t, "canonical-apparatus-manifest-selected", root, false)
	root = fixtureObject(t, "fixtures/experiment-core/experiment-apparatus-context-v1/valid/reference.json")
	object(at(root, "components", "processor", "identity"))["version"] = "other"
	assertObjectRule(t, "canonical-apparatus-manifest-selected", root, false)
	for _, test := range []struct {
		raw   string
		valid bool
	}{
		{`{"notes":["descriptive constraint"]}`, true},
		{`{"allowed_processor_refs":[{"ref_kind":"processor","ref_id":"p","ref_version":"1"}],"required_manifest_refs":[{"ref_id":"p","ref_version":"processor-manifest/v2","subject_ref":{"ref_kind":"processor","ref_id":"p","ref_version":"1"}}]}`, true},
		{`{"allowed_processor_refs":[{"ref_kind":"processor","ref_id":"p","ref_version":"1"}],"required_manifest_refs":[{"ref_id":"p","ref_version":"processor-manifest/v2","subject_ref":{"ref_kind":"processor","ref_id":"p","ref_version":"2"}}]}`, false},
		{`{}`, false},
	} {
		assertRule(t, "apparatus-constraint-identity-manifest-resolves", test.raw, test.valid)
	}
}

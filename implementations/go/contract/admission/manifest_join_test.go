package admission

import (
	"encoding/json"
	"testing"
)

type testManifestContext struct{ processor, backend []byte }

func (c testManifestContext) ProcessorManifest() []byte       { return c.processor }
func (c testManifestContext) BackendManifest() []byte         { return c.backend }
func (c testManifestContext) ProcessorManifestDigest() string { return "" }
func (c testManifestContext) BackendManifestDigest() string   { return "" }
func TestApparatusManifestPayloadJoins(t *testing.T) {
	e := boundTestOwner(t)
	apparatus := fixtureObject(t, "fixtures/experiment-core/experiment-apparatus-context-v1/valid/reference.json")
	processor := fixtureObject(t, "fixtures/processor-manifest/processor-manifest-v2/valid/reference.json")
	backend := fixtureObject(t, "fixtures/backend-manifest/backend-manifest-v2/valid/stub.json")
	for kind, manifest := range map[string]any{"processor": processor, "backend": backend} {
		component := object(at(apparatus, "components", kind))
		component["identity"] = at(manifest, "identity")
		ref := object(component["manifest_ref"])
		ref["ref_id"] = at(manifest, "identity", "name")
		subject := object(ref["subject_ref"])
		subject["ref_id"] = at(manifest, "identity", "name")
		subject["ref_version"] = at(manifest, "identity", "version")
	}
	// Keep the candidate's selected references consistent with its component records.
	apparatus["selected_manifests"] = []any{at(apparatus, "components", "processor", "manifest_ref"), at(apparatus, "components", "backend", "manifest_ref"), at(apparatus, "components", "participant-policy", "manifest_ref")}
	c := testManifestContext{}
	var err error
	c.processor, err = json.Marshal(processor)
	if err != nil {
		t.Fatal(err)
	}
	c.backend, err = json.Marshal(backend)
	if err != nil {
		t.Fatal(err)
	}
	if checkErr := validateTestDocument(t, e, "experiment-apparatus-context-v1", apparatus, c); checkErr != nil {
		t.Fatal(checkErr)
	}
	object(processor["compatibility"])["backends"] = []any{"foreign"}
	c.processor, err = json.Marshal(processor)
	if err != nil {
		t.Fatal(err)
	}
	if err := validateTestDocument(t, e, "experiment-apparatus-context-v1", apparatus, c); err == nil {
		t.Error("accepted incompatible selected manifests")
	}
}

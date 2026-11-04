package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestApparatusRejectsRepeatedManifestSubject(t *testing.T) {
	v := fixtureObject(t, "fixtures/experiment-core/experiment-apparatus-context-v1/valid/reference.json")
	if err := apparatusSelected(validation.Invocation{Instance: v}); err != nil {
		t.Fatal(err)
	}
	refs := array(at(v, "selected_manifests"))
	object(v)["selected_manifests"] = append(refs, refs[0])
	if err := apparatusSelected(validation.Invocation{Instance: v}); err == nil {
		t.Error("accepted two manifest references for one subject")
	}
}

func TestApparatusConstraintCombinesIndependentRequirements(t *testing.T) {
	for _, raw := range []string{
		`{"required_capabilities":["capability"],"notes":["constraint"]}`,
		`{"required_manifest_refs":[{"ref_kind":"manifest","ref_id":"guide","ref_version":"other-manifest/v1"}],"required_capabilities":["capability"]}`,
	} {
		if err := apparatusConstraint(validation.Invocation{Instance: decodeRuleObject(t, raw)}); err != nil {
			t.Fatalf("nonempty independent constraints rejected: %v", err)
		}
	}
}

func TestRequiredCanonicalManifestChecksSubjectIdentity(t *testing.T) {
	for _, kind := range []string{kindProcessor, kindBackend} {
		subject := map[string]any{fieldRefKind: kind, fieldRefID: "owner"}
		ref := map[string]any{fieldRefID: "owner", fieldRefVersion: kind + "-manifest/v2"}
		if err := requiredManifest(ref, subject); err != nil {
			t.Fatal(err)
		}
		ref[fieldRefID] = "substitution"
		if err := requiredManifest(ref, subject); err == nil {
			t.Errorf("%s manifest admitted a different subject", kind)
		}
		ref[fieldRefVersion] = "other-manifest/v1"
		if err := requiredManifest(ref, subject); err != nil {
			t.Errorf("canonical %s rule claimed another manifest format: %v", kind, err)
		}
	}
}

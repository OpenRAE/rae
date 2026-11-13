package realization

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/base/softwareversion"
)

func TestVersionSupportChecksPinnedRelationsInsideDefinitionsAndNestedRecords(t *testing.T) {
	owner, err := realizationOwner()
	if err != nil {
		t.Fatal(err)
	}
	identity, err := softwareversion.Installed("numeric-triplet")
	if err != nil {
		t.Fatal(err)
	}
	for _, installed := range []bool{true, false} {
		revision := identity.Revision
		if !installed {
			revision = "future"
		}
		domain := map[string]any{"kind": "domain", "domain": map[string]any{"kind": "version", "lower": "1.0.0", "relation": map[string]any{"authority": identity.Authority, "contract_id": identity.ID, "revision": revision, "digest": identity.Digest}}}
		document := map[string]any{"semantic_profile": "test/v1", "default_closure": map[string]any{"posture": "open", "universe": "software", "profile": "test/v1"}, "root": map[string]any{"kind": "literal", "value": "unchanged"}, "definitions": map[string]any{"nested": map[string]any{"kind": "recursive-record", "fields": map[string]any{"version": domain}}}}
		constraint, err := admission.AdmitFragment(owner, admission.RealizationConstraint, document, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
		if err != nil {
			t.Fatal(err)
		}
		versioned, supported := versionRequirements(Requirement{Constraint: constraint})
		if !versioned || supported != installed {
			t.Fatalf("pinned version support=%t/%t, want installed=%t", versioned, supported, installed)
		}
	}
}
